"""
game.py - a minimal, text-only playable skeleton for the "Die Drachen
von Laas" port.

STATUS: groundwork + a real verb layer. This proves the real game data
(rooms, exits, objects, descriptions) loads and is navigable end to
end, and supports LOOK, EXAMINE, TAKE, DROP, INVENTORY, movement,
OPEN/CLOSE/LOCK/UNLOCK, SAVE/LOAD, CHARACTER (a port utility, not a
reconstructed original verb - see characters.py), and HELP through a
proper parser/dispatch architecture - but it is NOT a reimplementation
of the original's ~80 verb handlers (combat, puzzles, NPC dialogue,
shopping, etc. are all still just hex-coded logic in the `laas`
analysis project's decompiled/seg005_batch*.md notes, not ported here
yet). Treat this as the foundation to build the rest of the real verbs
on top of.

Known gaps, deliberately left for follow-up work (see reference/ and
the analysis project's PHASE0_FINDINGS.md):
  - Room description text (`room_text.py`) covers 90 of 109 rooms
    (rooms 48, 88, and 89-99 remain - see its module docstring for what
    was tried and ruled out). Unmapped rooms show a placeholder.
  - Object NAMES (`names.py`) covers 12 NPCs/creatures/items so far,
    found by cross-referencing tracked object locations against the fan
    map and each room's own confirmed text - everything else (portable
    items, and the ambiguous room-1/2 NPC pairs) must be referenced by
    numeric code (e.g. "nimm #35") until the real per-room noun-dispatch
    mechanism is found (see names.py's docstring for what was tried and
    ruled out this session).
  - Combat (`combat.py`) ports the confirmed CORE melee formula (hit
    rolls, armor-based damage reduction/blocking, character targeting,
    leveling, HP) but deliberately does NOT implement the spell system
    (Aszhanti's LEVI/FEBR/etc. effects are a much larger, separately-
    dispatched mechanic - see combat.py's own docstring) or weapon-
    specific damage/accuracy modifiers (Dolch/Schwert's real object
    codes are unresolved - see PHASE0_FINDINGS.md UPDATE 27).
  - Movement does NOT check door state (open/closed/locked) - the
    original's core exit-table movement code doesn't gate on msg_code
    either (confirmed: it reads dest_room unconditionally), so this
    matches the original rather than being an oversight. Whether any
    room-specific handler layers an obstacle check on top is unknown.
  - TAKE/DROP only work on the 39 object codes that have a tracked
    instance in the original game (see world.py) - everything else is
    static scenery in the original too, not a limitation specific to
    this port.
  - SAVE/LOAD exist (JSON, this port's own format - see the module
    docstring above `GameState.save`) but only cover this port's own
    mutable state; no combat/dialogue/quest-progress state exists yet
    to save in the first place.

world.DIRECTION_NAMES (the exit-slot-to-compass mapping) IS confirmed -
see its own docstring in world.py for the evidence (4 independently
verified room-67 exits, all consistent with a clockwise-from-north
ordering: N, NE, E, SE, S, SW, W, NW).
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

from .story import Story
from .world import (
    World,
    LIMBO_CARRIED,
    LIMBO_REMOVED,
    DIRECTION_NAMES,
    DIRECTION_SLOTS,
    DOOR_OPEN,
    DOOR_CLOSED,
    DOOR_LOCKED,
)
from .item_stats import ItemStats
from .objects import ObjectTable
from .room_text import look_text, first_visit_text
from .room_titles import room_title
from .names import resolve_name, OBJECT_NAMES
from .parser import parse, parse_chain, Command, DIRECTION_WORDS
from .characters import Character, DEFAULT_NARRATOR
from . import levels
from . import combat
from . import pictures
from .monster_stats import MonsterStats
from .repl_input import prompt_with_default, init_repl_input

SHOW_PICTURES = False # Tests should not show pictures, but the real game does on first room visit

DEFAULT_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"

DIRECTIONS = {"N", "NE", "E", "SE", "S", "SW", "W", "NW"}

# The real game's "F2" exit listing (PHASE0_FINDINGS.md UPDATE 61,
# user-supplied real gameplay text): "Unmittelbare Ausgänge führen
# <exits>." - default rule confirmed against FOUR real examples
# (rooms 10, 11, 18, 2): "nach" precedes every direction word, always -
#   room 11: "...nach Osten, nach Südosten, nach Süden und nach
#             Westen." (Südosten, a compound direction, keeps "nach")
#   room 18: "...nach Norden, nach Südwesten, nach Westen und nach
#             Nordwesten." (Südwesten/Nordwesten - also compound -
#             both keep "nach" too)
#   room 2:  "...nach Norden, nach Osten, nach Westen und nach Oben."
# All list exits in ascending slot order (0-7), matching this port's
# own `Room.available_exits()` iteration order already.
#
# UPDATE 61 first read room 10's text as evidence that "nach" drops
# before any compound direction - WRONG, corrected by UPDATE 66's two
# further examples above, which keep "nach" before Südosten/Südwesten/
# Nordwesten. Room 10's own confirmed text really does omit "nach"
# before "Nordosten" specifically ("...nach Norden, Nordosten, nach
# Osten..."), but nothing else does - a genuine one-off exception (this
# port's best guess: something in the original's own text-assembly
# quirked out ONLY for this one word), not a rule. Special-cased below
# rather than generalized into one.
EXIT_DIRECTION_WORDS = {
    "N": "Norden", "NE": "Nordosten", "E": "Osten", "SE": "Südosten",
    "S": "Süden", "SW": "Südwesten", "W": "Westen", "NW": "Nordwesten",
}
EXIT_NACH_OMITTED = {(10, "NE")}

# UPDATE 66: slot 7 (the exit table's "NW" slot - see world.py's
# DIRECTION_NAMES comment for the full history) is confirmed real
# "Oben" for room 2 specifically (a staircase up to Smirga's room), but
# confirmed real "Nordwesten" for room 18 (and, by reciprocity, every
# other room using this same slot that hasn't been independently
# checked) - the same raw exit-table slot means different things in
# different rooms, distinguished (as far as this port can tell) only by
# a different `msg_code` on the exit record itself (room 2: 3, room 18:
# the generic 1 shared by every confirmed-"Nordwesten" slot-7 exit).
# Deliberately narrow: only room 2's case is independently confirmed by
# real text, so only `(2, "NW")` is overridden here - typing "nw" still
# moves you there too (same underlying exit), and "oben"/"hinauf"/
# "rauf" are just additional parser aliases for the same "NW" move
# (see parser.py) - this dict only changes what the F2 listing PRINTS,
# not how movement resolves.
EXIT_LABEL_OVERRIDES = {(2, "NW"): "Oben"}


def _exit_phrase(room_number: int, direction: str) -> str:
    label = EXIT_LABEL_OVERRIDES.get((room_number, direction), EXIT_DIRECTION_WORDS[direction])
    if (room_number, direction) in EXIT_NACH_OMITTED:
        return label
    return f"nach {label}"

# Dolch/Schwert's real object codes (PHASE0_FINDINGS.md UPDATE 84/85) -
# a gap this project had left explicitly unresolved for a long time
# (combat.py's own docstring: "the real object codes for Dolch/Schwert
# were investigated at length and are UNRESOLVED"). Closed via two
# user-supplied pairs of live memory dumps, each bracketing a single
# "verkaufe <weapon>" action at Gultibas Laden: the confirmed
# `LIMBO_CARRIED` sentinel (150) disappears from exactly one file
# position in each pair, cross-validated by a forced 48-byte-stride
# relationship to Schinken's independently-confirmed code (21) and an
# exact carried-item-count match (7->6 for Dolch, 6->5 for Schwert).
# Neither code has any entry in the generic merchant price table
# (item_stats.py) - consistent with both being Foroll's own scripted,
# non-catalog bundle rather than regular shop goods; their own real
# SELL prices (5 and 15 Gerfs respectively, confirmed via the same two
# screenshots) are hardcoded in `sell()` (STARTER_WEAPON_SELL_PRICES,
# below) for the same reason. Defined here, ahead of the door-verb
# constants right below, since KEY_OBJECT_CODE/UNLOCK_GATE_OBJECT turn
# out to be these same two codes (see that block's own comment).
DOLCH_CODE = 0
SCHWERT_CODE = 1

# Door-verb constants, all confirmed via `sub_EEC0`/funcs 7-10 - see the
# `laas` analysis project's decompiled/seg005_batch5.md. Room 0x55 itself
# is still not known by name (see room_text.py). The key (code 1) and
# the UNLOCK gate object (code 0) WERE "not yet known by name" when this
# was first confirmed - PHASE0_FINDINGS.md UPDATE 84/85 resolved both
# independently (via live memory dumps bracketing Foroll's starter
# weapons being sold), and they turn out to be Dolch (0) and Schwert
# (1) - the same two codes, cross-confirmed by two completely different
# methods (disassembly here, memory-dump differencing there). So this
# puzzle door's real "key" is genuinely the Schwert, and it can only be
# unlocked while NOT carrying the Dolch - an odd-sounding but
# textually-confirmed pair of requirements (`word_b3f4==1` to proceed
# at all, and object `0`/`0x96` (LIMBO_CARRIED) presence check failing
# unlock outright), not a coincidence introduced by this port.
#
# CONFIRMED against the real shipped data (not just the disassembly):
# room 0x55's own exit slot 0 (north) is genuinely pre-locked
# (msg_code==DOOR_LOCKED) in the loaded RESTORE state, and nowhere else
# in the game does a locked door happen to sit in room 0x55 - this really
# is the one deliberate lock/unlock puzzle door the reverse-engineering
# notes predicted.
KEY_OBJECT_CODE = SCHWERT_CODE
UNLOCK_GATE_OBJECT = DOLCH_CODE
UNLOCK_ROOM = 0x55  # 85

# Gultiba's bedroom (room 88, behind the room-85 door above) - a full
# scripted encounter, confirmed via direct disassembly of the room's
# own handler (PHASE0_FINDINGS.md UPDATE 87): walking in catches
# Gultiba's wife and her lover together ("Ehebruch nennt man das
# glaube ich!" - see room_text.py's ROOM_FIRST_VISIT_MESSAGE). Object
# codes for the 4 scripted fixtures (none instance-tracked - this is
# pure scenery, not combat), and the EXAMINE text confirmed for each,
# traced from the handler's own `si` (direct-object) comparisons:
GULTIBA_WIFE_CODE = 186
GULTIBA_LOVER_CODE = 145
GULTIBA_BEDROOM_BED_CODE = 119
GULTIBA_BEDROOM_WINDOW_CODE = 9
GULTIBA_BEDROOM_ROOM = 88
GULTIBA_BEDROOM_EXAMINE = {
    GULTIBA_WIFE_CODE: 1052,
    # Confirmed via verb code (EXAMINE is verb 0x32 - PHASE0_FINDINGS.md
    # UPDATE 8) explicitly dispatching to THIS message for the lover,
    # not message 1053 ("Der Mann ist ein Schmächtling...") - that text
    # belongs to a SEPARATE, unconfirmed di==1 sub-dispatch this port
    # doesn't model (see room 88's own disassembly notes, UPDATE 87).
    GULTIBA_LOVER_CODE: 2269,
    GULTIBA_BEDROOM_BED_CODE: 1049,
    GULTIBA_BEDROOM_WINDOW_CODE: 1050,
}
# Both of the scene's confirmed resolutions share the same consequence
# shape (Ansehen shift, the Dolch lost to true limbo, the door relocks
# behind you) - see `_resolve_gultibas_bedroom_encounter()`. Only one
# can ever fire (`_gultiba_bedroom_resolved` gates both):
#
# ATTACKing the lover (verb 0x24, already-confirmed as ATTACK, UPDATE
# 29): he suffers a fatal heart attack, Ansehen drops 2 - confirmed via
# the SAME `sub_AB36` object-relocation call this room's handler makes
# for this outcome, matching message 2311's own text ("...vergessen
# sogar den Schlüssel" - the real Schwert/KEY_OBJECT_CODE is untouched;
# it's the Dolch, the door's own UNLOCK gate object, that's lost).
#
# Letting him go peacefully (message 1058, Ansehen +2): PHASE0_
# FINDINGS.md UPDATE 88 traced `word_b770`'s real setter - a parser-
# level verb-aliasing routine (flat 0x5d44) that rewrites typed verb
# 0x67 to internal verb 0x40 (exactly what room 88 checks) whenever its
# argument is object code 2, also setting word_b770=1 as a side effect.
# Ported as a new "LASS" verb (parser.py) - a PORT UTILITY name, same
# caveat as ATTACK/HELFEN: the confirmed EFFECT (verb 0x67 + arg-code-2
# -> internal release trigger) is disassembly-solid, but the exact
# TYPED WORD behind 0x67 isn't independently confirmed, only inferred
# from context (the lover's own "Bitte, laßt mich gehen!" line) the
# same way ATTACK's own German trigger word was never confirmed either.
#
# STILL UNPORTED: message 1059 ("Gut. Ich stoße den Typ wieder
# zurück" - reached when LASS-ing something/someone that ISN'T
# confirmed as this exact lover+room combination) and message 1054 (a
# rebuke, triggered by an unconfirmed verb 4 applied to the wife) -
# real, confirmed text with no confidently-identified trigger this
# port implements.
GULTIBA_LOVER_DEATH_MESSAGE = 2311
GULTIBA_LOVER_DEATH_ANSEHEN = -2
GULTIBA_LOVER_RELEASE_MESSAGE = 1058
GULTIBA_LOVER_RELEASE_ANSEHEN = 2

DEFAULT_SAVE_PATH = Path("savegame.json")

# Both merchants confirmed via item_stats.py's WORLD Section 1 field
# semantics + real merchant prices the user supplied (Laas_CS.xlsx's
# "Händler" sheet) - see PHASE0_FINDINGS.md UPDATE 18. Gultiba is a fixed
# shopkeeper (188, room 75 "Laden" - see names.py). Yarom (167) is a
# TRAVELING merchant - confirmed via a direct disassembly trace of his
# price-quote dialogue (see names.py's entry for the full derivation) -
# so he only trades when his tracked instance happens to be in the
# player's current room, exactly like `_merchant_here()` already checks
# for anyone in MERCHANTS. His own price fields (1/2) were already
# confirmed separately in item_stats.py before his object code was known.
MERCHANTS = {
    188: {"name": "Gultiba", "sell_field": 3, "buy_field": 4},
    167: {"name": "Yarom", "sell_field": 1, "buy_field": 2},
}

# Foroll (34, room 3 "Schmiede" - both confirmed, see names.py/room_text.py)
# sells the player's starting dagger+sword as a SCRIPTED, hardcoded-price
# event, confirmed via a real DOSBox screenshot matched byte-for-byte
# against STORY messages 123-124 (room_text.py's ROOM_FIRST_VISIT_MESSAGE):
# Foroll's exact line is "'Tja, habts er denn auch Geld? Macht genau 7
# Gerfs.'" - NOT looked up from item_stats.py's WORLD Section 1 table
# (confirmed absent there for "Dolch" specifically - it isn't a generic
# shop item at all, consistent with being this one-time bundle).
FOROLL_OBJECT_CODE = 34
FOROLL_ROOM = 3
FOROLL_WEAPON_PRICE = 7
STARTER_WEAPON_SELL_PRICES = {DOLCH_CODE: 5, SCHWERT_CODE: 15}

# The farmer's harvest-help quest (PHASE0_FINDINGS.md UPDATE 68) -
# found while tracing what raises/lowers Ansehen (user asked directly:
# "can we figure out the reputation system?"). Fully confirmed via a
# disassembly trace of the real code (flat 0x16887-0x16980 for the
# help/reward path, flat 0x6a5f-0x6a99 for the storm timer):
#   - Bauer (99, confirmed farmer, day-only per DAY_ROSTER) needs help
#     bringing in the harvest at room 20 (Kornfeld) before a storm hits.
#   - A per-turn counter advances once per turn spent in room 20 while
#     the quest is still unresolved; at FARMER_QUEST_STORM_TURNS turns,
#     the storm hits and the quest fails PERMANENTLY (see
#     `_check_farmer_storm()`) - matches the walkthrough's own framing
#     ("wenn Ihr ihm auf dem Feld helft") as a real race, not a
#     standing offer.
#   - Helping in time (`helfen()`) triggers a whole scripted farmhouse
#     scene: +1 Ansehen, +2 Smirga Strength, +1 Aszhanti Strength, +1
#     MAX hp to both party members (the same "won fight" pattern
#     `attack()` already applies elsewhere), Hunger/Durst reset to full
#     (the farmer feeds you), a farmhouse conversation that reacts to
#     your CURRENT Ansehen tier (the exact same 4 thresholds as the
#     status screen's own ladder - UPDATE 23), and a Schinken (ham)
#     reward, object code 21 - confirmed via the disassembly's own
#     "give object" call sitting directly after the reward text, not
#     independently corroborated by a second source the way some other
#     codes are.
FARMER_CODE = 99
FARMER_ROOM = 20
FARMER_QUEST_STORM_TURNS = 6
FARMER_QUEST_SCHINKEN_CODE = 21

# The Tuatara bounty/diplomacy quest (PHASE0_FINDINGS.md UPDATE 69) -
# the walkthrough's "1. Auftrag", found while chasing Phadraig's oar-
# return Ansehen reward (UPDATE 67/68) - it turned out to gate on this
# whole quest's own resolution, not just "did you give the oar back".
# Confirmed via disassembly (flat 0xa79a-0xa7d3 for Phadraig's own
# check; flat 0x12fa9-0x1300e for the Tuatara dialogue; flat 0x9154 for
# the kill path) that BOTH endings satisfy it - the fishing village's
# tavern offers 150 Gerfs to deal with a Tuatara (146, already sitting
# at its own room by default) terrorizing their fishing grounds; you
# can kill it in a real fight (it has real combat stats already) or
# talk to it - it turns out to be intelligent and has never been
# spoken to, only hunted - and negotiate on the fishermen's behalf.
# Both endings pay the same 150-Gerf bounty (confirmed word-for-word:
# both STORY messages 626/627 end "...um 150 Gerfs reicher").
#
# Confirmed real state progression (`word_b678`): 1 = quest accepted
# (asked Phadraig), 2 = boat/oar obtained, 3 = encountered Tuatara
# (arrived at the lake), 4 = killed it, 5 = successfully talked it into
# helping. KNOWN SIMPLIFICATION: stages 1/2 are collapsed into a single
# `frage()` interaction (accepting the quest and getting the oar happen
# in one unbroken scripted scene in the real text too - message 566 -
# so nothing is lost by not splitting it further), and this port only
# tracks stage via `_tuatara_quest_stage` for 0/3/4/5 - "do you have
# the Ruder" already does the job of gating stages 1-2's own actions.
# The harpoon Phadraig hands over (message 566) has no confirmed object
# code (not found in the object-description table, not price-matched
# to anything) - modeled as flavor text only, not a trackable item.
TUATARA_CODE = 146
PHADRAIG_CODE = 147
RUDER_CODE = 152
TUATARA_TAVERN_ROOM = 35        # "Zum singenden Barben"
TUATARA_BOATHOUSE_ROOM = 36     # "Bootsschuppen"
TUATARA_LAKE_ROOMS = (37, 38, 39)  # confirmed zero-compass-exit "rudere"-only rowing states
TUATARA_ENCOUNTER_ROOM = 39     # confirmed closest to Tuatara
TUATARA_BOUNTY_GERFS = 150

# Potidan's Mondscheinkraut fetch-quest (PHASE0_FINDINGS.md UPDATE 70,
# another of UPDATE 67's 8 confirmed Ansehen sources, +2 at flat
# `0x17398`). Potidan (243, room 27) offers to heal the party in
# exchange for the Mondscheinkraut (moonlight herb, object 64 - object
# identity confirmed the same way as Ruder/152 was: a `cmp si, 0x40`
# check in Potidan's own topic dispatcher). Confirmed real state
# machine (`word_b6e6`): 2 = quest known/offered, 3 = accepted/waiting
# for the herb, 4 = turned in. KNOWN SIMPLIFICATION: this port collapses
# 2/3 into one `_potidan_quest_stage` value (1) - the real dialogue's
# extra accept/confirm step has no other observable game-state effect.
# The herb itself is a monster loot-drop (killing the Skelett/244, the
# confirmed room-28 night-only creature - see NIGHT_ROSTER, whose
# arrival/departure messages 1553/1552 independently confirm the
# identity) - the EXACT drop mechanism wasn't found in the disassembly
# (unlike, say, Skeeve's confirmed GIB-based handoffs), so this port
# grants it directly on kill, the same simplification already applied
# to Tuatara's harpoon. The confirmed reward (message 1538): 100 Gerfs,
# +2 Ansehen, and an offer to heal on the spot (message 1557's own
# "erst müßt ihr mir einen Gefallen tun" - the favor - confirms the
# healing IS the quest's motivation, not just a bonus) - this port
# auto-accepts the heal (message 1515) rather than modeling a separate
# yes/no prompt, since declining has no confirmed consequence.
# Room 28 (the herb valley) has zero compass exits in the confirmed
# room graph - room 47's own dead-end "N:999" edge-of-map sentinel
# (previously assumed unused, room_text.py's own note) is the real
# climb-in point, matching the walkthrough's "climb through the
# passage" framing and room 28's own text ("im Westen der Durchgang
# ... durch den wir hierher gefunden haben").
POTIDAN_CODE = 243
MONDSCHEINKRAUT_CODE = 64
SKELETT_CODE = 244
POTIDAN_ROOM = 27
POTIDAN_PASSAGE_ROOM = 47       # mountain ridge/pass - the climb-in point
POTIDAN_HERB_VALLEY_ROOM = 28   # zero-compass-exit, night-only Skelett
POTIDAN_QUEST_GERFS = 100

# Hyllok is a safe zone - no random ambush (see _check_ambush) ever
# happens there, user-confirmed. Matches room_text.py's already-confirmed
# room map exactly: 1-9 are Hyllok's own interiors (Aszhantis/Smirgas
# Elternhaus, Schmiede, Beim Scharlatan, Hühnerstall, Aszhantis/Smirgas
# Zimmer, Speisekammer, im Brunnen), 67 is the village square ("Auf dem
# Dorfplatz"), and room 10 ("Vor Hyllok") is the confirmed first room
# OUTSIDE the village - i.e. the first place random combat can occur.
SAFE_ZONE_ROOMS = set(range(1, 10)) | {67}

# The real per-monster room-list CONTENT (PHASE0_FINDINGS.md UPDATE
# 78) - the exact restriction UPDATE 30/77 had marked unreconstructable
# from static analysis alone. Found by brute-force scanning a user-
# supplied live memory dump (`MEMDUMP_in_fight_goblin.BIN`) for a base
# address where all 9 wanderers' far pointers (`ObjectInstance.
# has_room_list`'s `raw[0xc:0x10]`, segment 0x3337 for all of them)
# simultaneously decode into `sub_C301`'s confirmed (tag, room) pair
# format with every room in 1..108 - a search space narrow enough
# (9 independent constraints at once) that a match is essentially
# unambiguous. One candidate base (0x285C4, relative to the dump file's
# own start) decoded all 9 cleanly; the `tag` half is read by
# `sub_C301` only as a zero/nonzero terminator check, never compared
# against anything else, so it carries no gameplay meaning beyond that
# and isn't kept here. Cross-validated three ways: (1) byte-for-byte
# identical across all 12 memory dumps supplied over the course of this
# project, captured in entirely different rooms/sessions - confirming
# genuinely static, session-independent game data, not a coincidence
# of one capture; (2) Goblin's list contains rooms 11 and 12, both
# "Das Hügelland" - the exact room the user's own ambush screenshot was
# taken in; (3) Ork's list contains room 106, "Felsklippe" - the exact
# room the user's second memory dump was captured in, fighting an Ork
# there. Every entry also independently matches this project's own
# already-confirmed DAY_ROSTER_BY_INSTANCE/NIGHT_ROSTER_BY_INSTANCE_*
# placements (Zombie's list includes 23, Werwolf's includes 50,
# Wildschwein's includes 51 - one off from its own confirmed 50, this
# project's own long-flagged +1 discrepancy - Ork's includes 106,
# Kobold's includes 43), and geographically clusters exactly as
# expected: Goblin (11/12/17/19/26) and Raubfliege (a much longer list,
# 10-16/18/30/40/41/44/47/91) both sit in the beginner region before
# the bridge troll, matching the user's report precisely, while every
# other wanderer's list sits entirely outside it (Werwolf/Wildschwein
# share rooms 50-57, Ork sits at 46/48/105/106 near Felsklippe, Slime
# at 92-96, Kobold at 42-44, Bandit at 71/73/74/76/79 near the
# Magiergilde/78) - explaining exactly why Ork and Slime were wrongly
# ambushing in the beginner area under the port's old "any non-Hyllok
# room" simplification. Replaces UPDATE 77's `PRE_BRIDGE_ROOMS`/
# `PRE_BRIDGE_ALLOWED_INSTANCES` heuristic entirely - this is the real
# mechanism, not an approximation of it, and it applies everywhere, not
# just before the bridge.
MONSTER_ROOM_LISTS: dict[int, frozenset[int]] = {
    0: frozenset({11, 12, 17, 19, 26}),               # Goblin
    2: frozenset({14, 15, 17, 18, 22, 23, 24}),        # Zombie (87)
    26: frozenset({50, 51, 52, 53, 54, 55, 56, 57}),   # Werwolf
    27: frozenset({46, 48, 105, 106}),                 # Ork
    28: frozenset({92, 93, 94, 95, 96}),                # Slime
    30: frozenset({51, 52, 53, 54, 55, 56, 57}),        # Wildschwein
    31: frozenset({42, 43, 44}),                        # Kobold
    32: frozenset({71, 73, 74, 76, 79}),                # Bandit
    36: frozenset({10, 11, 12, 13, 14, 15, 16, 18, 30, 40, 41, 44, 47, 91}),  # Raubfliege
}

# Room-bound creatures/objects (UPDATE 21's taxonomy: monsters split
# into room-bound fixed encounters vs. the free-wandering ambush pool)
# all have `ambush_eligible=True` in the raw instance data despite not
# belonging to the wandering pool at all - 134 Bruckentroll (guards the
# bridge, room 25), 146 Tuatara (the lake creature at the Fischerdorf,
# room 39, tied to a peaceful fetch-quest, not hostile), 237 Lindwurm/
# 238 Tatzelwurm (the two dragon bosses). UPDATE 48/49 correctly flipped
# the ambush condition to match the real game (candidates must NOT be
# at 299 rather than must be), which exposed these as newly "active"
# false positives; UPDATE 74-76 patched them out one confirmed case at a
# time via a hand-curated exclusion list.
#
# UPDATE 77 replaced that whole curated list with the REAL discriminator
# it was always approximating: `ObjectInstance.has_room_list`. Fully
# re-disassembling `sub_C301` (the actual random-ambush trigger) showed
# it skips any instance whose room-list far pointer is the -1,-1
# sentinel, unconditionally, before even checking the current room - and
# every one of these four room-bound entries (confirmed via the RESTORE
# instance table's own bytes) has exactly that sentinel. So does every
# other confirmed room-bound/fixed encounter (Oger, Skelett,
# Höhlentroll, Treksis, Golem, Dämon, Harpyie - previously handled by
# `AMBUSH_EXCLUDED_INSTANCE_INDICES`, now removed the same way). One
# entry in the old curated list was actually WRONG under this real
# rule - Raubfliege (36) DOES have a real room-list pointer (a genuine
# wanderer), so `AMBUSH_EXCLUDED_INSTANCE_INDICES` was silently keeping
# a real early-game monster out of the pool; see `_ambush_candidates()`.
#
# Steinkreuz (105) was never part of either list (UPDATE 76): a live
# memory dump captured mid-fight, plus a plain-text 39-entry name table
# found in it (see INSTANCE_NAMES below), confirmed that instance 0 -
# the slot object 105's own flags word happens to point to - is NOT
# actually Steinkreuz's combat data at all. It's a genuine wandering
# monster, "Goblin" (hp10/atk10/def10/1d6+3 damage - the user's own
# screenshot shows a Goblin hit for exactly 9, the maximum possible
# roll), which is exactly why it DOES have a real room-list pointer.
# See AMBUSH_INSTANCE_IGNORES_OBJECT_CODE below for how instance 0's
# ambushes avoid misidentifying themselves as Steinkreuz.

# Confirmed via that same live memory dump (user-supplied,
# "MEMDUMP_in_fight_goblin.BIN") - a plain-text (NOT STORY-encoded),
# NUL-separated name table with exactly 39 entries, one per instance
# index in exact ascending order. Cross-validated against EVERY
# already-independently-confirmed identity with zero mismatches
# (instance 10=Bauer/99, 11=Bruckentroll/134, 12=Tuatara/146,
# 13=Phadraig/147, 14=Oger/162, 15=Yarom/167, 16=Bettler/183,
# 21=Lindwurm/237, 22=Tatzelwurm/238, 23=Potidan/243, 24=Skelett/244,
# 25=Höhlentroll - UPDATE 74's own room-text-based find). This resolves
# every remaining "Kreatur #N" wanderer at once, PLUS names object 87
# for the first time (instance 2 = "Zombie" - see names.py). Only the
# subset without their own confirmed object-code name is listed here;
# instance 0 (Goblin) is included despite HAVING a mapped code (105,
# Steinkreuz) because that code's own name is wrong for ambush purposes
# - see AMBUSH_INSTANCE_IGNORES_OBJECT_CODE.
INSTANCE_NAMES = {
    0: "Goblin",
    25: "Höhlentroll",
    26: "Werwolf",
    27: "Ork",
    28: "Slime",
    29: "Treksis",
    30: "Wildschwein",
    31: "Kobold",
    32: "Bandit",
    33: "Golem",
    34: "Dämon",
    35: "Harpyie",
    36: "Raubfliege",
}

# Instance 0's own object-code link (105/Steinkreuz) must be ignored
# for ambush naming/movement - using it would misname the Goblin as
# "Steinkreuz" and incorrectly relocate the actual Steinkreuz landmark
# object out of its own room (26) whenever the Goblin ambushes.
AMBUSH_INSTANCE_IGNORES_OBJECT_CODE = {0}

# Day/night NPC and monster roster (PHASE0_FINDINGS.md UPDATE 49):
# confirmed via the day/night clock's own dawn/nightfall subroutines,
# which place each roster member at a specific room for its active
# phase and reset it to LIMBO_REMOVED for the other phase - dawn and
# nightfall are exact mirror images of each other. These entries all
# have a confirmed object code; the real game also cycles several more
# members that were never resolved to an object code (day instance
# indices 27/28/30, night indices 26/31/32/33/34, gated behind a
# progression check) - wired up separately below
# (DAY_ROSTER_BY_INSTANCE/NIGHT_ROSTER_BY_INSTANCE_*), since they
# genuinely have no object code at all (UPDATE 74), not a gap left
# unaddressed.
#
# Room values for 30/31/32/33 (the room-1/room-2 family members) match
# the disassembly exactly. Bauer/Yarom/Bettler's rooms use their
# ALREADY independently-confirmed rooms (20/44/70) rather than the
# dawn function's own encoded immediates (21/45/70) - the first two are
# consistently +1 from the confirmed real values (verified against raw
# bytes, not a transcription slip), an unresolved discrepancy not
# chased down further. 87/162(Oger)/244's night rooms have no
# independent cross-check at all - taken directly from the disassembly.
DAY_ROSTER = {
    31: 2,    # Smirgas Elternhaus family member (not ambush-eligible)
    32: 1,    # Aszhantis Elternhaus family member (not ambush-eligible)
    33: 1,    # Aszhantis Elternhaus family member (not ambush-eligible)
    30: 2,    # Smirgas Elternhaus family member (not ambush-eligible)
    99: 20,   # Bauer (confirmed farmer, Kornfeld)
    167: 44,  # Yarom (confirmed traveling merchant)
    183: 70,  # Bettler (confirmed market beggar)
}
NIGHT_ROSTER = {
    87: 23,
    162: 32,  # Oger (confirmed via FEBR, UPDATE 38 - room not independently confirmed)
    244: 28,
}

# The day/night roster members UPDATE 49 confirmed but couldn't resolve
# to an object code (see DAY_ROSTER's own docstring) - wired up here
# UPDATE 74 by INSTANCE INDEX directly, since that's genuinely how the
# real dawn/nightfall subroutine addresses them (`word_16A4 +
# instance_index*0x20`, confirmed - no object-code lookup involved at
# all for these). Room values for 27/28/30 are read directly from this
# port's own world data (matching UPDATE 49's own hand-decoded values
# almost exactly, the ~105/106 approximation resolving cleanly to 106).
# `_instance_location_overrides` (parallel to `_location_overrides`'s
# object-code keying) tracks these; `_advance_day_night_roster()`
# toggles them the same way as DAY_ROSTER/NIGHT_ROSTER.
DAY_ROSTER_BY_INSTANCE = {27: 106, 28: 93, 30: 50}

# UPDATE 49's confirmed progression gate: nightfall checks Ansehen
# (`word_b688`, confirmed identity - UPDATE 67) >= 5 to decide which
# night roster is active - EARLY replaces with LATE once unlocked, they
# never coexist (instance 31 is exclusively early-game; 26/33/34
# exclusively late-game).
NIGHT_ROSTER_BY_INSTANCE_EARLY = {31: 43}
NIGHT_ROSTER_BY_INSTANCE_LATE = {26: 50, 33: 45, 34: 43}
ANSEHEN_LATE_ROSTER_THRESHOLD = 5

# A THIRD night roster member (UPDATE 49's own table, initially missed
# when this was first wired up - caught during a user-driven follow-up
# investigation, UPDATE 75) - listed there with no "early/late"
# qualifier, unlike 31 and 26/33/34: unconditionally active every
# night regardless of Ansehen, not part of the progression swap.
NIGHT_ROSTER_BY_INSTANCE_ALWAYS = {32: 78}  # room 78, "Die Magiergilde"

# The remaining ambush-eligible-but-uncoded instances found alongside
# the day/night roster gap (UPDATE 74), each sitting at a REAL, FIXED
# room regardless of time of day: 25="Höhlentroll" (room 64/65, already
# confirmed independently via room_text.py messages 1590/1599, a nice
# cross-check), 29="Treksis" (room 101), 35="Harpyie" (room 108) -
# genuinely room-bound (`has_room_list` is False for all three, per
# UPDATE 77), so `_ambush_candidates()` excludes them the same way it
# now excludes Oger/Skelett/Golem/Dämon/Bruckentroll/Tuatara/Lindwurm/
# Tatzelwurm - via the real room-list check, not a curated list.
#
# 36="Raubfliege" (room 16) was ORIGINALLY grouped in here too (a
# curated `AMBUSH_EXCLUDED_INSTANCE_INDICES` set, since removed) on the
# same "sits at one fixed room" reasoning - but UPDATE 77 found that
# reasoning doesn't hold for Raubfliege specifically: unlike the other
# three, it DOES have a real room-list pointer, meaning the real game
# treats it as a genuine wanderer (matching the user's own gameplay
# report that Raubfliege ambushes alongside Goblin in the early rooms).
# It was a real bug, not a redundant safeguard - now a normal wandering
# candidate again, room 16 is just its static default rather than a
# day/night-toggled slot.

# The automatic room->picture table (PHASE0_FINDINGS.md UPDATE 72):
# `word_ad62` (the pointer `sub_495a`'s room-lookup reads - see
# pictures.py's own docstring for the manual F6/BILD picture viewer)
# is confirmed to be WORLD's 13th and final section's start pointer,
# via its own single write site (flat `0x384a`) sitting at the exact
# end of the WORLD loader's cumulative section-pointer chain. WORLD's
# real header format (traced directly from `sub_3777`'s fopen/fread
# calls, correcting an earlier documented mis-read): a leading u16
# total-blob-size, THEN 13 u16 section sizes (not 13 sizes from byte 0
# as originally assumed) - extracting section 13 (84 bytes, offset 1118
# in the 1202-byte blob) from the real WORLD asset file gives a clean,
# perfectly-terminated (0xFF,0xFF) table of 42 (room, picture) byte
# pairs. Cross-validated two independent ways: room 67 (the game's own
# confirmed starting room, `word_b34e=0x43` in the main loop's own
# init code) maps to picture 1 (P1 - the farmhouse scene already
# checked against the user's screenshot), and rooms 104/108 (the
# Tatzelwurm/Lindwurm dragon lairs, both already independently
# confirmed via names.py) map to pictures 21/22 - both of which decode
# to unmistakable dragon artwork.
ROOM_PICTURE_TABLE = {
    67: 1, 1: 2, 2: 2, 4: 3, 17: 4, 18: 4, 14: 4, 24: 5, 25: 5, 20: 6,
    21: 7, 29: 8, 30: 8, 55: 8, 53: 8, 98: 9, 61: 10, 62: 10, 63: 10,
    31: 11, 32: 11, 34: 12, 36: 12, 33: 12, 45: 13, 46: 13, 47: 13,
    105: 14, 107: 14, 84: 15, 85: 15, 75: 16, 35: 17, 100: 18, 101: 18,
    71: 19, 72: 19, 106: 20, 48: 20, 104: 21, 108: 22,
}

# SLEEP (SCHLAFEN) verb - confirmed room-by-room in an earlier analysis
# pass (`decompiled/seg005_batch7.md`, `sub_10792`), re-verified this
# session against the STORY text directly (avoiding that file's stale
# address notation) and cross-checked room-by-room against room_text.py's
# independently-confirmed room map - every room matches cleanly (Gultiba's
# shop/bedroom, Nichidor's forge, Skeeve's bedroom, both dragons' lairs,
# Sabrina's house at 98 - a nice cross-validation against UPDATE 44's
# completely separate identification of that same room).
#
# Confirmed structure: sleeping is a night-only action - ANY room during
# the day (`time_of_day < 0x80`) gets the generic "too much going on
# during the day" refusal, room 72 (Oerli's tavern) excepted (it has its
# own always-available scripted event). At night, each room group has
# its own outcome, several with real consequences (robbery, a fatal
# Lindwurm attack). See `sleep()` for what's simplified vs ported as-is.
SLEEP_MSG_DAYTIME_REFUSAL = 1689
SLEEP_MSG_HYLLOK_OWN_BED = 1693
SLEEP_MSG_OWN_BEDROOM = 1694
SLEEP_MSG_BRIDGE_TROLL = 1698
SLEEP_MSG_FOREST_MOSS = 1086
SLEEP_MSG_CAVE_SUGGEST = 1695
SLEEP_MSG_SABRINA_NIGHTMARE = 1242
SLEEP_MSG_TATZELWURM_BITE = 1697
SLEEP_MSG_LINDWURM_DEATH = 1692
SLEEP_MSG_STREET_ROBBERY = 1732
SLEEP_MSG_UNCOMFORTABLE_BUT_SAFE = 1230
SLEEP_MSG_SKEEVE_BED = 1691
SLEEP_MSG_MAKESHIFT_CAMP = 1405
SLEEP_MSG_DEFAULT_MANAGE = 1696
SLEEP_MSG_WAKE_UP = 1446

SLEEP_HYLLOK_OWN_BED_ROOMS = {1, 2, 5, 8, 67}
SLEEP_OWN_BEDROOM_ROOMS = {6, 7}
SLEEP_BRIDGE_TROLL_ROOM = 25
SLEEP_FOREST_MOSS_ROOMS = set(range(50, 58))
SLEEP_CAVE_SUGGEST_ROOM = 64
# One distinct message per room - confirmed 1:1 by matching list order
# (both ascending by room number) against room_text.py's identities:
# Gultiba's shop, the Mage's Guild, the healers' temple, Nichidor's
# forge, and Gultiba's own bedroom (his own "wouldn't like that" line
# is a clean thematic match for his private room specifically).
SLEEP_KICKOUT_MESSAGES = {75: 1733, 78: 1734, 82: 1735, 86: 1736, 88: 1737}
SLEEP_SABRINA_ROOMS = {97, 98}
SLEEP_TATZELWURM_ROOMS = set(range(100, 105))
SLEEP_LINDWURM_DEATH_ROOM = 109
SLEEP_SKEEVE_BED_ROOM = 62
SLEEP_MAKESHIFT_CAMP_ROOMS = {106, 107, 108}
SLEEP_UNCOMFORTABLE_BUT_SAFE_ROOMS = set(range(92, 97))
SLEEP_STREET_ROBBERY_ROOMS = set(range(70, 89)) - {72}  # Oerli's tavern (72) is its own case

# Ambient "impatience" ticks - confirmed via the master per-turn dispatcher
# (flat 0x64A3-0x6A5F in the `laas` analysis project, called once per turn
# from the real main game loop - see PHASE0_FINDINGS.md UPDATE 40). Foroll
# and Oerli each have their own turn counter that advances only while the
# player stays in their room, firing an increasingly annoyed line if you
# linger without buying/paying. The dispatcher's other room/global events
# (a dragon-cult ambush, a poison-gas cave trap, Gultiba's one-time hooks,
# a Sabrina encounter) are all now confirmed too (UPDATE 40/41/43 - an
# earlier mid-session worry that some of their room numbers were
# unreliable was itself a mistake, corrected in UPDATE 41) but each has
# its own separate remaining gap (an unidentified object, untraced charge
# semantics, a death/game-over outcome) - see UPDATE 42/43 - so only
# these two simplest ones are wired in here.
#
# Simplified from the real mechanic: the original alternates between two
# message variants per stage (via a persistent flag not traced this
# session) and RNG-gates the second stage; this port fires a single fixed
# message once per stage (not repeating), which avoids message spam
# without needing the untraced probability/flavor-alternation details.
ROOM_IMPATIENCE_EVENTS = {
    FOROLL_ROOM: {"warn_at": 5, "kick_at": 10, "warn_msg": 125, "kick_msg": 133},
    72: {"warn_at": 4, "kick_at": 8, "warn_msg": 821, "kick_msg": 823},  # Oerli's Taverne
}

# Day/night clock (see PHASE0_FINDINGS.md UPDATE 43): confirmed 4 exact
# transition points in the real 0-255 wrapping cycle, each with a
# verbatim STORY message. dawn=0 also increments a separate day counter
# in the real game (`GameState.day_count` here).
CLOCK_TRANSITIONS = {
    0: 745,     # "Eben steigt die Sonne über dem Horizont auf...Morgen." (dawn)
    0x46: 687,  # "Die Sonne hat nun den höchsten Punkt...Mittag." (noon)
    0x73: 688,  # "Die Farben werden langsam blasser...dämmert." (dusk)
    0x80: 388,  # "Eben verschwindet die Sonne...Nacht über Laas hereingebrochen." (nightfall)
}

# Two more ambient events from the same master dispatcher (PHASE0_FINDINGS.md
# UPDATE 40/43/44) - now fully confirmed and ported. Both center on object
# 206 (Skarabäus, already confirmed via merchant pricing) and object 182
# (near-certainly its depleted/smashed form - see UPDATE 44 - referenced by
# code only, since its exact typed noun isn't confirmed).
SCARABAEUS_CODE = 206
SCARABAEUS_DEPLETED_CODE = 182

# The Salami race (UPDATE 58, user-reported): a Salami (11) starts in
# room 8 (Speisekammer). Confirmed via two live screenshots: Har (25),
# starting in room 2 (Smirgas Elternhaus) alongside the player, follows
# wordlessly ("Har kommt wortlos zu uns.") when the player walks into
# room 8, and - if the Salami is still there - immediately pockets it
# ("Har steckt die Salami ein, die hier herumlag."). If the player gets
# there first (or by some other route) and takes it themselves, Har's
# event simply finds nothing left to take.
# KNOWN SIMPLIFICATION: only this one specific, confirmed room2->room8
# follow-and-take is modeled - not a general "NPCs follow the player"
# mechanic (no evidence for that beyond this one scene), and not a
# turn-scheduled autonomous walk (no evidence for the exact timing
# beyond "the first few rounds" - modeling it as triggered by the
# player's own move matches both screenshots exactly without guessing
# at an unconfirmed turn threshold).
SALAMI_CODE = 11
SALAMI_ROOM = 8
SALAMI_HOME_ROOM = 2  # Smirgas Elternhaus - Har's confirmed starting room
SALAMI_TAKEN_MESSAGE = "Har steckt die Salami ein, die hier herumlag."
SALAMI_HAR_FOLLOWS_MESSAGE = "Har kommt wortlos zu uns."

# The dragon-cult fanatic ambush (UPDATE 40/43): room 100 (a stone plateau
# below the dragon's cliff, per room_text.py's independently-confirmed
# exit-graph chain), active only in the confirmed time window - deep
# night through just past dawn, never full daylight (UPDATE 43's
# corrected, exhaustively-simulated signed-comparison re-read).
FANATIC_AMBUSH_ROOM = 100
FANATIC_AMBUSH_ACTIVE_CLOCK = set(range(0, 20)) | set(range(149, 256))
FANATIC_AMBUSH_MESSAGE = 1846

# The poison-gas cave trap (UPDATE 40/41/44): rooms 102/103 ("inside the
# cave"/"deeper in the cave" per room_text.py). Confirmed 3-way outcome:
# carrying the depleted Scarabäus (182) is always fatal; otherwise it
# depends on the charge level (`GameState.scarabaeus_charge`, 0-2) and
# whether the near-miss warning already fired once this game
# (`_gas_trap_warned` - the real game's `[0xB732]` one-shot flag).
GAS_TRAP_ROOMS = {102, 103}
GAS_TRAP_DEATH_182_PRESENT = 1362
GAS_TRAP_PROTECTED = 1361
GAS_TRAP_NEAR_MISS = 2275
GAS_TRAP_DEATH_UNPROTECTED = 1845

# Mygra's Scarabäus recharge (PHASE0_FINDINGS.md UPDATE 45): confirmed via
# reference/walkthrough_de.txt - "Den Skarabäus gibt man in Hyllok Mygra und
# wartet einen Tag, bis er repariert ist." The real verb is GIB (give), a
# simple "give X to Y". The 10-turn deadline (`[0xAD5C]+10`) is confirmed;
# the exact hand-back mechanism is NOT (see UPDATE 45) - this port swaps
# the held object back from 182 to 206 once the deadline passes, a
# deliberate, clearly-flagged adaptation that keeps the gas trap (UPDATE
# 44) coherent rather than leaving recharging pointless.
MYGRA_OBJECT_CODE = 35
SCARABAEUS_RECHARGE_TURNS = 10
MYGRA_GIVE_ACCEPT_MESSAGE = (
    "Mygra nimmt den Scarabäus entgegen. 'Er ist sehr verbraucht! "
    "Kommt in ein paar Tagen wieder, dann ist er repariert.'"
)

# Mygra's other confirmed GIB interaction (user-supplied real DOSBox
# screenshot, "lerne_spells.png"): giving her money - "geld" isn't a
# real object (no names.py entry, nothing to resolve via
# objects_carried()), so this is special-cased in give() before its
# normal item/recipient split, matching the screenshot's own single-
# word "gebe geld" (no explicit recipient needed - Mygra is simply
# whoever's there). ANY amount is accepted but only a flat
# MYGRA_SPELL_TEACHING_PRICE (3) is ever taken - "'Nein, gebt mir nicht
# alles. Ich will nur 3 Gerfs.'" - the same "fixed scripted price,
# regardless of amount offered" shape as Foroll's starter-weapon sale
# (FOROLL_WEAPON_PRICE), and confirms this is a ONE-TIME event: she
# teaches "die Zaubersprüche I und II".
#
# SPELL_LEARN_ORDER (PHASE0_FINDINGS.md UPDATE 82, correcting UPDATE
# 81's own initial guess): the original's "Spruch I/II/III/IV/V"
# copy-protection numbering is a SEPARATE fixed sequence from
# `SPELL_PROMPT`'s own combat-menu ordering (LEVI, KUBL, FEBR, UNSI,
# TOPA - independently confirmed via each spell's own `spell_choice`
# dispatch slot, UPDATE 34/36/37/38) - user-confirmed directly (not
# from a screenshot this time, but from their own knowledge of the
# game): Spell I=LEVI, II=FEBR, III=KUBL, IV=UNSI, V=TOPA. Mygra only
# ever teaches I+II (LEVI+FEBR); III-V are confirmed to require a
# separate, entirely unmodeled "Magiergilde" (mage guild) mechanic -
# not implemented here, since nothing beyond this one fact is
# evidenced about it yet. Ported as "LEVI und FEBR" rather than the
# original's own "I"/"II" numbering, same established substitution
# UPDATE 35 already made everywhere else in this port (the real
# "Spruch N" phrasing was 1990s copy protection, not meaningful
# in-universe naming).
#
# KNOWN GAP, deliberately NOT addressed by this change: nothing outside
# this one flag reads `aszhanti_known_spells` - SPELL_PROMPT and actual
# spell-casting (`_resolve_combat_round`) still treat all 5 spells as
# always available, exactly as before. `spells()`'s own long-standing
# "KNOWN GAP" comment already flags that which spells unlock when was
# never confirmed; this event is the first real, confirmed DATA POINT
# for that question, but wiring a full unlock-gated casting system
# throughout the rest of combat is a separate, much larger change this
# pass didn't attempt (it would need a confirmed default starting
# spell-count for a brand-new game too, which isn't evidenced any more
# than `self.money`'s own starting value is - see that field's own
# docstring).
SPELL_LEARN_ORDER = ["LEVI", "FEBR", "KUBL", "UNSI", "TOPA"]
MYGRA_SPELL_TEACHING_PRICE = 3
MYGRA_SPELL_TEACHING_SPELLS = 2  # Spell I+II = LEVI+FEBR (SPELL_LEARN_ORDER)
MYGRA_SPELL_TEACHING_MESSAGE = (
    f"'Nein, gebt mir nicht alles. Ich will nur {MYGRA_SPELL_TEACHING_PRICE} "
    "Gerfs.' sagt Mygra, nimmt sich das Geld und bringt mir dann die "
    "Zaubersprüche LEVI und FEBR bei. Nach kurzer Zeit habe ich sie unter "
    "Kontrolle und bedanke mich bei dem Scharlatan."
)


class GameState:
    def __init__(self, assets_dir: Path = DEFAULT_ASSETS_DIR):
        self.assets_dir = Path(assets_dir)
        self.story = Story.load(assets_dir)
        self.world = World.load(assets_dir)
        self.objects = ObjectTable.load(assets_dir)
        self.item_stats = ItemStats.load(assets_dir)
        self.monster_stats = MonsterStats.load(assets_dir)
        # RESTORE's own saved position - a real, valid mid-game state,
        # used as a starting point until a real "new game" state is
        # identified separately.
        self.current_room = int.from_bytes(self.world.chunks["current_room"], "little")
        self.running = True
        # Runtime object-location overrides, applied on top of world.py's
        # static (RESTORE-loaded) locations - lets TAKE/DROP actually move
        # things without mutating the loaded asset data. Only meaningful
        # for object codes that have a tracked instance in the first
        # place (see World.object_location) - everything else has no
        # location concept at all, in this port or the original game.
        self._location_overrides: dict[int, int] = {}
        # Same idea as `_location_overrides`, but keyed by raw INSTANCE
        # INDEX rather than object code - for the confirmed ambush-
        # eligible creatures that have no object code mapped to them at
        # all (DAY_ROSTER_BY_INSTANCE/NIGHT_ROSTER_BY_INSTANCE_*,
        # PHASE0_FINDINGS.md UPDATE 49/74). See `_instance_location()`/
        # `_move_instance()`.
        self._instance_location_overrides: dict[int, int] = {}
        # Runtime door-state overrides, keyed (room, slot) -> msg_code.
        # Mirrors the original's `sub_EEC0`: mutating one side of a door
        # always mutates the reciprocal slot in the destination room too
        # (see _set_door_state) - a door's state is one fact shared by
        # both rooms it connects, not two independent numbers.
        self._door_state_overrides: dict[tuple[int, int], int] = {}
        # Which party member is currently "narrating" (see characters.py) -
        # selects narrator-dependent room/object text clauses. No in-game
        # character-switch verb is ported yet; defaults to Aszhanti,
        # matching the original's fallback branch (anything != Smirga's
        # constant reads as Aszhanti narrating).
        self.narrator: Character = DEFAULT_NARRATOR
        # The in-game currency is confirmed as "Gerfs" (seg005_batch4.md's
        # resolved merchant dialogue - "ich würde euch %d Gerfs dafür
        # geben"), and word_2B974 is confirmed as the player's money global
        # (used in the real buy-affordability check, sub_E5B2). Its real
        # STARTING value in a fresh game is NOT confirmed anywhere in this
        # project (RESTORE is a mid-game save, not a new-game state, and no
        # "new game" initialization code has been traced) - starting at 0
        # is a deliberate, conservative PORT DEFAULT (not fabricated game
        # data), not a claim about what the real game starts you with.
        # Selling items (a real, confirmed mechanic - see MERCHANTS above)
        # is how a player earns Gerfs to spend from this starting point.
        self.money: int = 0
        # Rooms already entered at least once - gates ROOM_FIRST_VISIT_MESSAGE
        # (room_text.py): a confirmed scripted scene (e.g. Foroll's forge)
        # is shown only the first time, the normal look text every time
        # after. Starts empty (RESTORE's own saved position is treated as
        # "not yet visited" for this purpose, same simplification as
        # current_room defaulting to a mid-game save rather than tracking
        # real play history).
        self._visited_rooms: set[int] = set()
        # Whether the player has already bought the starting dagger+sword
        # bundle from Foroll (see FOROLL_* constants / buy_starter_weapons) -
        # a one-time, hardcoded-price scripted purchase, separate from the
        # generic MERCHANTS shop mechanic.
        self._bought_starter_weapons: bool = False
        # One-time gate for Gultiba's bedroom encounter (room 88, see
        # GULTIBA_* constants) - only one of its two confirmed
        # resolutions (attack the lover, or let him go) can ever fire.
        self._gultiba_bedroom_resolved: bool = False
        # How many of the 5 real spells, in SPELL_LEARN_ORDER (the
        # confirmed "Spell I-V" progression order - PHASE0_FINDINGS.md
        # UPDATE 82), Aszhanti currently knows - see
        # MYGRA_SPELL_TEACHING_* / give()'s "geld" special case. 0 is
        # this port's own starting default (same unconfirmed-but-
        # conservative status as `self.money` defaulting to 0 - see
        # that field's own docstring), not a claim about what a
        # brand-new real game starts you with.
        self.aszhanti_known_spells: int = 0
        # Per-room "impatience" turn counters (see ROOM_IMPATIENCE_EVENTS) -
        # {room: turns spent there} and {room: set of thresholds already
        # fired}, so each stage fires exactly once rather than repeating.
        self._room_impatience_turns: dict[int, int] = {}
        self._room_impatience_fired: dict[int, set[int]] = {}
        # Day/night clock (see CLOCK_TRANSITIONS, PHASE0_FINDINGS.md
        # UPDATE 43): a confirmed 0-255 wrapping counter, advancing once
        # every TWO turns (gated on a master turn counter's low bit in
        # the real game - `self._turn_counter` here). `day_count`
        # increments each time the clock wraps back to 0 - tracked
        # faithfully but not surfaced anywhere yet (not shown on the
        # confirmed status screen layout either). Starting value isn't
        # confirmed from any real save/screenshot - defaults to 0 (dawn),
        # documented as a simplification like the hunger/durst defaults.
        self._turn_counter: int = 0
        self.time_of_day: int = 0
        self.day_count: int = 1
        # Scarabäus charge level (see SCARABAEUS_* constants, PHASE0_
        # FINDINGS.md UPDATE 44/45): 0 = never charged, 1 = recharging in
        # progress (via `give()` to Mygra), 2 = fully charged. Starts at
        # 0 (the confirmed static default). `_gas_trap_warned` is the
        # one-shot "already had a near miss" latch (`[0xB732]` in the
        # real game). `_scarabaeus_recharge_deadline` is the confirmed
        # `[0xAD5C]+10` turn-counter deadline, set when handed to Mygra.
        self.scarabaeus_charge: int = 0
        self._gas_trap_warned: bool = False
        self._scarabaeus_recharge_deadline: int | None = None
        # The farmer's harvest-help quest (see FARMER_* constants,
        # PHASE0_FINDINGS.md UPDATE 68): 0 = unresolved, 1 = succeeded,
        # 2 = failed (storm already hit) - confirmed real state machine
        # (`word_b66c`). `_farmer_storm_turns` is the confirmed per-turn
        # countdown (`word_b66e`) that forces state 2 once it reaches
        # `FARMER_QUEST_STORM_TURNS`.
        self._farmer_quest_state: int = 0
        self._farmer_storm_turns: int = 0
        # The Tuatara bounty/diplomacy quest (see TUATARA_* constants,
        # PHASE0_FINDINGS.md UPDATE 69): 0 = not yet encountered, 3 =
        # arrived at the lake and encountered Tuatara, 4 = killed it,
        # 5 = successfully talked it into helping - matches the real
        # game's own `word_b678` values (1/2 are collapsed into the
        # single `frage()` interaction, see that constant's docstring).
        # `_tuatara_greeted` gates `bitte()` on `gruesse()` having
        # already happened, matching the confirmed real dialogue order.
        self._tuatara_quest_stage: int = 0
        self._tuatara_greeted: bool = False
        # Phadraig's raw default location (999) isn't a real room - he's
        # never independently placed anywhere in the raw data, so this
        # port places him at the tavern (see TUATARA_TAVERN_ROOM) where
        # the confirmed quest-offer dialogue happens.
        self._move_object(PHADRAIG_CODE, TUATARA_TAVERN_ROOM)
        # Potidan's Mondscheinkraut quest (see POTIDAN_* constants,
        # PHASE0_FINDINGS.md UPDATE 70): 0 = not yet asked, 1 = asked/
        # offered (collapsed from the real game's 2/3), 2 = turned in.
        self._potidan_quest_stage: int = 0
        # The character-sheet title-progression tracks from levels.py -
        # see PHASE0_FINDINGS.md UPDATE 23 (and its "Correction, same
        # session" addendum, which fixed two real bugs in this feature's
        # first draft using a real DOSBox screenshot of the actual
        # fresh-game screen) for the confirmed thresholds and column
        # ownership. This port has no combat/time-passage simulation
        # (see this module's docstring), so nothing increments or
        # decrements these; `status()` just reads whatever's here.
        #
        # Strength/Ansehen/Aszhanti's Astral start at 0, CONFIRMED
        # correct by the real screenshot (0 genuinely falls through each
        # ladder's first bracket - "Milchbubi"/"Niemand"/"Scharlatan").
        # Smirga's Astral has no field at all - it's a fixed constant
        # (levels.SMIRGA_ASTRAL_TITLE), never computed from a stat.
        self.aszhanti_strength: int = 0
        self.smirga_strength: int = 0
        self.aszhanti_astral: int = 0
        self.ansehen: int = 0
        # Gesundheit (HP): confirmed starting value from the real
        # screenshot - both characters start at 20.
        self.aszhanti_health: int = 20
        self.smirga_health: int = 20
        # MAX hp - a separate, hidden pair of globals (word_b6b4/b6b2),
        # never shown directly on the status screen itself but confirmed
        # via a second screenshot + tracing the kill-handler and the
        # healing/clamp utility that reads them (see PHASE0_FINDINGS.md
        # UPDATE 23's second correction). A won fight grants +1 MAX hp to
        # BOTH party members (regardless of who fought - same pattern as
        # the Strength gain), but does NOT touch current hp - only
        # healing (confirmed: eating) does that, clamped to this max.
        # +1 to both on every kill, applied by attack() below. No EAT
        # verb exists yet to apply healing up to this max (no food
        # object has a confirmed code) - current hp only goes down
        # (combat) for now, never back up. Fresh game: current == max.
        self.aszhanti_max_health: int = 20
        self.smirga_max_health: int = 20
        # Equipped armor (object codes, or None) - confirmed items are
        # Lederwams/264, Echsenpanzer/196, Kettenhemd/52 (see names.py,
        # combat.py's ARMOR_CLASS) - see equip().
        self.aszhanti_armor: int | None = None
        self.smirga_armor: int | None = None
        # Ongoing melee fight state (combat.py's resolve_round(), see
        # its own docstring for the confirmed formula and this port's
        # deliberate simplifications - no real spell effects, no real
        # weapon modifiers, even though both are now PROMPTED FOR - see
        # the "combat" section below). None when no fight is in
        # progress. `_combat_instance_idx` is the PRIMARY "are we
        # fighting" signal (0-38, see world.py's ObjectInstance.index) -
        # ALWAYS set while a fight is on, whether or not the monster has
        # a mapped object code (see UPDATE 74: the confirmed real
        # ambush scanner works by raw instance index, not object code,
        # and roughly a third of real eligible creatures have no
        # object code mapped at all). `_combat_monster_code` is that
        # object code WHEN one exists (None otherwise - used for
        # naming and the quest-specific kill hooks below, never as the
        # "are we fighting" check - use `_combat_instance_idx` for
        # that). `_combat_monster_hp` is remaining hp this fight
        # (starts at the object's own instance-record hp). `_combat_
        # awaiting` is which prompt is currently pending - None,
        # "weapon", or "spell" - confirmed via real screenshots and
        # direct user correction: the real game asks "Welche Waffe...?"
        # then "Welchen Zauber...?" BEFORE resolving each round,
        # automatically re-asking for the next round's weapon
        # immediately if the fight continues - not a separate
        # "attackiere" command each round (this port's first draft got
        # that wrong).
        self._combat_instance_idx: int | None = None
        self._combat_monster_code: int | None = None
        self._combat_monster_hp: int | None = None
        self._combat_awaiting: str | None = None
        # BILD (F6/Entf picture viewer, see bild()) - set while awaiting
        # the player's typed picture number, same bypass-normal-parsing
        # pattern as `_combat_awaiting`.
        self._awaiting_picture_number: bool = False
        # The automatic per-room picture trigger (see ROOM_PICTURE_TABLE,
        # PHASE0_FINDINGS.md UPDATE 72): 0 means "none shown yet",
        # matching the real game's own `word_b736` starting at 0 -
        # since no real picture number is ever 0, this correctly lets
        # the very first picture-having room (including the starting
        # room itself) fire immediately.
        self._last_shown_picture: int = 0
        # Hunger (party-wide) / Durst (per character): the screenshot
        # confirms both start in their best/highest bracket ("Satt" /
        # "Kein Durst" for both), but only the qualitative state is
        # confirmed, not the exact starting number - these are ticking
        # countdown timers (high = fine, low = critical) whose real
        # starting values and decay rate haven't been traced. The
        # numbers below are PORT DEFAULTS chosen only to land solidly
        # inside the confirmed "everything's fine" bracket (>100 for
        # Hunger, >60 for Durst) - not claimed as real game data.
        self.hunger: int = 200
        self.aszhanti_durst: int = 100
        self.smirga_durst: int = 100

        self._check_room_picture()

    # --- location tracking (mutable on top of world.py's static data) ---

    def object_location(self, code: int) -> int | None:
        if code in self._location_overrides:
            return self._location_overrides[code]
        loc = self.world.object_location(code)
        if loc is None or loc == LIMBO_CARRIED:
            return loc
        flag = self.world.flags[code] if code < len(self.world.flags) else None
        if flag is not None and not flag.has_instance:
            # CORRECTED TWICE OVER (UPDATE 59, then this pass): UPDATE
            # 58 found a non-instance object's raw flags word CAN be a
            # real room number - confirmed for Salami. UPDATE 59 found
            # that's false for objects with a real merchant price
            # (user-reported, with a screenshot: no Schild in room 10
            # despite its raw value reading like one) - a shop item's
            # not-yet-bought raw value is some other kind of reference.
            # Checking further (user-reported again: no known pickable
            # object in room 67 despite one now showing, object 38)
            # found the problem is bigger than just priced items: doing
            # this for EVERY non-instance code surfaces roughly ONE such
            # "object" in nearly every one of the 109 rooms -
            # overwhelmingly more consistent with some other general
            # per-room engine structure (unidentified; possibly related
            # to the same kind of generic per-room table already seen
            # elsewhere in this project, e.g. WORLD's own per-room
            # tables) than with ~100 forgotten takeable items,
            # especially since real gameplay has only ever confirmed
            # ONE of them as an actual pickup (Salami) and explicitly
            # disproved another (Schild, despite being a real, named,
            # priced item). So: only trust this raw "location" when the
            # object is BOTH independently confirmed real in `names.py`
            # AND has no merchant price (`item_stats.buy_price() == 0`)
            # - currently just Salami/11 - everything else (unnamed
            # filler objects, and named-but-priced shop items alike)
            # stays unplaced rather than guessed at.
            if code not in OBJECT_NAMES or self.item_stats.buy_price(code) > 0:
                return None
        return loc

    def _all_trackable_codes(self):
        """Every object code this port can report a location for: the
        250 codes `world.py`'s flags/instance system covers, PLUS any
        code that only ever got a location via `_location_overrides`
        (e.g. Lederwams/264 - a real, confirmed object code (see
        names.py) that exceeds `FLAG_COUNT`=250 and so can never be
        found via `object_location`'s flags lookup alone; a real bug
        this fixes, found while adding the EQUIP verb - Lederwams
        could be bought and "carried" internally but would silently
        never show up in `objects_carried()`)."""
        return set(range(len(self.world.flags))) | set(self._location_overrides)

    def objects_in_room(self, room_number: int) -> list[int]:
        return [
            code
            for code in self._all_trackable_codes()
            if self.object_location(code) == room_number
        ]

    def objects_carried(self) -> list[int]:
        return [
            code
            for code in self._all_trackable_codes()
            if self.object_location(code) == LIMBO_CARRIED
        ]

    def _move_object(self, code: int, dest_room: int):
        self._location_overrides[code] = dest_room

    def _object_code_for_instance(self, instance_idx: int) -> int | None:
        """Reverse lookup of `ObjectFlags.instance_index` - most
        instances have exactly one object code pointing to them; the
        confirmed ambush-eligible creatures with no object code at all
        (see DAY_ROSTER_BY_INSTANCE etc., UPDATE 74) return None."""
        for code in range(len(self.world.flags)):
            flag = self.world.flags[code]
            if flag.has_instance and flag.instance_index == instance_idx:
                return code
        return None

    def _instance_location(self, instance_idx: int) -> int:
        """An instance's current room by INDEX rather than object code -
        works for every instance regardless of whether one is mapped
        (delegates to `object_location()` when it is, so the two stay
        consistent; falls back to `_instance_location_overrides`/the
        raw static default otherwise)."""
        code = self._object_code_for_instance(instance_idx)
        if code is not None:
            return self.object_location(code)
        return self._instance_location_overrides.get(
            instance_idx, self.world.instances[instance_idx].location
        )

    def _move_instance(self, instance_idx: int, dest_room: int) -> None:
        self._instance_location_overrides[instance_idx] = dest_room

    # --- save/load ---
    #
    # Not a port of the original's save format - RESTORE's own 18200-byte
    # layout mixes truly static data (the object description table, the
    # exit table's base layout, etc.) with the small amount of state that
    # actually changes during play, and reconstructing the former from
    # scratch would gain nothing (this port always loads the real RESTORE
    # for the static half anyway). Instead, a save here is just this
    # port's own mutable state - current room, which party member is
    # narrating, and the two runtime override dicts (object locations,
    # door states) - as JSON. Loading replays those overrides on top of
    # a freshly-loaded World/Story/ObjectTable, same as __init__ does for
    # the RESTORE-provided starting state.

    def save(self, path: Path) -> str:
        data = {
            "current_room": self.current_room,
            "narrator": int(self.narrator),
            "location_overrides": {str(k): v for k, v in self._location_overrides.items()},
            "instance_location_overrides": {
                str(k): v for k, v in self._instance_location_overrides.items()
            },
            "door_state_overrides": [
                [room, slot, code] for (room, slot), code in self._door_state_overrides.items()
            ],
            "money": self.money,
            "visited_rooms": sorted(self._visited_rooms),
            "bought_starter_weapons": self._bought_starter_weapons,
            "gultiba_bedroom_resolved": self._gultiba_bedroom_resolved,
            "aszhanti_known_spells": self.aszhanti_known_spells,
            "aszhanti_strength": self.aszhanti_strength,
            "smirga_strength": self.smirga_strength,
            "aszhanti_astral": self.aszhanti_astral,
            "ansehen": self.ansehen,
            "aszhanti_health": self.aszhanti_health,
            "smirga_health": self.smirga_health,
            "aszhanti_max_health": self.aszhanti_max_health,
            "smirga_max_health": self.smirga_max_health,
            "hunger": self.hunger,
            "aszhanti_durst": self.aszhanti_durst,
            "smirga_durst": self.smirga_durst,
            "aszhanti_armor": self.aszhanti_armor,
            "smirga_armor": self.smirga_armor,
            "combat_instance_idx": self._combat_instance_idx,
            "combat_monster_code": self._combat_monster_code,
            "combat_monster_hp": self._combat_monster_hp,
            "combat_awaiting": self._combat_awaiting,
            "awaiting_picture_number": self._awaiting_picture_number,
            "last_shown_picture": self._last_shown_picture,
            "room_impatience_turns": self._room_impatience_turns,
            "room_impatience_fired": {
                str(k): sorted(v) for k, v in self._room_impatience_fired.items()
            },
            "turn_counter": self._turn_counter,
            "time_of_day": self.time_of_day,
            "day_count": self.day_count,
            "scarabaeus_charge": self.scarabaeus_charge,
            "gas_trap_warned": self._gas_trap_warned,
            "scarabaeus_recharge_deadline": self._scarabaeus_recharge_deadline,
            "farmer_quest_state": self._farmer_quest_state,
            "farmer_storm_turns": self._farmer_storm_turns,
            "tuatara_quest_stage": self._tuatara_quest_stage,
            "tuatara_greeted": self._tuatara_greeted,
            "potidan_quest_stage": self._potidan_quest_stage,
        }
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return f"Spiel gespeichert ({path})."

    def load_save(self, path: Path) -> str:
        data = json.loads(path.read_text(encoding="utf-8"))
        self.current_room = data["current_room"]
        self.narrator = Character(data["narrator"])
        self._location_overrides = {int(k): v for k, v in data["location_overrides"].items()}
        self._instance_location_overrides = {
            int(k): v for k, v in data.get("instance_location_overrides", {}).items()
        }
        self._door_state_overrides = {
            (room, slot): code for room, slot, code in data["door_state_overrides"]
        }
        self.money = data.get("money", 0)
        self._visited_rooms = set(data.get("visited_rooms", []))
        self._bought_starter_weapons = data.get("bought_starter_weapons", False)
        self._gultiba_bedroom_resolved = data.get("gultiba_bedroom_resolved", False)
        self.aszhanti_known_spells = data.get("aszhanti_known_spells", 0)
        self.aszhanti_strength = data.get("aszhanti_strength", 0)
        self.smirga_strength = data.get("smirga_strength", 0)
        self.aszhanti_astral = data.get("aszhanti_astral", 0)
        self.ansehen = data.get("ansehen", 0)
        self.aszhanti_health = data.get("aszhanti_health", 20)
        self.smirga_health = data.get("smirga_health", 20)
        self.aszhanti_max_health = data.get("aszhanti_max_health", 20)
        self.smirga_max_health = data.get("smirga_max_health", 20)
        self.hunger = data.get("hunger", 200)
        self.aszhanti_durst = data.get("aszhanti_durst", 100)
        self.smirga_durst = data.get("smirga_durst", 100)
        self.aszhanti_armor = data.get("aszhanti_armor")
        self.smirga_armor = data.get("smirga_armor")
        self._combat_instance_idx = data.get("combat_instance_idx")
        self._combat_monster_code = data.get("combat_monster_code")
        if self._combat_instance_idx is None and self._combat_monster_code is not None:
            # Pre-UPDATE-74 save - back-fill from the object code (every
            # fight startable via attack()/typed noun always has one).
            self._combat_instance_idx = self.world.flags[self._combat_monster_code].instance_index
        self._combat_monster_hp = data.get("combat_monster_hp")
        self._combat_awaiting = data.get("combat_awaiting")
        self._awaiting_picture_number = data.get("awaiting_picture_number", False)
        self._last_shown_picture = data.get("last_shown_picture", 0)
        self._room_impatience_turns = {
            int(k): v for k, v in data.get("room_impatience_turns", {}).items()
        }
        self._room_impatience_fired = {
            int(k): set(v) for k, v in data.get("room_impatience_fired", {}).items()
        }
        self._turn_counter = data.get("turn_counter", 0)
        self.time_of_day = data.get("time_of_day", 0)
        self.day_count = data.get("day_count", 1)
        self.scarabaeus_charge = data.get("scarabaeus_charge", 0)
        self._gas_trap_warned = data.get("gas_trap_warned", False)
        self._scarabaeus_recharge_deadline = data.get("scarabaeus_recharge_deadline")
        self._farmer_quest_state = data.get("farmer_quest_state", 0)
        self._farmer_storm_turns = data.get("farmer_storm_turns", 0)
        self._tuatara_quest_stage = data.get("tuatara_quest_stage", 0)
        self._tuatara_greeted = data.get("tuatara_greeted", False)
        self._potidan_quest_stage = data.get("potidan_quest_stage", 0)
        return f"Spielstand geladen ({path})."

    # --- noun resolution ---

    def _resolve_noun(self, noun: str, candidate_codes: list[int]) -> int | None:
        """Resolve a typed noun to an object code among `candidate_codes`
        - either a known name (names.py) or an explicit numeric code
        (e.g. "35" or "#35"), regardless of whether that code is
        actually a candidate (numeric references always ignore
        candidate-list filtering, since the caller still checks
        presence/location afterwards)."""
        stripped = noun.strip().lstrip("#")
        if stripped.isdigit():
            return int(stripped)
        return resolve_name(noun, candidate_codes)

    # --- verbs ---

    def exits(self) -> str:
        """The real game's "F2" exit listing - see EXIT_DIRECTION_WORDS'
        docstring for the confirmed message template and join rule.
        KNOWN GAP: room 2 (Smirgas Elternhaus) has a confirmed real
        Westen exit that isn't in this port's room graph at all - its
        raw exit-table slot reads `dest_room=0`, previously assumed to
        always mean "no exit" (see world.py's `Exit.usable`), but that
        assumption is now known to be wrong at least here. The true
        destination isn't confirmed yet, so it's not added and won't
        appear in this list until it is - not guessed at.
        KNOWN SIMPLIFICATION: the join for exactly 2 exits isn't
        independently confirmed by any real example (both confirmed
        cases have 4 and 5) - this uses the same comma+"und" convention
        already established for `_who_is_here_line()`, the natural
        extrapolation of the n=1 case, not a wild guess. The zero-exits
        message below is a PORT UTILITY, not confirmed real text (no
        example of a genuinely exit-less room's F2 output exists yet -
        room 28 is the one known candidate, a special-action-only room)."""
        exits = self.world.room(self.current_room).available_exits()
        if not exits:
            return "Ich kann hier nirgendwo hingehen."
        phrases = [_exit_phrase(self.current_room, d) for d in exits]
        joined = phrases[0] if len(phrases) == 1 else ", ".join(phrases[:-1]) + " und " + phrases[-1]
        return f"Unmittelbare Ausgänge führen {joined}."

    def look(self) -> str:
        room = self.world.room(self.current_room)
        title = room_title(self.current_room)
        header = f"[Raum {self.current_room}: {title}]" if title else f"[Raum {self.current_room}]"
        lines = [header]
        first_visit = self.current_room not in self._visited_rooms
        self._visited_rooms.add(self.current_room)
        text = None
        if first_visit:
            text = first_visit_text(self.story, self.current_room, self.narrator)
        if text is None:
            text = look_text(self.story, self.current_room, self.narrator)
        if (
            text is not None
            and self.current_room == SALAMI_ROOM
            and self.object_location(SALAMI_CODE) != SALAMI_ROOM
        ):
            # Confirmed via a user-supplied screenshot: once the Salami
            # is gone (taken by Har or the player), room 8's standing
            # text drops the "Eine große Salami hängt..." sentence
            # entirely rather than swapping in different wording.
            salami_sentence = self.story.message(184)
            text = text.replace(f" {salami_sentence}", "").replace(salami_sentence, "")
        if text is not None and self.current_room == FARMER_ROOM and self._farmer_quest_state != 0:
            # Confirmed via the disassembly (UPDATE 68): room 20's own
            # standing text switches entirely - message 345 once the
            # harvest-help quest succeeds ("...an einem geernteten
            # Kornfeld..."), message 346 once the storm destroys the
            # crop instead ("...zerschlagenen Kornfeld...") - unlike
            # the Salami case, this replaces the WHOLE text, not one
            # sentence within it.
            text = self.story.message(345 if self._farmer_quest_state == 1 else 346)
        if text is not None:
            lines.append(text)
        else:
            lines.append("(Raumbeschreibung noch nicht bekannt)")
        objs = self.objects_in_room(self.current_room)
        people = [o for o in objs if self.world.flags[o].has_instance]
        items = [o for o in objs if not self.world.flags[o].has_instance]
        if people:
            lines.append(self._who_is_here_line(people))
        if items:
            lines.append("Objekte hier: " + ", ".join(self._object_display_name(o) for o in items))
        exits = room.available_exits()
        if exits:
            lines.append("Ausgänge: " + ", ".join(sorted(exits.keys())))
        else:
            lines.append("(keine bekannten Ausgänge)")
        return "\n".join(lines)

    def character(self, noun: str | None) -> str:
        """PORT UTILITY, not a reconstructed original verb - see
        characters.py's module docstring and parser.py's VERB_ALIASES
        comment: no in-game command for this was found anywhere in the
        disassembly (the real flag, word_b722, gets set somewhere this
        project hasn't traced - most likely by scripted story events,
        not a player-typed command). This exists only so a player or
        tester can view both narrator text variants on demand; bare
        `charakter`/`wechsel` toggles, `charakter smirga`/`charakter
        aszhanti` picks one directly."""
        if noun:
            word = noun.strip().lower()
            if word == "smirga":
                self.narrator = Character.SMIRGA
            elif word == "aszhanti":
                self.narrator = Character.ASZHANTI
            else:
                return f"Unbekannter Charakter: {noun} (bekannt: smirga, aszhanti)"
        else:
            self.narrator = (
                Character.SMIRGA if self.narrator == Character.ASZHANTI else Character.ASZHANTI
            )
        name = "Smirga" if self.narrator == Character.SMIRGA else "Aszhanti"
        return f"Du erzählst nun als {name}."

    def go(self, direction: str, rng=random) -> str:
        direction = direction.upper()
        room = self.world.room(self.current_room)
        exits = room.available_exits()
        if direction not in exits:
            return "Dort kann ich nicht hingehen."
        origin_room = self.current_room
        self.current_room = exits[direction].dest_room
        har_follows_for_salami = (
            origin_room == SALAMI_HOME_ROOM
            and self.current_room == SALAMI_ROOM
            and self.object_location(25) == SALAMI_HOME_ROOM
        )
        if har_follows_for_salami:
            self._move_object(25, SALAMI_ROOM)
        result = self.look()
        if har_follows_for_salami:
            result = f"{SALAMI_HAR_FOLLOWS_MESSAGE}\n{result}"
            if self.object_location(SALAMI_CODE) == SALAMI_ROOM:
                self._move_object(SALAMI_CODE, LIMBO_REMOVED)
                result = f"{result}\n{SALAMI_TAKEN_MESSAGE}"
        ambush = self._check_ambush(rng=rng)
        if ambush:
            result = f"{result}\n{ambush}"
        return result

    def examine(self, noun: str) -> str:
        """EXAMINE (confirmed real verb code 0x32). Gultiba's bedroom
        (room 88) special-cases its 4 scripted fixtures ahead of the
        generic path below - they're pure scenery, not really "in" the
        room via `objects_in_room()` (none are instance-tracked or
        location-tracked at all), so the generic candidate list would
        never find them (see GULTIBA_BEDROOM_EXAMINE, UPDATE 87)."""
        if self.current_room == GULTIBA_BEDROOM_ROOM:
            fixture_code = self._resolve_noun(noun, list(GULTIBA_BEDROOM_EXAMINE))
            if fixture_code in GULTIBA_BEDROOM_EXAMINE:
                return self.story.message(GULTIBA_BEDROOM_EXAMINE[fixture_code])
        candidates = self.objects_in_room(self.current_room) + self.objects_carried()
        code = self._resolve_noun(noun, candidates)
        if code is None:
            return "Das sehe ich hier nicht."
        loc = self.object_location(code)
        present_here = loc == self.current_room or loc == LIMBO_CARRIED
        text = self.objects.describe(code, self.story)
        if not present_here:
            return f"(nicht hier, aber laut Datenbank: {text})"
        price = self.item_stats.buy_price(code)
        if price:
            text = f"{text} (Preis: {price} Gerfs)"
        return text

    def take(self, noun: str) -> str:
        candidates = self.objects_in_room(self.current_room)
        code = self._resolve_noun(noun, candidates)
        if code is None:
            return "Das sehe ich hier nicht."
        if self.object_location(code) != self.current_room:
            return "Das ist hier nicht zu finden."
        self._move_object(code, LIMBO_CARRIED)
        return "Genommen."

    def drop(self, noun: str) -> str:
        candidates = self.objects_carried()
        code = self._resolve_noun(noun, candidates)
        if code is None:
            return "Das trage ich nicht bei mir."
        if self.object_location(code) != LIMBO_CARRIED:
            return "Das trage ich nicht bei mir."
        self._move_object(code, self.current_room)
        return "Abgelegt."

    def _worn_armor_line(self, armor_code: int | None, equipped_msg_index: int, default_msg_index: int) -> str:
        """One line of the confirmed real "F4 Inventory" screen (UPDATE
        63) reporting a character's worn armor - STORY message
        `default_msg_index` ("Smirga/Aszhanti trägt normale Kleidung.")
        when nothing is equipped, confirmed exactly via a user-supplied
        screenshot of a fresh game. When real armor IS equipped, uses
        the confirmed companion message ("Smirga/Aszhanti hat %s %s
        an.") with the item's name substituted - the exact indefinite
        article for each of the 3 confirmed armor codes is ordinary
        German grammar (Kettenhemd/Lederwams neuter -> "ein",
        Echsenpanzer masculine -> "einen"), NOT independently verified
        against a screenshot the way the "normale Kleidung" default is."""
        if armor_code is None:
            return self.story.message(default_msg_index)
        article = self.ARMOR_WEAR_ARTICLE.get(armor_code, "ein")
        name = self._object_display_name(armor_code)
        return self.story.message(equipped_msg_index) % (article, name)

    def inventory(self) -> str:
        """Confirmed real "F4 Inventory" screen (UPDATE 63, user-
        supplied screenshot): STORY message 121 ("Leider haben wir
        nichts.") when empty - exact match - followed by a blank line
        and each character's worn-armor line (see
        `_worn_armor_line()`). KNOWN SIMPLIFICATION: the non-empty case
        uses confirmed message 120 ("Wir haben ") as a prefix (also
        real, found right next to message 121), but the multi-item join
        itself isn't independently confirmed by any real example - uses
        the same comma+"und" convention already established elsewhere
        in this port (`_who_is_here_line()`), not a wild guess."""
        carried = self.objects_carried()
        if not carried:
            items_line = self.story.message(121)
        else:
            names = [self._object_display_name(o) for o in carried]
            joined = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " und " + names[-1]
            items_line = f"{self.story.message(120)}{joined}."
        smirga_line = self._worn_armor_line(self.smirga_armor, 1878, 1884)
        aszhanti_line = self._worn_armor_line(self.aszhanti_armor, 1879, 1885)
        return f"{items_line}\n\n{smirga_line}\n{aszhanti_line}"

    # --- SLEEP (SCHLAFEN) - confirmed real room-by-room mechanic, see
    # SLEEP_* constants above and PHASE0_FINDINGS.md UPDATE 50 ---

    def sleep(self) -> str:
        """Confirmed `sub_10792` (see the SLEEP_* constants' docstring).
        Night-only; room 72 (Oerli's tavern) has its own always-available
        scripted event in the real game (arming a "dragon threat" timer
        this port has no model for at all - a separate, real prerequisite,
        not guessed around) - simplified here to the same daytime gate as
        everywhere else rather than silently doing nothing."""
        room = self.current_room
        if self.time_of_day < 0x80:
            return self.story.message(SLEEP_MSG_DAYTIME_REFUSAL)

        lines = []
        if room in SLEEP_OWN_BEDROOM_ROOMS:
            lines.append(self.story.message(SLEEP_MSG_OWN_BEDROOM))
        elif room in SLEEP_HYLLOK_OWN_BED_ROOMS:
            lines.append(self.story.message(SLEEP_MSG_HYLLOK_OWN_BED))
        elif room == SLEEP_BRIDGE_TROLL_ROOM:
            lines.append(self.story.message(SLEEP_MSG_BRIDGE_TROLL))
        elif room in SLEEP_FOREST_MOSS_ROOMS:
            lines.append(self.story.message(SLEEP_MSG_FOREST_MOSS))
        elif room == SLEEP_CAVE_SUGGEST_ROOM:
            lines.append(self.story.message(SLEEP_MSG_CAVE_SUGGEST))
        elif room in SLEEP_KICKOUT_MESSAGES:
            lines.append(self.story.message(SLEEP_KICKOUT_MESSAGES[room]))
        elif room in SLEEP_SABRINA_ROOMS:
            # KNOWN SIMPLIFICATION: the confirmed text is a vivid "turned
            # into a frog" nightmare scene with no further described
            # mechanical consequence (no stat/state change confirmed) -
            # ported as flavor text only.
            lines.append(self.story.message(SLEEP_MSG_SABRINA_NIGHTMARE))
        elif room in SLEEP_TATZELWURM_ROOMS:
            lines.append(self.story.message(SLEEP_MSG_TATZELWURM_BITE))
        elif room == SLEEP_LINDWURM_DEATH_ROOM:
            lines.append(self.story.message(SLEEP_MSG_LINDWURM_DEATH))
            self.aszhanti_health = 0
            self.smirga_health = 0
            self._check_player_death(lines)
            return "\n".join(lines)
        elif room == SLEEP_SKEEVE_BED_ROOM:
            lines.append(self.story.message(SLEEP_MSG_SKEEVE_BED))
        elif room in SLEEP_MAKESHIFT_CAMP_ROOMS:
            lines.append(self.story.message(SLEEP_MSG_MAKESHIFT_CAMP))
        elif room in SLEEP_UNCOMFORTABLE_BUT_SAFE_ROOMS:
            lines.append(self.story.message(SLEEP_MSG_UNCOMFORTABLE_BUT_SAFE))
        elif room in SLEEP_STREET_ROBBERY_ROOMS:
            lines.append(self.story.message(SLEEP_MSG_STREET_ROBBERY))
            self.money = 0
        else:
            lines.append(self.story.message(SLEEP_MSG_DEFAULT_MANAGE))
        lines.append(self.story.message(SLEEP_MSG_WAKE_UP))
        return "\n".join(lines)

    # --- status screen (levels.py's title tracks - see PHASE0_FINDINGS.md
    # UPDATE 23; matches the original's own "Zustandsübersicht" menu item,
    # STORY message 1456) ---

    def spells(self) -> str:
        """Confirmed real "F5 Zaubersprüche" screen (UPDATE 64, user-
        supplied screenshot): STORY message 1460 (title) + message 322
        (header, keeping its own confirmed embedded line break between
        the two sentences) + message 655 (the confirmed "can't cast
        anything yet" fallback) - exact match to the screenshot.

        KNOWN GAP: the screen's OTHER state - an actual list of known
        spell names once Aszhanti's astral level rises above
        "Scharlatan" - has never been seen in any screenshot and isn't
        modeled here. The 5 real spell names (LEVI/KUBL/FEBR/UNSI/TOPA,
        already confirmed via combat.py's `SPELL_PROMPT`) exist, but
        which ones unlock at which astral level isn't confirmed, so
        nothing is guessed at - this always shows the confirmed
        "nothing yet" text regardless of `aszhanti_astral` until that
        gap is filled with real evidence."""
        lines = [
            self.story.message(1460),
            "",
            self.story.message(322).rstrip("\n"),
            "",
            self.story.message(655),
        ]
        return "\n".join(lines)

    def bild(self, noun: str | None) -> str:
        """BILD (picture) - the real game's "F6"/Entf illustration
        viewer, confirmed via its "What Picture ?" debug prompt (flat
        `0x4b11` - PHASE0_FINDINGS.md UPDATE 71): types a number 1-22
        and shows the matching LAASPIC/Pn file, decoded fresh from the
        original compressed file every time (see pictures.py). The real
        prompt string was in English ("What Picture ? ", clearly a
        leftover dev/debug string never translated for players, unlike
        every other player-facing string in this game) - adapted to
        German here for consistency; "Illegale Bild Nr.!" for an
        out-of-range number IS the real confirmed text.

        KNOWN GAP: the real game ALSO shows illustrations automatically
        per-room (a separate mechanism, `word_ad62`'s room->picture
        table) - that table is loaded at runtime from WORLD and wasn't
        traced, so only this manual picker is ported, not the automatic
        one."""
        if noun is None:
            self._awaiting_picture_number = True
            return "Welches Bild? (1-22)"
        return self._show_picture_number(noun)

    def _show_picture_number(self, raw: str) -> str:
        text = raw.strip()
        if not text.isdigit() or not 1 <= int(text) <= pictures.PICTURE_COUNT:
            self._awaiting_picture_number = True
            return "Illegale Bild Nr.!"
        self._awaiting_picture_number = False
        pictures.show_picture(self.assets_dir, int(text))
        return f"[Bild {text}]"

    def _check_room_picture(self) -> str | None:
        """Confirmed real automatic trigger (flat `0x7e3c`/`0x7e79`,
        PHASE0_FINDINGS.md UPDATE 72): the main loop calls this every
        single turn, not just on movement - but it's a no-op unless the
        current room's picture (ROOM_PICTURE_TABLE) differs from the
        last one shown, so in practice it only fires once per distinct
        picture-having room actually visited (matching the confirmed
        real `word_b736` "last shown" tracker). Called once at
        `GameState.__init__` too, matching the real main loop calling
        it as part of its own startup before any player command - the
        confirmed real starting room (67) has a picture, so the real
        game shows one immediately, unprompted, before you type
        anything."""

        picture = ROOM_PICTURE_TABLE.get(self.current_room)
        if picture is None or picture == self._last_shown_picture:
            return None
        self._last_shown_picture = picture
        if SHOW_PICTURES:
            pictures.show_picture(self.assets_dir, picture)
        return f"[Bild {picture}]"

    def debug_info(self) -> str:
        """DEBUG (F7) - a PORT UTILITY, not a reproduction of any real
        game screen: dumps the internal counters and calculations
        behind this port's own mechanics, in particular the confirmed
        ambush roll (PHASE0_FINDINGS.md UPDATE 30, corrected UPDATE
        48/49: 1d6 per eligible candidate, ambush on a roll >3, first
        candidate to succeed wins - see `_check_ambush()`). The
        candidate list/probability shown here is a live, exact
        recomputation (`_ambush_candidates()`), not a cached guess."""
        safe_zone = self.current_room in SAFE_ZONE_ROOMS
        fighting = self._combat_instance_idx is not None
        candidates = self._ambush_candidates()
        n = len(candidates)
        probability = 1 - 0.5 ** n if n else 0.0
        if fighting:
            ambush_note = " (Kampf läuft bereits - kein Ambush-Wurf)"
        elif safe_zone:
            ambush_note = " (Safe Zone - kein Ambush-Wurf)"
        else:
            ambush_note = ""
        day_or_night = "Tag" if self.time_of_day < 0x80 else "Nacht"
        candidate_labels = []
        for idx in candidates:
            code = (
                None
                if idx in AMBUSH_INSTANCE_IGNORES_OBJECT_CODE
                else self._object_code_for_instance(idx)
            )
            if code is not None:
                candidate_labels.append(f"{idx}({self._object_display_name(code)})")
            elif idx in INSTANCE_NAMES:
                candidate_labels.append(f"{idx}({INSTANCE_NAMES[idx]})")
            else:
                candidate_labels.append(f"{idx}(kein Code)")

        lines = [
            "=== DEBUG ===",
            f"Raum: {self.current_room} (Safe Zone: {'ja' if safe_zone else 'nein'})",
            f"Uhrzeit: {self.time_of_day}/255 ({day_or_night})  Tag {self.day_count}  "
            f"Runden gesamt: {self._turn_counter}",
            f"Ambush-Kandidaten (Instanz-Index): {candidate_labels} (n={n})",
            f"Ambush-Wahrscheinlichkeit: 1 - 0.5^{n} = {probability:.1%}{ambush_note}",
        ]
        if fighting:
            name = self._combat_monster_display_name()
            lines.append(
                f"Kampf: {name} (Instanz #{self._combat_instance_idx}, "
                f"Code={self._combat_monster_code}) "
                f"HP={self._combat_monster_hp}  wartet_auf={self._combat_awaiting}"
            )
        else:
            lines.append("Kampf: keiner")
        lines += [
            f"Ansehen: {self.ansehen}  Gerfs: {self.money}",
            f"Stärke (Asz/Smi): {self.aszhanti_strength}/{self.smirga_strength}  "
            f"Astral (Asz): {self.aszhanti_astral}",
            f"HP (Asz/Smi): {self.aszhanti_health}/{self.aszhanti_max_health}  "
            f"{self.smirga_health}/{self.smirga_max_health}",
            f"Rüstung (Asz/Smi): {self.aszhanti_armor}/{self.smirga_armor}",
            f"Hunger: {self.hunger}  Durst (Asz/Smi): {self.aszhanti_durst}/{self.smirga_durst}",
            f"Scarabäus: charge={self.scarabaeus_charge}  gewarnt={self._gas_trap_warned}  "
            f"recharge_deadline={self._scarabaeus_recharge_deadline}",
            f"Bauer-Quest: state={self._farmer_quest_state}  sturm_runden={self._farmer_storm_turns}",
            f"Tuatara-Quest: stage={self._tuatara_quest_stage}  gegruesst={self._tuatara_greeted}",
            f"Potidan-Quest: stage={self._potidan_quest_stage}",
            f"Bekannte Sprüche (Asz): {self.aszhanti_known_spells}",
            f"Letztes Bild: {self._last_shown_picture}  wartet_auf_bildnummer={self._awaiting_picture_number}",
        ]
        return "\n".join(lines)

    def status(self) -> str:
        """The real "Zustandsübersicht" screen, same line order as the
        original (confirmed via a real DOSBox screenshot,
        `Status_anfang.png` - see PHASE0_FINDINGS.md UPDATE 23):
        Gesundheit, Stärke, Ansehen (party-wide), Astral, Hunger
        (party-wide), Durst - Aszhanti's column first, Smirga's second,
        matching the original's own layout.

        Title line and column-header separator added (UPDATE 62,
        user-supplied screenshot of the real "F3" shortcut) - STORY
        message 1456 ("Zustandsübersicht.") is real, confirmed text
        already referenced above but never actually printed; every
        other line below was already an exact match to the screenshot's
        values. The dash separator's exact length isn't independently
        confirmed byte-for-byte from a screenshot - it's set to match
        the header row's own width, a reasonable visual default rather
        than a guessed different length."""
        header = "                    Aszhanti          Smirga"
        lines = [
            self.story.message(1456),
            "",
            header,
            "-" * len(header),
            f"Gesundheit : {self.aszhanti_health:>18} {self.smirga_health:>17}",
            f"Stärke     : {levels.strength_title(self.aszhanti_strength):>18} "
            f"{levels.strength_title(self.smirga_strength):>17}",
            f"Ansehen    : {levels.ansehen_title(self.ansehen)}",
            f"Astral     : {levels.astral_title(self.aszhanti_astral):>18} "
            f"{levels.SMIRGA_ASTRAL_TITLE:>17}",
            f"Hunger     : {levels.hunger_title(self.hunger)}",
            f"Durst      : {levels.durst_title(self.aszhanti_durst):>18} "
            f"{levels.durst_title(self.smirga_durst):>17}",
        ]
        return "\n".join(lines)

    # --- shopping (BUY/SELL - see item_stats.py + MERCHANTS above) ---

    def _merchant_here(self) -> tuple[int, dict] | None:
        """The merchant NPC present in the current room, if any - (object
        code, MERCHANTS entry). Both Gultiba and Yarom are wired in (see
        MERCHANTS' comment)."""
        present = self.objects_in_room(self.current_room)
        for code, info in MERCHANTS.items():
            if code in present:
                return code, info
        return None

    def buy_starter_weapons(self) -> str:
        """Foroll's scripted, hardcoded-price sale of the starting
        dagger+sword bundle - see FOROLL_*/DOLCH_CODE/SCHWERT_CODE
        constants above. NOT wired into the generic candidate-
        resolution path buy() uses for MERCHANTS, since it isn't a
        lookup against item_stats.py at all.

        Now hands over real, trackable Dolch/Schwert objects (UPDATE
        84/85 resolved their object codes) - `_bought_starter_weapons`
        remains a separate one-time flag (not replaced by an inventory
        check) since it also gates Foroll's own impatience nagging and
        the "already bought" refusal below, which should stay true even
        if the player later sells or drops one of the weapons again."""
        if self.current_room != FOROLL_ROOM:
            return "Hier ist Foroll nicht, um mir Waffen zu verkaufen."
        if self._bought_starter_weapons:
            return "Ich habe meine Waffen schon von Foroll bekommen."
        if self.money < FOROLL_WEAPON_PRICE:
            return (
                f"'Tja, habts er denn auch Geld? Macht genau {FOROLL_WEAPON_PRICE} Gerfs.' "
                f"(Ich habe nur {self.money} Gerfs.)"
            )
        self.money -= FOROLL_WEAPON_PRICE
        self._bought_starter_weapons = True
        self._move_object(DOLCH_CODE, LIMBO_CARRIED)
        self._move_object(SCHWERT_CODE, LIMBO_CARRIED)
        return (
            f"Ich zahle Foroll {FOROLL_WEAPON_PRICE} Gerfs. Er gibt mir Dolch und Schwert."
        )

    def buy(self, noun: str) -> str:
        if (
            self.current_room == FOROLL_ROOM
            and noun
            and noun.strip().lower() in ("waffen", "waffn", "dolch", "schwert")
        ):
            return self.buy_starter_weapons()
        merchant = self._merchant_here()
        if merchant is None:
            return "Hier ist kein Händler, bei dem ich etwas kaufen könnte."
        _, info = merchant
        if not noun:
            return "Was soll ich kaufen?"
        candidates = [
            code for code in range(len(self.world.flags))
            if self.item_stats.lookup(code, info["buy_field"]) > 0
        ]
        code = self._resolve_noun(noun, candidates)
        if code is None:
            return f"Das hat {info['name']} nicht im Angebot."
        price = self.item_stats.lookup(code, info["buy_field"])
        if self.money < price:
            return f"Dafür reicht mein Geld nicht ({self.money} von {price} Gerfs)."
        self.money -= price
        self._move_object(code, LIMBO_CARRIED)
        return f"Gekauft für {price} Gerfs. Ich habe noch {self.money} Gerfs."

    def sell(self, noun: str) -> str:
        """Sell an item to whichever merchant is present. Dolch/Schwert
        (UPDATE 84/85) use their own confirmed, hardcoded prices
        (`STARTER_WEAPON_SELL_PRICES`) instead of the generic
        `item_stats.py` lookup, the same way `buy_starter_weapons()`
        buys them outside the regular catalog - both are absent from
        item_stats.py entirely, confirming they were never meant to go
        through the generic per-merchant price table."""
        merchant = self._merchant_here()
        if merchant is None:
            return "Hier ist kein Händler, bei dem ich etwas verkaufen könnte."
        _, info = merchant
        if not noun:
            return "Was soll ich verkaufen?"
        code = self._resolve_noun(noun, self.objects_carried())
        if code is None:
            return "Das trage ich nicht bei mir."
        price = STARTER_WEAPON_SELL_PRICES.get(code)
        if price is None:
            price = self.item_stats.lookup(code, info["sell_field"])
        if price <= 0:
            return f"{info['name']} hat daran kein Interesse."
        self.money += price
        self._move_object(code, LIMBO_REMOVED)
        return f"Verkauft für {price} Gerfs. Ich habe jetzt {self.money} Gerfs."

    # --- equip (ANLEGEN - real armor-equip mechanic, confirmed via
    # sub_133BE - see PHASE0_FINDINGS.md UPDATE 23's follow-up) ---

    # Indefinite article for each of the 3 confirmed armor codes (see
    # combat.ARMOR_CLASS), used by inventory()'s worn-armor line
    # (STORY message 1878/1879, "hat %s %s an."). Ordinary German
    # grammar (Kettenhemd/Lederwams are neuter -> "ein", Echsenpanzer is
    # masculine -> "einen") - NOT independently verified against a
    # screenshot the way the rest of UPDATE 63 is.
    ARMOR_WEAR_ARTICLE = {264: "ein", 196: "einen", 52: "ein"}

    def equip(self, noun: str | None) -> str:
        """Sets `aszhanti_armor`/`smirga_armor` (combat.py's
        ARMOR_CLASS - Lederwams/264, Echsenpanzer/196, Kettenhemd/52,
        the only three confirmed real armor codes) so the confirmed
        damage-reduction/"block" mechanic in combat.py actually has a
        way to get exercised through normal play, not just by setting
        the fields directly in tests.

        The real handler (`sub_133BE`) picks which party member's slot
        to write via a selector (`word_2BA12`) that this project
        confirmed is a generic "active character" value reused 100+
        times elsewhere for unrelated text-variant selection - NOT the
        same thing as `characters.py`'s narrator flag, and its real
        semantics for THIS specific purpose were never independently
        pinned down. So which character equips here is a PORT DECISION,
        not a reconstructed mechanic: whoever is currently narrating
        (see `character()`/`characters.py`) - switch narrator first
        (`charakter smirga`/`charakter aszhanti`) to equip the other
        one, rather than adding a second, unconfirmed noun slot to this
        verb's grammar."""
        if not noun:
            return "Was soll ich anlegen?"
        code = self._resolve_noun(noun, self.objects_carried())
        if code is None:
            return "Das trage ich nicht bei mir."
        if code not in combat.ARMOR_CLASS:
            return "Das kann ich nicht als Rüstung anlegen."
        who_name = "Smirga" if self.narrator == Character.SMIRGA else "Aszhanti"
        if self.narrator == Character.SMIRGA:
            self.smirga_armor = code
        else:
            self.aszhanti_armor = code
        name = self._object_display_name(code)
        return f"{who_name} legt {name} an."

    def give(self, raw: str | None) -> str:
        """GIB <item> <recipient> - confirmed real verb (see
        reference/walkthrough_de.txt: "Den Skarabäus gibt man in Hyllok
        Mygra und wartet einen Tag, bis er repariert ist." -
        PHASE0_FINDINGS.md UPDATE 45). Narrow and purpose-built for its
        confirmed uses (handing the depleted Skarabäus to Mygra for
        recharging; returning Phadraig's oar once the Tuatara quest is
        resolved, UPDATE 69; giving her money for spell lessons, see
        `_give_money_to_mygra()`) - not a general give-to-NPC system;
        anything else is politely refused rather than silently
        accepted."""
        if raw and raw.strip().lower() == "geld":
            # "geld" isn't a real object (no names.py entry) - handled
            # here, before the normal item/recipient split below, since
            # there's nothing to resolve via objects_carried(). Matches
            # the confirmed screenshot's own single-word "gebe geld"
            # (no explicit recipient - whoever's there receives it).
            return self._give_money_to_mygra()
        if not raw or len(raw.split()) < 2:
            return "Wem soll ich das geben?"
        *item_words, recipient_word = raw.split()
        item_code = self._resolve_noun(" ".join(item_words), self.objects_carried())
        if item_code is None or item_code not in self.objects_carried():
            return "Das trage ich nicht bei mir."
        recipient_code = self._resolve_noun(recipient_word, self.objects_in_room(self.current_room))
        if recipient_code is None:
            return "Das sehe ich hier nicht."
        if recipient_code == MYGRA_OBJECT_CODE and item_code == SCARABAEUS_DEPLETED_CODE:
            self._move_object(SCARABAEUS_DEPLETED_CODE, LIMBO_REMOVED)
            self.scarabaeus_charge = 1
            self._scarabaeus_recharge_deadline = self._turn_counter + SCARABAEUS_RECHARGE_TURNS
            return MYGRA_GIVE_ACCEPT_MESSAGE
        if recipient_code == PHADRAIG_CODE and item_code == RUDER_CODE:
            if self._tuatara_quest_stage <= 3:
                return self.story.message(2309)
            self._move_object(RUDER_CODE, LIMBO_REMOVED)
            self.ansehen += 1
            return self.story.message(1958)
        if recipient_code == POTIDAN_CODE:
            return self._give_potidan(item_code)
        recipient_name = self._object_display_name(recipient_code)
        return f"{recipient_name} kann damit nichts anfangen."

    def _give_money_to_mygra(self) -> str:
        """GIB GELD - see the MYGRA_SPELL_TEACHING_* constants' own
        docstring above for the full derivation. One-time (gated on
        `aszhanti_known_spells`); the "not enough money"/"already
        learned"/"Mygra not here" messages below are this port's own
        reasonable fallback text, NOT verbatim decompiled strings -
        same status as buy_starter_weapons()'s equivalent fallbacks."""
        if MYGRA_OBJECT_CODE not in self.objects_in_room(self.current_room):
            return "Wem soll ich das geben?"
        if self.aszhanti_known_spells >= MYGRA_SPELL_TEACHING_SPELLS:
            return "'Mehr kann ich dir gerade nicht beibringen.' meint Mygra."
        if self.money < MYGRA_SPELL_TEACHING_PRICE:
            return (
                f"'Tja, ich brauche schon {MYGRA_SPELL_TEACHING_PRICE} Gerfs dafür.' "
                f"(Ich habe nur {self.money} Gerfs.)"
            )
        self.money -= MYGRA_SPELL_TEACHING_PRICE
        self.aszhanti_known_spells = MYGRA_SPELL_TEACHING_SPELLS
        return MYGRA_SPELL_TEACHING_MESSAGE

    def _give_potidan(self, item_code: int) -> str:
        """Confirmed real reward (flat 0x17398, PHASE0_FINDINGS.md
        UPDATE 70): the Mondscheinkraut pays 100 Gerfs, +2 Ansehen, and
        a full heal (message 1538's own "Soll ich euch sofort heilen?"
        offer - auto-accepted here, see POTIDAN_* constants' docstring
        for why). Confirmed real brush-off (message 1555) for handing
        him anything else once the quest is known."""
        if item_code != MONDSCHEINKRAUT_CODE:
            if self._potidan_quest_stage == 0:
                recipient_name = self._object_display_name(POTIDAN_CODE)
                return f"{recipient_name} kann damit nichts anfangen."
            return self.story.message(1555)
        if self._potidan_quest_stage == 0:
            return "Das interessiert Potidan jetzt nicht."
        if self._potidan_quest_stage >= 2:
            return self.story.message(1540)
        self._move_object(MONDSCHEINKRAUT_CODE, LIMBO_REMOVED)
        self._potidan_quest_stage = 2
        self.money += POTIDAN_QUEST_GERFS
        self.ansehen += 2
        self.aszhanti_health = self.aszhanti_max_health
        self.smirga_health = self.smirga_max_health
        return "\n".join([self.story.message(1538), self.story.message(1515)])

    def _check_scarabaeus_recharge(self) -> str | None:
        """Completes Mygra's recharge once the confirmed 10-turn
        deadline (`[0xAD5C]+10`) passes (see give()). PORT ADAPTATION,
        clearly flagged (PHASE0_FINDINGS.md UPDATE 45): swaps the held
        object back from 182 to 206 - the real game's exact hand-back
        mechanism wasn't confirmed (a per-object sub-state rewrite was
        found instead, not a location move), so this is a deliberate
        simplification that keeps the gas trap (UPDATE 44) coherent,
        not a reconstructed instruction."""
        if self.scarabaeus_charge != 1 or self._scarabaeus_recharge_deadline is None:
            return None
        if self._turn_counter < self._scarabaeus_recharge_deadline:
            return None
        self.scarabaeus_charge = 2
        self._scarabaeus_recharge_deadline = None
        self._move_object(SCARABAEUS_CODE, LIMBO_CARRIED)
        return "Mygra gibt dir den reparierten Scarabäus zurück. 'Er ist wieder wie neu!'"

    def helfen(self, noun: str | None) -> str:
        """HELFEN (help) - a PORT UTILITY verb name (the real typed word
        was never confirmed, same caveat as ATTACK/EQUIP elsewhere in
        this file), built for the one confirmed real interaction it
        unlocks: helping the farmer (Bauer, `FARMER_CODE`) bring in the
        harvest at room 20 before a storm destroys it (see FARMER_*
        constants and `_check_farmer_storm()` - PHASE0_FINDINGS.md
        UPDATE 68)."""
        if not noun:
            return "Wem soll ich helfen?"
        code = self._resolve_noun(noun, self.objects_in_room(self.current_room))
        if code != FARMER_CODE or self.object_location(FARMER_CODE) != self.current_room:
            return "Das sehe ich hier nicht."
        if self._farmer_quest_state == 1:
            return self.story.message(358)
        if self._farmer_quest_state == 2:
            return self.story.message(359)
        self._farmer_quest_state = 1
        self._farmer_storm_turns = 0
        self.ansehen += 1
        self.smirga_strength += 2
        self.aszhanti_strength += 1
        self.aszhanti_max_health += 1
        self.smirga_max_health += 1
        self.hunger = 150
        self.aszhanti_durst = 100
        self.smirga_durst = 100
        self._move_object(FARMER_QUEST_SCHINKEN_CODE, LIMBO_CARRIED)
        lines = [self.story.message(349)]
        lines.append(self.story.message(350 if self.narrator == Character.SMIRGA else 351))
        lines.append(self.story.message(352))
        if self.ansehen <= 2:
            lines.append(self.story.message(353))
        elif self.ansehen <= 4:
            lines.append(self.story.message(354))
        elif self.ansehen <= 6:
            lines.append(self.story.message(355))
        else:
            lines.append(self.story.message(356))
        lines.append(self.story.message(357))
        return "\n".join(lines)

    def _check_farmer_storm(self) -> str | None:
        """Confirmed real timed event (flat 0x6a61 - see FARMER_*
        constants' docstring, PHASE0_FINDINGS.md UPDATE 68): a per-turn
        counter advances while the player stays in room 20 with the
        harvest-help quest still unresolved - at
        `FARMER_QUEST_STORM_TURNS` turns, a storm destroys the crop and
        the quest fails PERMANENTLY. Matches the same per-room ambient-
        dispatcher mechanism `ROOM_IMPATIENCE_EVENTS` already ports for
        Foroll/Oerli (this event just isn't repeating/multi-stage)."""
        if self.current_room != FARMER_ROOM or self._farmer_quest_state != 0:
            return None
        self._farmer_storm_turns += 1
        if self._farmer_storm_turns < FARMER_QUEST_STORM_TURNS:
            return None
        self._farmer_storm_turns = 0
        self._farmer_quest_state = 2
        return self.story.message(347)

    # --- the Tuatara bounty/diplomacy quest (see TUATARA_* constants,
    # PHASE0_FINDINGS.md UPDATE 69) ---

    def frage(self, noun: str | None) -> str:
        """FRAGE (ask) - a PORT UTILITY verb name (the real typed word
        wasn't confirmed, same caveat as ATTACK/HELFEN elsewhere in
        this file), collapsing the walkthrough's "nach Auftrag fragen"
        + "nach Ruder fragen" into one interaction at the tavern (see
        TUATARA_* constants' docstring for why that's a safe
        simplification, not a guess)."""
        if not noun:
            return "Wonach soll ich fragen?"
        code = self._resolve_noun(noun, self.objects_in_room(self.current_room))
        if code == POTIDAN_CODE and self.object_location(POTIDAN_CODE) == self.current_room:
            return self._frage_potidan()
        if code != PHADRAIG_CODE or self.object_location(PHADRAIG_CODE) != self.current_room:
            return "Das sehe ich hier nicht."
        if self.current_room != TUATARA_TAVERN_ROOM:
            return "Darüber möchte ich hier nicht sprechen."
        if RUDER_CODE in self.objects_carried() or self._tuatara_quest_stage > 0:
            return self.story.message(2309)
        self._move_object(RUDER_CODE, LIMBO_CARRIED)
        return "\n".join([
            self.story.message(556),
            self.story.message(557),
            self.story.message(566),
        ])

    def _frage_potidan(self) -> str:
        """Confirmed real dialogue (flat 0x1731d-0x17344, PHASE0_FINDINGS.md
        UPDATE 70): asking Potidan for the first time reveals the
        Mondscheinkraut quest (message 1516); asking again while it's
        still outstanding just repeats the "bring me the herb" line
        (message 1556); asking after it's done gets the confirmed
        "no other job for you" brush-off (message 1540) rather than
        re-triggering anything."""
        if self._potidan_quest_stage == 0:
            self._potidan_quest_stage = 1
            return self.story.message(1516)
        if self._potidan_quest_stage == 1:
            return self.story.message(1556)
        return self.story.message(1540)

    def klettere(self, noun: str | None) -> str:
        """KLETTERE (climb) - a PORT UTILITY verb name, matching the
        walkthrough's "Ins Boot klettern"/"Klettere durch Durchgang".
        Handles two confirmed special-action entry points: the Tuatara
        boat (room 36, requires the Ruder) and Potidan's herb valley
        (room 47's own dead-end "N:999" sentinel, PHASE0_FINDINGS.md
        UPDATE 70 - room 28 itself has zero compass exits in the
        confirmed room graph, so "klettere" is the only way in or out)."""
        if self.current_room == TUATARA_BOATHOUSE_ROOM:
            if RUDER_CODE not in self.objects_carried():
                return "Ohne Ruder nützt mir das Boot nichts."
            self.current_room = TUATARA_LAKE_ROOMS[0]
            return self.look()
        if self.current_room == POTIDAN_PASSAGE_ROOM:
            self.current_room = POTIDAN_HERB_VALLEY_ROOM
            return self.look()
        if self.current_room == POTIDAN_HERB_VALLEY_ROOM:
            self.current_room = POTIDAN_PASSAGE_ROOM
            return self.look()
        return "Das kann ich hier nicht."

    def rudere(self, noun: str | None) -> str:
        """RUDERE (row) - confirmed real verb (room_text.py's own
        comment on rooms 37-39: "zero-compass-exit special-action rooms
        - entered/left via a 'rudere'/row verb"). Forward rowing steps
        through `TUATARA_LAKE_ROOMS` one at a time; "rudere zurück"
        reverses. Arriving at `TUATARA_ENCOUNTER_ROOM` for the first
        time triggers the confirmed Tuatara encounter (messages 602/
        606). KNOWN SIMPLIFICATION: the real "dreimal rudern" timing
        (exactly which row triggers the surfacing) wasn't precisely
        pinned down - this triggers it on first arrival at the
        confirmed-closest room, the natural reading of "closest to the
        Tuatara" from room_text.py's own note."""
        if self.current_room not in TUATARA_LAKE_ROOMS and self.current_room != TUATARA_BOATHOUSE_ROOM:
            return "Ich bin doch gar nicht im Boot!"
        going_back = noun is not None and noun.strip().lower() in ("zurueck", "zurück")
        if going_back:
            if self.current_room == TUATARA_BOATHOUSE_ROOM:
                return "Ich bin doch schon am Ufer."
            idx = TUATARA_LAKE_ROOMS.index(self.current_room)
            self.current_room = TUATARA_LAKE_ROOMS[idx - 1] if idx > 0 else TUATARA_BOATHOUSE_ROOM
            if self.current_room == TUATARA_BOATHOUSE_ROOM:
                return self._resolve_tuatara_quest_return()
            return self.look()
        if self.current_room == TUATARA_BOATHOUSE_ROOM:
            return "Ich muss doch erst ins Boot steigen."
        idx = TUATARA_LAKE_ROOMS.index(self.current_room)
        if idx == len(TUATARA_LAKE_ROOMS) - 1:
            return self.look()
        self.current_room = TUATARA_LAKE_ROOMS[idx + 1]
        result = self.look()
        if self.current_room == TUATARA_ENCOUNTER_ROOM and self._tuatara_quest_stage == 0:
            self._tuatara_quest_stage = 3
            result = f"{result}\n{self.story.message(602)}"
        return result

    def _resolve_tuatara_quest_return(self) -> str:
        """Confirmed real outcome once you row back to the boathouse:
        a celebration (message 626 for the combat ending, 627 for the
        diplomacy one) and the 150-Gerf bounty if the quest was
        resolved - message 625 (an angry refusal, the Ruder confiscated
        outright) if you row back having done neither."""
        if self._tuatara_quest_stage >= 4:
            self.money += TUATARA_BOUNTY_GERFS
            msg = 626 if self._tuatara_quest_stage == 4 else 627
            return self.story.message(msg)
        self._move_object(RUDER_CODE, LIMBO_REMOVED)
        return self.story.message(625)

    def gruesse(self, noun: str | None) -> str:
        """GRÜSSE (greet) - a PORT UTILITY verb name matching the
        walkthrough's own "Grüße Tuatara" step exactly. Triggers the
        confirmed reveal (message 612: the Tuatara has never been
        spoken to, only hunted) - required before `bitte()` can
        succeed, matching the real dialogue's confirmed order."""
        if noun is None or self._resolve_noun(noun, self.objects_in_room(self.current_room)) != TUATARA_CODE:
            return "Das sehe ich hier nicht."
        self._tuatara_greeted = True
        return self.story.message(612)

    def bitte(self, noun: str | None) -> str:
        """BITTE (ask/request) - a PORT UTILITY verb name matching the
        walkthrough's "Bitte Tuatara um Hilfe für die Fischer" step.
        Confirmed real precondition (flat 0x12fcd/0x12ff6): asking
        before greeting gets the confirmed "I don't know what you're
        getting at" refusal (message 620); asking after greeting
        succeeds (message 621) and satisfies Phadraig's oar-return
        condition just as surely as killing Tuatara does."""
        if noun is None or self._resolve_noun(noun, self.objects_in_room(self.current_room)) != TUATARA_CODE:
            return "Das sehe ich hier nicht."
        if not self._tuatara_greeted:
            return self.story.message(620)
        if self._tuatara_quest_stage < 4:
            self._tuatara_quest_stage = 5
        return self.story.message(621)

    def danke(self, noun: str | None) -> str:
        """DANKE (thank) - a PORT UTILITY verb name matching the
        walkthrough's closing "Sage Danke" step exactly (an object-less
        phrase, unlike "Grüße Tuatara"/"Bitte Tuatara..." - so a bare
        "danke" falls back to Tuatara if it's present, rather than
        requiring "danke tuatara"). Pure flavor (message 622) - the
        mechanical reward is already confirmed to land on `bitte()`'s
        own success, not this closing courtesy."""
        if noun is None:
            target = TUATARA_CODE if TUATARA_CODE in self.objects_in_room(self.current_room) else None
        else:
            target = self._resolve_noun(noun, self.objects_in_room(self.current_room))
        if target == TUATARA_CODE:
            return self.story.message(622)
        return "Wofür denn?"

    # --- combat: a stateful, PROMPT-DRIVEN flow matching the real game
    # exactly - ambush or a typed attack starts a fight, which then
    # asks "Welche Waffe soll Smirga verwenden?" followed by "Welchen
    # Zauber soll Aszhanti schleudern?"; once both are answered the
    # round resolves automatically, and - if the fight isn't over - the
    # NEXT round's weapon prompt appears immediately, with no separate
    # command needed. Confirmed via real screenshots AND a direct user
    # correction: this port's first draft skipped straight to resolving
    # a round on a typed "attackiere" command instead of prompting
    # first, which isn't how the real game works at all.
    #
    # See combat.py's own docstring for the confirmed formula this
    # ports and its deliberate simplifications. Prompting for weapon/
    # spell choices now matches the real UI. Two checks are wired in
    # (PHASE0_FINDINGS.md UPDATE 83), both requested directly rather
    # than evidenced by a specific screenshot - reasonable common-sense
    # gameplay validation, not fabricated combat math:
    #   - WEAPON POSSESSION: choosing Dolch/Schwert at the weapon prompt
    #     is refused (reprompting) unless `_bought_starter_weapons` is
    #     set - the best available proxy for "does Smirga actually have
    #     a weapon", since the real object codes for Dolch/Schwert are
    #     themselves unresolved (UPDATE 27) and buy_starter_weapons()
    #     never grants trackable objects (its own KNOWN GAP). The
    #     chosen weapon still has NO effect on the round's damage math
    #     either way - `weapon_damage_bonus` stays 0 - since the real
    #     per-weapon bonus VALUES are exactly the unresolved part of
    #     UPDATE 27; adding possession-checking is a UI-layer
    #     correctness fix, not new (fabricated) combat math.
    #   - SPELL KNOWLEDGE: casting a real spell name Aszhanti hasn't
    #     learned yet (`aszhanti_known_spells`/`SPELL_LEARN_ORDER` - see
    #     MYGRA_SPELL_TEACHING_*, UPDATE 81/82) now has no effect,
    #     exactly like typing an unrecognized spell name already did -
    #     no new message/reprompt invented for this case specifically,
    #     since the real game's own behavior here isn't evidenced.
    #
    # SPELL_PROMPT deliberately shows the real magic words (LEVI, KUBL,
    # FEBR, UNSI, TOPA) rather than the original's own "Spruch I,
    # Spruch II..." phrasing - confirmed via direct user report to be
    # 1990s COPY PROTECTION: the real game never told the player these
    # names anywhere in its own text, only ever showing the generic
    # "Spruch N" labels - you needed the physical printed manual
    # (not included with a pirated copy) to know what to actually type.
    # This port has no such protection to reproduce and no reason to
    # gatekeep behind a manual that doesn't exist for it, so the real
    # names are shown directly (see PHASE0_FINDINGS.md UPDATE 35).

    WEAPON_PROMPT = "Welche Waffe soll Smirga verwenden?\nDolch, Schwert, Hände oder Fliehen."
    SPELL_PROMPT = "Welchen Zauber soll Aszhanti schleudern?\nLEVI, KUBL, FEBR, UNSI, TOPA oder Keinen."

    # Weapon-possession check at the weapon prompt (UPDATE 83, now
    # backed by real inventory since UPDATE 84/85 resolved DOLCH_CODE/
    # SCHWERT_CODE) - "Hände" (bare hands) needs no item at all, so it
    # isn't listed here. A real `objects_carried()` check (rather than
    # the earlier `_bought_starter_weapons` proxy) also correctly
    # refuses a weapon the player has since sold or dropped.
    WEAPON_CODES = {"dolch": DOLCH_CODE, "schwert": SCHWERT_CODE}
    WEAPON_NOT_OWNED_MESSAGES = {
        "dolch": "Ich habe keinen Dolch dabei.",
        "schwert": "Ich habe kein Schwert dabei.",
    }

    def _object_display_name(self, code: int) -> str:
        names = OBJECT_NAMES.get(code)
        return names[0].capitalize() if names else f"#{code}"

    def _who_is_here_line(self, codes: list[int]) -> str:
        """Port of the confirmed "wer ist hier" dynamic room-presence
        printer (`laas` analysis project, flat 0xF21E-0xF35E - see
        PHASE0_FINDINGS.md UPDATE 25/52): prints instance-tracked
        objects present in the room (has_instance - per UPDATE 26,
        almost always a person/creature, not a plain item) by name, in
        ascending object-code order, ending in "ist hier."/"sind hier."
        depending on count.

        CONFIRMED, not guessed - this project captured live memory
        dumps of room 67 (Hyllok's village square) with its two tracked
        NPCs, Har (25) and Sklar (26): the raw buffer literally contains
        the composited sentences "Har und Sklar sind hier." (both
        present) and "Sklar ist hier." (Sklar alone) - nailing the
        join word ("und", no comma for exactly two), the ascending
        print order, and the exact singular/plural suffix straight from
        memory, independent of and matching the earlier disassembly
        trace (UPDATE 25's room 3 "Foroll ist hier" report).

        KNOWN GAP: no real gameplay report or memory dump has ever shown
        3+ of these objects in one room, so the join for that case is
        NOT confirmed - this uses the standard German list-join
        (comma-separate all but the last, "und" before the last) as the
        natural extrapolation of the confirmed n=1/n=2 forms, not a
        blind guess."""
        names = [self._object_display_name(c) for c in codes]
        if len(names) == 1:
            joined = names[0]
        else:
            joined = ", ".join(names[:-1]) + " und " + names[-1]
        suffix = "ist hier." if len(names) == 1 else "sind hier."
        return f"{joined} {suffix}"

    def _start_combat(self, code: int | None, instance_idx: int | None = None) -> None:
        """Starts a fight. `code` is the object code when one exists
        (the normal case - `attack()`'s typed-noun path always has
        one); pass `code=None` with an explicit `instance_idx` for a
        confirmed-eligible creature that has no mapped object code
        (see `_check_ambush()` - UPDATE 74)."""
        if instance_idx is None:
            instance_idx = self.world.flags[code].instance_index
        self._combat_instance_idx = instance_idx
        self._combat_monster_code = code
        self._combat_monster_hp = self.world.instances[instance_idx].hp
        self._combat_awaiting = "weapon"

    def _combat_monster_display_name(self) -> str:
        """The current fight's display name - the object's real name
        when a code is mapped, the confirmed `INSTANCE_NAMES` entry
        when one exists (UPDATE 76), an honest "unidentified creature"
        numeric fallback (by instance index) otherwise - matching the
        SAME "numeric fallback... most of the candidate pool is still
        unnamed" precedent `_object_display_name()` already uses for
        unnamed-but-coded objects (PHASE0_FINDINGS.md UPDATE 30)."""
        if self._combat_monster_code is not None:
            return self._object_display_name(self._combat_monster_code)
        if self._combat_instance_idx in INSTANCE_NAMES:
            return INSTANCE_NAMES[self._combat_instance_idx]
        return f"Kreatur #{self._combat_instance_idx}"

    def attack(self, noun: str | None) -> str:
        """Starts a fight against `noun` - an instance-tracked object
        (has_instance - see world.py's object_location docstring and
        PHASE0_FINDINGS.md UPDATE 26, which found that's almost always
        a person/creature, not an item) present in the current room.
        Immediately returns the weapon prompt rather than resolving a
        round - see this section's own docstring for the confirmed
        Q&A flow. If already fighting, just re-sends whichever prompt
        is currently pending (weapon or spell) instead of starting a
        new fight.

        Gultiba's bedroom's lover (GULTIBA_LOVER_CODE) is special-cased
        ahead of the generic instance-based flow - he isn't instance-
        tracked (he's pure scripted scenery, not a fightable monster),
        and attacking him doesn't start a real fight at all - it's a
        confirmed, one-shot scripted outcome (see
        `_resolve_gultibas_bedroom_encounter()`, UPDATE 87/88; only one
        of ATTACK/LASS can ever resolve the scene -
        `_gultiba_bedroom_resolved` gates both)."""
        if (
            self._combat_instance_idx is None
            and self.current_room == GULTIBA_BEDROOM_ROOM
            and not self._gultiba_bedroom_resolved
            and noun
            and self._resolve_noun(noun, [GULTIBA_LOVER_CODE]) == GULTIBA_LOVER_CODE
        ):
            return self._resolve_gultibas_bedroom_encounter(
                GULTIBA_LOVER_DEATH_ANSEHEN, GULTIBA_LOVER_DEATH_MESSAGE
            )
        if self._combat_instance_idx is None:
            if not noun:
                return "Wen soll ich angreifen?"
            candidates = [
                c for c in self.objects_in_room(self.current_room)
                if self.world.flags[c].has_instance
            ]
            code = self._resolve_noun(noun, candidates)
            if code is None or code not in candidates:
                return "Das sehe ich hier nicht, oder es lässt sich nicht bekämpfen."
            self._start_combat(code)
        return self.WEAPON_PROMPT if self._combat_awaiting == "weapon" else self.SPELL_PROMPT

    def release(self, noun: str | None) -> str:
        """LASS <noun> [GEHEN] - see the GULTIBA_LOVER_RELEASE_* constants'
        own docstring for the disassembly trace behind this verb and its
        confidence caveats (PHASE0_FINDINGS.md UPDATE 88). Narrow and
        purpose-built, like HELFEN/RUDERE/KLETTERE - not a general
        "release" mechanic; anything else is politely refused."""
        if not noun:
            return "Wen soll ich gehen lassen?"
        words = [w for w in noun.split() if w not in ("gehen", "frei", "los")]
        stripped_noun = " ".join(words) if words else noun
        if (
            self.current_room == GULTIBA_BEDROOM_ROOM
            and not self._gultiba_bedroom_resolved
            and self._resolve_noun(stripped_noun, [GULTIBA_LOVER_CODE]) == GULTIBA_LOVER_CODE
        ):
            return self._resolve_gultibas_bedroom_encounter(
                GULTIBA_LOVER_RELEASE_ANSEHEN, GULTIBA_LOVER_RELEASE_MESSAGE
            )
        return "Das kann ich nicht loslassen."

    def _resolve_gultibas_bedroom_encounter(self, ansehen_delta: int, message_index: int) -> str:
        """Shared by both of the scene's confirmed resolutions
        (`attack()`'s special case, and `release()`) - see the
        GULTIBA_* constants' own docstring for the full derivation.
        Ansehen shifts by `ansehen_delta`, the Dolch (UNLOCK_GATE_
        OBJECT, not the Schwert key itself) is lost to true limbo -
        the same object-relocation call the room's own handler makes
        for both outcomes - and the puzzle door relocks behind you.
        One-shot: only the first call for a given game does anything,
        gated by `_gultiba_bedroom_resolved`."""
        self._gultiba_bedroom_resolved = True
        self.ansehen += ansehen_delta
        self._move_object(DOLCH_CODE, LIMBO_REMOVED)
        self._set_door_state(UNLOCK_ROOM, 0, DOOR_LOCKED)
        return self.story.message(message_index)

    def _combat_answer(self, raw: str, rng=random) -> str:
        """Handles the player's plain typed answer to whichever combat
        prompt is pending (`_combat_awaiting`) - routed here directly
        from `execute_chain()`, bypassing normal verb parsing entirely,
        the same way the real game's own combat Q&A works (you type
        "Schwert", not "attackiere Schwert").

        "Fliehen" (and equivalents) is specially recognized at the
        weapon prompt, ending the fight via `flee()`. Choosing "Dolch"
        or "Schwert" without currently carrying it (`WEAPON_CODES`/
        `objects_carried()` - UPDATE 83, backed by real inventory since
        UPDATE 84/85) is refused and re-prompted - "Hände" and anything
        else proceeds as before. KNOWN SIMPLIFICATION: even an owned
        weapon still isn't applied to the round's math (real weapon
        modifiers are a separately documented gap - see this section's
        own docstring).

        All 5 real spell names - "LEVI", "KUBL", "UNSI", "TOPA", "FEBR"
        - are recognized at the spell prompt and apply their confirmed
        real effects (see `combat.resolve_levi()`/`resolve_kubl()`/
        `resolve_unsi()`/`resolve_topa()`/`resolve_febr()`) IF Aszhanti
        has actually learned them yet (`aszhanti_known_spells`, UPDATE
        83) - otherwise, same as any other unrecognized text, it has no
        effect."""
        answer = raw.strip().lower()
        if self._combat_awaiting == "weapon":
            if answer in ("fliehen", "flee", "flieh"):
                self._combat_awaiting = None
                return self.flee()
            weapon_code = self.WEAPON_CODES.get(answer)
            if weapon_code is not None and weapon_code not in self.objects_carried():
                return f"{self.WEAPON_NOT_OWNED_MESSAGES[answer]}\n\n{self.WEAPON_PROMPT}"
            self._combat_awaiting = "spell"
            return self.SPELL_PROMPT

        result = self._resolve_combat_round(spell_choice=answer, rng=rng)
        if self._combat_instance_idx is not None:
            # Fight continues - the real game immediately re-prompts
            # for the next round's weapon, no extra command needed.
            self._combat_awaiting = "weapon"
            result = f"{result}\n\n{self.WEAPON_PROMPT}"
        return result

    def _check_player_death(self, lines: list[str]) -> None:
        """Confirmed via `sub_879F`'s own end-of-round check (flat
        0x9100-0x9138, right before the function's real end at 0x9147):
        if either character's HP has dropped to 0 or below, the fight
        ends in death - `sub_879F` returns a 0xFFFF sentinel and prints
        STORY message 1497 verbatim: "Die Attacke unseres Gegners hat
        uns den letzten Lebenshauch geraubt. Für dieses Monster hätten
        wir wohl stärker sein müssen. (Hä,hä,hä)" This was a real,
        previously-unhandled gap - health could go negative with no
        consequence at all. Appends the message and stops the game
        (`running=False`) if triggered."""
        if self.aszhanti_health <= 0 or self.smirga_health <= 0:
            lines.append(self.story.message(1497))
            self._combat_instance_idx = None
            self._combat_monster_code = None
            self._combat_monster_hp = None
            self._combat_awaiting = None
            self.running = False

    def _apply_kill(self, instance_idx: int) -> str | None:
        """Confirmed leveling-on-kill (UPDATE 22/23), shared by both
        melee and spell kills - applies regardless of which damage
        source landed the final blow. Returns an extra line of text
        for special, quest-specific kills (Tuatara - see TUATARA_*
        constants, PHASE0_FINDINGS.md UPDATE 69; the Skelett - see
        POTIDAN_* constants, UPDATE 70) - None otherwise."""
        killed_code = self._combat_monster_code
        self.aszhanti_strength += 1
        self.smirga_strength += self.monster_stats.strength_reward(instance_idx)
        self.aszhanti_max_health += 1
        self.smirga_max_health += 1
        self._combat_instance_idx = None
        self._combat_monster_code = None
        self._combat_monster_hp = None
        self._combat_awaiting = None
        if killed_code == TUATARA_CODE:
            self._tuatara_quest_stage = max(self._tuatara_quest_stage, 4)
            return self.story.message(611)
        if killed_code == SKELETT_CODE:
            self._move_object(MONDSCHEINKRAUT_CODE, LIMBO_CARRIED)
            return (
                "Zwischen den verstreuten Knochen entdecke ich das gesuchte "
                "Mondscheinkraut und nehme es an mich."
            )
        return None

    def _resolve_combat_round(self, spell_choice: str | None = None, rng=random) -> str:
        """The actual round math - melee (`combat.resolve_round()`)
        THEN, if the monster survives melee, Aszhanti's spell (only
        "levi" has a real effect - see `combat.resolve_levi()`) -
        applying both to game state (hp, leveling on kill). Matches the
        real function's own order (confirmed via disassembly: Smirga's
        attack resolves before the spell dispatch even runs).

        NOT called directly by the player-facing verb layer (see
        `attack()`/`_combat_answer()` for the real entry points);
        exposed as its own method mainly so tests can resolve a round
        deterministically without threading fake weapon/spell answers
        through the prompts first. `rng` is exposed for the same reason
        - real play always uses the default, real `random` module."""
        instance_idx = self._combat_instance_idx
        monster = self.world.instances[instance_idx]
        name = self._combat_monster_display_name()

        result = combat.resolve_round(
            monster,
            monster_hp_before=self._combat_monster_hp,
            monster_dice_count=self.monster_stats.dice_count(instance_idx),
            monster_dice_bonus=self.monster_stats.dice_bonus(instance_idx),
            smirga_strength=self.smirga_strength,
            aszhanti_armor_code=self.aszhanti_armor,
            smirga_armor_code=self.smirga_armor,
            rng=rng,
        )

        target_name = "Aszhanti" if result.target == combat.ASZHANTI else "Smirga"
        lines = []
        if not result.monster_hits:
            lines.append(f"{name} greift {target_name} an, trifft jedoch nicht.")
        elif result.monster_blocked:
            lines.append(
                f"{name} greift mit aller Kraft an, doch {target_name}'s Rüstung "
                "bewahrt ihn vor Schaden."
            )
        else:
            lines.append(f"{name} verletzt {target_name} für {result.monster_damage} Hitpoints.")
            if result.target == combat.ASZHANTI:
                self.aszhanti_health -= result.monster_damage
            else:
                self.smirga_health -= result.monster_damage

        if result.player_hits:
            lines.append(f"Smirga holt weit aus und verletzt {name} für {result.player_damage} Hitpoints.")
        else:
            lines.append(f"Smirga verfehlt {name}.")

        self._combat_monster_hp = result.monster_hp_after

        if result.monster_killed:
            lines.append(f"Sofort bricht {name} leblos zusammen. Das Monster ist besiegt!")
            extra = self._apply_kill(instance_idx)
            if extra:
                lines.append(extra)
            return "\n".join(lines)

        self._check_player_death(lines)
        if not self.running:
            return "\n".join(lines)

        known_spells = {name.lower() for name in SPELL_LEARN_ORDER[: self.aszhanti_known_spells]}
        if spell_choice not in known_spells:
            # A real spell name Aszhanti hasn't learned yet - same as
            # any other unrecognized text, falls through with no effect
            # (UPDATE 83; see MYGRA_SPELL_TEACHING_*/SPELL_LEARN_ORDER).
            spell_choice = None

        if spell_choice == "levi":
            levi = combat.resolve_levi(
                monster_hp_before=self._combat_monster_hp,
                aszhanti_astral=self.aszhanti_astral,
                aszhanti_strength=self.aszhanti_strength,
                rng=rng,
            )
            if not levi.cast_succeeded:
                lines.append("Aszhanti spricht einen Zauber aus, doch nichts passiert.")
            elif levi.bonus_landed:
                lines.append(
                    f"Aszhanti verwirrt {name} und schlägt Smirga unvermittelt zu und "
                    f"verletzt {name} für {levi.bonus_damage} Hitpoints."
                )
            else:
                lines.append(f"Aszhanti verwirrt {name} für einen Moment, doch nichts weiter passiert.")
            self._combat_monster_hp = levi.monster_hp_after
            if levi.monster_killed:
                lines.append(f"Sofort bricht {name} leblos zusammen. Das Monster ist besiegt!")
                extra = self._apply_kill(instance_idx)
                if extra:
                    lines.append(extra)
        elif spell_choice == "kubl":
            kubl = combat.resolve_kubl(
                monster_hp_before=self._combat_monster_hp,
                aszhanti_astral=self.aszhanti_astral,
                aszhanti_strength=self.aszhanti_strength,
                rng=rng,
            )
            if not kubl.cast_succeeded:
                lines.append("Aszhanti spricht einen Zauber aus, doch nichts passiert.")
            else:
                lines.append(
                    f"Aszhanti schleudert einen Kubl auf {name} und verletzt es "
                    f"für {kubl.damage} Hitpoints."
                )
            self._combat_monster_hp = kubl.monster_hp_after
            if kubl.monster_killed:
                lines.append(f"Sofort bricht {name} leblos zusammen. Das Monster ist besiegt!")
                extra = self._apply_kill(instance_idx)
                if extra:
                    lines.append(extra)
        elif spell_choice == "unsi":
            unsi = combat.resolve_unsi(aszhanti_astral=self.aszhanti_astral, rng=rng)
            if not unsi.cast_succeeded:
                lines.append("Aszhanti spricht einen Zauber aus, doch nichts passiert.")
            else:
                lines.append(f"Aszhanti schleudert einen Unsi und tatsächlich wird {name} stark verwirrt!")
        elif spell_choice == "topa":
            topa = combat.resolve_topa(aszhanti_astral=self.aszhanti_astral, rng=rng)
            if not topa.cast_succeeded:
                lines.append("Aszhanti spricht einen Zauber aus, doch nichts passiert.")
            else:
                lines.append(f"Aszhanti schleudert seinen Topa und {name} wird sehr stark verwirrt!")
        elif spell_choice == "febr":
            febr = combat.resolve_febr(
                monster_code=self._combat_monster_code,
                monster_hp_before=self._combat_monster_hp,
                aszhanti_astral=self.aszhanti_astral,
                aszhanti_strength=self.aszhanti_strength,
                rng=rng,
            )
            if not febr.cast_succeeded:
                lines.append("Aszhanti spricht einen Zauber aus, doch nichts passiert.")
            elif febr.bonus_landed:
                lines.append(
                    "Aszhanti murmelt seinen Zauber und hält sofort eine kleine, züngelnde "
                    f"Flamme in der hohlen Hand. Die Flamme blendet {name} ein wenig und Smirga "
                    f"kann einen Schlag plazieren, der {name} {febr.bonus_damage} Schadenspunkt zufügt."
                )
            else:
                lines.append(
                    "Aszhanti beschwört einen Febr und hält dann eine kleine Flamme in der hohlen Hand."
                )
            self._combat_monster_hp = febr.monster_hp_after
            if febr.monster_killed:
                lines.append(f"Sofort bricht {name} leblos zusammen. Das Monster ist besiegt!")
                extra = self._apply_kill(instance_idx)
                if extra:
                    lines.append(extra)

        return "\n".join(lines)

    def flee(self) -> str:
        """KNOWN SIMPLIFICATION: the real game's Fliehen option can
        fail ("Die Flucht mißlingt, da uns {monster} den Weg
        versperrt.", STORY message 1909) - the real success-chance
        formula wasn't traced (out of scope for this pass, see
        combat.py's docstring for what WAS ported). This always
        succeeds."""
        if self._combat_instance_idx is None:
            return "Ich kämpfe gerade nicht."
        self._combat_instance_idx = None
        self._combat_monster_code = None
        self._combat_monster_hp = None
        self._combat_awaiting = None
        return "Mit aller Mühe gelingt es uns zu fliehen!"

    def _check_ambush(self, rng=random) -> str | None:
        """Port of the confirmed core of `sub_C301` (see
        PHASE0_FINDINGS.md UPDATE 30, corrected in UPDATE 48/49, and
        UPDATE 74: the real function "scans all 39 instance records"
        directly, NOT by object code - this port's own iteration was
        silently missing every ambush-eligible creature with no object
        code mapped to it, a full third of the real total. User-
        reported: real, near-total loss of ambushes as a consequence).

        CORRECTED (UPDATE 48): the real `sub_C301` SKIPS a candidate
        whose location equals `LIMBO_REMOVED` (299) - verified directly
        against raw bytes, twice, and confirmed by a second, separate
        function with the identical pattern. This project's first draft
        had the condition backwards (only considering candidates AT
        299). 299 doesn't mean "off-stage, waiting to wander" - it
        means "not currently active for this time-of-day phase" (see
        UPDATE 49: the day/night clock's dawn/nightfall subroutines
        toggle the roster between a real room and 299 -
        `_advance_clock()` calls `_advance_day_night_roster()` at those
        exact transitions).

        UPDATE 77/78: fully re-disassembled `sub_C301` and found it
        skips any instance whose room-list far pointer is unset before
        checking anything else, AND - once decoded from a live memory
        dump, UPDATE 78 - restricts a real wanderer to only its own
        specific list of rooms (see `MONSTER_ROOM_LISTS`). Outside a
        wanderer's own list, it simply isn't a candidate at all - not
        even to roll and fail, matching the real function exactly.
        Combat can still only happen outside Hyllok in the first place
        (user-confirmed: the village is a safe zone, room 10 - "Vor
        Hyllok" - is the confirmed first room where combat can occur at
        all - see `SAFE_ZONE_ROOMS`). Confirmed roll: 1d6, triggers on
        > 3 (a clean 50% chance) -
        first eligible candidate (ascending INSTANCE INDEX, matching the
        real scan order) to roll a success wins, matching the real
        function's first-match-wins behavior. Does nothing if already
        fighting."""
        if self._combat_instance_idx is not None:
            return None
        if self.current_room in SAFE_ZONE_ROOMS:
            return None
        for idx in self._ambush_candidates():
            if combat.d6(rng) <= 3:
                continue
            code = (
                None
                if idx in AMBUSH_INSTANCE_IGNORES_OBJECT_CODE
                else self._object_code_for_instance(idx)
            )
            if code is not None:
                self._move_object(code, self.current_room)
            else:
                self._move_instance(idx, self.current_room)
            self._start_combat(code, instance_idx=idx)
            name = self._combat_monster_display_name()
            return (
                f"Plötzlich, wie aus dem Nichts, taucht {name} auf und greift uns an.\n\n"
                f"{self.WEAPON_PROMPT}"
            )
        return None

    def _ambush_candidates(self) -> list[int]:
        """The INSTANCE INDICES (not object codes - UPDATE 74)
        `_check_ambush()` would roll against right now, in the same
        ascending order - factored out so the debug view (see
        debug_info()) can report the exact live candidate list and
        probability without duplicating the eligibility rules.

        An instance is a candidate iff it's `ambush_eligible`, currently
        active (not `LIMBO_REMOVED`), and the CURRENT ROOM is in its own
        confirmed `MONSTER_ROOM_LISTS` entry (UPDATE 77/78 - the real
        `sub_C301` requires both a room list to exist at all AND the
        current room to actually be in it; an instance with no entry in
        `MONSTER_ROOM_LISTS` - i.e. no room list, confirmed via
        `ObjectInstance.has_room_list` - can never be a candidate
        anywhere). This replaces the old hand-curated
        `AMBUSH_EXCLUDED_CODES`/`AMBUSH_EXCLUDED_INSTANCE_INDICES`
        lists (UPDATE 77) and UPDATE 77's own `PRE_BRIDGE_ROOMS`
        heuristic (UPDATE 78) with the real, fully-decoded mechanism."""
        candidates = []
        for idx in range(len(self.world.instances)):
            instance = self.world.instances[idx]
            if not instance.ambush_eligible:
                continue
            if self.current_room not in MONSTER_ROOM_LISTS.get(idx, ()):
                continue
            if self._instance_location(idx) == LIMBO_REMOVED:
                continue
            candidates.append(idx)
        return candidates

    # --- doors (OPEN/CLOSE/LOCK/UNLOCK - see decompiled/seg005_batch5.md) ---

    def _direction_slot(self, noun: str) -> int | None:
        word = noun.strip().lower()
        compass = DIRECTION_WORDS.get(word)
        if compass is None and word.upper() in DIRECTION_SLOTS:
            compass = word.upper()
        if compass is None:
            return None
        return DIRECTION_SLOTS[compass]

    def get_door_state(self, room: int, slot: int) -> int:
        key = (room, slot)
        if key in self._door_state_overrides:
            return self._door_state_overrides[key]
        return self.world.room(room).exits[slot].msg_code

    def _set_door_state(self, room: int, slot: int, new_code: int):
        """Mirrors `sub_EEC0`: writes `new_code` into both this room's
        exit slot AND the reciprocal ((slot+4)%8) slot of the
        destination room, so the door's state is consistent from
        either side."""
        self._door_state_overrides[(room, slot)] = new_code
        dest = self.world.room(room).exits[slot].dest_room
        if dest:
            reciprocal = (slot + 4) % 8
            self._door_state_overrides[(dest, reciprocal)] = new_code

    def _door_scan(self, match_states: set[int]) -> list[int]:
        """Exit slots in the current room whose door state matches -
        the "no specific direction given" scan every door verb does."""
        room = self.world.room(self.current_room)
        return [
            slot
            for slot, ex in enumerate(room.exits)
            if ex.usable and self.get_door_state(self.current_room, slot) in match_states
        ]

    def _resolve_door_direction(self, noun: str | None, match_states: set[int]) -> int | str:
        """Shared "which door" resolution used by all 4 door verbs:
        returns a slot index on success, or an error message string."""
        if noun:
            slot = self._direction_slot(noun)
            if slot is None or not self.world.room(self.current_room).exits[slot].usable:
                return "Dort ist keine Tür."
            return slot
        matches = self._door_scan(match_states)
        if not matches:
            return "Ich sehe hier keine solche Tür."
        if len(matches) > 1:
            names = ", ".join(DIRECTION_NAMES[s] for s in matches)
            return f"Welche Richtung? ({names})"
        return matches[0]

    def open_door(self, noun: str | None) -> str:
        result = self._resolve_door_direction(noun, {DOOR_CLOSED, DOOR_LOCKED})
        if isinstance(result, str):
            return result
        slot = result
        state = self.get_door_state(self.current_room, slot)
        if state == DOOR_LOCKED:
            return "Die Tür ist verschlossen."
        if state == DOOR_OPEN:
            return "Die ist schon offen."
        if state != DOOR_CLOSED:
            return "Das kann ich nicht öffnen."
        self._set_door_state(self.current_room, slot, DOOR_OPEN)
        return f"Ich öffne die Tür Richtung {DIRECTION_NAMES[slot]}."

    def close_door(self, noun: str | None) -> str:
        result = self._resolve_door_direction(noun, {DOOR_OPEN})
        if isinstance(result, str):
            return result
        slot = result
        state = self.get_door_state(self.current_room, slot)
        if state != DOOR_OPEN:
            return "Das ist nicht offen."
        self._set_door_state(self.current_room, slot, DOOR_CLOSED)
        return f"Ich schließe die Tür Richtung {DIRECTION_NAMES[slot]}."

    def _check_key(self, instrument: str | None) -> str | None:
        """Shared LOCK/UNLOCK key-object gate. Returns an error message
        if the check fails, or None if the key was correctly specified
        (`KEY_OBJECT_CODE` - Schwert, confirmed UPDATE 84/85)."""
        if not instrument:
            return "Womit?"
        code = self._resolve_noun(instrument, self.objects_carried())
        if code is None or code != KEY_OBJECT_CODE:
            return "Es geht nicht. Na sowas. Sachen gibt's."
        return None

    def lock_door(self, noun: str | None, instrument: str | None) -> str:
        key_error = self._check_key(instrument)
        if key_error:
            return key_error
        result = self._resolve_door_direction(noun, {DOOR_CLOSED})
        if isinstance(result, str):
            return result
        slot = result
        if self.get_door_state(self.current_room, slot) != DOOR_CLOSED:
            return "Das kann ich so nicht verschließen."
        self._set_door_state(self.current_room, slot, DOOR_LOCKED)
        return f"Ich verschließe die Tür Richtung {DIRECTION_NAMES[slot]}."

    def unlock_door(self, noun: str | None, instrument: str | None) -> str:
        key_error = self._check_key(instrument)
        if key_error:
            return key_error
        # Extra gates confirmed only for UNLOCK (not LOCK): object 0 must
        # NOT be present/carried, and the player must be in room 0x55.
        if self.object_location(UNLOCK_GATE_OBJECT) == LIMBO_CARRIED:
            return "Wir haben keinen Schlüssel!"
        if self.current_room != UNLOCK_ROOM:
            return "Der Schlüssel paßt nicht."
        result = self._resolve_door_direction(noun, {DOOR_LOCKED})
        if isinstance(result, str):
            return result
        slot = result
        if self.get_door_state(self.current_room, slot) != DOOR_LOCKED:
            return "Das ist nicht verschlossen."
        self._set_door_state(self.current_room, slot, DOOR_CLOSED)
        return f"Ich schließe die Tür Richtung {DIRECTION_NAMES[slot]} auf."

    def cheat(self, noun: str) -> str:
        """Cheat commands - not in the original game. `noun` is the
        verb's typed noun (e.g. "teleport 10" -> "10")."""
        if noun == "teleport":
            return "Wohin?"
        if noun.startswith("teleport "):
            try:
                room = int(noun.split(" ", 1)[1])
            except ValueError:
                return "Ungültige Raumnummer."
            if room < 0 or room >= len(self.world.rooms):
                return "Ungültige Raumnummer."
            self.current_room = room
            return f"Wir teleportieren uns nach Raum {room}.\n\n{self.look()}"
        if noun == "money":
            self.money = 9999
            return "Wir haben jetzt 9999 Münzen."
        if noun == "kill":
            self.aszhanti_health = 0
            self.smirga_health = 0
            self.running = False
            return "Wir sind tot."
        return f"Unbekannter Cheat: {noun}"


    HELP_TEXT = (
        "Bewegung: n/s/e/w/ne/se/sw/nw (oder 'gehe norden' usw.)\n"
        "schau                          - Raum ansehen\n"
        "exits / ausgänge               - Ausgänge auflisten\n"
        "untersuche <name-oder-#code>   - Objekt untersuchen\n"
        "nimm <name-oder-#code>         - Objekt aufnehmen\n"
        "lege <name-oder-#code>         - Objekt ablegen\n"
        "inventar                       - Was trage ich bei mir?\n"
        "kaufe <name-oder-#code>        - Bei einem Händler etwas kaufen\n"
        "verkaufe <name-oder-#code>     - Einem Händler etwas verkaufen\n"
        "anlege <name-oder-#code>       - Rüstung anlegen (aktueller Erzähler)\n"
        "gib <name-oder-#code> <empfänger> - Gegenstand übergeben\n"
        "hilf <name-oder-#code>         - jemandem helfen\n"
        "schlafe / übernachte           - schlafen (nur nachts möglich)\n"
        "zustand                        - Zustandsübersicht (Stärke/Astral/Ansehen)\n"
        "zaubersprüche                  - bekannte Zaubersprüche auflisten\n"
        "attackiere <name-oder-#code>   - Angriff (Kampfrunde)\n"
        "fliehen                        - aus dem Kampf fliehen\n"
        "öffne <richtung>               - Tür öffnen\n"
        "schließe <richtung>            - Tür schließen\n"
        "schließe <richtung> auf/ab mit <item> - Tür auf-/zuschließen\n"
        "charakter [smirga|aszhanti]    - Erzähler wechseln/anzeigen (wechsel)\n"
        "speichern [datei]              - Spielstand speichern\n"
        "laden [datei]                  - Spielstand laden\n"
        "hilfe / ?                      - diese Übersicht\n"
        "ende                           - Spiel beenden"
    )

    def help(self) -> str:
        return self.HELP_TEXT

    # --- top-level command dispatch ---

    def execute(self, command: Command) -> str:
        #print(command)
        if command.verb == "CHEAT":
            if not command.noun:
                return "Welcher Cheat?"
            return self.cheat(command.noun)
        if command.verb in DIRECTIONS:
            return self.go(command.verb)
        if command.verb == "LOOK":
            return self.look()
        if command.verb == "EXITS":
            return self.exits()
        if command.verb == "INVENTORY":
            return self.inventory()
        if command.verb == "EXAMINE":
            if not command.noun:
                return "Was soll ich untersuchen?"
            return self.examine(command.noun)
        if command.verb == "TAKE":
            if not command.noun:
                return "Was soll ich nehmen?"
            return self.take(command.noun)
        if command.verb == "DROP":
            if not command.noun:
                return "Was soll ich ablegen?"
            return self.drop(command.noun)
        if command.verb == "OPEN":
            return self.open_door(command.noun)
        if command.verb == "CLOSE":
            return self.close_door(command.noun)
        if command.verb == "LOCK":
            return self.lock_door(command.noun, command.instrument)
        if command.verb == "UNLOCK":
            return self.unlock_door(command.noun, command.instrument)
        if command.verb == "GO":
            return "Wohin?"
        if command.verb == "STATUS":
            return self.status()
        if command.verb == "SPELLS":
            return self.spells()
        if command.verb == "BILD":
            return self.bild(command.noun)
        if command.verb == "DEBUG":
            return self.debug_info()
        if command.verb == "ATTACK":
            return self.attack(command.noun)
        if command.verb == "FLEE":
            return self.flee()
        if command.verb == "EQUIP":
            return self.equip(command.noun)
        if command.verb == "GIVE":
            return self.give(command.noun)
        if command.verb == "HELFEN":
            return self.helfen(command.noun)
        if command.verb == "LASS":
            return self.release(command.noun)
        if command.verb == "FRAGE":
            return self.frage(command.noun)
        if command.verb == "KLETTERE":
            return self.klettere(command.noun)
        if command.verb == "RUDERE":
            return self.rudere(command.noun)
        if command.verb == "GRUESSE":
            return self.gruesse(command.noun)
        if command.verb == "BITTE":
            return self.bitte(command.noun)
        if command.verb == "DANKE":
            return self.danke(command.noun)
        if command.verb == "SLEEP":
            return self.sleep()
        if command.verb == "BUY":
            return self.buy(command.noun)
        if command.verb == "SELL":
            return self.sell(command.noun)
        if command.verb == "CHARACTER":
            return self.character(command.noun)
        if command.verb == "HELP":
            return self.help()
        if command.verb == "SAVE":
            path = Path(command.noun) if command.noun else DEFAULT_SAVE_PATH
            return self.save(path)
        if command.verb == "LOAD":
            path = Path(command.noun) if command.noun else DEFAULT_SAVE_PATH
            if not path.exists():
                return f"Spielstand nicht gefunden ({path})."
            return self.load_save(path)
        if command.verb == "QUIT":
            self.running = False
            return ""
        return "Das verstehe ich nicht."

    def _advance_clock(self) -> str | None:
        """The confirmed day/night clock (PHASE0_FINDINGS.md UPDATE 43):
        advances once every TWO turns (`self._turn_counter`'s low bit,
        matching the real game's `[0xAD5C]` gate), wrapping 0-255, and
        returns one of the 4 confirmed transition messages (dawn/noon/
        dusk/nightfall) exactly when the clock lands on that value.
        Dawn (0) also increments `day_count`. Called once per turn."""
        self._turn_counter += 1
        if self._turn_counter % 2 != 0:
            return None
        self.time_of_day = (self.time_of_day + 1) % 256
        if self.time_of_day == 0:
            self.day_count += 1
        self._advance_day_night_roster()
        msg_index = CLOCK_TRANSITIONS.get(self.time_of_day)
        return self.story.message(msg_index) if msg_index is not None else None

    def _advance_day_night_roster(self) -> None:
        """Confirmed via the real dawn/nightfall subroutines (PHASE0_
        FINDINGS.md UPDATE 49): at dawn, place `DAY_ROSTER` at its
        confirmed rooms and clear `NIGHT_ROSTER` to `LIMBO_REMOVED`; at
        nightfall, the exact mirror. Only the two exact clock values
        that trigger this in the real game (dawn=0, nightfall=0x80) do
        anything here - noon/dusk don't touch the roster.

        Also toggles DAY_ROSTER_BY_INSTANCE/NIGHT_ROSTER_BY_INSTANCE_*
        (UPDATE 74) the same way, by instance index instead of object
        code, including the confirmed Ansehen>=5 progression gate that
        swaps which night roster is active (they never coexist)."""
        if self.time_of_day == 0:
            for code, room in DAY_ROSTER.items():
                self._move_object(code, room)
            for code in NIGHT_ROSTER:
                self._move_object(code, LIMBO_REMOVED)
            for idx, room in DAY_ROSTER_BY_INSTANCE.items():
                self._move_instance(idx, room)
            for idx in {
                **NIGHT_ROSTER_BY_INSTANCE_EARLY,
                **NIGHT_ROSTER_BY_INSTANCE_LATE,
                **NIGHT_ROSTER_BY_INSTANCE_ALWAYS,
            }:
                self._move_instance(idx, LIMBO_REMOVED)
        elif self.time_of_day == 0x80:
            for code in DAY_ROSTER:
                self._move_object(code, LIMBO_REMOVED)
            for code, room in NIGHT_ROSTER.items():
                self._move_object(code, room)
            for idx in DAY_ROSTER_BY_INSTANCE:
                self._move_instance(idx, LIMBO_REMOVED)
            active_night_roster = (
                NIGHT_ROSTER_BY_INSTANCE_LATE
                if self.ansehen >= ANSEHEN_LATE_ROSTER_THRESHOLD
                else NIGHT_ROSTER_BY_INSTANCE_EARLY
            )
            inactive_night_roster = (
                NIGHT_ROSTER_BY_INSTANCE_EARLY
                if self.ansehen >= ANSEHEN_LATE_ROSTER_THRESHOLD
                else NIGHT_ROSTER_BY_INSTANCE_LATE
            )
            for idx in inactive_night_roster:
                self._move_instance(idx, LIMBO_REMOVED)
            for idx, room in active_night_roster.items():
                self._move_instance(idx, room)
            for idx, room in NIGHT_ROSTER_BY_INSTANCE_ALWAYS.items():
                self._move_instance(idx, room)

    def _advance_room_events(self) -> str | None:
        """Ambient per-turn 'impatience' tick (see ROOM_IMPATIENCE_EVENTS)
        - a simplified port of the real per-turn dispatcher's room-3/
        room-72 branches (PHASE0_FINDINGS.md UPDATE 40). Called once per
        turn; returns the fired message, if any, else None."""
        room = self.current_room
        config = ROOM_IMPATIENCE_EVENTS.get(room)
        if config is None:
            return None
        if room == FOROLL_ROOM and self._bought_starter_weapons:
            return None
        turns = self._room_impatience_turns.get(room, 0) + 1
        self._room_impatience_turns[room] = turns
        fired = self._room_impatience_fired.setdefault(room, set())
        if turns == config["kick_at"] and config["kick_at"] not in fired:
            fired.add(config["kick_at"])
            return self.story.message(config["kick_msg"])
        if turns == config["warn_at"] and config["warn_at"] not in fired:
            fired.add(config["warn_at"])
            return self.story.message(config["warn_msg"])
        return None

    def _check_fanatic_ambush(self) -> str | None:
        """Confirmed dragon-cult ambush (PHASE0_FINDINGS.md UPDATE 40/43/
        44): room 100, active only during the confirmed night-into-dawn
        clock window. Destroys a carried Skarabäus - swapping it for its
        depleted form (object 182) - and damages both characters,
        matching the confirmed `word_b68e -= 2` (Aszhanti)/`word_b690 -=
        1` (Smirga). Self-gating: once 182 is carried, the "182 not
        already carried" guard (the real game's only check) stops it
        from re-firing.

        KNOWN SIMPLIFICATION: the real game's only guard is "182 isn't
        already carried" - it never checks whether the player has 206 at
        all before referencing "the Scarabäus" in the ambush text. This
        port adds that as an extra guard so a player who never had one
        doesn't get a Skarabäus conjured (and destroyed) out of nowhere -
        unlike the gas trap below, which is left exactly as confirmed."""
        if self.current_room != FANATIC_AMBUSH_ROOM:
            return None
        if self.time_of_day not in FANATIC_AMBUSH_ACTIVE_CLOCK:
            return None
        if self.object_location(SCARABAEUS_DEPLETED_CODE) == LIMBO_CARRIED:
            return None
        if self.object_location(SCARABAEUS_CODE) != LIMBO_CARRIED:
            return None
        self._move_object(SCARABAEUS_CODE, LIMBO_REMOVED)
        self._move_object(SCARABAEUS_DEPLETED_CODE, LIMBO_CARRIED)
        self.aszhanti_health -= 2
        self.smirga_health -= 1
        lines = [self.story.message(FANATIC_AMBUSH_MESSAGE)]
        self._check_player_death(lines)
        return "\n".join(lines)

    def _check_gas_trap(self) -> str | None:
        """Confirmed poison-gas cave trap (PHASE0_FINDINGS.md UPDATE 40/
        41/44): rooms 102/103. Carrying the depleted Skarabäus (182) is
        always fatal; otherwise the outcome depends on the charge level
        (`scarabaeus_charge`) and a one-shot near-miss warning
        (`_gas_trap_warned`, the real game's `[0xB732]`). Fires every
        turn spent in these rooms, exactly as confirmed - no extra guard
        for "no Skarabäus at all" (unlike the ambush above): the real
        code doesn't check that either, so a player with no Skarabäus at
        all can still see the "it protects you" flavor line, a real,
        inherited quirk rather than an invented one."""
        if self.current_room not in GAS_TRAP_ROOMS:
            return None
        lines = []
        if self.object_location(SCARABAEUS_DEPLETED_CODE) == LIMBO_CARRIED:
            lines.append(self.story.message(GAS_TRAP_DEATH_182_PRESENT))
            self.aszhanti_health = 0
            self.smirga_health = 0
        elif self.scarabaeus_charge == 2:
            lines.append(self.story.message(GAS_TRAP_PROTECTED))
        elif not self._gas_trap_warned:
            self._gas_trap_warned = True
            lines.append(self.story.message(GAS_TRAP_NEAR_MISS))
        else:
            lines.append(self.story.message(GAS_TRAP_DEATH_UNPROTECTED))
            self.aszhanti_health = 0
            self.smirga_health = 0
        self._check_player_death(lines)
        return "\n".join(lines)

    def execute_chain(self, raw: str) -> list[str]:
        """Real port of sub_14202's comma-chaining (see parser.py's
        module docstring): runs every comma-separated command in `raw`
        in sequence, stopping early if a command sets `running=False`
        (QUIT). Returns each command's non-empty result in order.

        While a combat prompt is pending (`_combat_awaiting`), bypasses
        normal verb parsing entirely and routes the WHOLE raw input to
        `_combat_answer()` instead - matching the real game's own
        combat Q&A, where you type "Schwert" or "LEVI" directly, not a
        verb command. See the "combat" section's docstring for why.

        Each individual command counts as one turn for `_advance_room_events`
        and `_advance_clock` (including a combat-answer turn), matching
        the real main loop calling its dispatchers once per processed
        input."""
        if self._combat_awaiting is not None:
            results = [self._combat_answer(raw)]
            for tick in (
                self._advance_clock(),
                self._advance_room_events(),
                self._check_scarabaeus_recharge(),
                self._check_fanatic_ambush(),
                self._check_gas_trap(),
                self._check_farmer_storm(),
                self._check_room_picture(),
            ):
                if tick:
                    results.append(tick)
            return results
        if self._awaiting_picture_number:
            results = [self._show_picture_number(raw)]
            for tick in (
                self._advance_clock(),
                self._advance_room_events(),
                self._check_scarabaeus_recharge(),
                self._check_fanatic_ambush(),
                self._check_gas_trap(),
                self._check_farmer_storm(),
                self._check_room_picture(),
            ):
                if tick:
                    results.append(tick)
            return results
        results = []
        for command in parse_chain(raw):
            result = self.execute(command)
            if result:
                results.append(result)
            for tick in (
                self._advance_clock(),
                self._advance_room_events(),
                self._check_scarabaeus_recharge(),
                self._check_fanatic_ambush(),
                self._check_gas_trap(),
                self._check_farmer_storm(),
                self._check_room_picture(),
            ):
                if tick:
                    results.append(tick)
            if not self.running:
                break
        return results


def _combat_prompt_default(awaiting: str | None, last_weapon_answer: str, last_spell_answer: str) -> str:
    """Which pre-fill default (if any) applies to the prompt about to be
    shown - see repl()'s docstring note. Deliberately scoped to ONLY
    WEAPON_PROMPT/SPELL_PROMPT (`awaiting == "weapon"`/`"spell"`), not
    every command - repeating "schau" or "n" by default would be more
    confusing than helpful outside combat."""
    if awaiting == "weapon":
        return last_weapon_answer
    if awaiting == "spell":
        return last_spell_answer
    return ""


def repl(assets_dir: Path = DEFAULT_ASSETS_DIR):
    # German text needs real umlaut/ß output; force UTF-8 on stdout so it
    # doesn't get mangled on consoles that default to another codepage.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    state = GameState(assets_dir)
    print("Die Drachen von Laas - Port-Grundgerüst")
    print(state.look())
    # Pre-fills the prompt with the last answer given to THIS SAME
    # combat prompt (see repl_input.py, _combat_prompt_default above) -
    # the same weapon/spell answer is often repeated round after round,
    # so press Enter to repeat it or edit it first.
    last_weapon_answer = ""
    last_spell_answer = ""
    while state.running:
        awaiting = state._combat_awaiting
        default = _combat_prompt_default(awaiting, last_weapon_answer, last_spell_answer)
        try:
            raw = prompt_with_default("> ", default).strip()
        except EOFError:
            break
        if not raw:
            continue
        if awaiting == "weapon":
            last_weapon_answer = raw
        elif awaiting == "spell":
            last_spell_answer = raw
        for result in state.execute_chain(raw):
            print(result)


if __name__ == "__main__":
    # Show pictures on first room visit only in the real game
    SHOW_PICTURES = True

    init_repl_input()
    repl()
