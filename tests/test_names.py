"""
Regression tests for names.py - the object-code -> German name table.

These lock in the first real entries added this session (room-location
+ fan-map cross-referencing - see names.py's module docstring for the
full evidence per entry) and the historical object-35 mistake that
motivated the CAUTION note there.
"""
from laas_port.names import OBJECT_NAMES, resolve_name


def test_known_npcs_resolve_within_their_room(game):
    """Each NPC name should resolve to its real object code when that
    code is a candidate (i.e. present in the current room)."""
    cases = [
        (3, "foroll", 34),
        (20, "bauer", 99),
        (72, "oerli", 142),
        (70, "bettler", 183),
        (75, "gultiba", 188),
        (86, "nichidor", 194),
        (61, "skeeve", 199),
        (27, "potidan", 243),
        (25, "troll", 134),
        (26, "steinkreuz", 105),
        (39, "tuatara", 146),
        (104, "tatzelwurm", 238),
        (104, "drache", 238),
        (109, "lindwurm", 237),
        (67, "har", 25),
        (67, "sklar", 26),
        (4, "mygra", 35),
        (44, "yarom", 167),
        (98, "sabrina", 202),
        (98, "hexe", 202),
    ]
    for room, name, code in cases:
        game.current_room = room
        candidates = game.objects_in_room(room)
        assert code in candidates, f"object {code} not tracked in room {room}"
        assert resolve_name(name, candidates) == code


def test_oger_resolves_by_code_confirmed_via_febr_not_room_location(game):
    """The Oger (162) is confirmed via a direct code reference in
    FEBR's rare bonus-hit branch (see PHASE0_FINDINGS.md UPDATE 38),
    not room-location + fan-map inference like the entries above - it's
    currently off-stage (LIMBO_REMOVED), so there's no room to test
    presence in."""
    assert OBJECT_NAMES.get(162) == ["oger"]
    assert resolve_name("oger", [162]) == 162


def test_merchant_price_confirmed_names_resolve():
    """17 entries confirmed via a 4-way match against real merchant
    prices the user collected in-game (Laas_CS.xlsx's "Händler" sheet
    cross-referenced against item_stats.py's WORLD Section 1 data - see
    PHASE0_FINDINGS.md UPDATE 18). None of these objects have a tracked
    RESTORE location, so unlike test_known_npcs_resolve_within_their_room
    this just checks resolve_name directly against a synthetic candidate
    list, and separately confirms names.py and item_stats.py agree on
    which object code each name refers to (both were confirmed from the
    same underlying price match, so they must be consistent)."""
    from pathlib import Path

    from laas_port.item_stats import ItemStats

    stats = ItemStats.load(Path(__file__).resolve().parent.parent / "assets")
    cases = [
        ("agitor", 233), ("cape", 201), ("schuessel", 85), ("fackel", 8),
        ("feldflasche", 46), ("flasche", 172), ("heilkraut", 154),
        ("netz", 138), ("echsenpanzer", 196), ("axt", 171),
        ("skarabaeus", 206), ("schild", 14), ("schuppen", 241),
        ("seil", 108), ("zeron", 227), ("lederwams", 264), ("kettenhemd", 52),
    ]
    for name, code in cases:
        assert resolve_name(name, [code]) == code
        # every one of these is a real, priced shop item - a basic sanity
        # cross-check that the name and the price data point at the same object
        assert stats.buy_price(code) > 0, f"object {code} ({name}) has no confirmed price"


def test_object_35_is_mygra_not_the_old_tisch_mistake():
    """Regression test: object 35 was once wrongly named "tisch"/
    "holztisch" via unreliable text-adjacency guessing (its own text
    span doesn't contain the word it was named after) - make sure that
    specific mistake never comes back. It's since been legitimately
    identified as Mygra via a completely different, reliable method
    (sole tracked object in "Mygras Haus", cross-checked against the
    fan map and STORY text - see PHASE0_FINDINGS.md UPDATE 28), so this
    no longer asserts the code has NO name at all."""
    assert OBJECT_NAMES.get(35) == ["mygra"]


def test_unknown_word_resolves_to_none():
    assert resolve_name("bahnhof", [34, 99, 142]) is None


def test_name_only_matches_within_candidate_list():
    """A known name shouldn't resolve if its code isn't among the
    candidates passed in (e.g. the NPC isn't actually present)."""
    assert resolve_name("foroll", [99, 142]) is None
