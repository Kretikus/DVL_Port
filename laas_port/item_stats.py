"""
item_stats.py - WORLD file Section 1, the item stats/price table.

Confirmed via direct instruction-level emulation (Unicorn) of the real
game's lookup function, `sub_E6A1` (flat `0xE6A3`) - see the `laas`
analysis project's `tools/unicorn_price.py` and PHASE0_FINDINGS.md
"UPDATE 16" for the full derivation. `sub_E6A1(key, field_index)`
linear-searches this table for a record whose object code matches
`key` and returns that record's field `field_index` (1-4), or 0 if no
record matches. Verified byte-for-byte against the real function for
every record and field in the shipped WORLD file (136/136 checks).

Record layout (10 bytes, `-1,-1,-1,-1,-1`-terminated):
    object_code: i16
    field1, field2, field3, field4: i16

Field 2 is confirmed (seg005_batch4.md fn 10, cross-checked against
`word_2B974`, the player's money global) as the price the player pays
to BUY the item from a shop. Fields 1 and 3 are confirmed (same batch,
a different call site) as two DIFFERENT merchant NPCs' (Yarom, Gultiba)
buy-FROM-player offers for the same item - not interchangeable with
field 2's meaning, and not necessarily equal to each other.

IMPORTANT, confirmed via emulation: object code 14 appears TWICE in the
real table with different stats (`(15,30,25,40)` and `(20,50,30,55)`).
`sub_E6A1` is a linear search that stops at the FIRST match, so the
real game can only ever produce the first row's values for object 14 -
the second row is permanently dead data. `ItemStats.lookup()` below
reproduces this exactly (first match wins), not a dict-based "last
write wins" table, since that would silently disagree with the real
function on this one object.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

CHUNK_INDEX = 0   # WORLD's 13 sections; section 1 is index 0
RECORD_SIZE = 10
SENTINEL = (-1, -1, -1, -1, -1)


@dataclass
class ItemStats:
    records: list[tuple[int, int, int, int, int]]

    @classmethod
    def load(cls, assets_dir: Path) -> "ItemStats":
        data = (assets_dir / "WORLD").read_bytes()
        sizes = struct.unpack_from("<13H", data, 2)
        offset = 2 + 13 * 2
        chunk = data[offset : offset + sizes[CHUNK_INDEX]]
        records = []
        for i in range(0, len(chunk), RECORD_SIZE):
            rec = struct.unpack_from("<5h", chunk, i)
            if rec == SENTINEL:
                break
            records.append(rec)
        return cls(records=records)

    def lookup(self, object_code: int, field_index: int) -> int:
        """Faithful port of sub_E6A1: first record whose object code
        matches, field `field_index` (1-4); 0 if no record matches."""
        for obj_code, f1, f2, f3, f4 in self.records:
            if obj_code == object_code:
                return {1: f1, 2: f2, 3: f3, 4: f4}[field_index]
        return 0

    def buy_price(self, object_code: int) -> int:
        """Field 2 - the price the player pays to buy this item from a
        shop (confirmed via seg005_batch4.md fn 10's word_2B974 check).
        0 if this object isn't a shop item at all."""
        return self.lookup(object_code, 2)
