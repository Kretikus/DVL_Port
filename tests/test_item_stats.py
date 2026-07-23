"""
Regression tests for item_stats.py - the WORLD Section 1 price/stats
table, confirmed byte-for-byte via Unicorn emulation of the real
sub_E6A1 lookup function (see item_stats.py's module docstring and the
`laas` analysis project's tools/unicorn_price.py / PHASE0_FINDINGS.md
"UPDATE 16").
"""
from pathlib import Path

from laas_port.item_stats import ItemStats

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"


def test_known_object_all_fields():
    stats = ItemStats.load(ASSETS_DIR)
    assert stats.lookup(233, 1) == 100
    assert stats.lookup(233, 2) == 500
    assert stats.lookup(233, 3) == 100
    assert stats.lookup(233, 4) == 600


def test_buy_price_is_field_2():
    stats = ItemStats.load(ASSETS_DIR)
    assert stats.buy_price(233) == 500


def test_unknown_object_returns_zero():
    stats = ItemStats.load(ASSETS_DIR)
    assert stats.lookup(9999, 2) == 0
    assert stats.buy_price(9999) == 0


def test_duplicate_key_returns_first_match():
    """Object 14 appears TWICE in the real WORLD data with different
    stats ((15,30,25,40) and (20,50,30,55)) - a genuine duplicate key
    in the shipped game. sub_E6A1 is a linear search that stops at the
    first match, confirmed via emulation - the second row is dead data,
    unreachable through this lookup in the real game. Locks in that
    behavior rather than a dict's "last write wins" semantics."""
    stats = ItemStats.load(ASSETS_DIR)
    matches = [r for r in stats.records if r[0] == 14]
    assert len(matches) == 2, "test fixture assumption changed - re-check WORLD data"
    assert stats.lookup(14, 1) == matches[0][1]
    assert stats.lookup(14, 1) != matches[1][1]
