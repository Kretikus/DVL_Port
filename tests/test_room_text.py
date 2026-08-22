"""
Regression tests for room_text.py - confirmed room "look" text and the
Smirga/Aszhanti narrator branching.
"""
from laas_port.characters import Character
from laas_port.room_text import first_visit_text, look_text


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


def test_room_1_first_visit_appends_the_breakfast_scene(story):
    """UPDATE 89: unlike every other ROOM_FIRST_VISIT_MESSAGE entry
    (which REPLACES the base look text on the first visit), room 1's
    real handler prints the base description unconditionally and then
    APPENDS message 99 (Sklar/Phira's breakfast-table scene) the first
    time only - modeled by duplicating the base narrator structure in
    the first-visit entry itself, not by changing first_visit_text()'s
    own replace semantics."""
    first = first_visit_text(story, 1)
    assert "mein Elternhaus" in first  # the base description is still there
    assert "Setzt euch" in first  # ...with the breakfast scene appended
    repeat = look_text(story, 1)
    assert "Setzt euch" not in repeat


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
    tools/room_handler_by_address.py's resolve_all_with_messages().
    UPDATE 87 split this into a first-visit scene (the affair itself)
    and the room's plain standing text, same shape as room 4."""
    assert "Ehebruch" in first_visit_text(story, 88)
    assert "Gultibas Schlafzimmer" in look_text(story, 88)


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


def test_first_visit_text_returns_none_for_a_room_with_no_scripted_scene(story):
    assert first_visit_text(story, 999) is None
    assert first_visit_text(story, 67) is None  # a mapped room, just no scripted scene


def test_room_4_first_visit_text_narrator_branch(story):
    """Confirmed via room_handler_by_address.py plus a user-supplied
    screenshot (see room_text.py's comment on ROOM_FIRST_VISIT_MESSAGE's
    room-4 entry) - Mygra's greeting clause is narrator-dependent, same
    (smirga_msg, aszhanti_msg) tuple convention as look_text()."""
    aszhanti_text = first_visit_text(story, 4, Character.ASZHANTI)
    smirga_text = first_visit_text(story, 4, Character.SMIRGA)
    assert "grüße ich ihn freundlich" in aszhanti_text
    assert "grüßt ihn Aszhanti freundlich" in smirga_text
    assert "Als er seinen Monolog endlich beendet hat" in aszhanti_text
    assert aszhanti_text != smirga_text


def test_all_first_visit_scenes_resolve_without_error(story):
    """Same broad smoke test as test_all_confirmed_rooms_resolve_without_error,
    for ROOM_FIRST_VISIT_MESSAGE."""
    from laas_port.room_text import ROOM_FIRST_VISIT_MESSAGE

    for room_number in ROOM_FIRST_VISIT_MESSAGE:
        for narrator in (Character.SMIRGA, Character.ASZHANTI):
            text = first_visit_text(story, room_number, narrator)
            assert text and len(text.strip()) > 0, room_number
