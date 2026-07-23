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
    ]
    for room, name, code in cases:
        game.current_room = room
        candidates = game.objects_in_room(room)
        assert code in candidates, f"object {code} not tracked in room {room}"
        assert resolve_name(name, candidates) == code


def test_object_35_has_no_name():
    """Regression test: object 35 ("tisch"/"holztisch") was a real
    mistake this project made and corrected - its own text span doesn't
    contain the word it was named after. Make sure it never comes back."""
    assert 35 not in OBJECT_NAMES


def test_unknown_word_resolves_to_none():
    assert resolve_name("bahnhof", [34, 99, 142]) is None


def test_name_only_matches_within_candidate_list():
    """A known name shouldn't resolve if its code isn't among the
    candidates passed in (e.g. the NPC isn't actually present)."""
    assert resolve_name("foroll", [99, 142]) is None
