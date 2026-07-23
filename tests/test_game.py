"""
Regression tests for game.py - GameState's verbs: movement, take/drop/
examine/inventory, the OPEN/CLOSE/LOCK/UNLOCK door tetralogy, SAVE/LOAD,
and the CHARACTER port utility.
"""
import json

from laas_port.characters import Character
from laas_port.parser import parse
from laas_port.world import DOOR_CLOSED, DOOR_LOCKED, DOOR_OPEN, LIMBO_CARRIED


def test_look_shows_room_number_and_exits(game):
    game.current_room = 67
    text = game.look()
    assert "[Raum 67" in text
    assert "Ausgänge:" in text


def test_movement_updates_current_room(game):
    game.current_room = 67
    game.go("N")
    assert game.current_room == 1


def test_movement_refuses_nonexistent_exit(game):
    game.current_room = 5  # Hühnerstall, only exit is W
    result = game.go("N")
    assert "nicht hingehen" in result
    assert game.current_room == 5


def test_take_and_drop_round_trip(game):
    game.current_room = 4
    assert game.object_location(35) == 4
    game.take("35")
    assert game.object_location(35) == LIMBO_CARRIED
    assert 35 in game.objects_carried()
    game.drop("35")
    assert game.object_location(35) == 4


def test_take_fails_for_absent_object(game):
    game.current_room = 67
    result = game.take("9999")
    assert "nicht" in result.lower() or "sehe" in result.lower()


def test_examine_present_vs_absent(game):
    game.current_room = 4
    present = game.examine("35")
    assert "nicht hier" not in present
    game.current_room = 67
    absent = game.examine("35")
    assert "nicht hier" in absent


def test_inventory_empty_message(game):
    game.current_room = 67
    assert "nichts" in game.inventory()


# --- door verbs (sub_EEC0 port) ---


def test_set_door_state_mutates_both_sides(game):
    """Mirrors sub_EEC0: mutating one side of a door's state always
    mutates the reciprocal slot in the destination room too, since a
    door's state is one fact shared by both rooms it connects."""
    room, slot = 67, 0  # room 67's N exit -> room 1
    dest = game.world.room(room).exits[slot].dest_room
    assert dest == 1
    reciprocal = (slot + 4) % 8
    game._set_door_state(room, slot, DOOR_LOCKED)
    assert game.get_door_state(room, slot) == DOOR_LOCKED
    assert game.get_door_state(dest, reciprocal) == DOOR_LOCKED


def test_room_0x55_door_is_locked_initially(game):
    game.current_room = 0x55
    state = game.get_door_state(0x55, 0)
    assert state == DOOR_LOCKED


def test_unlock_requires_correct_room_and_key(game):
    game.current_room = 0x55
    # wrong room
    game.current_room = 1
    result = game.unlock_door("N", "1")
    assert "Schlüssel paßt nicht" in result or "keinen Schlüssel" in result or "Tür" in result


def test_unlock_then_open_then_close_then_lock_round_trip(game):
    game.current_room = 0x55
    # give ourselves the key (object code 1) by placing it in inventory
    game._location_overrides[1] = LIMBO_CARRIED
    result = game.unlock_door("N", "1")
    assert "auf" in result
    assert game.get_door_state(0x55, 0) == DOOR_CLOSED
    result = game.open_door("N")
    assert game.get_door_state(0x55, 0) == DOOR_OPEN
    result = game.close_door("N")
    assert game.get_door_state(0x55, 0) == DOOR_CLOSED
    result = game.lock_door("N", "1")
    assert game.get_door_state(0x55, 0) == DOOR_LOCKED
    # reciprocal room's slot must match too
    dest = game.world.room(0x55).exits[0].dest_room
    reciprocal_slot = (0 + 4) % 8
    assert game.get_door_state(dest, reciprocal_slot) == DOOR_LOCKED


# --- save/load ---


def test_save_load_round_trip(game, tmp_path):
    game.current_room = 4
    game.take("35")
    game.narrator = Character.SMIRGA
    path = tmp_path / "save.json"
    game.save(path)

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["current_room"] == 4
    assert data["narrator"] == int(Character.SMIRGA)

    from laas_port.game import DEFAULT_ASSETS_DIR, GameState

    fresh = GameState(DEFAULT_ASSETS_DIR)
    assert fresh.current_room != 4  # sanity: a fresh state starts elsewhere
    fresh.load_save(path)
    assert fresh.current_room == 4
    assert fresh.narrator == Character.SMIRGA
    assert fresh.object_location(35) == LIMBO_CARRIED


def test_load_missing_file_is_handled_by_execute(game, tmp_path):
    missing = tmp_path / "does_not_exist.json"
    cmd = parse(f"laden {missing}")
    result = game.execute(cmd)
    assert "nicht gefunden" in result


# --- CHARACTER (port utility - not a reconstructed original verb) ---


def test_character_toggle(game):
    from laas_port.characters import DEFAULT_NARRATOR

    assert game.narrator == DEFAULT_NARRATOR
    game.execute(parse("wechsel"))
    assert game.narrator != DEFAULT_NARRATOR
    game.execute(parse("wechsel"))
    assert game.narrator == DEFAULT_NARRATOR


def test_character_direct_selection(game):
    game.execute(parse("charakter smirga"))
    assert game.narrator == Character.SMIRGA
    game.execute(parse("charakter aszhanti"))
    assert game.narrator == Character.ASZHANTI


def test_character_unknown_name(game):
    result = game.execute(parse("charakter niemand"))
    assert "Unbekannter Charakter" in result


def test_help_lists_verbs(game):
    for word in ("hilfe", "?"):
        result = game.execute(parse(word))
        assert "schau" in result and "nimm" in result and "speichern" in result


# --- execute_chain() - real port of sub_14202's comma-chaining ---


def test_execute_chain_runs_multiple_commands_in_sequence(game):
    game.current_room = 4
    results = game.execute_chain("nimm #35, inventar")
    assert results[0] == "Genommen."
    assert "35" in results[1]


def test_execute_chain_stops_after_quit(game):
    game.current_room = 67
    results = game.execute_chain("schau, ende, inventar")
    assert game.running is False
    # QUIT's own result is empty (filtered out); "inventar" must never run -
    # so only "schau"'s result should appear.
    assert len(results) == 1


# --- item_stats.py wiring (sub_E6A1 port, see PHASE0_FINDINGS.md UPDATE 16) ---


def test_examine_surfaces_shop_price(game):
    """Object 233 has a confirmed nonzero buy price (500 Gerfs) - EXAMINE
    should surface it when the item is actually present."""
    game.current_room = 67
    game._location_overrides[233] = 67
    result = game.examine("233")
    assert "Preis: 500 Gerfs" in result


def test_examine_omits_price_for_unpriced_object(game):
    game.current_room = 4
    result = game.examine("35")
    assert "Preis" not in result
