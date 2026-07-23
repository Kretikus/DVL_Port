"""
A broad integration test: BFS-walk the ENTIRE real exit graph starting
from room 67 (the confirmed starting room), using the actual
parser+execute() path (not direct room-number assignment) for every
step. This exercises real navigation across all rooms reachable from
the confirmed anchors - not just the 62 with confirmed "look" text -
so it catches navigation-layer bugs (parser/direction handling,
GameState.go()) independent of room-text coverage.
"""
import collections

from laas_port.parser import parse
from laas_port.room_text import ROOM_LOOK_MESSAGE
from laas_port.world import DIRECTION_NAMES, ROOM_COUNT


def _reachable_from(world, start):
    visited = {start}
    queue = collections.deque([start])
    edges = []
    while queue:
        room = queue.popleft()
        for direction, exit_ in world.room(room).available_exits().items():
            dest = exit_.dest_room
            edges.append((room, direction, dest))
            if 0 < dest < ROOM_COUNT and dest not in visited:
                visited.add(dest)
                queue.append(dest)
    return visited, edges


def test_full_graph_is_navigable_without_error(game):
    """Walk every real edge reachable from room 67 via the actual
    parse()+execute() path. No move should raise, and every move should
    land GameState.current_room on the edge's real destination."""
    game.current_room = 67
    visited, edges = _reachable_from(game.world, 67)

    # Sanity: this is the same well-connected component found and
    # verified by hand during room_text.py's construction - if this
    # shrinks significantly, something about world.py's loading broke.
    assert len(visited) >= 90

    for room, direction, dest in edges:
        game.current_room = room
        result = game.execute(parse(direction.lower()))
        assert game.current_room == dest, (room, direction, dest, result)


def test_confirmed_rooms_produce_real_text_during_traversal(game):
    """For every room with confirmed look text (room_text.py), walking
    into it via execute() should show that real text, not the
    "not yet known" placeholder."""
    game.current_room = 67
    visited, edges = _reachable_from(game.world, 67)
    by_dest = {}
    for room, direction, dest in edges:
        by_dest.setdefault(dest, (room, direction))

    for room_number in ROOM_LOOK_MESSAGE:
        if room_number == 67 or room_number not in by_dest:
            continue
        src, direction = by_dest[room_number]
        game.current_room = src
        result = game.execute(parse(direction.lower()))
        assert "noch nicht bekannt" not in result, room_number


def test_all_direction_words_are_covered():
    """DIRECTION_NAMES and the parser's direction-word table must stay
    in sync - a mismatch here would silently break navigation for
    whichever direction fell out of sync."""
    from laas_port.parser import DIRECTION_WORDS

    covered = set(DIRECTION_WORDS.values())
    assert covered == set(DIRECTION_NAMES)
