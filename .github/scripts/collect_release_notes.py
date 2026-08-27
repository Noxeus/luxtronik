#!/usr/bin/env python3
"""Collect the upgrade notes written in merged pull requests.

The release workflow asks GitHub to generate its notes, which yields the PR
*titles* and nothing else. Anything a PR author wrote for users - a renamed
entity, a changed state value, something to fix by hand after upgrading - was
therefore lost unless someone pasted it into the release by hand afterwards,
which is what happened for the 2026.08.15 / .17 / .18 releases.

This script walks the pull requests merged since the previous full release,
lifts the upgrade-note section out of each body, and writes them to a file the
release step passes as `body_path`. The action pre-pends that body to the
generated notes, so the result matches the layout those releases already had.

Matching is deliberately loose. The pull request template offers one canonical
heading, but six merged PRs each invented their own wording before it existed,
so any second- or third-level heading mentioning an upgrade note, a release
note, a breaking change, a migration or a behaviour change counts.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys

# Headings whose section is meant for the people installing the release.
NOTE_HEADING = re.compile(
    r"^(#{2,3})[ \t]*.*(?:upgrade note|release note|breaking|migration|behaviour change|behavior change).*$",
    re.IGNORECASE | re.MULTILINE,
)

# ... unless the heading negates it. "No behaviour change" (#749) matches the
# keyword while saying the opposite.
NEGATED_HEADING = re.compile(r"\b(?:no|without)\b", re.IGNORECASE)

# Instructions to the PR author, including the ones the template ships with:
# never part of what users read.
HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)

# Trailers the section should not swallow when it runs to the end of the body.
TRAILER = re.compile(
    r"(?im)^\s*(?:refs|resolves|closes|fixes)\s+#\d+\s*$"
    r"|^\s*\U0001f916 Generated with \[Claude Code\].*$"
)

# The compare API returns at most 250 commits, so a release spanning more than
# that would silently lose the notes of its oldest pull requests.
COMPARE_COMMIT_LIMIT = 250

logging.basicConfig(level=logging.INFO, format="%(message)s")
LOG = logging.getLogger(__name__)


def extract_notes(body: str | None) -> list[str]:
    """Return every upgrade-note section of a pull request body."""
    if not body:
        return []
    body = body.replace("\r\n", "\n")
    notes: list[str] = []
    for match in NOTE_HEADING.finditer(body):
        if NEGATED_HEADING.search(match.group(0)):
            continue
        level = len(match.group(1))
        rest = body[match.end() :]
        # A section ends at the next heading of the same level or higher, so a
        # note written with ### subsections keeps them.
        end = re.search(rf"^#{{1,{level}}}[ \t]", rest, re.MULTILINE)
        section = rest[: end.start()] if end else rest
        section = HTML_COMMENT.sub("", section)
        section = TRAILER.sub("", section).strip()
        if not section:
            # An untouched template section, or a heading with nothing under
            # it: there is no note here to tell anyone about.
            continue
        heading = match.group(0).strip()
        notes.append(f"{heading}\n\n{section}")
    return notes


def render(notes_by_pr: list[tuple[int, list[str]]], repo: str) -> str:
    """Render the collected notes as the release body."""
    blocks: list[str] = []
    for number, notes in notes_by_pr:
        link = f"https://github.com/{repo}/pull/{number}"
        for note in notes:
            heading, _, rest = note.partition("\n")
            blocks.append(f"{heading} ([#{number}]({link}))\n{rest}".strip())
    return "\n\n".join(blocks)


def _gh(*args: str) -> str:
    return subprocess.run(
        ["gh", *args], check=True, capture_output=True, text=True
    ).stdout


def _pull_requests(repo: str, base: str, head: str) -> list[int]:
    """Pull request numbers merged between two revisions, oldest first."""
    compare = json.loads(_gh("api", f"repos/{repo}/compare/{base}...{head}"))
    commits = compare.get("commits", [])
    total = compare.get("total_commits", len(commits))
    if total > len(commits):
        LOG.warning(
            "::warning::compare returned %s of %s commits (API caps at %s); "
            "notes from the oldest pull requests in this range are missing",
            len(commits),
            total,
            COMPARE_COMMIT_LIMIT,
        )
    numbers: list[int] = []
    for commit in commits:
        associated = json.loads(
            _gh("api", f"repos/{repo}/commits/{commit['sha']}/pulls")
        )
        for pull in associated:
            if pull["number"] not in numbers:
                numbers.append(pull["number"])
    return numbers


def _write(path: str, content: str) -> None:
    """Write the release body. Always called, so body_path always resolves;
    an empty body simply leaves the generated notes alone."""
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)


def main() -> int:
    repo = os.environ["GITHUB_REPOSITORY"]
    base = os.environ.get("PREVIOUS_STABLE", "").strip()
    head = os.environ.get("GITHUB_SHA", "HEAD").strip()
    out_path = os.environ.get("RELEASE_NOTES_PATH", "release_notes.md")

    if not base:
        # No full release to compare against yet - the generated notes stand
        # on their own. The file is still written: the release step points at
        # it unconditionally.
        _write(out_path, "")
        LOG.info("No previous stable tag; skipping upgrade notes")
        return 0

    notes_by_pr: list[tuple[int, list[str]]] = []
    for number in _pull_requests(repo, base, head):
        body = json.loads(_gh("api", f"repos/{repo}/pulls/{number}")).get("body")
        notes = extract_notes(body)
        if notes:
            notes_by_pr.append((number, notes))

    rendered = render(notes_by_pr, repo)
    _write(out_path, rendered + "\n" if rendered else "")
    LOG.info("Collected upgrade notes from %s pull request(s)", len(notes_by_pr))
    return 0


if __name__ == "__main__":
    sys.exit(main())
