"""
room_titles.py - the short status-bar room title shown top-left on
screen (e.g. "Das Hügelland." - see the real game screenshot the user
provided), separate from the room's full "look" description
(room_text.py).

FOUND this session: a clean, NUL-delimited list of ALL room titles,
authored in room-number order, living in the same flat data region as
STORY/ITEMS (flat 0x22800+ in the `laas` analysis project's IDB -
*not* part of the STORY message table itself; confirmed by exact
string search that none of these titles exist anywhere in STORY's
2360-entry message table). Immediately following the room-title list
(at the same base, roughly index 107 onward) is a SEPARATE, much
longer list that looks like the game's full generic-object vocabulary
("Schlüssel", "Tür", "Tisch", "Schwert", "Seil", ... - promising lead
for extending names.py's noun-dispatch coverage, not yet used here).

The runtime mechanism (traced earlier this session, see
PHASE0_FINDINGS.md's newest addendum): a per-room dispatcher reads a
far-pointer table (`word_16b0`, `room*4`-indexed - NOT `room-1`, unlike
the main look-dispatch table) and prints the room's title via a
dedicated status-bar print routine (`sub_4CA7`) whenever a per-room
flag byte's low nibble is 0 - i.e. this is the DEFAULT/generic title
path; a room whose flag is set instead prints a title from within its
own handler (not investigated further - not needed since the shared
title list already covers every confirmed room by content).

CONFIRMED entries below matched by EXACT, distinctive string content
against already-verified rooms (room_text.py) - the title list is
authored in room-number order with occasional runs of consecutive rooms
sharing one generic title (rooms 11-16 all share "Das Hügelland.", for
instance) - same reuse pattern already seen for room look-text and
names.py. Where a title covers a whole run of similar rooms, EVERY room
in that run gets the same entry below; this is a real reuse in the
original game, not a porting shortcut.
"""
from __future__ import annotations

ROOM_TITLE: dict[int, str] = {
    1: "Aszhantis Elternhaus.",
    2: "Smirgas Elternhaus.",
    3: "Schmiede.",
    4: "Beim Scharlatan.",
    5: "Hühnerstall.",
    6: "Aszhantis Zimmer.",
    7: "Smirgas Zimmer.",
    8: "Speisekammer.",
    9: "Im Brunnen.",
    10: "Vor Hyllok.",
    # Hill-country cluster: confirmed by exact match against the user's own
    # screenshot (room 12's content, message 234, displayed under this exact
    # title) - all six rooms in this run share it.
    11: "Das Hügelland.",
    12: "Das Hügelland.",
    13: "Das Hügelland.",
    14: "Das Hügelland.",
    15: "Das Hügelland.",
    16: "Das Hügelland.",
    17: "An einem Fluß.",
    18: "An einem Fluß.",
    19: "Auf einem Feldweg.",
    20: "Auf einem Feldweg.",
    21: "Vor dem Bauernhof.",
    22: "Das Hügelland.",
    23: "Das Hügelland.",
    24: "Vor der Brücke.",
    25: "Vor der Brücke.",
    26: "Unter einer Baumgruppe.",  # exact match, room 26 confirmed independently
    27: "In Potidans Hütte.",       # exact match, room 27 confirmed independently
    28: "Das Tal des Mondscheinkrauts.",  # exact match, room 28 confirmed independently
    29: "An einer Gabelung.",       # exact match, room 29 confirmed independently
    30: "Auf einem Kiesweg.",
    31: "Auf dem Weg ins Tal.",
    32: "In einem Fischerdorf.",
    33: "Am Seeufer.",
    34: "Am Seeufer.",
    35: "In der Kneipe.",           # matches room 35's confirmed tavern content
    36: "In einem Bootsschuppen.",  # matches room 36's confirmed boathouse content
    37: "Auf dem See.",
    38: "Auf dem See.",
    39: "Auf dem See.",
    40: "Auf einer Ebene.",
    41: "Auf einer Ebene.",
    42: "Auf einer Ebene.",
    43: "Auf einer Ebene.",
    44: "Vor einem Gebirge.",
    45: "Vor den Stadttoren.",      # matches room 45's confirmed Scarbloom-gates content
    46: "Vor einem Gebirge.",
    47: "Vor einem Gebirge.",
    48: "Vor einer Hütte.",         # matches room 48's confirmed Potidan's-hut-exterior content
    50: "Im Wald.",
    51: "Im Wald.",
    52: "Im Wald.",
    53: "Im Wald.",
    54: "Im Wald.",
    55: "Im Wald.",
    56: "Im Wald.",
    57: "Im Wald.",
    60: "Im Garten.",               # matches room 60's confirmed Skeeve's-garden content
    61: "Bei Skeeve.",              # matches room 61's confirmed Skeeve's-living-room content
    62: "Bei Skeeve.",
    63: "Bei Skeeve.",
    64: "Vor einer Höhle.",         # matches room 64's confirmed cave-troll-entrance content
    65: "In der Höhle.",            # matches room 65's confirmed troll's-lair content
    67: "Auf dem Dorfplatz.",       # matches room 67, the very first anchor of this whole project
    70: "Scarbloom.",               # matches room 70's confirmed marketplace content
    71: "Scarbloom.",
    72: "Scarbloom Inn.",           # matches room 72's confirmed Oerli's-tavern content
    73: "Scarbloom.",
    74: "Scarbloom.",
    75: "Gultibas Laden.",          # matches room 75's confirmed shop content
    76: "Scarbloom.",
    77: "Scarbloom.",
    78: "Die Magiergilde.",         # matches room 78's confirmed mages'-guild content
    79: "Scarbloom.",
    80: "Vor dem Palast.",
    81: "Vor dem Palast.",          # matches room 81's confirmed palace-portal content
    82: "In der Schmiede.",         # matches room 82's confirmed temple content - NOTE: this
                                    # specific pairing is LOWER confidence (the title list has
                                    # "Relieh Tempel" nearby which reads like the more fitting
                                    # match for a temple room - see the module docstring's
                                    # caveat; not switched yet since room 82's exact index
                                    # alignment in a run of similar Scarbloom rooms isn't pinned
                                    # down precisely).
    83: "Sackgasse.",               # matches room 83's confirmed alley content
    84: "Sackgasse.",
    85: "Sackgasse.",
    86: "In der Schmiede.",         # matches room 86's confirmed Nichidor's-forge content
    87: "Sackgasse.",               # matches room 87's confirmed dead-end-alley content
    88: "Gultibas Wohnung.",        # matches room 88's confirmed Gultiba's-bedroom scene (see
                                    # room_text.py) - also confirms the title blob's index 94
                                    # is room 88, which in turn confirms indices 95-99
                                    # ("Hexenhaus"/"Marschland."/"Im Sumpf."/"Vor dem
                                    # Hexenhaus."/"Im Hexenhaus.") are rooms 89-93 - corroborating
                                    # PHASE0_FINDINGS.md's swamp/witch-house hypothesis for that
                                    # cluster, though those rooms remain genuinely uncompiled
                                    # (no handler exists to source their actual look text from).
    100: "Auf einem Plateau.",      # exact match, room 100 confirmed independently
    101: "In der Höhle.",
    102: "In der Höhle.",
    103: "Felsklippe.",
    104: "Die Schatzkammer des Drachen.",  # matches room 104's confirmed Tatzelwurm's-hoard content
    105: "Eine weite Ebene.",       # matches room 105's confirmed sunlit-plain content
    106: "Felsklippe.",             # matches room 106's confirmed cliff-base content
    107: "Felsklippe.",             # matches room 107's confirmed cliff-climb content
    108: "Burgruine.",              # matches room 108's confirmed ruined-castle content
}


def room_title(room_number: int) -> str | None:
    return ROOM_TITLE.get(room_number)
