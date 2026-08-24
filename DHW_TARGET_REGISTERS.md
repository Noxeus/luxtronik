# The DHW target temperature registers

Reference notes for maintainers on the two "hot water target" parameters, why
the `number` and `water_heater` platforms gate them on different firmware
versions, and what to ask for when the next report about a wrong DHW setpoint
arrives.

**Nothing here is a bug report or a plan.** The thresholds described below are
deliberately left as they are — see [Why nothing was changed](#why-nothing-was-changed).

## The two registers

| | parameter | controller label | meaning |
|---|---|---|---|
| **P0002** | `ID_Einst_BWS_akt` | "Deckung WP" | the temperature reachable by the compressor alone. The controller **lowers this by itself** when the setpoint cannot be reached (documented in the AIT manual), so it is not a pure user setting. |
| **P0105** | `ID_Soll_BWS_akt` | "Wunschwert" | the desired value, shown as the primary figure on the controller display. |
| **C0018** | `ID_WEB_Einst_BWS_akt` | "Warmwasser-Soll" | read-only mirror of the *effective* target, including any Smart Grid offset. This is what the pump actually aims at. |

C0018 is the useful one when analysing a dump: it tells you which of the two
parameters the controller is currently deriving its target from.

## Two separate firmware events, often conflated

The single most common mistake in this area is treating "P0105 became correct"
and "P0002 became broken" as one event. They are not.

### Event 1 — writing P0105 starts propagating to P0002

Somewhere in the interval `(minor 79, minor 88.3]`:

- **FW 3.79** — writing P0105 from HA did *not* move P0002 (stayed 53), and the
  pump heated to 53. P0105 was inert.
  ([#280](https://github.com/BenPru/luxtronik/issues/280#issuecomment-2430134992))
- **FW 2.88.3** — a reporter confirmed P0105 "sets the right value" on his unit.
  ([#280](https://github.com/BenPru/luxtronik/issues/280#issuecomment-3690032168))
- **FW 3.90.0** — writing P0105 changed P0002 identically and the pump heated to
  it. ([#280](https://github.com/BenPru/luxtronik/issues/280#issuecomment-2428257354))

### Event 2 — P0105 becomes a cap on the effective target

At roughly minor 90.1. Below it the effective target is read from P0002 and
P0105 does not participate; at and above it the effective target follows
`min(P0002, P0105)`. This is why a P0002 stuck at the 75.0 sentinel stops
mattering there, and it is the event [#280](https://github.com/BenPru/luxtronik/issues/280)
and [#428](https://github.com/BenPru/luxtronik/issues/428) actually reported.

Put plainly:

> **Event 1 is where using P0002 became the wrong choice.
> Event 2 is where that wrong choice started to hurt.**

Before Event 2 the two registers usually track each other, so P0002 mostly
worked and nobody complained.

## The evidence

From the local `diagnostics/` corpus. Dumps where `P0002 == P0105` carry no
information and are omitted; every divergent case is listed.

### Below minor 90.1 — effective target follows P0002

| firmware | P0002 | P0105 | C0018 | note |
|---|---|---|---|---|
| V1.88.3 | 43.0 | 46.0 | 43.0 | |
| V1.90.0 | 49.0 | 48.0 | 49.0 | `min()` would give 48.0 |
| V1.90.0 | 49.0 | 48.0 | 54.0 | Smart Grid +5 K on top of P0002 |
| V3.88.0 | 40.0 | 38.0 | 40.0 | `min()` would give 38.0 |
| V3.88.0 | 48.5 | 47.5 | 48.5 | `min()` would give 47.5 |

Three of these discriminate between "follows P0002" and "follows `min()`", and
all three say P0002.

### At and above minor 90.1 — effective target follows min(P0002, P0105)

| firmware | P0002 | P0105 | C0018 |
|---|---|---|---|
| V3.92.0 | 54.7 | 45.0 | 45.0 |
| V3.92.0 | 75.0 | 50.0 | 50.0 |
| V3.92.0 | 75.0 | 52.0 | 52.0 |
| V3.92.1 | 53.5 | 59.5 | 53.5 |
| V3.92.1 | 56.5 | 60.0 | 56.5 |
| V3.92.1 | 75.0 | 50.0 | 50.0 |
| V3.92.1 | 75.0 | 53.0 | 53.0 |
| V3.92.1 | 75.0 | 53.0 | 59.5 |
| V3.92.1 | 75.0 | 56.5 | 56.5 |
| V3.92.1 | 75.0 | 57.0 | 57.0 |
| V3.92.3 | 49.5 | 47.5 | 47.5 |
| V3.92.3 | 75.0 | 56.0 | 56.0 |
| V3.92.3 | 75.0 | 58.0 | 58.0 |

Twelve of thirteen fit `min(P0002, P0105)` exactly. The one exception
(`75.0 / 53.0 / 59.5`) carries a Smart Grid offset.

Note the two V3.92.1 rows where P0105 is the *higher* value: the effective
target stays at P0002. P0105 acts as a ceiling, not as the setpoint.

## Why the two platforms disagree

| platform | threshold | set by |
|---|---|---|
| `number_entities_predefined.py` | minor 90.0 / 90.1 | [PR #357](https://github.com/BenPru/luxtronik/pull/357), May 2025 |
| `water_heater.py` | minor 88.2 / 88.3 | commit `fecdf38`, Jan 2026 |

Both platforms were set to 90.0/90.1 by PR #357. Commit `fecdf38` later did two
things at once — converted `water_heater` from the absolute firmware fields to
the series-agnostic `*_minor` ones (correct) *and* lowered its threshold to
88.3 (a separate judgement, based on the single 2.88.3 report above). It touched
`common.py`, `coordinator.py`, `model.py`, `sensor.py` and `water_heater.py`;
`number_entities_predefined.py` was simply not in the commit.

**The divergence is an oversight, not a decision.**

A later change converted the `number` gates to the `*_minor` form too, which is
why both platforms now use minor comparisons while still disagreeing on the
value. That conversion fixed a real bug — the absolute form compares the
firmware *major*, which is the controller series, so every V1.x and V2.x unit
read as older than any "3.x" bound — but it deliberately preserved each
platform's existing threshold.

## Why nothing was changed

Neither threshold is clearly right, because a single register cannot express
both events:

- **Writing** P0105 appears correct from Event 1 onward — which supports
  `water_heater`'s 88.3.
- **Reading** P0105 is wrong until Event 2 — the corpus shows a V1.88.3 unit
  displaying 46 while the pump works toward 43 — which supports `number`'s 90.1.

Both can be true at the same time, because the integration uses one register
for both directions. Picking either threshold for both platforms fixes one
direction and breaks the other, so the thresholds were left alone rather than
churned on incomplete evidence. Nobody has reported a problem against the
current state.

Two dead ends worth not re-deriving:

- **Register-existence detection does not work here.** Both P0002 and P0105
  exist on both sides of both events. The discriminator is meaning, not
  presence, so a firmware gate really is the only available lever.
- **C0018 alone does not settle which register is authoritative.** It is the
  P0002-lineage mirror below Event 2, so "C0018 equals P0002" is nearly
  circular there. It only becomes informative because the *relationship*
  changes at Event 2.

## What to ask the next reporter

The corpus is static snapshots, so it cannot show write propagation. One
measurement closes the remaining gap. Ask for, on a unit below minor 90.1:

1. The firmware version and a diagnostics dump.
2. Write P0105 via the `luxtronik2.write` action to a clearly different value.
3. After the next DHW cycle: what temperature did the water actually reach,
   and what do P0002 and C0018 read now?

If the water reaches the P0105 value, Event 1 has happened on that firmware.
If it reaches P0002 instead, it has not — which is exactly the false positive
that makes "P0105 sets the right value" untrustworthy on its own, since the
displayed figure changes either way.

Also worth knowing: the corpus contains **no V1.x or V2.x dump at minor ≥ 90.1**
at all. If a report arrives from one, it is the first of its kind — capture it.

## Related

- [#280](https://github.com/BenPru/luxtronik/issues/280) — the original thread; contains the FW 3.79, 3.90.0 and 2.88.3 observations, and the Smart Grid explanation of C0018.
- [#428](https://github.com/BenPru/luxtronik/issues/428) — V3.92.0, P0002 showing "Deckung WP" instead of the setpoint.
- [#517](https://github.com/BenPru/luxtronik/issues/517) — unrelated to the thresholds: the `firmware_version_minor` crash on two-part versions introduced alongside `fecdf38`, since fixed.
