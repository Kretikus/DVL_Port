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

FIELD SEMANTICS, fully confirmed (corrected from an earlier, incomplete
reading): cross-referenced every record against real prices the user
collected in-game from both merchants (Laas_CS.xlsx's "Händler" sheet)
by matching all 4 fields simultaneously - a 4-way numeric match per
item, not a single-field coincidence. The two merchant NPCs are
**Yarom** and **Gultiba** (named in seg005_batch4.md's resolved dialogue
text), and each has his OWN separate buy-from-player and sell-to-player
price - NOT one shared "buy price" as an earlier pass here assumed:

    field1 = Yarom's buy-FROM-player offer   ("Verkaufen" in the sheet)
    field2 = price to buy FROM Yarom         ("Kaufen" in the sheet)
    field3 = Gultiba's buy-FROM-player offer ("Verkaufen" in the sheet)
    field4 = price to buy FROM Gultiba       ("Kaufen" in the sheet)

`buy_price()` below returns field 2 (Yarom's price) as a convenience
default - Gultiba's own buy price (field 4) can differ and isn't
exposed as a separate method yet.

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
        """Field 2 - the price to buy this item from Yarom specifically
        (see the module docstring's corrected field semantics). 0 if
        this object isn't one of Yarom's shop items at all."""
        return self.lookup(object_code, 2)
