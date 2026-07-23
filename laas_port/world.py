"""
world.py - the room graph and object-instance/location data.

All of this comes from the RESTORE save file, not WORLD (WORLD turned
out to hold only item stats/description-pointer/event tables unrelated
to room connectivity - see the `laas` analysis project's
PHASE0_FINDINGS.md, "UPDATE 3"). Room exits themselves are NOT
compile-time data in the original binary either - they're the first of
several fixed-size state chunks loaded from RESTORE at startup, which
makes sense once you notice they never change during play, so any save
file (including the one shipped with the original game) carries the
real, permanent map.

RESTORE's chunk layout (all offsets confirmed by tracing the real
save/restore routine byte-for-byte - see PHASE0_FINDINGS.md UPDATE 4/5):

    offset   size     contents
    0x0000   0x0DA0   room exit table      (109 rooms x 32 bytes)
    0x0DA0   0x04E0   object instance table (39 entries x 32 bytes)
    0x1280   0x2EE0   object description table (250 entries x 48 bytes) - see objects.py
    0x4160   0x01F4   object flags array   (250 entries x 2 bytes)
    0x4354   1        unidentified flag byte
    0x4355   0x006D   per-room byte array #1 (unidentified)
    0x43C2   0x006D   per-room byte array #2 (unidentified)
    0x442F   0x01F4   unidentified 250-entry x 2-byte array
    0x4623   0x00F0   unidentified 240-byte block
    0x4713   2        current room number (word_b34e)
    0x4715   1        dragon mood/relationship gauge (word_b40a)
    0x4716   2        unidentified word
                      (total 0x4718 = 18200 bytes, matches RESTORE exactly)

Only the exit table, object instance table, and object flags are
understood well enough to use here; the rest are preserved as raw
bytes on the `World` object for future work (e.g. `world.chunks`).
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path

ROOM_COUNT = 109
ROOM_STRIDE = 32
DIR_STRIDE = 4
NUM_DIRECTIONS = ROOM_STRIDE // DIR_STRIDE  # 8

INSTANCE_COUNT = 39
INSTANCE_STRIDE = 32
INSTANCE_LOCATION_OFFSET = 6  # word at this offset = the object's current room

FLAG_COUNT = 250

# Direction slot -> compass label. CONFIRMED against real gameplay text
# and user-verified directions from room 67 (Auf dem Dorfplatz), which has
# real exits in 5 of its 8 slots - a clockwise-from-north ordering, one
# compass point per slot:
#   slot 0 (N)  -> room 1  "Aszhantis Elternhaus" - game text: "Im Norden
#                  steht das Häuschen von Aszhantis Eltern"
#   slot 2 (E)  -> room 10 "Vor Hyllok"           - game text: "Im Osten
#                  bilden... einen Durchgang, der hinaus... führt"
#   slot 4 (S)  -> room 4  "Beim Scharlatan"      - matches the fan map's
#                  spatial layout (drawn directly south of the square);
#                  not yet confirmed by in-game text directly
#   slot 5 (SW) -> room 3  "Schmiede"             - user-confirmed directly
#                  ("Southwest of Dorfplatz ist die Schmiede")
#   slot 6 (W)  -> room 2  "Smirgas Elternhaus"   - game text: "Im Westen
#                  steht das Elternhaus von Smirga"
# An earlier placeholder guess (N,S,E,W,NE,SE,SW,NW - compass-then-
# diagonals) was WRONG; this clockwise ordering is the one that makes all
# 4 independently-confirmed slots (0, 2, 5, 6) match simultaneously.
DIRECTION_NAMES = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
DIRECTION_SLOTS = {name: i for i, name in enumerate(DIRECTION_NAMES)}

# Sentinel "not really a room" locations seen throughout the original
# game's object-relocation code.
LIMBO_CARRIED = 0x96   # "in hand" / carried by the player
LIMBO_REMOVED = 0x12B  # "off-stage" - can still randomly reappear (unmodeled here)

# Exit `dest_room` sentinels, found while writing tests/test_traversal.py
# (an earlier bug let GameState.go() walk straight into these and crash
# with an IndexError - Exit.usable now excludes them). Two distinct
# values appear across the exit table, only one of which is a plain
# "no exit" marker:
#   999  - a real "you can't go that way" dead end. The original's own
#          movement handler explicitly special-cases dest_room==0x3e7
#          (999) with a "can't go that way" message (varying by mood) -
#          see PHASE0_FINDINGS.md / seg005_batch3.md - so this is
#          intentional data, not corruption, and matches the fan map's
#          own "ENDE DER KARTE" nodes.
#   109  - one past the valid room range (0-108: ROOM_COUNT rooms).
#          Likely a special game-ending trigger (see seg005_batch3.md's
#          note on room 0x6d/109 being probed by dedicated per-room
#          hooks) rather than a generic sentinel - not modeled yet, so
#          treated as unusable like 999 until ending/win-state handling
#          exists.

# `Exit.msg_code` doubles as a LIVE, MUTABLE DOOR STATE for exits that are
# actual doors (confirmed via `sub_EEC0`, flat 0xEEC0, the shared
# OPEN/CLOSE/LOCK/UNLOCK mutator - see `laas` analysis project's
# decompiled/seg005_batch5.md). Not every msg_code value is a door state -
# these three are the ones the original's door verbs actually recognize;
# other values (1, 3, 4, 5, 8, 9, 11, 13, ...) are unrelated per-exit
# message selectors (e.g. flavor text), not door states, and are left
# alone by the door verbs' state scans.
DOOR_OPEN = 2
DOOR_CLOSED = 6
DOOR_LOCKED = 7

_CHUNK_OFFSETS = {
    "exits": (0x0000, 0x0DA0),
    "instances": (0x0DA0, 0x04E0),
    "descriptions": (0x1280, 0x2EE0),  # consumed by objects.py, not here
    "flags": (0x4160, 0x01F4),
    "unident_flag": (0x4354, 1),
    "unident_room_a": (0x4355, 0x006D),
    "unident_room_b": (0x43C2, 0x006D),
    "unident_250x2": (0x442F, 0x01F4),
    "unident_240": (0x4623, 0x00F0),
    "current_room": (0x4713, 2),
    "dragon_mood": (0x4715, 1),
    "unident_tail": (0x4716, 2),
}


@dataclass
class Exit:
    msg_code: int
    dest_room: int  # 0 means "no exit this direction"

    @property
    def usable(self) -> bool:
        # dest_room != 0 excludes "no exit this direction"; dest_room <
        # ROOM_COUNT excludes the 999/109 sentinels (see the module-level
        # note above) - both are out of GameState.room()'s valid range and
        # would otherwise crash movement with an IndexError.
        return self.dest_room != 0 and self.dest_room < ROOM_COUNT


@dataclass
class Room:
    number: int
    exits: list[Exit]  # length NUM_DIRECTIONS, index by direction slot

    def available_exits(self) -> dict[str, "Exit"]:
        return {
            DIRECTION_NAMES[i]: ex
            for i, ex in enumerate(self.exits)
            if ex.usable
        }


@dataclass
class ObjectInstance:
    index: int
    raw: bytes

    @property
    def location(self) -> int:
        return struct.unpack_from("<H", self.raw, INSTANCE_LOCATION_OFFSET)[0]


@dataclass
class ObjectFlags:
    raw_word: int

    @property
    def has_instance(self) -> bool:
        return bool(self.raw_word & 0x8000)

    @property
    def instance_index(self) -> int:
        return self.raw_word & 0x7FFF


@dataclass
class World:
    rooms: list[Room]
    instances: list[ObjectInstance]
    flags: list[ObjectFlags]
    chunks: dict[str, bytes] = field(repr=False)

    @classmethod
    def load(cls, assets_dir: Path) -> "World":
        data = (assets_dir / "RESTORE").read_bytes()

        chunks = {}
        for name, (offset, size) in _CHUNK_OFFSETS.items():
            chunks[name] = data[offset : offset + size]

        rooms = []
        exit_blob = chunks["exits"]
        for room_no in range(ROOM_COUNT):
            rec = exit_blob[room_no * ROOM_STRIDE : (room_no + 1) * ROOM_STRIDE]
            exits = []
            for d in range(NUM_DIRECTIONS):
                msg_code, dest = struct.unpack_from("<Hh", rec, d * DIR_STRIDE)
                exits.append(Exit(msg_code=msg_code, dest_room=dest))
            rooms.append(Room(number=room_no, exits=exits))

        instance_blob = chunks["instances"]
        instances = [
            ObjectInstance(index=i, raw=instance_blob[i * INSTANCE_STRIDE : (i + 1) * INSTANCE_STRIDE])
            for i in range(INSTANCE_COUNT)
        ]

        flags_blob = chunks["flags"]
        flags = [
            ObjectFlags(raw_word=struct.unpack_from("<H", flags_blob, i * 2)[0])
            for i in range(FLAG_COUNT)
        ]

        return cls(rooms=rooms, instances=instances, flags=flags, chunks=chunks)

    def room(self, number: int) -> Room:
        return self.rooms[number]

    def object_location(self, object_code: int) -> int | None:
        """Current room of `object_code`, or None if it has no tracked
        instance (most of the 250 objects are static/scenery and never
        move - only the 39 tracked instances do)."""
        if object_code >= len(self.flags):
            return None
        flag = self.flags[object_code]
        if not flag.has_instance or flag.instance_index >= len(self.instances):
            return None
        return self.instances[flag.instance_index].location

    def objects_in_room(self, room_number: int) -> list[int]:
        """Only finds objects with a TRACKED instance (39 of the 250
        object codes - the ones that can actually move: NPCs, monsters,
        carried/movable items). The other ~211 object codes are static
        scenery with no location record in this system at all, and
        their room association hasn't been traced yet (see objects.py's
        module docstring) - this will under-report what's really in a
        room until that's solved."""
        return [
            code
            for code in range(len(self.flags))
            if self.object_location(code) == room_number
        ]
