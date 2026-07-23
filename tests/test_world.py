"""
Regression tests for world.py - the room exit graph, compass-direction
mapping, and object-instance/location tracking.
"""
from laas_port.world import ROOM_COUNT, DIRECTION_NAMES, DOOR_LOCKED


def test_room_count(world):
    assert len(world.rooms) == ROOM_COUNT


def test_compass_mapping_confirmed_via_room_67(world):
    """Room 67 (Auf dem Dorfplatz) is the anchor this mapping was derived
    from - see world.py's DIRECTION_NAMES docstring. N->1 (Aszhantis
    Elternhaus), E->10 (Vor Hyllok), SW->3 (Schmiede), W->2 (Smirgas
    Elternhaus) are all independently confirmed via real game text."""
    exits = world.room(67).available_exits()
    assert exits["N"].dest_room == 1
    assert exits["E"].dest_room == 10
    assert exits["SW"].dest_room == 3
    assert exits["W"].dest_room == 2


def test_room_1_exits_to_5_and_6_not_swapped(world):
    """Regression test for a real bug this session: an earlier
    graph-isomorphism-only pass had swapped rooms 5 and 6. Room 1's exit
    graph is ground truth - N goes to room 6 (Aszhantis Zimmer), E to
    room 5 (Hühnerstall)."""
    exits = world.room(1).available_exits()
    assert exits["N"].dest_room == 6
    assert exits["E"].dest_room == 5


def test_exit_reciprocity_for_a_sample_of_confirmed_rooms(world):
    """Every confirmed room in room_text.py's second batch was verified
    to have fully reciprocal edges against the real exit graph before
    being trusted - spot-check a few of the longer chains here so a
    future edit to world.py loading can't silently break that."""
    pairs = [
        (10, "N", 11, "S"),
        (24, "N", 22, "S"),
        (45, "N", 70, "S"),
        (81, "E", 82, "W"),
    ]
    for room_a, dir_a, room_b, dir_b in pairs:
        exits_a = world.room(room_a).available_exits()
        exits_b = world.room(room_b).available_exits()
        assert exits_a[dir_a].dest_room == room_b
        assert exits_b[dir_b].dest_room == room_a


def test_room_0x55_has_a_genuinely_locked_door(world):
    """Confirmed against real shipped data: room 0x55 (85) has a real
    pre-locked door in RESTORE - the one deliberate lock/unlock puzzle
    door predicted by the seg005 disassembly (see game.py's UNLOCK_ROOM)."""
    exits = world.room(0x55).exits
    assert any(e.msg_code == DOOR_LOCKED for e in exits)


def test_direction_names_length_matches_stride():
    assert len(DIRECTION_NAMES) == 8
