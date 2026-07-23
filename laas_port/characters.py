"""
characters.py - the Smirga/Aszhanti narrator flag.

The player controls a party of two (Smirga and Aszhanti); many room and
object descriptions branch on which one is currently "narrating" (first-
person "mein/meine" vs. third-person "sein/seine"/"ihr/ihre" for the
other party member's things).

CONFIRMED this session by disassembling the room-1 ("Aszhantis
Elternhaus") look-handler (flat 0x147bd, laas analysis project's
PHASE0_FINDINGS.md UPDATE 12): the handler repeatedly does
`cmp word_b722, 0x1a; je <third-person message>` before falling through
to a first-person message otherwise. The two variants for the room's
opening line are message 93 ("Dies ist Aszhantis Elternhaus. Seine
Eltern...") vs. message 94 ("Dies ist mein Elternhaus. Meine Eltern...").
Since message 94's first-person framing can only be correct when
ASZHANTI is the narrator (it's Aszhanti's own parents' house), and that
is the branch taken when `word_b722 != 0x1a`:

    word_b722 == SMIRGA_CODE (0x1a)  -> third-person text (about Aszhanti)
    word_b722 != SMIRGA_CODE         -> first-person text (Aszhanti narrating)

0x1a is NOT a valid entry in objects.py's 250-object table in any way
that identifies "Smirga" by name (object 26 is unrelated scenery) - it's
a small, separate enum the game keeps in word_b722, not an object code.
Aszhanti's own matching constant hasn't been located yet (no xref to a
`mov word_b722, imm` write site has been traced), but isn't needed to
reproduce the game's actual branch logic, which only ever tests
equality against the Smirga constant and treats everything else as
"Aszhanti is narrating" - so that's exactly what `narrator` does here.
"""
from __future__ import annotations

from enum import IntEnum


class Character(IntEnum):
    SMIRGA = 0x1A
    ASZHANTI = 0  # placeholder - real constant not yet traced, see module docstring


DEFAULT_NARRATOR = Character.ASZHANTI
