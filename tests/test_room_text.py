"""
Regression tests for room_text.py - confirmed room "look" text and the
Smirga/Aszhanti narrator branching.
"""
from laas_port.characters import Character
from laas_port.room_text import look_text


def test_room_67_dorfplatz(story):
    """The very first confirmed anchor of this whole project - exact
    text match against a real DOSBox screenshot."""
    text = look_text(story, 67)
    assert "Dorfplatz von Hyllok" in text


def test_room_1_narrator_branch(story):
    """Room 1 (Aszhantis Elternhaus) branches on the narrator: Aszhanti
    narrating uses first-person ("mein Elternhaus"), Smirga narrating
    uses third-person ("Aszhantis Elternhaus"). Confirmed by
    disassembling the room's real handler (flat 0x147bd) - see
    characters.py."""
    aszhanti_text = look_text(story, 1, Character.ASZHANTI)
    smirga_text = look_text(story, 1, Character.SMIRGA)
    assert "mein Elternhaus" in aszhanti_text
    assert "Aszhantis Elternhaus" in smirga_text
    assert aszhanti_text != smirga_text


def test_room_5_and_6_not_swapped(story):
    """Regression test for a real bug this session: room 5 (the
    Hühnerstall/chicken coop) and room 6 (Aszhantis Zimmer) were
    initially swapped by a graph-isomorphism-only pass. Room 1's real
    exit graph and its own text (see test_world.py) proved the fix."""
    room5_text = look_text(story, 5)
    room6_text = look_text(story, 6)
    assert "Hühnerstall" in room5_text
    assert "Zimmer" in room6_text


def test_room_12_second_narrator_pair(story):
    """A second, independent Smirga/Aszhanti narrator pair (messages
    233/234) found in room 12's text - opposite naming convention from
    room 1/6 (here the narrator refers to the OTHER party member by
    name) but the same underlying mechanism."""
    aszhanti_text = look_text(story, 12, Character.ASZHANTI)
    smirga_text = look_text(story, 12, Character.SMIRGA)
    assert "Smirga und ich" in aszhanti_text
    assert "Aszhanti und ich" in smirga_text


def test_room_88_gultibas_bedroom(story):
    """Recovered via a real tool bug fix (segment-boundary, not a scanner
    artifact) - see room_text.py's comment on room 88 and
    tools/room_handler_by_address.py's resolve_all_with_messages()."""
    text = look_text(story, 88)
    assert "Ehebruch" in text
    assert "Gultibas Schlafzimmer" in text


def test_unmapped_room_returns_none(story):
    assert look_text(story, 999) is None


def test_all_confirmed_rooms_resolve_without_error(story):
    """Every room_number in ROOM_LOOK_MESSAGE should produce non-empty
    text for both narrators - a broad smoke test that catches typos in
    message indices immediately rather than only when a specific room
    is visited."""
    from laas_port.room_text import ROOM_LOOK_MESSAGE

    for room_number in ROOM_LOOK_MESSAGE:
        for narrator in (Character.SMIRGA, Character.ASZHANTI):
            text = look_text(story, room_number, narrator)
            assert text and len(text.strip()) > 0, room_number
