"""
monster_stats.py - WORLD file Section 5 (0-based index 4), the per-
creature combat stats table read by `sub_879F` (the real combat
resolver - see the `laas` analysis project's PHASE0_FINDINGS.md UPDATE
17/22/24/28).

Confirmed via direct disassembly trace: `sub_879F` computes
`bx = word_b3f2 + instance_index*3` and reads three bytes from that
3-byte record - the creature's outgoing-damage dice count, a flat
damage bonus added after the dice, and the Strength points the
attacking character (Smirga) gains for landing the killing blow. Table
base (`word_b3f2`) resolves to exactly this WORLD section, verified by
matching the WORLD-sections memory-layout initializer's own pointer
math (`base + sum(section_sizes[0:4])`) - see UPDATE 24's correction of
an earlier wrong section identification for a full account of how
easy it is to get this indexing wrong.

Indexed by INSTANCE INDEX (0-38, matching `world.py`'s `ObjectInstance.
index` / `INSTANCE_COUNT`), NOT object code directly - exactly 39
records, no sentinel needed (the table's own size is the full 39*3
bytes with nothing else after it).

`dice_bonus` can be negative (byte 36 in the shipped WORLD file is
0xfe = -2, signed) - stored as a signed byte here.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

CHUNK_INDEX = 4  # WORLD's 13 sections, 0-based; this is the 5th section
RECORD_SIZE = 3
RECORD_COUNT = 39  # matches world.py's INSTANCE_COUNT


@dataclass
class MonsterStats:
    records: list[tuple[int, int, int]]

    @classmethod
    def load(cls, assets_dir: Path) -> "MonsterStats":
        data = (assets_dir / "WORLD").read_bytes()
        sizes = struct.unpack_from("<13H", data, 2)
        offset = 2 + 13 * 2 + sum(sizes[:CHUNK_INDEX])
        chunk = data[offset : offset + sizes[CHUNK_INDEX]]
        # All three bytes are read via `cwde` (sign-extend AL) in the
        # real code, so all three are signed here, not just the ones
        # observed negative in the shipped data.
        records = [
            struct.unpack_from("<bbb", chunk, i)
            for i in range(0, RECORD_COUNT * RECORD_SIZE, RECORD_SIZE)
        ]
        return cls(records=records)

    def dice_count(self, instance_index: int) -> int:
        return self.records[instance_index][0]

    def dice_bonus(self, instance_index: int) -> int:
        return self.records[instance_index][1]

    def strength_reward(self, instance_index: int) -> int:
        return self.records[instance_index][2]
