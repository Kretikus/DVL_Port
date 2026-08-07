"""
levels.py - the character-sheet title-progression tracks (Stärke/
Astral/Ansehen/Hunger/Durst), confirmed via disassembly of the real
"Zustandsübersicht" status-screen function (flat 0x6F92-0x72B3 in the
`laas` analysis project) AND a real DOSBox screenshot of the actual
start-of-game screen (`Status_anfang.png`) - see PHASE0_FINDINGS.md
UPDATE 23 (plus its "Correction, same session" addendum) for the full
trace and the two bugs that screenshot caught in this module's first
draft.

Each ladder is strictly-ordered: the first threshold the value is `<=`
wins, the last entry's title applies above every listed threshold. This
is code-confirmed for every track with NO special-casing for value 0 -
a fresh game's real screenshot shows both characters' Strength as
"Milchbubi" (not a placeholder "-") and Aszhanti's Astral as
"Scharlatan" (not "Unbegabt"), proving value 0 genuinely falls through
the first bracket like any other value. An earlier version of this
module wrongly special-cased value 0 for both tracks - corrected here.

Smirga's Astral is NOT a computed stat at all: the disassembly shows his
column is built from a permanently-fixed STORY-message pointer
(message 1484, "Unbegabt"), not a ladder read from any word_XXXX global -
he canonically never gains magic levels. `smirga_astral_title()` below
returns this fixed constant; there is no numeric field backing it.
"""
from __future__ import annotations

# (max_value_inclusive, title) - first match wins; the last entry's
# title is used for anything above every listed threshold.
STRENGTH_LEVELS = [
    (17, "Milchbubi"),
    (26, "Schaumschläger"),
    (37, "Kraftprotz"),
]
STRENGTH_MAX_TITLE = "Gladiator"

ASTRAL_LEVELS = [
    (2, "Scharlatan"),
    (4, "Kleriker"),
    (6, "Illusionist"),
]
ASTRAL_MAX_TITLE = "Magier"

SMIRGA_ASTRAL_TITLE = "Unbegabt"  # fixed, see module docstring - not a ladder

ANSEHEN_LEVELS = [
    (2, "Niemand"),
    (4, "Leicht zu übersehen"),
    (6, "Beachtlich"),
    (9, "Bekannt"),
]
ANSEHEN_MAX_TITLE = "Heldenhaft"

# Party-wide (one value for both characters) - confirmed via the user's
# own gameplay observation, matching the disassembly exactly.
HUNGER_LEVELS = [
    (0, "Am Verhungern"),
    (50, "Sehr hungrig"),
    (100, "Hungrig"),
]
HUNGER_MAX_TITLE = "Satt"

# Per character - confirmed via the user's own gameplay observation,
# matching the disassembly exactly (two separate globals, one per
# party member, unlike Hunger's single shared one).
DURST_LEVELS = [
    (0, "Am Verdursten"),
    (30, "Sehr durstig"),
    (60, "Durstig"),
]
DURST_MAX_TITLE = "Kein Durst"


def _ladder_title(value: int, levels: list[tuple[int, str]], max_title: str) -> str:
    for threshold, title in levels:
        if value <= threshold:
            return title
    return max_title


def strength_title(value: int) -> str:
    return _ladder_title(value, STRENGTH_LEVELS, STRENGTH_MAX_TITLE)


def astral_title(value: int) -> str:
    """Aszhanti's Astral track only - Smirga's is a fixed constant, see
    SMIRGA_ASTRAL_TITLE (not a function - there's no stat to pass in)."""
    return _ladder_title(value, ASTRAL_LEVELS, ASTRAL_MAX_TITLE)


def ansehen_title(value: int) -> str:
    return _ladder_title(value, ANSEHEN_LEVELS, ANSEHEN_MAX_TITLE)


def hunger_title(value: int) -> str:
    return _ladder_title(value, HUNGER_LEVELS, HUNGER_MAX_TITLE)


def durst_title(value: int) -> str:
    return _ladder_title(value, DURST_LEVELS, DURST_MAX_TITLE)
