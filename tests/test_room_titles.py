"""
Regression tests for room_titles.py - the short status-bar room title
(distinct from room_text.py's full "look" description).
"""
from laas_port.room_titles import ROOM_TITLE, room_title


def test_room_12_matches_the_users_screenshot():
    """The exact anchor this module was built from: a real DOSBox
    screenshot showed room 12's content under the title 'Das
    Hügelland.'."""
    assert room_title(12) == "Das Hügelland."


def test_distinctive_titles_match_confirmed_rooms():
    cases = {
        1: "Aszhantis Elternhaus.",
        26: "Unter einer Baumgruppe.",
        27: "In Potidans Hütte.",
        28: "Das Tal des Mondscheinkrauts.",
        29: "An einer Gabelung.",
        67: "Auf dem Dorfplatz.",
        72: "Scarbloom Inn.",
        78: "Die Magiergilde.",
        100: "Auf einem Plateau.",
        108: "Burgruine.",
    }
    for room, expected in cases.items():
        assert ROOM_TITLE[room] == expected


def test_unknown_room_returns_none():
    assert room_title(999) is None


def test_look_includes_title_in_header(game):
    game.current_room = 12
    text = game.look()
    assert text.splitlines()[0] == "[Raum 12: Das Hügelland.]"


def test_look_falls_back_when_title_unknown(game):
    """Room 90 is a real, reachable room with no confirmed title (or
    look text) yet - look() should still show a plain header, not
    crash or show a stale/wrong title."""
    assert 90 not in ROOM_TITLE
    game.current_room = 90
    text = game.look()
    assert text.splitlines()[0] == "[Raum 90]"
