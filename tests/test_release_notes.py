"""Tests for .github/scripts/collect_release_notes.py.

The release workflow generates its notes from PR titles only, so the upgrade
notes written into PR bodies never reached a release: #728, #735, #748, #750,
#759 and #762 each carried one, and every August release body was either the
bare title list or a block someone re-pasted by hand. This script lifts those
sections out of the merged PRs and hands them to the release step.
"""

import importlib.util
from pathlib import Path

_SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent
    / ".github"
    / "scripts"
    / "collect_release_notes.py"
)
_spec = importlib.util.spec_from_file_location("collect_release_notes", _SCRIPT_PATH)
assert _spec and _spec.loader
collect_release_notes = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(collect_release_notes)

extract_notes = collect_release_notes.extract_notes
render = collect_release_notes.render


class TestExtractNotes:
    def test_the_canonical_heading(self):
        body = "## \u2728 Changes\n\nstuff\n\n## \u26a0\ufe0f Upgrade notes\n\nDo the thing.\n"
        assert extract_notes(body) == ["## \u26a0\ufe0f Upgrade notes\n\nDo the thing."]

    def test_stops_at_the_next_section(self):
        body = (
            "## \u26a0\ufe0f Upgrade notes\n\nDo the thing.\n\n"
            "## \U0001f9ea Tests\n\n1153 passed\n"
        )
        assert extract_notes(body) == ["## \u26a0\ufe0f Upgrade notes\n\nDo the thing."]

    def test_keeps_subsections(self):
        """The 2026.08.18 note used ### subheadings inside its block."""
        body = (
            "## \u26a0\ufe0f Upgrade notes\n\nintro\n\n"
            "### \u2705 Handled for you\n\nthe migration runs\n\n"
            "## \U0001f9ea Tests\n"
        )
        assert "### \u2705 Handled for you" in extract_notes(body)[0]

    def test_matches_the_headings_used_before_the_convention(self):
        """Six merged PRs each invented their own wording; all should be found."""
        for heading in (
            "## \u26a0\ufe0f Note for release notes",
            "## \u26a0\ufe0f Breaking change for dump consumers",
            "## \U0001f517 Migration",
            "## \u26a0\ufe0f Upgrade note for the release",
            "## \u26a0\ufe0f Behaviour change worth noting in the release notes",
            "## \U0001f4a5 Breaking changes",
        ):
            assert extract_notes(f"{heading}\n\nbody text\n"), heading

    def test_ignores_a_heading_that_negates_the_keyword(self):
        """#749 wrote "No behaviour change" - the opposite of a note."""
        assert extract_notes("## ✅ No behaviour change\n\nnothing to do\n") == []
        assert extract_notes("## \U0001f50d Without migration\n\nnope\n") == []

    def test_an_untouched_template_section_yields_nothing(self):
        """The PR template ships the heading with an instruction comment. An
        author who leaves it in place has no note, not an empty one."""
        body = (
            "## ⚠️ Upgrade notes\n\n"
            "<!--\nKEEP THIS SECTION ONLY IF USERS MUST DO SOMETHING\n-->\n"
        )
        assert extract_notes(body) == []

    def test_strips_html_comments_from_a_real_note(self):
        body = "## ⚠️ Upgrade notes\n\n<!-- a hint -->\nRename it.\n"
        assert extract_notes(body) == ["## ⚠️ Upgrade notes\n\nRename it."]

    def test_ignores_sections_that_are_not_upgrade_notes(self):
        body = (
            "## \U0001f50d What this fixes\n\nnope\n\n"
            "## \u26a0\ufe0f Field-verification status\n\nalso nope\n"
        )
        assert extract_notes(body) == []

    def test_strips_issue_trailers_and_the_generated_with_line(self):
        """#762's section ran to the end of the body and swallowed both."""
        body = (
            "## \u26a0\ufe0f Note for release notes\n\nRenaming 1135 removes it.\n\n"
            "Refs #752\n\n"
            "\U0001f916 Generated with [Claude Code](https://claude.com/claude-code)\n"
        )
        assert extract_notes(body) == [
            "## \u26a0\ufe0f Note for release notes\n\nRenaming 1135 removes it."
        ]

    def test_a_pr_can_carry_more_than_one(self):
        body = (
            "## \U0001f4a5 Breaking changes\n\nfirst\n\n"
            "## \U0001f9ea Tests\n\nx\n\n"
            "## \U0001f517 Migration\n\nsecond\n"
        )
        assert len(extract_notes(body)) == 2

    def test_an_empty_body_yields_nothing(self):
        assert extract_notes("") == []
        assert extract_notes(None) == []


class TestRender:
    def test_attributes_each_note_to_its_pull_request(self):
        out = render(
            [(771, ["## \u26a0\ufe0f Upgrade notes\n\nDo the thing."])],
            "BenPru/luxtronik",
        )
        assert "## \u26a0\ufe0f Upgrade notes" in out
        assert "https://github.com/BenPru/luxtronik/pull/771" in out
        assert "Do the thing." in out

    def test_nothing_to_report_renders_empty(self):
        assert render([], "BenPru/luxtronik") == ""

    def test_keeps_pull_requests_in_the_order_given(self):
        out = render(
            [
                (728, ["## \u26a0\ufe0f Upgrade notes\n\nfirst"]),
                (771, ["## \u26a0\ufe0f Upgrade notes\n\nsecond"]),
            ],
            "BenPru/luxtronik",
        )
        assert out.index("first") < out.index("second")


class TestMainAlwaysWritesTheFile:
    """The release step passes body_path unconditionally, so the file has to
    exist even when there is nothing to say."""

    def test_writes_an_empty_file_without_a_previous_stable_tag(
        self, tmp_path, monkeypatch
    ):
        out = tmp_path / "release_notes.md"
        monkeypatch.setenv("GITHUB_REPOSITORY", "BenPru/luxtronik")
        monkeypatch.setenv("PREVIOUS_STABLE", "")
        monkeypatch.setenv("RELEASE_NOTES_PATH", str(out))

        assert collect_release_notes.main() == 0
        assert out.exists()
        assert out.read_text(encoding="utf-8") == ""

    def test_writes_an_empty_file_when_no_pull_request_carried_a_note(
        self, tmp_path, monkeypatch
    ):
        out = tmp_path / "release_notes.md"
        monkeypatch.setenv("GITHUB_REPOSITORY", "BenPru/luxtronik")
        monkeypatch.setenv("PREVIOUS_STABLE", "2026.08.18")
        monkeypatch.setenv("RELEASE_NOTES_PATH", str(out))
        monkeypatch.setattr(collect_release_notes, "_pull_requests", lambda *a: [])

        assert collect_release_notes.main() == 0
        assert out.read_text(encoding="utf-8") == ""
