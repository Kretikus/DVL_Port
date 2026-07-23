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
  - Combat and shopping are NOT ported - both depend on runtime-
    populated data tables (weapon-class/dice-roll formulas, a price
    table) whose initialization code hasn't been located in the binary;
    porting either faithfully needs that data found first, not just
    more verb-dispatch plumbing.
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
import sys
from pathlib import Path

from .story import Story
from .world import (
    World,
    LIMBO_CARRIED,
    DIRECTION_NAMES,
    DIRECTION_SLOTS,
    DOOR_OPEN,
    DOOR_CLOSED,
    DOOR_LOCKED,
)
from .item_stats import ItemStats
from .objects import ObjectTable
from .room_text import look_text
from .room_titles import room_title
from .names import resolve_name
from .parser import parse, parse_chain, Command, DIRECTION_WORDS
from .characters import Character, DEFAULT_NARRATOR

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


class GameState:
    def __init__(self, assets_dir: Path = DEFAULT_ASSETS_DIR):
        self.story = Story.load(assets_dir)
        self.world = World.load(assets_dir)
        self.objects = ObjectTable.load(assets_dir)
        self.item_stats = ItemStats.load(assets_dir)
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

    # --- location tracking (mutable on top of world.py's static data) ---

    def object_location(self, code: int) -> int | None:
        if code in self._location_overrides:
            return self._location_overrides[code]
        return self.world.object_location(code)

    def objects_in_room(self, room_number: int) -> list[int]:
        return [
            code
            for code in range(len(self.world.flags))
            if self.object_location(code) == room_number
        ]

    def objects_carried(self) -> list[int]:
        return [
            code
            for code in range(len(self.world.flags))
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
        text = look_text(self.story, self.current_room, self.narrator)
        if text is not None:
            lines.append(text)
        else:
            lines.append("(Raumbeschreibung noch nicht bekannt)")
        objs = self.objects_in_room(self.current_room)
        if objs:
            lines.append("Objekte hier: " + ", ".join(f"#{o}" for o in objs))
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

    def go(self, direction: str) -> str:
        direction = direction.upper()
        room = self.world.room(self.current_room)
        exits = room.available_exits()
        if direction not in exits:
            return "Dort kann ich nicht hingehen."
        self.current_room = exits[direction].dest_room
        return self.look()

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
        return "Ich trage: " + ", ".join(f"#{o}" for o in carried)

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

    def execute_chain(self, raw: str) -> list[str]:
        """Real port of sub_14202's comma-chaining (see parser.py's
        module docstring): runs every comma-separated command in `raw`
        in sequence, stopping early if a command sets `running=False`
        (QUIT). Returns each command's non-empty result in order."""
        results = []
        for command in parse_chain(raw):
            result = self.execute(command)
            if result:
                results.append(result)
            if not self.running:
                break
        return results


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
    while state.running:
        try:
            raw = input("\n> ").strip()
        except EOFError:
            break
        if not raw:
            continue
        for result in state.execute_chain(raw):
            print(result)


if __name__ == "__main__":
    repl()
