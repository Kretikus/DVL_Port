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
from .monster_stats import MonsterStats
from .repl_input import prompt_with_default

DEFAULT_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"

DIRECTIONS = {"N", "NE", "E", "SE", "S", "SW", "W", "NW"}

# Door-verb constants, all confirmed via `sub_EEC0`/funcs 7-10 - see the
# `laas` analysis project's decompiled/seg005_batch5.md. Object identities
# for the key (code 1) and the UNLOCK gate object (code 0), and room 0x55,
# are not yet known by name (see room_text.py/names.py) - referenced by
# raw code/number here, matching how little is confirmed about them.
#
# CONFIRMED against the real shipped data (not just the disassembly):
# room 0x55's own exit slot 0 (north) is genuinely pre-locked
# (msg_code==DOOR_LOCKED) in the loaded RESTORE state, and nowhere else
# in the game does a locked door happen to sit in room 0x55 - this really
# is the one deliberate lock/unlock puzzle door the reverse-engineering
# notes predicted.
KEY_OBJECT_CODE = 1
UNLOCK_GATE_OBJECT = 0
UNLOCK_ROOM = 0x55  # 85

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

# Hyllok is a safe zone - no random ambush (see _check_ambush) ever
# happens there, user-confirmed. Matches room_text.py's already-confirmed
# room map exactly: 1-9 are Hyllok's own interiors (Aszhantis/Smirgas
# Elternhaus, Schmiede, Beim Scharlatan, Hühnerstall, Aszhantis/Smirgas
# Zimmer, Speisekammer, im Brunnen), 67 is the village square ("Auf dem
# Dorfplatz"), and room 10 ("Vor Hyllok") is the confirmed first room
# OUTSIDE the village - i.e. the first place random combat can occur.
SAFE_ZONE_ROOMS = set(range(1, 10)) | {67}

# Confirmed ROOM-BOUND creatures/objects (UPDATE 21's taxonomy: monsters
# split into room-bound fixed encounters vs. the free-wandering ambush
# pool) all have `ambush_eligible=True` in the raw instance data despite
# not belonging to the wandering pool at all:
#   105 Steinkreuz    - an ancient stone cross, a landmark, not even a
#                       creature (UPDATE 30) - room 26.
#   134 Bruckentroll  - guards the bridge, room 25 (UPDATE 21) - meant
#                       to be fought there deliberately, not stumbled
#                       into elsewhere.
#   146 Tuatara       - the lake creature at the Fischerdorf, room 39 -
#                       tied to a peaceful, scripted fetch-quest
#                       (reference/walkthrough_de.txt: "Grüße Tuatara.
#                       Bitte Tuatara um Hilfe für die Fischer."), not a
#                       hostile random encounter (user-reported).
#   237 Lindwurm      - dragon boss, room 109 (UPDATE 21).
#   238 Tatzelwurm    - dragon boss, room 104 (UPDATE 21).
# All five were harmless under the port's original (backwards) ambush
# condition, which only considered candidates AT `LIMBO_REMOVED` and
# none of these are ever at 299 - so none could be picked. UPDATE 48/49
# correctly flipped that condition to match the real game (candidates
# must NOT be at 299), and that fix, applied faithfully, exposed this
# pre-existing data quirk for all five: each is now always "active"
# (real location, ambush_eligible) and, under the port's own "any
# non-Hyllok room" simplification (the real per-creature room-list
# restriction is still unresolved, UPDATE 30), could ambush the player
# anywhere instead of only at - or via a deliberate encounter with -
# their own room. First Steinkreuz (UPDATE 51), then Tuatara (user-
# reported) surfaced this; the fix was generalized here to cover all
# five confirmed room-bound entries at once rather than patching them
# in one at a time as each gets independently noticed. Not a generic
# mechanism - a curated list of confirmed exceptions, extend only when
# another one is confirmed the same way.
AMBUSH_EXCLUDED_CODES = {105, 134, 146, 237, 238}

# Day/night NPC and monster roster (PHASE0_FINDINGS.md UPDATE 49):
# confirmed via the day/night clock's own dawn/nightfall subroutines,
# which place each roster member at a specific room for its active
# phase and reset it to LIMBO_REMOVED for the other phase - dawn and
# nightfall are exact mirror images of each other. Only entries with a
# CONFIRMED object code are ported here; the real game also cycles
# several more (day instance indices 27/28/30, night indices 26/31/32/
# 33/34, one of them gated behind a progression check) that this
# session couldn't resolve to a real object code - a known, documented
# gap, not guessed around with a synthetic identifier.
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


class GameState:
    def __init__(self, assets_dir: Path = DEFAULT_ASSETS_DIR):
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
        # progress. `_combat_monster_code` is the object code currently
        # being fought; `_combat_monster_hp` is its remaining hp this
        # fight (starts at the object's own instance-record hp, see
        # world.py's ObjectInstance.hp). `_combat_awaiting` is which
        # prompt is currently pending - None, "weapon", or "spell" -
        # confirmed via real screenshots and direct user correction:
        # the real game asks "Welche Waffe...?" then "Welchen
        # Zauber...?" BEFORE resolving each round, automatically
        # re-asking for the next round's weapon immediately if the
        # fight continues - not a separate "attackiere" command each
        # round (this port's first draft got that wrong).
        self._combat_monster_code: int | None = None
        self._combat_monster_hp: int | None = None
        self._combat_awaiting: str | None = None
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

    # --- location tracking (mutable on top of world.py's static data) ---

    def object_location(self, code: int) -> int | None:
        if code in self._location_overrides:
            return self._location_overrides[code]
        return self.world.object_location(code)

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
            "door_state_overrides": [
                [room, slot, code] for (room, slot), code in self._door_state_overrides.items()
            ],
            "money": self.money,
            "visited_rooms": sorted(self._visited_rooms),
            "bought_starter_weapons": self._bought_starter_weapons,
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
            "combat_monster_code": self._combat_monster_code,
            "combat_monster_hp": self._combat_monster_hp,
            "combat_awaiting": self._combat_awaiting,
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
        }
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return f"Spiel gespeichert ({path})."

    def load_save(self, path: Path) -> str:
        data = json.loads(path.read_text(encoding="utf-8"))
        self.current_room = data["current_room"]
        self.narrator = Character(data["narrator"])
        self._location_overrides = {int(k): v for k, v in data["location_overrides"].items()}
        self._door_state_overrides = {
            (room, slot): code for room, slot, code in data["door_state_overrides"]
        }
        self.money = data.get("money", 0)
        self._visited_rooms = set(data.get("visited_rooms", []))
        self._bought_starter_weapons = data.get("bought_starter_weapons", False)
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
        self._combat_monster_code = data.get("combat_monster_code")
        self._combat_monster_hp = data.get("combat_monster_hp")
        self._combat_awaiting = data.get("combat_awaiting")
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

    def look(self) -> str:
        room = self.world.room(self.current_room)
        title = room_title(self.current_room)
        header = f"[Raum {self.current_room}: {title}]" if title else f"[Raum {self.current_room}]"
        lines = [header]
        first_visit = self.current_room not in self._visited_rooms
        self._visited_rooms.add(self.current_room)
        text = None
        if first_visit:
            text = first_visit_text(self.story, self.current_room)
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

    def inventory(self) -> str:
        carried = self.objects_carried()
        if not carried:
            return "Ich trage nichts bei mir."
        return "Ich trage: " + ", ".join(self._object_display_name(o) for o in carried)

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

    def status(self) -> str:
        """The real "Zustandsübersicht" screen, same line order as the
        original (confirmed via a real DOSBox screenshot,
        `Status_anfang.png` - see PHASE0_FINDINGS.md UPDATE 23):
        Gesundheit, Stärke, Ansehen (party-wide), Astral, Hunger
        (party-wide), Durst - Aszhanti's column first, Smirga's second,
        matching the original's own layout."""
        lines = [
            "                    Aszhanti          Smirga",
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
        dagger+sword bundle - see FOROLL_* constants above. NOT wired
        into the generic candidate-resolution path buy() uses for
        MERCHANTS, since it isn't a lookup against item_stats.py at all.

        KNOWN GAP: this deducts the confirmed 7-Gerfs price and marks the
        purchase done, but does NOT hand over trackable "Dolch"/"Schwert"
        objects - their real object codes are UNRESOLVED (see
        PHASE0_FINDINGS.md UPDATE 27, which retracts an earlier "32=Dolch,
        33=Schwert" guess: those two codes turned out to have a tracked
        world-instance, a signal that - checked project-wide - means
        "person/creature", not "item", the same pattern that already
        identifies them as candidates for room 1's other family member(s)
        instead. `133` remains a single, unconfirmed candidate for
        Schwert specifically - matches the confirmed damage cap cleanly
        but lacks a second independent signal. Wire in real object codes
        here once they're properly confirmed."""
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
        merchant = self._merchant_here()
        if merchant is None:
            return "Hier ist kein Händler, bei dem ich etwas verkaufen könnte."
        _, info = merchant
        if not noun:
            return "Was soll ich verkaufen?"
        code = self._resolve_noun(noun, self.objects_carried())
        if code is None:
            return "Das trage ich nicht bei mir."
        price = self.item_stats.lookup(code, info["sell_field"])
        if price <= 0:
            return f"{info['name']} hat daran kein Interesse."
        self.money += price
        self._move_object(code, LIMBO_REMOVED)
        return f"Verkauft für {price} Gerfs. Ich habe jetzt {self.money} Gerfs."

    # --- equip (ANLEGEN - real armor-equip mechanic, confirmed via
    # sub_133BE - see PHASE0_FINDINGS.md UPDATE 23's follow-up) ---

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
        PHASE0_FINDINGS.md UPDATE 45). Narrow and purpose-built for the
        one confirmed use (handing the depleted Skarabäus to Mygra for
        recharging) - not a general give-to-NPC system; anything else
        is politely refused rather than silently accepted."""
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
        recipient_name = self._object_display_name(recipient_code)
        return f"{recipient_name} kann damit nichts anfangen."

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
    # spell choices now matches the real UI, but neither has a real
    # effect yet beyond LEVI (see combat.resolve_levi() and UPDATE 34):
    # weapon codes (Dolch/Schwert) are unresolved (UPDATE 27) and most
    # of the spell system isn't implemented (a separate, much larger
    # mechanic - UPDATE 24's spell follow-up) - see `_combat_answer()`'s
    # own docstring.
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

    def _start_combat(self, code: int) -> None:
        instance_idx = self.world.flags[code].instance_index
        self._combat_monster_code = code
        self._combat_monster_hp = self.world.instances[instance_idx].hp
        self._combat_awaiting = "weapon"

    def attack(self, noun: str | None) -> str:
        """Starts a fight against `noun` - an instance-tracked object
        (has_instance - see world.py's object_location docstring and
        PHASE0_FINDINGS.md UPDATE 26, which found that's almost always
        a person/creature, not an item) present in the current room.
        Immediately returns the weapon prompt rather than resolving a
        round - see this section's own docstring for the confirmed
        Q&A flow. If already fighting, just re-sends whichever prompt
        is currently pending (weapon or spell) instead of starting a
        new fight."""
        if self._combat_monster_code is None:
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

    def _combat_answer(self, raw: str, rng=random) -> str:
        """Handles the player's plain typed answer to whichever combat
        prompt is pending (`_combat_awaiting`) - routed here directly
        from `execute_chain()`, bypassing normal verb parsing entirely,
        the same way the real game's own combat Q&A works (you type
        "Schwert", not "attackiere Schwert").

        KNOWN SIMPLIFICATION: accepts any text as the weapon/spell
        choice; the weapon choice isn't applied to the round's math at
        all (real weapon modifiers are a separately documented gap -
        see this section's own docstring). "Fliehen" (and equivalents)
        is specially recognized at the weapon prompt, ending the fight
        via `flee()`. All 5 real spell names - "LEVI", "KUBL", "UNSI",
        "TOPA", "FEBR" - are recognized at the spell prompt and apply
        their confirmed real effects (see `combat.resolve_levi()`/
        `resolve_kubl()`/`resolve_unsi()`/`resolve_topa()`/
        `resolve_febr()`); any other typed text has no effect."""
        answer = raw.strip().lower()
        if self._combat_awaiting == "weapon":
            if answer in ("fliehen", "flee", "flieh"):
                self._combat_awaiting = None
                return self.flee()
            self._combat_awaiting = "spell"
            return self.SPELL_PROMPT

        result = self._resolve_combat_round(spell_choice=answer, rng=rng)
        if self._combat_monster_code is not None:
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
            self._combat_monster_code = None
            self._combat_monster_hp = None
            self._combat_awaiting = None
            self.running = False

    def _apply_kill(self, instance_idx: int) -> None:
        """Confirmed leveling-on-kill (UPDATE 22/23), shared by both
        melee and spell kills - applies regardless of which damage
        source landed the final blow."""
        self.aszhanti_strength += 1
        self.smirga_strength += self.monster_stats.strength_reward(instance_idx)
        self.aszhanti_max_health += 1
        self.smirga_max_health += 1
        self._combat_monster_code = None
        self._combat_monster_hp = None
        self._combat_awaiting = None

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
        code = self._combat_monster_code
        instance_idx = self.world.flags[code].instance_index
        monster = self.world.instances[instance_idx]
        name = self._object_display_name(code)

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
            self._apply_kill(instance_idx)
            return "\n".join(lines)

        self._check_player_death(lines)
        if not self.running:
            return "\n".join(lines)

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
                self._apply_kill(instance_idx)
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
                self._apply_kill(instance_idx)
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
                monster_code=code,
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
                self._apply_kill(instance_idx)

        return "\n".join(lines)

    def flee(self) -> str:
        """KNOWN SIMPLIFICATION: the real game's Fliehen option can
        fail ("Die Flucht mißlingt, da uns {monster} den Weg
        versperrt.", STORY message 1909) - the real success-chance
        formula wasn't traced (out of scope for this pass, see
        combat.py's docstring for what WAS ported). This always
        succeeds."""
        if self._combat_monster_code is None:
            return "Ich kämpfe gerade nicht."
        self._combat_monster_code = None
        self._combat_monster_hp = None
        self._combat_awaiting = None
        return "Mit aller Mühe gelingt es uns zu fliehen!"

    def _check_ambush(self, rng=random) -> str | None:
        """Port of the confirmed core of `sub_C301` (see
        PHASE0_FINDINGS.md UPDATE 30, corrected in UPDATE 48/49): a
        per-move chance for a currently-ACTIVE creature to appear and
        start a fight.

        CORRECTED (UPDATE 48): the real `sub_C301` SKIPS a candidate
        whose location equals `LIMBO_REMOVED` (299) - verified directly
        against raw bytes, twice, and confirmed by a second, separate
        function with the identical pattern. This project's first draft
        had the condition backwards (only considering candidates AT
        299). 299 doesn't mean "off-stage, waiting to wander" - it
        means "not currently active for this time-of-day phase" (see
        UPDATE 49: the day/night clock's dawn/nightfall subroutines
        toggle `DAY_ROSTER`/`NIGHT_ROSTER` members between a real room
        and 299 - `_advance_clock()` calls `_advance_day_night_roster()`
        at those exact transitions).

        KNOWN SIMPLIFICATION: the real game also restricts each
        creature to its own specific list of valid rooms (a far pointer
        this project couldn't resolve - see UPDATE 30) - not reproduced
        here, so any currently-active candidate can ambush in any room
        OUTSIDE Hyllok (user-confirmed: the village is a safe zone,
        room 10 - "Vor Hyllok" - is the confirmed first room where
        combat can occur at all - see `SAFE_ZONE_ROOMS`). Candidates
        are instance-tracked objects that are `ambush_eligible` (see
        world.py's `ObjectInstance`), NOT currently at the
        `LIMBO_REMOVED` sentinel, and not in `AMBUSH_EXCLUDED_CODES`
        (the confirmed room-bound creatures/objects - Steinkreuz,
        Bruckentroll, Tuatara, Lindwurm, Tatzelwurm - all flagged
        eligible in the raw data despite belonging to fixed encounters
        rather than the wandering pool, exposed by the location-
        condition fix above - see that constant's docstring). Confirmed
        roll: 1d6, triggers on > 3 (a clean 50% chance) - first
        eligible candidate (ascending object code) to roll a success
        wins, matching the real function's first-match-wins behavior.
        Does nothing if already fighting."""
        if self._combat_monster_code is not None:
            return None
        if self.current_room in SAFE_ZONE_ROOMS:
            return None
        for code in range(len(self.world.flags)):
            if code in AMBUSH_EXCLUDED_CODES:
                continue
            flag = self.world.flags[code]
            if not flag.has_instance:
                continue
            instance = self.world.instances[flag.instance_index]
            if not instance.ambush_eligible:
                continue
            if self.object_location(code) == LIMBO_REMOVED:
                continue
            if combat.d6(rng) <= 3:
                continue
            self._move_object(code, self.current_room)
            self._start_combat(code)
            name = self._object_display_name(code)
            return (
                f"Plötzlich, wie aus dem Nichts, taucht {name} auf und greift uns an.\n\n"
                f"{self.WEAPON_PROMPT}"
            )
        return None

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
        (object code 1 - identity not yet known by name, see
        names.py)."""
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

    HELP_TEXT = (
        "Bewegung: n/s/e/w/ne/se/sw/nw (oder 'gehe norden' usw.)\n"
        "schau                          - Raum ansehen\n"
        "untersuche <name-oder-#code>   - Objekt untersuchen\n"
        "nimm <name-oder-#code>         - Objekt aufnehmen\n"
        "lege <name-oder-#code>         - Objekt ablegen\n"
        "inventar                       - Was trage ich bei mir?\n"
        "kaufe <name-oder-#code>        - Bei einem Händler etwas kaufen\n"
        "verkaufe <name-oder-#code>     - Einem Händler etwas verkaufen\n"
        "anlege <name-oder-#code>       - Rüstung anlegen (aktueller Erzähler)\n"
        "gib <name-oder-#code> <empfänger> - Gegenstand übergeben\n"
        "schlafe / übernachte           - schlafen (nur nachts möglich)\n"
        "zustand                        - Zustandsübersicht (Stärke/Astral/Ansehen)\n"
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
        if command.verb in DIRECTIONS:
            return self.go(command.verb)
        if command.verb == "LOOK":
            return self.look()
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
        if command.verb == "ATTACK":
            return self.attack(command.noun)
        if command.verb == "FLEE":
            return self.flee()
        if command.verb == "EQUIP":
            return self.equip(command.noun)
        if command.verb == "GIVE":
            return self.give(command.noun)
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
        anything here - noon/dusk don't touch the roster."""
        if self.time_of_day == 0:
            for code, room in DAY_ROSTER.items():
                self._move_object(code, room)
            for code in NIGHT_ROSTER:
                self._move_object(code, LIMBO_REMOVED)
        elif self.time_of_day == 0x80:
            for code in DAY_ROSTER:
                self._move_object(code, LIMBO_REMOVED)
            for code, room in NIGHT_ROSTER.items():
                self._move_object(code, room)

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
            raw = prompt_with_default("\n> ", default).strip()
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
    repl()
