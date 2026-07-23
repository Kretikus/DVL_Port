"""
Regression tests for parser.py - the verb/noun/instrument splitter,
notably the German "schließe X auf/ab" disambiguation, and
parse_chain()'s real port of the original's comma-chaining/explain-flag
behavior (sub_14202).
"""
from laas_port.parser import parse, parse_chain


def test_bare_direction():
    assert parse("n").verb == "N"
    assert parse("nordosten").verb == "NE"


def test_go_plus_direction_word():
    assert parse("gehe norden").verb == "N"


def test_simple_verb_noun():
    cmd = parse("nimm schluessel")
    assert cmd.verb == "TAKE"
    assert cmd.noun == "schluessel"


def test_schliesse_ambiguity_close_lock_unlock():
    assert parse("schließe tür").verb == "CLOSE"
    assert parse("schließe tür ab").verb == "LOCK"
    assert parse("schließe tür auf").verb == "UNLOCK"


def test_lock_unlock_with_instrument():
    cmd = parse("schließe norden auf mit schluessel")
    assert cmd.verb == "UNLOCK"
    assert cmd.noun == "norden"
    assert cmd.instrument == "schluessel"


def test_unknown_verb():
    assert parse("floskelverb blah").verb == "UNKNOWN"


def test_empty_input_returns_none():
    assert parse("") is None
    assert parse("   ") is None


def test_save_load_aliases():
    assert parse("speichern").verb == "SAVE"
    assert parse("laden").verb == "LOAD"
    assert parse("speichere meinspiel.json").noun == "meinspiel.json"


# --- parse_chain() - real port of sub_14202's chaining/explain-flag ---


def test_chain_splits_on_comma():
    cmds = parse_chain("nimm schwert, oeffne tuer")
    assert [c.verb for c in cmds] == ["TAKE", "OPEN"]
    assert cmds[0].noun == "schwert"
    assert cmds[1].noun == "tuer"


def test_chain_single_command_no_comma():
    cmds = parse_chain("schau")
    assert len(cmds) == 1
    assert cmds[0].verb == "LOOK"


def test_chain_trailing_question_mark_sets_explain_on_all():
    cmds = parse_chain("nimm schwert, schau?")
    assert len(cmds) == 2
    assert cmds[0].explain and cmds[1].explain


def test_chain_bare_question_mark_is_still_help():
    cmds = parse_chain("?")
    assert len(cmds) == 1
    assert cmds[0].verb == "HELP"
    assert cmds[0].explain is False


def test_chain_ignores_blank_segments():
    cmds = parse_chain("schau,, ende")
    assert [c.verb for c in cmds] == ["LOOK", "QUIT"]


def test_chain_empty_input():
    assert parse_chain("") == []
    assert parse_chain("   ") == []
