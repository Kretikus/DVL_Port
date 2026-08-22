"""
Regression tests for game.py - GameState's verbs: movement, take/drop/
examine/inventory, the OPEN/CLOSE/LOCK/UNLOCK door tetralogy, SAVE/LOAD,
BUY/SELL, and the CHARACTER port utility.
"""
import json

from laas_port import pictures
from laas_port.characters import Character
from laas_port.game import (
    ANSEHEN_LATE_ROSTER_THRESHOLD,
    DAY_ROSTER,
    DAY_ROSTER_BY_INSTANCE,
    DOLCH_CODE,
    FANATIC_AMBUSH_ROOM,
    FARMER_CODE,
    FARMER_QUEST_SCHINKEN_CODE,
    FARMER_QUEST_STORM_TURNS,
    FARMER_ROOM,
    NIGHT_ROSTER,
    NIGHT_ROSTER_BY_INSTANCE_EARLY,
    NIGHT_ROSTER_BY_INSTANCE_LATE,
    MONDSCHEINKRAUT_CODE,
    PHADRAIG_CODE,
    POTIDAN_HERB_VALLEY_ROOM,
    POTIDAN_PASSAGE_ROOM,
    POTIDAN_QUEST_GERFS,
    POTIDAN_ROOM,
    ROOM_PICTURE_TABLE,
    RUDER_CODE,
    SALAMI_CODE,
    SALAMI_HOME_ROOM,
    SALAMI_ROOM,
    SCARABAEUS_CODE,
    SCARABAEUS_DEPLETED_CODE,
    SCHWERT_CODE,
    SKELETT_CODE,
    TUATARA_BOATHOUSE_ROOM,
    TUATARA_BOUNTY_GERFS,
    TUATARA_ENCOUNTER_ROOM,
    TUATARA_LAKE_ROOMS,
    TUATARA_TAVERN_ROOM,
)
from laas_port.parser import parse
from laas_port.world import DOOR_CLOSED, DOOR_LOCKED, DOOR_OPEN, LIMBO_CARRIED, LIMBO_REMOVED


def test_look_shows_room_number_and_exits(game):
    game.current_room = 67
    text = game.look()
    assert "[Raum 67" in text
    assert "Ausgänge:" in text


def test_look_lists_two_present_npcs_with_the_confirmed_sentence(game):
    """Room 67 (Auf dem Dorfplatz) tracks Har (25) and Sklar (26) - user
    supplied live memory dumps of this exact room/NPC state, and the raw
    buffer literally contained the composited sentence "Har und Sklar
    sind hier." (see PHASE0_FINDINGS.md UPDATE 52/_who_is_here_line).
    They are people (has_instance) and must be on this line, not lumped
    into "Objekte hier:". UPDATE 59's follow-up (user-reported: no known
    pickable object in room 67) tightened object_location() so room 67's
    one unnamed, unpriced "filler" object (code 38) no longer shows up
    at all - "Objekte hier:" should not appear here."""
    game.current_room = 67
    text = game.look()
    assert "Har und Sklar sind hier." in text
    assert "Objekte hier" not in text


def test_look_lists_a_single_present_npc_with_singular_phrasing(game):
    """Room 25 (Vor der Brücke) tracks only the Bruckentroll (134) -
    singular phrasing confirmed both by disassembly (UPDATE 25's room 3
    "Foroll ist hier" report) and directly in the user's memory dumps
    ("Sklar ist hier." once Har left room 67)."""
    game.current_room = 25
    text = game.look()
    assert "ist hier." in text
    assert "sind hier." not in text


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
    # UPDATE 58 fixed object_location() to actually report LIMBO_CARRIED
    # for non-instance items - the bundled save's player genuinely
    # starts out carrying the Axt (171), previously hidden by the bug
    # this fixed. Move it out of LIMBO_CARRIED to test the true empty case.
    # The `game` fixture also grants Dolch/Schwert by default since
    # UPDATE 84/85 - remove those too for a genuinely empty inventory.
    game.current_room = 67
    game._location_overrides[171] = 67
    _remove_starter_weapons(game)
    assert "nichts" in game.inventory()


def test_inventory_shows_the_carried_axt_by_name(game):
    """UPDATE 58: object_location() now correctly reports LIMBO_CARRIED
    for non-instance items - the bundled save's player starts out
    carrying the Axt (171, already confirmed in names.py), previously
    hidden by the bug this fixed. Must show by name, not raw code."""
    game.current_room = 67
    assert "Axt" in game.inventory()


def test_inventory_matches_the_confirmed_f4_screenshot_exactly(game):
    """UPDATE 63: user-supplied screenshot of the real "F4" shortcut -
    empty inventory (STORY message 121) plus both characters' default
    "normale Kleidung" lines (messages 1884/1885), exact text match."""
    game.current_room = 67
    game._location_overrides[171] = 67  # move the Axt out of carried, matching the screenshot's moment
    _remove_starter_weapons(game)  # the fixture also grants Dolch/Schwert by default (UPDATE 84/85)
    assert game.inventory() == (
        "Leider haben wir nichts.\n\n"
        "Smirga trägt normale Kleidung.\n"
        "Aszhanti trägt normale Kleidung."
    )


def test_inventory_reports_equipped_armor_instead_of_normale_kleidung(game):
    """UPDATE 63: once real armor is equipped, inventory() uses the
    confirmed companion message ("hat %s %s an.") instead of the
    "normale Kleidung" default."""
    game.smirga_armor = 196  # Echsenpanzer
    game.aszhanti_armor = 52  # Kettenhemd
    result = game.inventory()
    assert "Smirga hat einen Echsenpanzer an." in result
    assert "Aszhanti hat ein Kettenhemd an." in result
    assert "normale Kleidung" not in result


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
    # the key (object code 1 - confirmed as Schwert, UPDATE 84/85) is
    # already carried via the `game` fixture's own default; UNLOCK_GATE_
    # OBJECT (0, confirmed as Dolch) must NOT be carried though, so
    # explicitly move it out of the way (the fixture grants it too).
    game._location_overrides.pop(DOLCH_CODE, None)
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


# --- Gultiba's bedroom (room 88) - a full scripted encounter behind the
# room-85 door above, confirmed via direct disassembly of the room's own
# handler (PHASE0_FINDINGS.md UPDATE 87) ---


def test_room_88_first_visit_shows_the_affair_scene_once(game):
    game.current_room = 88
    first = game.look()
    assert "Ehebruch nennt man das glaube ich" in first
    second = game.look()
    assert "Ehebruch" not in second
    assert "Wir stehen in Gultibas Schlafzimmer" in second


def test_room_88_examine_fixtures(game):
    game.current_room = 88
    assert "Träne ihre Wange" in game.examine("frau")
    assert "zu aufgeregt" in game.examine("mann")
    assert "Himmelbett" in game.examine("bett")
    assert "verglastes Fenster" in game.examine("fenster")


def test_room_88_attacking_the_lover_kills_him_and_costs_the_key(game):
    """Confirmed scripted outcome: Ansehen drops, the Dolch (the
    UNLOCK_GATE_OBJECT, not the Schwert key itself) is lost to true
    limbo, and the door relocks behind you - matching message 2311's
    own "...vergessen sogar den Schlüssel"."""
    game.current_room = 88
    ansehen_before = game.ansehen
    result = game.attack("mann")
    assert "verzerrt er plötzlich das Gesicht" in result
    assert "tot ist" in result
    assert game.ansehen == ansehen_before - 2
    assert DOLCH_CODE not in game.objects_carried()
    assert game.get_door_state(0x55, 0) == DOOR_LOCKED
    dest = game.world.room(0x55).exits[0].dest_room
    assert game.get_door_state(dest, (0 + 4) % 8) == DOOR_LOCKED
    # doesn't start a real fight
    assert game._combat_instance_idx is None


def test_room_88_lover_is_not_attackable_elsewhere(game):
    """The lover isn't instance-tracked - he's pure scripted scenery for
    this one room, not a fightable monster anywhere else."""
    game.current_room = TROLL_ROOM
    result = game.attack("mann")
    assert "sehe ich hier nicht" in result or "lässt sich nicht bekämpfen" in result


def test_room_88_releasing_the_lover_lets_him_go_and_still_costs_the_key(game):
    """Confirmed peaceful resolution (PHASE0_FINDINGS.md UPDATE 88):
    Ansehen rises instead of falling, but the Dolch is still lost and
    the door still relocks - the same consequence shape as the ATTACK
    outcome, just the opposite Ansehen sign and a different message."""
    game.current_room = 88
    ansehen_before = game.ansehen
    result = game.release("mann gehen")
    assert "Der Mann nimmt seine Beine unter die Arme und rennt davon" in result
    assert game.ansehen == ansehen_before + 2
    assert DOLCH_CODE not in game.objects_carried()
    assert game.get_door_state(0x55, 0) == DOOR_LOCKED


def test_room_88_release_also_accepts_bare_mann_without_gehen(game):
    """No "gehen" required - just the noun. (Pronouns like "ihn" aren't
    resolved at all - this port has no generic pronoun mechanism, only
    the exact confirmed noun "mann"/"liebhaber".)"""
    game.current_room = 88
    result = game.release("mann")
    assert "rennt davon" in result


def test_room_88_release_elsewhere_or_wrong_noun_is_refused(game):
    game.current_room = TROLL_ROOM
    assert "loslassen" in game.release("mann gehen")
    game.current_room = 88
    assert "loslassen" in game.release("frau")


def test_room_88_encounter_only_resolves_once_either_way(game):
    """Attacking after already releasing (or vice versa) doesn't fire
    the scene a second time - `_gultiba_bedroom_resolved` gates both
    outcomes together, not just each one against itself."""
    game.current_room = 88
    game.release("mann gehen")
    ansehen_after_release = game.ansehen
    attack_result = game.attack("mann")
    assert "sehe ich hier nicht" in attack_result or "lässt sich nicht bekämpfen" in attack_result
    assert game.ansehen == ansehen_after_release  # unchanged - no second resolution

    from laas_port.game import DEFAULT_ASSETS_DIR, GameState

    fresh_game = GameState(DEFAULT_ASSETS_DIR)
    fresh_game.current_room = 88
    fresh_game.attack("mann")
    ansehen_after_attack = fresh_game.ansehen
    release_result = fresh_game.release("mann gehen")
    assert "loslassen" in release_result
    assert fresh_game.ansehen == ansehen_after_attack  # unchanged


def test_room_88_encounter_resolution_persists_across_save_load(game, tmp_path):
    game.current_room = 88
    game.release("mann gehen")
    path = tmp_path / "save.json"
    game.save(path)

    from laas_port.game import DEFAULT_ASSETS_DIR, GameState

    fresh = GameState(DEFAULT_ASSETS_DIR)
    fresh.load_save(path)
    assert fresh._gultiba_bedroom_resolved is True


def test_lass_mann_gehen_parses_and_executes_end_to_end(game):
    """Exact phrasing from the lover's own dialogue ("Bitte, laßt mich
    gehen!") - full parse()/execute() path, not just the direct
    release() call the other tests above use."""
    game.current_room = 88
    result = game.execute(parse("lass mann gehen"))
    assert "rennt davon" in result
    assert game._gultiba_bedroom_resolved is True


# --- save/load ---


def test_save_load_round_trip(game, tmp_path):
    game.current_room = 4
    game.take("35")
    game.narrator = Character.SMIRGA
    game.money = 42
    game.look()  # marks current_room visited
    game._bought_starter_weapons = True
    path = tmp_path / "save.json"
    game.save(path)

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["current_room"] == 4
    assert data["narrator"] == int(Character.SMIRGA)
    assert data["money"] == 42
    assert 4 in data["visited_rooms"]
    assert data["bought_starter_weapons"] is True

    from laas_port.game import DEFAULT_ASSETS_DIR, GameState

    fresh = GameState(DEFAULT_ASSETS_DIR)
    assert fresh.current_room != 4  # sanity: a fresh state starts elsewhere
    fresh.load_save(path)
    assert fresh.current_room == 4
    assert fresh.narrator == Character.SMIRGA
    assert fresh.object_location(35) == LIMBO_CARRIED
    assert fresh.money == 42
    assert 4 in fresh._visited_rooms
    assert fresh._bought_starter_weapons is True


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
    game._last_shown_picture = ROOM_PICTURE_TABLE[4]  # not what this test is about
    results = game.execute_chain("nimm #35, inventar")
    assert results[0] == "Genommen."
    # UPDATE 58: inventory() shows real names (names.py has 35 = Mygra),
    # not raw codes, now that carried items resolve correctly.
    assert "Mygra" in results[1]


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


# --- BUY/SELL (see MERCHANTS in game.py, item_stats.py's field semantics) ---


def test_buy_from_gultiba(game):
    """Object 233 (Agitor) is confirmed to cost 600 Gerfs to buy from
    Gultiba (WORLD field 4) - see PHASE0_FINDINGS.md UPDATE 18."""
    game.current_room = 75  # Gultiba's shop ("Laden")
    game.money = 600
    result = game.buy("agitor")
    assert "Gekauft" in result
    assert game.money == 0
    assert 233 in game.objects_carried()


def test_buy_fails_without_enough_money(game):
    game.current_room = 75
    game.money = 10
    result = game.buy("agitor")
    assert "reicht" in result
    assert game.money == 10
    assert 233 not in game.objects_carried()


def test_sell_to_gultiba(game):
    """Gultiba's own buy-from-player price for Agitor (WORLD field 3) is
    100 Gerfs."""
    game.current_room = 75
    game._location_overrides[233] = LIMBO_CARRIED
    result = game.sell("agitor")
    assert "Verkauft" in result
    assert game.money == 100
    assert 233 not in game.objects_carried()


def test_buy_and_sell_require_a_merchant_present(game):
    game.current_room = 1
    game.money = 1000
    assert "Händler" in game.buy("agitor")
    assert "Händler" in game.sell("agitor")


def test_buy_unknown_item_is_refused(game):
    game.current_room = 75
    game.money = 1000
    result = game.buy("nichtvorhanden")
    assert "nicht im Angebot" in result


def test_buy_from_yarom(game):
    """Yarom (167) is a traveling merchant, tracked at room 44 in this
    project's bundled save - see PHASE0_FINDINGS.md UPDATE 39. His price
    to buy FROM him (WORLD field 2) for Agitor is 500 Gerfs."""
    assert game.object_location(167) == 44
    game.current_room = 44
    game.money = 500
    result = game.buy("agitor")
    assert "Gekauft" in result
    assert game.money == 0
    assert 233 in game.objects_carried()


def test_sell_to_yarom(game):
    """Yarom's own buy-from-player price (WORLD field 1) for Agitor is
    100 Gerfs."""
    game.current_room = 44
    game._location_overrides[233] = LIMBO_CARRIED
    result = game.sell("agitor")
    assert "Verkauft" in result
    assert game.money == 100
    assert 233 not in game.objects_carried()


# --- Foroll's scripted starter-weapons sale (see FOROLL_* constants, and
# ROOM_FIRST_VISIT_MESSAGE in room_text.py - confirmed via a real DOSBox
# screenshot matched byte-for-byte against STORY messages 123-124) ---


def test_room_3_first_visit_shows_scripted_scene_once(game):
    game.current_room = 3
    first = game.look()
    assert "Macht genau 7 Gerfs" in first
    second = game.look()
    assert "Macht genau 7 Gerfs" not in second
    assert "Nordwand der Halle" in second  # the plain standing text (message 126)


# --- room 1's breakfast-scene first visit (the ORIGINAL flagged gap this
# whole ROOM_FIRST_VISIT_MESSAGE mechanism started from - UPDATE 89) ---


def test_room_1_first_visit_appends_breakfast_scene_once(game):
    game.current_room = 1
    first = game.look()
    assert "Setzt euch" in first
    assert "Aszhantis Elternhaus" in first or "mein Elternhaus" in first
    second = game.look()
    assert "Setzt euch" not in second


# --- Mygra's first-visit greeting scene (room 4, "Beim Scharlatan" - see
# ROOM_FIRST_VISIT_MESSAGE's room-4 entry, confirmed via room_handler_
# by_address.py plus two user-supplied DOSBox screenshots of a first-ever
# visit, paginated across a "(Taste)" prompt) ---


def test_room_4_first_visit_shows_mygras_full_greeting_once(game):
    """User-reported: the port's first visit to Mygra's shop was missing
    almost the whole scene (entry narration + greeting + monologue),
    including its exact closing two sentences ("Als er seinen Monolog
    endlich beendet hat...'Ja was wollt ihr denn?'...") - confirmed
    against a real screenshot, not paraphrased."""
    game.current_room = 4
    first = game.look()
    assert "Vorsichtig betreten wir das Haus von Mygra" in first
    assert "Kann ich euch irgendwie behilflich sein" in first
    assert "Als er seinen Monolog endlich beendet hat" in first
    assert "'Ja was wollt ihr denn?'" in first
    second = game.look()
    assert "Vorsichtig betreten wir das Haus von Mygra" not in second
    assert "Wir stehen in Mygras Haus" in second  # the plain standing text (message 139)


def test_room_4_first_visit_greeting_is_narrator_dependent(game):
    """Message 138's greeting clause is narrator-dependent (136 for
    Aszhanti narrating, first-person "grüße ich ihn"; 137 for Smirga
    narrating, third-person "grüßt ihn Aszhanti") - same (smirga_msg,
    aszhanti_msg) tuple convention as ROOM_LOOK_MESSAGE's room-1 entry,
    now also supported by first_visit_text(). Two separate GameStates
    (rather than resetting `_visited_rooms` mid-test) keep this a clean
    first-visit check for each narrator."""
    game.current_room = 4
    aszhanti_text = game.look()
    assert "grüße ich ihn freundlich" in aszhanti_text

    from laas_port.game import GameState

    smirga_game = GameState(game.assets_dir)
    smirga_game.narrator = Character.SMIRGA
    smirga_game.current_room = 4
    smirga_text = smirga_game.look()
    assert "grüßt ihn Aszhanti freundlich" in smirga_text


def test_room_4_standing_text_includes_the_drachenblut_continuation(game):
    """User-reported: the standing (repeat-visit) text for room 4 was
    missing message 155's continuation, confirmed via a real screenshot
    to appear right after message 139, before "Mygra ist hier.\""""
    game.current_room = 4
    game.look()  # consume the first-visit scene
    second = game.look()
    assert "Unschwer identifiziere ich es als Drachenblut" in second


def _remove_starter_weapons(game):
    """Undoes the `game` fixture's own default (starter weapons already
    bought and carried) for the handful of tests that specifically need
    to start from Foroll's unbought/unowned state - resetting only
    `_bought_starter_weapons` is no longer enough since UPDATE 84/85
    made the weapon-possession check read real inventory."""
    game._bought_starter_weapons = False
    game._location_overrides.pop(DOLCH_CODE, None)
    game._location_overrides.pop(SCHWERT_CODE, None)


def test_buy_starter_weapons_requires_exact_price(game):
    _remove_starter_weapons(game)
    game.current_room = 3
    game.money = 6
    result = game.buy_starter_weapons()
    assert "0 Gerfs" not in result  # didn't happen to already read as 0
    assert game.money == 6
    assert game._bought_starter_weapons is False


def test_buy_starter_weapons_succeeds_and_is_one_time(game):
    _remove_starter_weapons(game)
    game.current_room = 3
    game.money = 7
    result = game.buy_starter_weapons()
    assert "Dolch und Schwert" in result
    assert game.money == 0
    assert game._bought_starter_weapons is True
    assert DOLCH_CODE in game.objects_carried()  # UPDATE 84/85: real objects, not just the flag
    assert SCHWERT_CODE in game.objects_carried()
    # buying again does nothing, even with plenty of money
    game.money = 100
    second = game.buy_starter_weapons()
    assert "schon" in second
    assert game.money == 100


def test_buy_waffen_routes_to_foroll_when_present(game):
    _remove_starter_weapons(game)
    game.current_room = 3
    game.money = 7
    result = game.buy("waffen")
    assert "Dolch und Schwert" in result


def test_buy_starter_weapons_only_works_at_forolls_forge(game):
    game.current_room = 1
    game.money = 7
    result = game.buy_starter_weapons()
    assert "nicht" in result
    assert game.money == 7


# --- ambient "impatience" ticks (Foroll/Oerli, see ROOM_IMPATIENCE_EVENTS,
# PHASE0_FINDINGS.md UPDATE 40) ---


def test_foroll_warns_after_lingering_then_kicks_you_out(game):
    _remove_starter_weapons(game)
    game.current_room = 3
    for _ in range(4):
        result = game.execute_chain("schau")
        assert not any("Mann Bübchens" in r for r in result)
    warn = game.execute_chain("schau")
    assert any("Mann Bübchens" in r for r in warn)
    for _ in range(4):
        result = game.execute_chain("schau")
        assert not any("Wenn er kein Geld" in r for r in result)
    kick = game.execute_chain("schau")
    assert any("Wenn er kein Geld" in r for r in kick)
    # each stage fires exactly once, not on every later turn
    again = game.execute_chain("schau")
    assert not any("Wenn er kein Geld" in r for r in again)
    assert not any("Mann Bübchens" in r for r in again)


def test_foroll_does_not_nag_once_starter_weapons_are_bought(game):
    game.current_room = 3
    game.money = 7
    game.buy_starter_weapons()
    for _ in range(10):
        result = game.execute_chain("schau")
        assert not any("Mann Bübchens" in r or "Wenn er kein Geld" in r for r in result)


def test_oerli_warns_after_lingering_in_the_tavern(game):
    game.current_room = 72
    for _ in range(3):
        game.execute_chain("schau")
    warn = game.execute_chain("schau")
    assert any("Wat is nu" in r for r in warn)


def test_impatience_counter_is_per_room_and_does_not_tick_elsewhere(game):
    game.current_room = 67
    for _ in range(10):
        result = game.execute_chain("schau")
        assert not any("Foroll" in r or "Wirt" in r for r in result)
    assert game._room_impatience_turns == {}


def test_save_load_round_trip_includes_impatience_counters(game, tmp_path):
    game.current_room = 3
    for _ in range(5):
        game.execute_chain("schau")
    path = tmp_path / "save.json"
    game.save(path)

    from laas_port.game import DEFAULT_ASSETS_DIR, GameState

    fresh = GameState(DEFAULT_ASSETS_DIR)
    fresh.load_save(path)
    assert fresh._room_impatience_turns == game._room_impatience_turns
    assert fresh._room_impatience_fired == game._room_impatience_fired
    # the warning already fired in the saved game must not refire
    result = fresh.execute_chain("schau")
    assert not any("Mann Bübchens" in r for r in result)


# --- day/night clock (see CLOCK_TRANSITIONS, PHASE0_FINDINGS.md UPDATE 43) ---


def test_clock_advances_once_every_two_turns(game):
    game.current_room = 67
    game.execute_chain("schau")
    assert game.time_of_day == 0  # first turn - no tick yet (matches [0xAD5C]'s gate)
    game.execute_chain("schau")
    assert game.time_of_day == 1
    game.execute_chain("schau")
    assert game.time_of_day == 1  # third turn - no tick
    game.execute_chain("schau")
    assert game.time_of_day == 2


def test_clock_transition_messages_fire_at_confirmed_thresholds(game):
    game.current_room = 67
    game.time_of_day = 0x45  # one clock-tick from noon (0x46)
    result = game.execute_chain("schau")  # turn 1: no clock tick yet
    assert not any("Mittag" in r for r in result)
    result = game.execute_chain("schau")  # turn 2: clock ticks to 0x46
    assert game.time_of_day == 0x46
    assert any("Mittag" in r for r in result)


def test_dawn_increments_day_count_on_wraparound(game):
    game.current_room = 67
    game.time_of_day = 255
    start_day = game.day_count
    game.execute_chain("schau")  # turn 1: no tick
    assert game.day_count == start_day
    result = game.execute_chain("schau")  # turn 2: wraps to 0 -> new day
    assert game.time_of_day == 0
    assert game.day_count == start_day + 1
    assert any("Morgen" in r for r in result)


def test_save_load_round_trip_includes_the_clock(game, tmp_path):
    game.current_room = 67
    game.time_of_day = 200
    game.day_count = 3
    game.execute_chain("schau")
    path = tmp_path / "save.json"
    game.save(path)

    from laas_port.game import DEFAULT_ASSETS_DIR, GameState

    fresh = GameState(DEFAULT_ASSETS_DIR)
    fresh.load_save(path)
    assert fresh.time_of_day == game.time_of_day
    assert fresh.day_count == game.day_count
    assert fresh._turn_counter == game._turn_counter


# --- day/night NPC and monster roster (see DAY_ROSTER/NIGHT_ROSTER,
# PHASE0_FINDINGS.md UPDATE 49 - confirmed via the day/night clock's own
# dawn/nightfall subroutines) ---


def test_dawn_places_the_day_roster_and_clears_the_night_roster(game):
    from laas_port.world import LIMBO_REMOVED

    game.current_room = 67
    game.time_of_day = 255  # one tick from wrapping to dawn (0)
    game.execute_chain("schau")  # turn 1: no clock tick yet
    game.execute_chain("schau")  # turn 2: wraps to 0 -> dawn
    assert game.time_of_day == 0
    for code, room in DAY_ROSTER.items():
        assert game.object_location(code) == room, f"code {code} not placed at {room}"
    for code in NIGHT_ROSTER:
        assert game.object_location(code) == LIMBO_REMOVED, f"code {code} not cleared"


def test_nightfall_places_the_night_roster_and_clears_the_day_roster(game):
    from laas_port.world import LIMBO_REMOVED

    game.current_room = 67
    game.time_of_day = 0x7F  # one tick from nightfall (0x80)
    game.execute_chain("schau")  # turn 1: no clock tick yet
    game.execute_chain("schau")  # turn 2: ticks to 0x80 -> nightfall
    assert game.time_of_day == 0x80
    for code, room in NIGHT_ROSTER.items():
        assert game.object_location(code) == room, f"code {code} not placed at {room}"
    for code in DAY_ROSTER:
        assert game.object_location(code) == LIMBO_REMOVED, f"code {code} not cleared"


def test_noon_and_dusk_do_not_touch_the_roster(game):
    game.current_room = 67
    game._location_overrides[87] = 999  # sentinel - untouched if roster logic is skipped
    game.time_of_day = 0x45  # one tick from noon (0x46)
    game.execute_chain("schau")
    game.execute_chain("schau")
    assert game.time_of_day == 0x46
    assert game.object_location(87) == 999


def test_night_roster_monster_only_ambushes_after_nightfall(game):
    """End-to-end: object 87 (NIGHT_ROSTER) can't ambush during the day
    (still LIMBO_REMOVED) but can once nightfall places it. Room 23 is
    both object 87's own confirmed NIGHT_ROSTER room and, per UPDATE 78,
    in its `MONSTER_ROOM_LISTS` entry."""
    from laas_port.world import LIMBO_REMOVED

    game.current_room = 23  # outside the safe zone
    assert game.object_location(87) == LIMBO_REMOVED  # not yet - still day/inactive

    game.time_of_day = 0x7F
    game.execute_chain("schau")
    game.execute_chain("schau")  # ticks to nightfall - places object 87
    assert game.object_location(87) == NIGHT_ROSTER[87]
    result = game._check_ambush(rng=_FakeRng([6] * 30))
    assert game._combat_monster_code == 87


# --- status screen (levels.py's confirmed title tracks, PHASE0_FINDINGS.md
# UPDATE 23 + its screenshot-driven correction) ---


def test_status_matches_real_fresh_game_screenshot(game):
    """A fresh GameState's status() output should match Status_anfang.png
    (a real DOSBox screenshot of the actual start-of-game screen) line
    for line - see PHASE0_FINDINGS.md UPDATE 23's correction addendum."""
    result = game.status()
    assert "Gesundheit :                 20                20" in result
    assert "Milchbubi" in result and result.count("Milchbubi") == 2
    assert "Ansehen    : Niemand" in result
    assert "Scharlatan" in result and "Unbegabt" in result
    assert "Hunger     : Satt" in result
    assert "Kein Durst" in result and result.count("Kein Durst") == 2


def test_status_shows_the_real_title_and_a_header_separator(game):
    """UPDATE 62: user-supplied screenshot of the real "F3" shortcut
    shows a "Zustandsübersicht." title line (STORY message 1456,
    already referenced in status()'s own docstring but never actually
    printed) and a dashed separator under the column header, both
    missing before this."""
    result = game.status()
    lines = result.splitlines()
    assert lines[0] == "Zustandsübersicht."
    assert lines[1] == ""
    assert "Aszhanti" in lines[2] and "Smirga" in lines[2]
    assert set(lines[3]) == {"-"}


def test_spells_matches_the_confirmed_f5_screenshot_exactly(game):
    """UPDATE 64: user-supplied screenshot of the real "F5" shortcut -
    fresh game (Aszhanti still "Scharlatan"), exact text match."""
    assert game.spells() == (
        "Zaubersprüche.\n\n"
        "Aszhanti beherrscht die folgenden Zaubersprüche.\n"
        "(Um die Namen der Zauber zu erfahren, bitte im Handbuch nachschlagen.)\n\n"
        "Tja, sieht so aus als könnte Aszhanti noch gar nicht zaubern!"
    )


def test_spells_verb_is_reachable_via_the_parser(game):
    assert game.execute(parse("zaubersprüche")) == game.spells()
    assert game.execute(parse("spells")) == game.spells()


def test_status_reflects_strength_thresholds(game):
    game.aszhanti_strength = 17  # top of "Milchbubi" bracket
    game.smirga_strength = 38  # just past "Kraftprotz" -> "Gladiator"
    result = game.status()
    assert "Milchbubi" in result
    assert "Gladiator" in result


def test_status_reflects_astral_and_ansehen_thresholds(game):
    game.aszhanti_astral = 7  # past "Illusionist" -> "Magier"
    game.ansehen = 10  # past "Bekannt" -> "Heldenhaft"
    result = game.status()
    assert "Astral     :             Magier" in result
    assert "Unbegabt" in result  # Smirga's is always fixed, regardless of any stat
    assert "Ansehen    : Heldenhaft" in result


def test_smirga_astral_is_always_unbegabt_never_a_ladder_title(game):
    # Smirga has no astral field at all - this just confirms the display
    # never varies, since it's a fixed constant, not a computed stat.
    result_before = game.status()
    game.aszhanti_astral = 100
    result_after = game.status()
    assert "Unbegabt" in result_before and "Unbegabt" in result_after


def test_status_reflects_hunger_and_durst_thresholds(game):
    game.hunger = 0
    game.aszhanti_durst = 0
    game.smirga_durst = 61
    result = game.status()
    assert "Hunger     : Am Verhungern" in result
    assert "Am Verdursten" in result
    assert "Kein Durst" in result


def test_zustand_verb_routes_to_status(game):
    result = game.execute(parse("zustand"))
    assert "Stärke" in result and "Astral" in result and "Ansehen" in result


def test_save_load_round_trip_includes_level_tracks(game, tmp_path):
    game.aszhanti_strength = 20
    game.smirga_strength = 5
    game.aszhanti_astral = 3
    game.ansehen = 8
    game.aszhanti_health = 15
    game.smirga_health = 12
    game.aszhanti_max_health = 22
    game.smirga_max_health = 21
    game.hunger = 40
    game.aszhanti_durst = 20
    game.smirga_durst = 10
    path = tmp_path / "save.json"
    game.save(path)

    from laas_port.game import DEFAULT_ASSETS_DIR, GameState

    fresh = GameState(DEFAULT_ASSETS_DIR)
    fresh.load_save(path)
    assert fresh.aszhanti_strength == 20
    assert fresh.smirga_strength == 5
    assert fresh.aszhanti_astral == 3
    assert fresh.ansehen == 8
    assert fresh.aszhanti_health == 15
    assert fresh.smirga_health == 12
    assert fresh.aszhanti_max_health == 22
    assert fresh.smirga_max_health == 21
    assert fresh.hunger == 40
    assert fresh.aszhanti_durst == 20
    assert fresh.smirga_durst == 10


def test_max_health_starts_equal_to_current_health(game):
    # Confirmed via a real screenshot after one won fight + eating: max
    # hp is a separate, hidden pair of globals - see PHASE0_FINDINGS.md
    # UPDATE 23's second correction. A fresh game's current == max.
    assert game.aszhanti_max_health == game.aszhanti_health == 20
    assert game.smirga_max_health == game.smirga_health == 20


# --- equip (ANLEGEN - real armor mechanic, see combat.py's ARMOR_CLASS,
# PHASE0_FINDINGS.md UPDATE 23's follow-up) ---


def test_equip_without_a_target_asks_what(game):
    result = game.equip(None)
    assert "anlegen" in result.lower()


def test_equip_requires_carrying_the_item(game):
    result = game.equip("lederwams")
    assert "trage ich nicht" in result


def test_equip_non_armor_item_is_refused(game):
    game._location_overrides[233] = LIMBO_CARRIED  # Agitor - a real item, not armor
    result = game.equip("agitor")
    assert "kann ich nicht" in result.lower()
    assert game.aszhanti_armor is None
    assert game.smirga_armor is None


def test_equip_sets_armor_for_the_current_narrator(game):
    from laas_port.characters import Character, DEFAULT_NARRATOR

    game._location_overrides[264] = LIMBO_CARRIED  # Lederwams
    assert game.narrator == DEFAULT_NARRATOR == Character.ASZHANTI
    result = game.equip("lederwams")
    assert "Aszhanti" in result
    assert game.aszhanti_armor == 264
    assert game.smirga_armor is None


def test_equip_respects_a_narrator_switch(game):
    from laas_port.characters import Character

    game._location_overrides[52] = LIMBO_CARRIED  # Kettenhemd
    game.narrator = Character.SMIRGA
    result = game.equip("kettenhemd")
    assert "Smirga" in result
    assert game.smirga_armor == 52
    assert game.aszhanti_armor is None


def test_equip_verb_routes_through_parse(game):
    game._location_overrides[196] = LIMBO_CARRIED  # Echsenpanzer
    result = game.execute(parse("anlege echsenpanzer"))
    assert game.aszhanti_armor == 196


# --- combat (ATTACK/FLEE, combat.py's confirmed formula - see
# PHASE0_FINDINGS.md UPDATE 17/18/22/23/24/27/28) ---


class _FakeRng:
    """Same fixed-sequence fake as test_combat.py's - see that file's
    docstring for the exact call order resolve_round() uses."""

    def __init__(self, values):
        self._values = list(values)

    def randint(self, a, b):
        return self._values.pop(0)


# The bridge troll (object 134, room 25 - see names.py) is the only
# confirmed-identity creature with real, checked-in instance stats:
# hp=1, attack=0 (always hits), defense=10.
TROLL_ROOM = 25
TROLL_CODE = 134


def _start_and_resolve_round(game, noun, rng):
    """Drives the confirmed Q&A flow (attack -> weapon prompt -> spell
    prompt -> round resolves) exactly like a real player would, instead
    of calling internal round-resolution directly - see the "combat"
    section's docstring in game.py for why this shape is required (a
    direct user correction: this port's first draft skipped straight
    to resolving a round on a typed "attackiere", which isn't how the
    real game works)."""
    weapon_prompt = game.attack(noun)
    assert weapon_prompt == game.WEAPON_PROMPT
    spell_prompt = game._combat_answer("Schwert")
    assert spell_prompt == game.SPELL_PROMPT
    return game._combat_answer("Keinen", rng=rng)


def test_attack_without_a_target_present_asks_who(game):
    game.current_room = 1  # no instance-tracked hostile object here
    result = game.attack(None)
    assert "angreifen" in result.lower()


def test_attack_unknown_target_is_refused(game):
    game.current_room = TROLL_ROOM
    result = game.attack("nichtvorhanden")
    assert "sehe" in result.lower()


def test_attack_immediately_prompts_for_weapon_not_a_resolved_round(game):
    """The exact bug the user caught: a typed attack (or an ambush)
    must ask "Welche Waffe...?" right away, NOT resolve a round on the
    same call."""
    game.current_room = TROLL_ROOM
    result = game.attack("troll")
    assert result == game.WEAPON_PROMPT
    assert game._combat_awaiting == "weapon"
    assert game._combat_monster_hp == 1  # fight started, no round resolved yet


# --- weapon possession check at the weapon prompt (UPDATE 83) ---


def test_weapon_prompt_refuses_dolch_or_schwert_without_owning_them(game):
    _remove_starter_weapons(game)
    game.current_room = TROLL_ROOM
    game.attack("troll")
    result = game._combat_answer("Schwert")
    assert "kein Schwert" in result
    assert game.WEAPON_PROMPT in result
    assert game._combat_awaiting == "weapon"  # re-prompted, not advanced to spell

    dolch_result = game._combat_answer("Dolch")
    assert "keinen Dolch" in dolch_result
    assert game._combat_awaiting == "weapon"


def test_weapon_prompt_allows_hande_without_owning_a_weapon(game):
    """Bare hands need no possession check - unaffected by real
    inventory state."""
    _remove_starter_weapons(game)
    game.current_room = TROLL_ROOM
    game.attack("troll")
    result = game._combat_answer("Hände")
    assert result == game.SPELL_PROMPT
    assert game._combat_awaiting == "spell"


def test_weapon_prompt_allows_schwert_once_owned(game):
    game.current_room = TROLL_ROOM  # fixture default: _bought_starter_weapons already True
    game.attack("troll")
    result = game._combat_answer("Schwert")
    assert result == game.SPELL_PROMPT
    assert game._combat_awaiting == "spell"


def test_combat_answer_sequence_asks_weapon_then_spell_then_resolves(game):
    game.current_room = TROLL_ROOM
    game.attack("troll")
    spell_prompt = game._combat_answer("Schwert")
    assert spell_prompt == game.SPELL_PROMPT
    assert game._combat_awaiting == "spell"
    # target-select, monster roll(always hits, attack=0), monster dmg
    # dice x3, player roll(miss, defense=10)
    rng = _FakeRng([5, 1, 2, 2, 2, 1])
    result = game._combat_answer("Keinen", rng=rng)
    assert "Smirga verfehlt" in result
    assert game._combat_awaiting is None or game._combat_awaiting == "weapon"


def test_fight_continues_with_an_automatic_reprompt_for_next_round(game):
    """Confirmed via direct user correction: once a round resolves and
    the fight isn't over, the next round's weapon prompt appears
    automatically - no separate "attackiere" needed."""
    game.current_room = TROLL_ROOM
    rng = _FakeRng([5, 1, 2, 2, 2, 1])  # monster hits but player misses - troll survives
    result = _start_and_resolve_round(game, "troll", rng)
    assert game._combat_monster_code == TROLL_CODE  # still fighting
    assert game._combat_awaiting == "weapon"
    assert game.WEAPON_PROMPT in result  # auto-reprompt appended to the round's own text


def test_levi_bonus_strike_can_finish_off_a_monster_that_survives_melee(game):
    """Integration test for combat.resolve_levi() wired into the real
    Q&A flow - see PHASE0_FINDINGS.md UPDATE 34."""
    game.aszhanti_known_spells = 5  # UPDATE 83 gates casting on this
    game.current_room = TROLL_ROOM
    game.attack("troll")
    game._combat_answer("Schwert")
    # melee: target-select, monster roll(hits, attack=0), monster dmg
    # dice x3, player roll(miss, defense=10) - troll (hp=1) survives;
    # LEVI: cast roll 6 (>5) succeeds, power roll 1 (<=2) lands the
    # bonus strike for exactly 1 damage - enough to finish it off.
    rng = _FakeRng([5, 1, 2, 2, 2, 1, 6, 1])
    result = game._combat_answer("LEVI", rng=rng)
    assert "Smirga verfehlt" in result  # melee missed
    assert "verwirrt" in result  # LEVI's own flavor line
    assert "besiegt" in result  # the bonus strike finished it off
    assert game._combat_monster_code is None


def test_febr_lands_its_rare_bonus_hit_against_the_oger(game):
    """Integration test for combat.resolve_febr() wired into the real
    Q&A flow - see PHASE0_FINDINGS.md UPDATE 38. FEBR only ever deals
    damage against one specific monster, the Oger (object 162)."""
    OGER_CODE = 162
    game.aszhanti_known_spells = 5  # UPDATE 83 gates casting on this
    game.current_room = 1
    game._location_overrides[OGER_CODE] = 1  # place the (normally off-stage) Oger here
    game.attack("oger")
    assert game._combat_monster_code == OGER_CODE
    game._combat_answer("Schwert")
    # target-select, monster roll(miss, attack=12), player roll(miss,
    # defense=10), FEBR: cast roll 6 (>5) succeeds, power roll 3 (>=3)
    # lands the bonus hit.
    rng = _FakeRng([5, 1, 1, 6, 3])
    result = game._combat_answer("FEBR", rng=rng)
    assert "blendet" in result  # the bonus-hit variant, not the flavor-only one
    assert "Schadenspunkt" in result
    assert game._combat_monster_hp == 39  # 40 hp - 1 point


def test_febr_is_flavor_only_against_a_different_monster(game):
    game.aszhanti_known_spells = 5  # UPDATE 83 gates casting on this
    game.current_room = TROLL_ROOM  # the bridge troll (134) is NOT the Oger
    game.attack("troll")
    game._combat_answer("Schwert")
    # target-select, monster roll(hits, attack=0), monster dmg x3,
    # player roll(miss, defense=10), FEBR cast roll 6 (>5) succeeds
    # but wrong monster - no power roll even attempted.
    rng = _FakeRng([5, 1, 2, 2, 2, 1, 6])
    result = game._combat_answer("FEBR", rng=rng)
    assert "Schadenspunkt" not in result
    assert game._combat_monster_hp == 1  # unchanged


def test_unrecognized_spell_name_has_no_effect(game):
    """All 5 real spell names (LEVI/KUBL/UNSI/TOPA/FEBR) are
    implemented - anything else typed at the spell prompt still
    changes nothing beyond the melee round."""
    game.current_room = TROLL_ROOM
    game.attack("troll")
    game._combat_answer("Schwert")
    rng = _FakeRng([5, 1, 2, 2, 2, 1])  # melee only - troll survives (misses)
    result = game._combat_answer("Spruch III", rng=rng)
    assert "verwirrt" not in result
    assert game._combat_monster_hp == 1  # unchanged by the unrecognized spell name


# --- spell-known check at the spell prompt (UPDATE 83) ---


def test_casting_an_unlearned_real_spell_name_has_no_effect(game):
    """LEVI/FEBR are Spell I/II (SPELL_LEARN_ORDER) - a fresh game
    (`aszhanti_known_spells == 0`, before ever visiting Mygra) hasn't
    learned either yet, so casting LEVI has no effect, same as typing
    any other unrecognized text (see test_unrecognized_spell_name_has_
    no_effect just above)."""
    assert game.aszhanti_known_spells == 0
    game.current_room = TROLL_ROOM
    game.attack("troll")
    game._combat_answer("Schwert")
    rng = _FakeRng([5, 1, 2, 2, 2, 1])  # melee only - troll survives (misses)
    result = game._combat_answer("LEVI", rng=rng)
    assert "verwirrt" not in result
    assert game._combat_monster_hp == 1  # unchanged - LEVI not learned yet


def test_learning_only_levi_and_febr_still_blocks_kubl(game):
    """Spell III (KUBL) requires aszhanti_known_spells >= 3 - having
    learned just the first two (Mygra's own confirmed event) isn't
    enough."""
    game.aszhanti_known_spells = 2  # LEVI + FEBR, exactly what Mygra teaches
    game.current_room = TROLL_ROOM
    game.attack("troll")
    game._combat_answer("Schwert")
    rng = _FakeRng([5, 1, 2, 2, 2, 1])
    result = game._combat_answer("KUBL", rng=rng)
    assert "Kubl" not in result
    assert game._combat_monster_hp == 1  # unchanged - KUBL not learned yet


def test_kubl_deals_direct_damage_and_can_finish_off_a_monster(game):
    """Integration test for combat.resolve_kubl() wired into the real
    Q&A flow - see PHASE0_FINDINGS.md UPDATE 36."""
    game.aszhanti_known_spells = 5  # UPDATE 83 gates casting on this
    game.current_room = TROLL_ROOM
    game.attack("troll")
    game._combat_answer("Schwert")
    # melee: target-select, monster roll(hits, attack=0), monster dmg
    # dice x3, player roll(miss, defense=10) - troll (hp=1) survives;
    # KUBL: cast roll 6 (>5) succeeds, damage die 4 -> more than enough
    # to finish off the troll's 1 remaining hp.
    rng = _FakeRng([5, 1, 2, 2, 2, 1, 6, 4])
    result = game._combat_answer("KUBL", rng=rng)
    assert "Smirga verfehlt" in result
    assert "Kubl" in result
    assert "besiegt" in result
    assert game._combat_monster_code is None


def test_unsi_and_topa_are_pure_status_effects_with_no_damage(game):
    """Integration test for combat.resolve_unsi()/resolve_topa() wired
    into the real Q&A flow - see PHASE0_FINDINGS.md UPDATE 37. Neither
    touches monster hp at all, confirmed via the real disassembly."""
    game.aszhanti_known_spells = 5  # UPDATE 83 gates casting on this
    game.current_room = TROLL_ROOM
    game.aszhanti_health = 1000  # generous - this test isn't about survival
    game.attack("troll")
    game._combat_answer("Schwert")
    rng = _FakeRng([5, 1, 2, 2, 2, 1, 6])  # melee misses, then UNSI cast succeeds
    result = game._combat_answer("UNSI", rng=rng)
    assert "Unsi" in result and "verwirrt" in result
    assert game._combat_monster_hp == 1  # unchanged - no damage from UNSI
    assert game._combat_monster_code == TROLL_CODE  # still fighting
    assert game._combat_awaiting == "weapon"  # auto-reprompted for the next round

    game._combat_answer("Schwert")  # now awaiting "spell" again
    rng2 = _FakeRng([5, 1, 2, 2, 2, 1, 6])
    result2 = game._combat_answer("TOPA", rng=rng2)
    assert "Topa" in result2 and "verwirrt" in result2
    assert game._combat_monster_hp == 1  # still unchanged


def test_attack_kills_monster_and_applies_confirmed_leveling(game):
    game.current_room = TROLL_ROOM
    start_aszhanti_str = game.aszhanti_strength
    start_smirga_str = game.smirga_strength
    start_aszhanti_max = game.aszhanti_max_health
    start_smirga_max = game.smirga_max_health
    # target-select, monster roll(always hits, dmg irrelevant to test),
    # monster damage dice x3, player roll(hits, defense=10), player dmg die
    rng = _FakeRng([5, 1, 1, 1, 1, 20, 6])
    result = _start_and_resolve_round(game, "troll", rng)
    assert "besiegt" in result
    assert game._combat_monster_code is None  # fight over
    assert game._combat_monster_hp is None
    assert game._combat_awaiting is None
    # confirmed leveling (UPDATE 22/23): Aszhanti +1 flat Strength, Smirga
    # += the troll's own strength-reward byte, both +1 max hp
    assert game.aszhanti_strength == start_aszhanti_str + 1
    assert game.smirga_strength == start_smirga_str + game.monster_stats.strength_reward(
        game.world.flags[TROLL_CODE].instance_index
    )
    assert game.aszhanti_max_health == start_aszhanti_max + 1
    assert game.smirga_max_health == start_smirga_max + 1


# --- player death (sub_879F's own end-of-round HP<=0 check, flat
# 0x9100-0x9138 - see PHASE0_FINDINGS.md UPDATE 41, and _check_player_death
# in game.py) ---


def test_monster_damage_that_drops_a_character_to_zero_ends_the_game(game):
    game.current_room = TROLL_ROOM
    # target-select(<=10 -> Aszhanti), monster roll(always hits, attack=0),
    # 3 damage dice maxed out (18+5 dice_bonus=23, no armor -> lethal
    # against Aszhanti's default 20 hp), player roll(misses, defense=10)
    rng = _FakeRng([1, 1, 6, 6, 6, 1])
    result = _start_and_resolve_round(game, "troll", rng)
    assert "letzten Lebenshauch" in result
    assert game.aszhanti_health <= 0
    assert game.running is False
    # the fight state itself is torn down too - nothing to resume
    assert game._combat_monster_code is None
    assert game._combat_awaiting is None


def test_death_does_not_reprompt_for_the_next_weapon(game):
    game.current_room = TROLL_ROOM
    rng = _FakeRng([1, 1, 6, 6, 6, 1])
    result = _start_and_resolve_round(game, "troll", rng)
    assert game.WEAPON_PROMPT not in result


# --- repl()'s pre-filled combat prompt (see _combat_prompt_default in
# game.py, repl_input.py) - scoped to ONLY the weapon/spell prompts, not
# every command, per explicit correction of an earlier, too-broad draft ---


def test_combat_prompt_default_only_applies_to_weapon_and_spell_prompts():
    from laas_port.game import _combat_prompt_default

    assert _combat_prompt_default("weapon", "schwert", "levi") == "schwert"
    assert _combat_prompt_default("spell", "schwert", "levi") == "levi"
    assert _combat_prompt_default(None, "schwert", "levi") == ""


# --- the dragon-cult ambush and poison-gas cave trap (both confirmed via
# the master per-turn dispatcher - see PHASE0_FINDINGS.md UPDATE 40/41/44) ---


def test_fanatic_ambush_fires_in_the_confirmed_window_and_destroys_the_scarabaeus(game):
    game.current_room = FANATIC_AMBUSH_ROOM
    game.time_of_day = 10  # inside the confirmed 0-19 window
    game._location_overrides[SCARABAEUS_CODE] = LIMBO_CARRIED
    result = game.execute_chain("schau")
    assert any("Fanatiker" in r for r in result)
    assert game.object_location(SCARABAEUS_CODE) != LIMBO_CARRIED
    assert game.object_location(SCARABAEUS_DEPLETED_CODE) == LIMBO_CARRIED
    assert game.aszhanti_health == 18  # 20 - 2
    assert game.smirga_health == 19  # 20 - 1


def test_fanatic_ambush_does_not_fire_outside_the_confirmed_window(game):
    game.current_room = FANATIC_AMBUSH_ROOM
    game.time_of_day = 70  # noon - well outside 0-19/149-255
    game._location_overrides[SCARABAEUS_CODE] = LIMBO_CARRIED
    result = game.execute_chain("schau")
    assert not any("Fanatiker" in r for r in result)
    assert game.object_location(SCARABAEUS_CODE) == LIMBO_CARRIED


def test_fanatic_ambush_does_not_fire_without_a_scarabaeus(game):
    """Port-only guard (see _check_fanatic_ambush's docstring): the real
    game never checks this, but conjuring object 182 for a player who
    never had 206 would be a real mechanical anomaly, not just a
    narrative quirk - unlike the gas trap's equivalent case."""
    game.current_room = FANATIC_AMBUSH_ROOM
    game.time_of_day = 10
    result = game.execute_chain("schau")
    assert not any("Fanatiker" in r for r in result)
    assert game.object_location(SCARABAEUS_DEPLETED_CODE) != LIMBO_CARRIED


def test_fanatic_ambush_does_not_refire_once_depleted(game):
    game.current_room = FANATIC_AMBUSH_ROOM
    game.time_of_day = 10
    game._location_overrides[SCARABAEUS_DEPLETED_CODE] = LIMBO_CARRIED
    result = game.execute_chain("schau")
    assert not any("Fanatiker" in r for r in result)


def test_gas_trap_kills_instantly_with_the_depleted_scarabaeus(game):
    game.current_room = 102
    game._location_overrides[SCARABAEUS_DEPLETED_CODE] = LIMBO_CARRIED
    result = game.execute_chain("schau")
    assert any("letzten Lebenshauch" in r for r in result)
    assert game.running is False


def test_gas_trap_protects_at_full_charge(game):
    game.current_room = 103
    game.scarabaeus_charge = 2
    result = game.execute_chain("schau")
    assert any("nimmt er uns nicht die Sinne" in r for r in result)
    assert game.running is True


def test_gas_trap_near_miss_then_death_on_second_exposure(game):
    game.current_room = 102
    first = game.execute_chain("schau")
    assert any("keine große" in r for r in first)  # the near-miss flicker line
    assert game.running is True
    assert game._gas_trap_warned is True
    second = game.execute_chain("schau")
    assert any("letzten Lebenshauch" in r for r in second)
    assert game.running is False


def test_save_load_round_trip_includes_scarabaeus_state(game, tmp_path):
    game.current_room = 102
    game.execute_chain("schau")  # triggers the near-miss, sets _gas_trap_warned
    game.scarabaeus_charge = 1
    path = tmp_path / "save.json"
    game.save(path)

    from laas_port.game import DEFAULT_ASSETS_DIR, GameState

    fresh = GameState(DEFAULT_ASSETS_DIR)
    fresh.load_save(path)
    assert fresh.scarabaeus_charge == 1
    assert fresh._gas_trap_warned is True


# --- GIB <item> <recipient>, Mygra's Scarabäus recharge (see PHASE0_
# FINDINGS.md UPDATE 45, reference/walkthrough_de.txt) ---


def test_give_depleted_scarabaeus_to_mygra_starts_recharging(game):
    game.current_room = 4  # Mygra's house
    game._location_overrides[SCARABAEUS_DEPLETED_CODE] = LIMBO_CARRIED
    result = game.give("#182 mygra")
    assert "Mygra" in result
    assert game.scarabaeus_charge == 1
    assert game.object_location(SCARABAEUS_DEPLETED_CODE) != LIMBO_CARRIED
    assert game._scarabaeus_recharge_deadline == game._turn_counter + 10


def test_give_without_carrying_the_item_is_refused(game):
    game.current_room = 4
    result = game.give("#182 mygra")
    assert "trage ich nicht" in result
    assert game.scarabaeus_charge == 0


def test_give_to_someone_who_cannot_use_it_is_refused(game):
    game.current_room = 67
    game._location_overrides[SCARABAEUS_DEPLETED_CODE] = LIMBO_CARRIED
    game._location_overrides[25] = 67  # Har - present, but not Mygra
    result = game.give("#182 har")
    assert "kann damit nichts anfangen" in result
    assert game.scarabaeus_charge == 0


# --- give money to Mygra for spell lessons (see MYGRA_SPELL_TEACHING_*,
# user-supplied real DOSBox screenshot "lerne_spells.png") ---


def test_give_money_to_mygra_requires_the_flat_price(game):
    game.current_room = 4
    game.money = 2
    result = game.give("geld")
    assert "3 Gerfs" in result
    assert game.money == 2
    assert game.aszhanti_known_spells == 0


def test_give_money_to_mygra_teaches_levi_and_febr_and_is_one_time(game):
    """Spell I=LEVI, II=FEBR (SPELL_LEARN_ORDER, PHASE0_FINDINGS.md
    UPDATE 82) - NOT KUBL, which is Spell III and only learnable at the
    Magiergilde (user-corrected; an earlier pass of this feature
    wrongly assumed the combat SPELL_PROMPT's own menu order - LEVI,
    KUBL, FEBR, ... - also matched the Spell I-V progression order)."""
    game.current_room = 4
    game.money = 100  # any amount - only the flat price is ever taken
    result = game.give("geld")
    assert "LEVI und FEBR" in result
    assert "3 Gerfs" in result
    assert game.money == 97
    assert game.aszhanti_known_spells == 2
    # a second gift doesn't teach anything more or charge again
    second = game.give("geld")
    assert "LEVI" not in second
    assert game.money == 97


def test_give_money_without_mygra_present_is_refused(game):
    game.current_room = 67  # Hyllok village square - Mygra isn't here
    game.money = 100
    result = game.give("geld")
    assert "geben" in result
    assert game.money == 100
    assert game.aszhanti_known_spells == 0


def test_gebe_geld_parses_and_executes_end_to_end(game):
    """Exact interaction from the screenshot: typing "gebe geld" (no
    explicit recipient) while Mygra is present."""
    game.current_room = 4
    game.money = 3
    result = game.execute(parse("gebe geld"))
    assert "LEVI und FEBR" in result
    assert game.aszhanti_known_spells == 2


def test_save_load_round_trip_includes_known_spells(game, tmp_path):
    game.current_room = 4
    game.money = 3
    game.give("geld")
    path = tmp_path / "save.json"
    game.save(path)

    from laas_port.game import DEFAULT_ASSETS_DIR, GameState

    fresh = GameState(DEFAULT_ASSETS_DIR)
    fresh.load_save(path)
    assert fresh.aszhanti_known_spells == 2


def test_scarabaeus_recharge_completes_after_ten_turns(game):
    game.current_room = 4
    game._location_overrides[SCARABAEUS_DEPLETED_CODE] = LIMBO_CARRIED
    game.give("#182 mygra")
    for _ in range(9):
        result = game.execute_chain("schau")
        assert not any("repariert" in r for r in result)
    result = game.execute_chain("schau")
    assert any("repariert" in r for r in result)
    assert game.scarabaeus_charge == 2
    assert game.object_location(SCARABAEUS_CODE) == LIMBO_CARRIED


def test_recharged_scarabaeus_protects_from_the_gas_trap(game):
    game.current_room = 4
    game._location_overrides[SCARABAEUS_DEPLETED_CODE] = LIMBO_CARRIED
    game.give("#182 mygra")
    for _ in range(10):
        game.execute_chain("schau")
    assert game.scarabaeus_charge == 2
    game.current_room = 102
    result = game.execute_chain("schau")
    assert any("nimmt er uns nicht die Sinne" in r for r in result)
    assert game.running is True


def test_save_load_round_trip_includes_the_recharge_deadline(game, tmp_path):
    game.current_room = 4
    game._location_overrides[SCARABAEUS_DEPLETED_CODE] = LIMBO_CARRIED
    game.give("#182 mygra")
    path = tmp_path / "save.json"
    game.save(path)

    from laas_port.game import DEFAULT_ASSETS_DIR, GameState

    fresh = GameState(DEFAULT_ASSETS_DIR)
    fresh.load_save(path)
    assert fresh._scarabaeus_recharge_deadline == game._scarabaeus_recharge_deadline
    assert fresh.scarabaeus_charge == 1


def test_flee_ends_the_fight_from_the_weapon_prompt(game):
    game.current_room = TROLL_ROOM
    game.attack("troll")
    assert game._combat_awaiting == "weapon"
    result = game._combat_answer("Fliehen")
    assert "fliehen" in result.lower()
    assert game._combat_monster_code is None
    assert game._combat_monster_hp is None
    assert game._combat_awaiting is None


def test_flee_verb_also_ends_the_fight_directly(game):
    game.current_room = TROLL_ROOM
    game.attack("troll")
    result = game.flee()
    assert "fliehen" in result.lower()
    assert game._combat_monster_code is None


def test_flee_without_a_fight_says_so(game):
    result = game.flee()
    assert "kämpfe" in result.lower()


def test_execute_chain_routes_to_combat_answer_while_a_fight_is_pending(game):
    """The other half of the fix: raw typed text ("Schwert") must be
    interpreted as the pending prompt's answer, not parsed as an
    unknown verb command."""
    game.current_room = TROLL_ROOM
    game._last_shown_picture = ROOM_PICTURE_TABLE[TROLL_ROOM]  # not what this test is about
    game.attack("troll")
    results = game.execute_chain("Schwert")
    assert results == [game.SPELL_PROMPT]


# --- ambush (GameState._check_ambush(), see combat.py/PHASE0_FINDINGS.md
# UPDATE 30, corrected in UPDATE 48/49: a candidate is only eligible while
# NOT at LIMBO_REMOVED (299) - the real sub_C301 skips 299 candidates,
# confirmed via disassembly; this project's first draft had it backwards.
# Object 87 (instance idx 2, ambush_eligible=True) defaults to 299 in the
# bundled save (it's a NIGHT_ROSTER member - see UPDATE 49), so tests
# that want it to be a candidate must explicitly place it somewhere real
# first, matching what `_advance_day_night_roster()` would do at
# nightfall. ---


def test_ambush_triggers_on_a_successful_roll_and_starts_combat(game):
    game.current_room = 23  # in object 87's own MONSTER_ROOM_LISTS entry (UPDATE 78)
    game._location_overrides[87] = 23  # active, matching a real nightfall placement
    rng = _FakeRng([6])  # 1d6 roll of 6 > 3 -> ambush succeeds
    result = game._check_ambush(rng=rng)
    assert result is not None
    assert "taucht" in result
    assert game._combat_monster_code == 87
    assert game._combat_monster_hp is not None
    assert game.object_location(87) == game.current_room


def test_ambush_does_nothing_on_a_failed_roll(game):
    game.current_room = 10  # outside the safe zone, so the roll is what's under test
    game._location_overrides[87] = 10  # active - the roll, not eligibility, is under test
    rng = _FakeRng([1] * 30)  # every candidate rolls <=3 -> no ambush
    result = game._check_ambush(rng=rng)
    assert result is None
    assert game._combat_monster_code is None
    assert game.object_location(87) == 10  # unmoved


def test_ambush_does_nothing_for_a_candidate_still_at_limbo_removed(game):
    """The corrected condition itself: a candidate genuinely off (299,
    e.g. a day-roster monster during the day) must not ambush even on a
    guaranteed roll. Other creatures (the confirmed room-bound ones,
    e.g. the Brückentroll/Steinkreuz) are legitimately active by
    default in the bundled save and MAY still trigger - only object
    87's own exclusion is under test here."""
    from laas_port.world import LIMBO_REMOVED

    game.current_room = 10
    assert game.object_location(87) == LIMBO_REMOVED  # the bundled save's default
    game._check_ambush(rng=_FakeRng([6] * 30))
    assert game._combat_monster_code != 87


def test_ambush_does_not_trigger_while_already_fighting(game):
    game.current_room = TROLL_ROOM
    game.attack("troll")
    assert game._combat_monster_code == TROLL_CODE

    result = game._check_ambush(rng=_FakeRng([6]))
    assert result is None
    assert game._combat_monster_code == TROLL_CODE  # unchanged, still the troll


def test_steinkreuz_never_ambushes_despite_its_raw_ambush_eligible_flag(game):
    """User-reported: attacked by a Steinkreuz. It's a landmark (see
    names.py), not a creature - its `ambush_eligible=True` flag is a
    genuine data quirk (UPDATE 30), harmless under the port's original
    (backwards) ambush condition but exposed once that was corrected
    (UPDATE 48) - see `ObjectInstance.has_room_list` (UPDATE 77)."""
    game.current_room = 10  # outside the safe zone
    assert game.world.instances[game.world.flags[105].instance_index].ambush_eligible
    assert game.object_location(105) == 26  # its own room, not LIMBO_REMOVED

    game._check_ambush(rng=_FakeRng([6] * 30))  # every roll would succeed
    assert game._combat_monster_code != 105


def test_tuatara_never_ambushes_despite_its_raw_ambush_eligible_flag(game):
    """User-reported: the Tuatara is not a random enemy - it's the lake
    creature at the Fischerdorf (room 39), tied to a peaceful, scripted
    fetch-quest (reference/walkthrough_de.txt: "Grüße Tuatara. Bitte
    Tuatara um Hilfe für die Fischer."), not a hostile random encounter.
    Same bug shape as Steinkreuz: `ambush_eligible=True` is a genuine
    data quirk, exposed once the ambush condition was corrected
    (UPDATE 48) - see `ObjectInstance.has_room_list` (UPDATE 77)."""
    game.current_room = 10  # outside the safe zone
    assert game.world.instances[game.world.flags[146].instance_index].ambush_eligible
    assert game.object_location(146) == 39  # its own room, not LIMBO_REMOVED

    game._check_ambush(rng=_FakeRng([6] * 30))  # every roll would succeed
    assert game._combat_monster_code != 146


def test_bruckentroll_never_random_ambushes_outside_its_bridge(game):
    """Confirmed room-bound fixed encounter (UPDATE 21) - guards the
    bridge at room 25, meant to be fought there deliberately, not
    stumbled into elsewhere. Same bug shape as Steinkreuz/Tuatara above
    - see `ObjectInstance.has_room_list` (UPDATE 77)."""
    game.current_room = 10  # outside the safe zone
    assert game.world.instances[game.world.flags[134].instance_index].ambush_eligible
    assert game.object_location(134) == 25  # its own room, not LIMBO_REMOVED

    game._check_ambush(rng=_FakeRng([6] * 30))  # every roll would succeed
    assert game._combat_monster_code != 134


def test_lindwurm_never_random_ambushes_outside_its_lair(game):
    """Confirmed room-bound dragon boss (UPDATE 21) - its own lair,
    room 109. Same bug shape as Steinkreuz/Tuatara above - see
    `ObjectInstance.has_room_list` (UPDATE 77)."""
    game.current_room = 10  # outside the safe zone
    assert game.world.instances[game.world.flags[237].instance_index].ambush_eligible
    assert game.object_location(237) == 109  # its own room, not LIMBO_REMOVED

    game._check_ambush(rng=_FakeRng([6] * 30))  # every roll would succeed
    assert game._combat_monster_code != 237


def test_tatzelwurm_never_random_ambushes_outside_its_lair(game):
    """Confirmed room-bound dragon boss (UPDATE 21) - its own lair,
    room 104. Same bug shape as Steinkreuz/Tuatara above - see
    `ObjectInstance.has_room_list` (UPDATE 77)."""
    game.current_room = 10  # outside the safe zone
    assert game.world.instances[game.world.flags[238].instance_index].ambush_eligible
    assert game.object_location(238) == 104  # its own room, not LIMBO_REMOVED

    game._check_ambush(rng=_FakeRng([6] * 30))  # every roll would succeed
    assert game._combat_monster_code != 238


# --- Hyllok is a safe zone - no random ambush there (user-confirmed; see
# SAFE_ZONE_ROOMS, matching room_text.py's already-confirmed room map) ---


def test_no_ambush_anywhere_inside_hyllok_even_on_a_guaranteed_roll(game):
    for room in (1, 2, 3, 4, 5, 6, 7, 8, 9, 67):
        game.current_room = room
        game._location_overrides[87] = room  # active - the safe-zone check is under test
        result = game._check_ambush(rng=_FakeRng([6] * 30))  # every roll would succeed
        assert result is None, f"ambush fired in safe room {room}"
        assert game._combat_monster_code is None
        assert game.object_location(87) == room  # unmoved


def test_ambush_can_fire_at_room_10_the_first_room_outside_hyllok(game):
    game.current_room = 10  # "Vor Hyllok" - confirmed the first non-safe room
    # Raubfliege (36) is the only wanderer whose confirmed
    # MONSTER_ROOM_LISTS entry includes room 10 (UPDATE 78).
    result = game._check_ambush(rng=_FakeRng([6] * 30))
    assert result is not None
    assert game._combat_instance_idx == 36


def test_go_never_triggers_an_ambush_while_moving_within_hyllok(game):
    game.current_room = 67
    game._location_overrides[87] = 1  # active at the destination - safe zone still wins
    result = game.go("N", rng=_FakeRng([6] * 30))  # every roll would succeed
    assert game.current_room == 1  # still inside Hyllok
    assert "taucht" not in result
    assert game._combat_monster_code is None


def test_go_appends_ambush_message_on_a_successful_roll(game):
    game.current_room = 10  # "Vor Hyllok" - outside the safe zone (see SAFE_ZONE_ROOMS)
    # instance 0 (Goblin) is always active and room 11 (the destination)
    # is in its own confirmed MONSTER_ROOM_LISTS entry (UPDATE 78) - no
    # override needed.
    result = game.go("N", rng=_FakeRng([6]))
    assert game.current_room == 11
    assert "taucht" in result
    assert game.WEAPON_PROMPT in result  # combat starts immediately, no separate command
    assert game._combat_instance_idx == 0
    assert game._combat_awaiting == "weapon"


def test_go_does_not_append_anything_on_a_failed_roll(game):
    game.current_room = 67
    result = game.go("N", rng=_FakeRng([1] * 30))
    assert game.current_room == 1
    assert "taucht" not in result
    assert game._combat_monster_code is None


def test_save_load_round_trip_includes_combat_state(game, tmp_path):
    game.current_room = TROLL_ROOM
    game.attack("troll")
    game._combat_answer("Schwert")  # now awaiting "spell", mid-prompt
    game.aszhanti_armor = 264
    game.smirga_armor = 52
    path = tmp_path / "save.json"
    game.save(path)

    from laas_port.game import DEFAULT_ASSETS_DIR, GameState

    fresh = GameState(DEFAULT_ASSETS_DIR)
    fresh.load_save(path)
    assert fresh._combat_monster_code == TROLL_CODE
    assert fresh._combat_monster_hp == game._combat_monster_hp
    assert fresh._combat_awaiting == "spell"
    assert fresh.aszhanti_armor == 264
    assert fresh.smirga_armor == 52


# --- SLEEP (schlafe/übernachte) - confirmed room-by-room mechanic, see
# SLEEP_* constants in game.py and PHASE0_FINDINGS.md UPDATE 50 ---


def test_sleep_is_refused_during_the_day(game):
    game.current_room = 67
    game.time_of_day = 50  # well before nightfall (0x80)
    result = game.sleep()
    assert "tagsüber" in result
    assert "munter" not in result  # the wake-up line never fires


def test_sleep_in_own_bedroom_at_night_is_safe(game):
    game.current_room = 6  # Aszhantis Zimmer
    game.time_of_day = 0x90
    result = game.sleep()
    assert "Wunderbares" in result
    assert "munter" in result  # the confirmed wake-up line


def test_sleep_in_hyllok_suggests_going_home(game):
    game.current_room = 67  # Dorfplatz, not a bedroom itself
    game.time_of_day = 0x90
    result = game.sleep()
    assert "eigenen Betten" in result


def test_sleep_near_the_bridge_troll_is_refused(game):
    game.current_room = TROLL_ROOM
    game.time_of_day = 0x90
    result = game.sleep()
    assert "Brückentroll" in result


def test_sleep_gets_kicked_out_of_gultibas_shop(game):
    game.current_room = 75
    game.time_of_day = 0x90
    result = game.sleep()
    assert "Laden zu verlassen" in result


def test_sleep_gets_kicked_out_of_gultibas_bedroom(game):
    game.current_room = 88
    game.time_of_day = 0x90
    result = game.sleep()
    assert "Gultiba hätte das gar nicht gern" in result


def test_sleep_in_sabrinas_house_triggers_the_nightmare_scene(game):
    game.current_room = 98
    game.time_of_day = 0x90
    result = game.sleep()
    assert "Sabrina hat uns im Schlaf erwischt" in result


def test_sleep_near_the_tatzelwurm_gets_you_bitten_awake(game):
    game.current_room = 100
    game.time_of_day = 0x90
    result = game.sleep()
    assert "Tatzelwurms" in result


def test_sleep_in_the_lindwurms_lair_is_fatal(game):
    game.current_room = 109
    game.time_of_day = 0x90
    result = game.sleep()
    assert "versengende" in result
    assert "letzten Lebenshauch" in result
    assert game.running is False


def test_sleep_in_skeeves_bedroom_is_fine(game):
    game.current_room = 62
    game.time_of_day = 0x90
    result = game.sleep()
    assert "Skeeve" in result


def test_sleep_in_the_open_street_gets_you_robbed(game):
    game.current_room = 70  # Marktplatz - a generic street room, not specially handled
    game.money = 100
    game.time_of_day = 0x90
    result = game.sleep()
    assert "alles Geld" in result
    assert game.money == 0


def test_sleep_elsewhere_manages_somehow(game):
    game.current_room = 40  # a generic, unhandled room
    game.time_of_day = 0x90
    result = game.sleep()
    assert "irgendwie einrichten" in result
    assert "munter" in result


# --- the Salami race (UPDATE 58, user-reported + confirmed via live
# screenshots): a Salami (11) starts in room 8 (Speisekammer); Har (25)
# follows the player there from room 2 and takes it unless the player
# gets there first ---


def test_salami_is_present_in_the_speisekammer_by_default(game):
    game.current_room = SALAMI_ROOM
    text = game.look()
    assert "Salami" in text
    assert "Objekte hier: Salami" in text


def test_har_follows_the_player_from_room_2_and_takes_the_salami(game):
    game.current_room = SALAMI_HOME_ROOM
    game._move_object(25, SALAMI_HOME_ROOM)  # Har alongside the player, as in the screenshot
    result = game.go("N")
    assert "Har kommt wortlos zu uns." in result
    assert "Har ist hier." in result
    assert "Har steckt die Salami ein, die hier herumlag." in result
    assert game.object_location(SALAMI_CODE) == LIMBO_REMOVED

    # A second look no longer mentions the Salami at all (confirmed via
    # screenshot: the sentence is dropped entirely, not replaced).
    text = game.look()
    assert "Salami" not in text


def test_player_can_grab_the_salami_before_har_does(game):
    game.current_room = SALAMI_ROOM
    assert game.take("salami") == "Genommen."
    assert game.object_location(SALAMI_CODE) == LIMBO_CARRIED

    game.current_room = SALAMI_HOME_ROOM
    game._move_object(25, SALAMI_HOME_ROOM)
    result = game.go("N")
    assert "Har kommt wortlos zu uns." in result
    assert "steckt die Salami ein" not in result


def test_har_does_not_follow_from_a_different_room(game):
    game.current_room = 1  # Aszhantis Elternhaus, not Har's confirmed room-2 spot
    game._move_object(25, 1)
    result = game.go("N")
    assert "Har kommt wortlos zu uns." not in result


def test_unpurchased_shop_items_are_not_located_in_a_room(game):
    """User-reported (with a screenshot): no Schild in room 10 ("Vor
    Hyllok"), despite its raw flags word reading exactly 10 - UPDATE 58's
    object_location() fix was too broad. A merchant-priced item's raw
    value (when not yet bought/carried) is some kind of shop-stock
    reference, not a room placement (UPDATE 59) - Schild's price is 30
    Gerfs, confirmed via item_stats."""
    assert game.item_stats.buy_price(14) > 0  # Schild - a real shop item
    assert game.object_location(14) is None
    game.current_room = 10
    assert game.take("schild") == "Das sehe ich hier nicht."
    assert "Schild" not in game.look()


# --- EXITS (the real game's "F2" key shortcut, UPDATE 61) ---


def test_exits_matches_the_confirmed_room_10_text(game):
    game.current_room = 10
    assert game.exits() == (
        "Unmittelbare Ausgänge führen nach Norden, Nordosten, nach Osten, "
        "nach Süden und nach Westen."
    )


def test_exits_matches_the_confirmed_room_2_text(game):
    """KNOWN GAP: room 2 also has a confirmed real Westen exit not
    reflected here - see GameState.exits()'s docstring."""
    game.current_room = 2
    assert game.exits() == "Unmittelbare Ausgänge führen nach Norden, nach Osten und nach Oben."


def test_exits_matches_the_confirmed_room_18_text(game):
    """UPDATE 66: room 18's F2 listing confirms its slot-7 exit is real
    "Nordwesten", not "Oben" - the same slot room 2 uses for "Oben" -
    proving that override is room-specific, not a slot-wide relabeling."""
    game.current_room = 18
    assert game.exits() == (
        "Unmittelbare Ausgänge führen nach Norden, nach Südwesten, "
        "nach Westen und nach Nordwesten."
    )


def test_exits_matches_the_confirmed_room_11_text(game):
    """UPDATE 66: proves "nach" is kept before a compound direction
    (Südosten) here, disproving UPDATE 61's "compound directions drop
    nach" theory - only room 10's Nordosten does that, a one-off."""
    game.current_room = 11
    assert game.exits() == (
        "Unmittelbare Ausgänge führen nach Osten, nach Südosten, "
        "nach Süden und nach Westen."
    )


def test_exits_verb_is_reachable_via_the_parser(game):
    game.current_room = 10
    assert game.execute(parse("exits")) == game.exits()
    assert game.execute(parse("ausgänge")) == game.exits()


def test_oben_is_a_room_2_specific_alias_for_the_same_nw_move(game):
    """UPDATE 66 (correcting UPDATE 61's over-generalization): the
    exit-table slot this port calls "NW" is confirmed real "Oben" for
    room 2 specifically (a staircase up to Smirga's room, room 7) -
    but confirmed real "Nordwesten" elsewhere (room 18, via a second
    user screenshot AND independent exit-graph reciprocity with room
    11). "oben"/"hinauf"/"rauf" are just parser aliases for the same
    "NW" move, not a distinct direction - typing "nw" at room 2 must
    reach the exact same place "oben" does."""
    game.current_room = 2
    assert parse("oben").verb == "NW"
    assert game.execute(parse("oben")).startswith("[Raum 7")
    game.current_room = 2
    assert game.go("NW").startswith("[Raum 7")


def test_nw_is_a_real_compass_direction_elsewhere(game):
    """UPDATE 66: room 18's slot 7 is confirmed real "Nordwesten" -
    the SAME raw exit-table slot room 2 uses for "Oben" - proving the
    label isn't fixed by slot index alone. Room 11's real SE exit leads
    to 18, and 18's slot 7 leads right back to 11 - independent
    reciprocity confirmation on top of the screenshot text."""
    assert parse("nw").verb == "NW"
    game.current_room = 18
    assert game.go("NW").startswith("[Raum 11")


# --- the farmer's harvest-help quest (UPDATE 68, found while tracing
# what raises/lowers Ansehen) ---


def test_helfen_bauer_triggers_the_full_harvest_reward(game):
    game.current_room = FARMER_ROOM
    game._move_object(FARMER_CODE, FARMER_ROOM)
    game.ansehen = 0
    game.smirga_strength = 0
    game.aszhanti_strength = 0
    game.aszhanti_max_health = 20
    game.smirga_max_health = 20
    result = game.helfen("bauer")
    assert "Oh danke" in result
    assert "Schinken" in result
    assert game.ansehen == 1
    assert game.smirga_strength == 2
    assert game.aszhanti_strength == 1
    assert game.aszhanti_max_health == 21
    assert game.smirga_max_health == 21
    assert game.hunger == 150
    assert game.aszhanti_durst == 100
    assert game.smirga_durst == 100
    assert FARMER_QUEST_SCHINKEN_CODE in game.objects_carried()


def test_helfen_bauer_reflects_the_current_ansehen_tier(game):
    """UPDATE 68: the farmhouse conversation reacts to Ansehen using
    the exact same 4 thresholds as the confirmed status-screen ladder
    (UPDATE 23) - checked AFTER this quest's own +1 bump, matching the
    disassembly's instruction order."""
    game.current_room = FARMER_ROOM
    game._move_object(FARMER_CODE, FARMER_ROOM)
    game.ansehen = 5  # +1 from the quest -> 6, the "<=6" tier
    result = game.helfen("bauer")
    assert "Ja ja, ich habe schon von euch gehört" in result


def test_helfen_bauer_is_a_one_time_reward(game):
    game.current_room = FARMER_ROOM
    game._move_object(FARMER_CODE, FARMER_ROOM)
    game.helfen("bauer")
    ansehen_after_first = game.ansehen
    result = game.helfen("bauer")
    assert "fertig mit der" in result and "Ernte" in result
    assert game.ansehen == ansehen_after_first  # no repeat reward


def test_farmer_storm_destroys_the_harvest_if_you_wait_too_long(game):
    game.current_room = FARMER_ROOM
    game._move_object(FARMER_CODE, FARMER_ROOM)
    result = None
    for _ in range(FARMER_QUEST_STORM_TURNS):
        result = game._check_farmer_storm()
    assert result is not None
    assert "Gewitter" in result or "regnen" in result
    assert game._farmer_quest_state == 2
    # too late now - helping just gets the angry response, no reward
    game.ansehen = 0
    late_result = game.helfen("bauer")
    assert "zu spät" in late_result
    assert game.ansehen == 0


def test_farmer_storm_does_not_advance_outside_the_farmer_room(game):
    game.current_room = 67
    for _ in range(FARMER_QUEST_STORM_TURNS + 2):
        assert game._check_farmer_storm() is None
    assert game._farmer_quest_state == 0


def test_room_20_description_reflects_quest_state(game):
    game.current_room = FARMER_ROOM
    game._move_object(FARMER_CODE, FARMER_ROOM)
    assert "geerntet" not in game.look()  # untouched state (message 344)

    game.helfen("bauer")
    assert "geernteten Kornfeld" in game.look()

    game._farmer_quest_state = 2
    assert "zerschlagenen Kornfeld" in game.look()


# --- the Tuatara bounty/diplomacy quest (UPDATE 69, found while tracing
# Phadraig's confirmed oar-return reward) ---


def test_frage_phadraig_starts_the_tuatara_quest(game):
    game.current_room = TUATARA_TAVERN_ROOM
    result = game.frage("phadraig")
    assert "150 Gerfs" in result
    assert RUDER_CODE in game.objects_carried()


def test_frage_phadraig_is_a_one_time_offer(game):
    game.current_room = TUATARA_TAVERN_ROOM
    game.frage("phadraig")
    result = game.frage("phadraig")
    assert result == game.story.message(2309)


def test_frage_phadraig_elsewhere_is_refused(game):
    """Phadraig only talks business at the tavern - moving him
    elsewhere (never happens in real play, but exercises the branch)
    hits the confirmed "not here" refusal instead of handing out the
    quest."""
    game._move_object(PHADRAIG_CODE, 67)
    game.current_room = 67
    result = game.frage("phadraig")
    assert result == "Darüber möchte ich hier nicht sprechen."
    assert RUDER_CODE not in game.objects_carried()


def test_frage_without_phadraig_present_is_refused(game):
    game.current_room = 1
    result = game.frage("phadraig")
    assert result == "Das sehe ich hier nicht."


def test_klettere_outside_the_boathouse_is_refused(game):
    game.current_room = 67
    result = game.klettere(None)
    assert result == "Das kann ich hier nicht."


def test_klettere_requires_the_ruder(game):
    game.current_room = TUATARA_BOATHOUSE_ROOM
    result = game.klettere(None)
    assert "Ruder" in result
    assert game.current_room == TUATARA_BOATHOUSE_ROOM


def test_klettere_boards_the_boat(game):
    game.current_room = TUATARA_BOATHOUSE_ROOM
    game._move_object(RUDER_CODE, LIMBO_CARRIED)
    game.klettere(None)
    assert game.current_room == TUATARA_LAKE_ROOMS[0]


def test_rudere_without_a_boat_is_refused(game):
    game.current_room = 67
    result = game.rudere(None)
    assert "gar nicht im Boot" in result


def test_rudere_from_the_boathouse_requires_boarding_first(game):
    game.current_room = TUATARA_BOATHOUSE_ROOM
    result = game.rudere(None)
    assert "erst ins Boot steigen" in result


def test_rudere_forward_through_the_lake_triggers_the_tuatara_encounter(game):
    game.current_room = TUATARA_LAKE_ROOMS[0]
    game.rudere(None)
    assert game.current_room == TUATARA_LAKE_ROOMS[1]
    result = game.rudere(None)
    assert game.current_room == TUATARA_ENCOUNTER_ROOM
    assert game.story.message(602) in result
    assert game._tuatara_quest_stage == 3
    # the confirmed-closest room is the end of the line - rowing further
    # just stays put, and the one-time encounter text doesn't repeat
    again = game.rudere(None)
    assert game.current_room == TUATARA_ENCOUNTER_ROOM
    assert game.story.message(602) not in again


def test_rudere_zurueck_from_the_boathouse_is_refused(game):
    game.current_room = TUATARA_BOATHOUSE_ROOM
    result = game.rudere("zurueck")
    assert "schon am Ufer" in result


def test_rudere_zurueck_confiscates_the_ruder_if_the_quest_is_unresolved(game):
    game.current_room = TUATARA_LAKE_ROOMS[0]
    game._move_object(RUDER_CODE, LIMBO_CARRIED)
    result = game.rudere("zurueck")
    assert game.current_room == TUATARA_BOATHOUSE_ROOM
    assert result == game.story.message(625)
    assert RUDER_CODE not in game.objects_carried()


def test_rudere_zurueck_pays_the_bounty_for_the_combat_ending(game):
    game.current_room = TUATARA_LAKE_ROOMS[0]
    game._tuatara_quest_stage = 4
    start_money = game.money
    result = game.rudere("zurueck")
    assert game.current_room == TUATARA_BOATHOUSE_ROOM
    assert result == game.story.message(626)
    assert game.money == start_money + TUATARA_BOUNTY_GERFS


def test_rudere_zurueck_pays_the_same_bounty_for_the_diplomacy_ending(game):
    game.current_room = TUATARA_LAKE_ROOMS[0]
    game._tuatara_quest_stage = 5
    start_money = game.money
    result = game.rudere("zurueck")
    assert result == game.story.message(627)
    assert game.money == start_money + TUATARA_BOUNTY_GERFS


def test_gruesse_wrong_target_is_refused(game):
    game.current_room = 67
    result = game.gruesse("tuatara")
    assert result == "Das sehe ich hier nicht."


def test_gruesse_tuatara_reveals_it_has_never_been_spoken_to(game):
    game.current_room = TUATARA_ENCOUNTER_ROOM
    result = game.gruesse("tuatara")
    assert result == game.story.message(612)
    assert game._tuatara_greeted is True


def test_bitte_before_greeting_is_refused(game):
    game.current_room = TUATARA_ENCOUNTER_ROOM
    result = game.bitte("tuatara")
    assert result == game.story.message(620)
    assert game._tuatara_quest_stage == 0


def test_bitte_after_greeting_resolves_the_quest_diplomatically(game):
    game.current_room = TUATARA_ENCOUNTER_ROOM
    game.gruesse("tuatara")
    result = game.bitte("tuatara")
    assert result == game.story.message(621)
    assert game._tuatara_quest_stage == 5


def test_bitte_does_not_downgrade_an_already_confirmed_kill(game):
    """Confirmed real precondition order (flat 0x12fcd/0x12ff6): asking
    for help after already having killed it still gets the friendly
    reply, but shouldn't undo the combat ending's own quest stage."""
    game.current_room = TUATARA_ENCOUNTER_ROOM
    game._tuatara_quest_stage = 4
    game.gruesse("tuatara")
    game.bitte("tuatara")
    assert game._tuatara_quest_stage == 4


def test_danke_defaults_to_tuatara_if_present(game):
    game.current_room = TUATARA_ENCOUNTER_ROOM
    result = game.danke(None)
    assert result == game.story.message(622)


def test_danke_elsewhere_has_no_target(game):
    game.current_room = 67
    result = game.danke(None)
    assert result == "Wofür denn?"


def test_give_ruder_to_phadraig_before_resolving_the_quest_is_refused(game):
    game.current_room = TUATARA_TAVERN_ROOM
    game._move_object(RUDER_CODE, LIMBO_CARRIED)
    result = game.give("ruder phadraig")
    assert result == game.story.message(2309)
    assert RUDER_CODE in game.objects_carried()


def test_give_ruder_to_phadraig_after_resolving_the_quest_pays_off(game):
    game.current_room = TUATARA_TAVERN_ROOM
    game._move_object(RUDER_CODE, LIMBO_CARRIED)
    game._tuatara_quest_stage = 4
    start_ansehen = game.ansehen
    result = game.give("ruder phadraig")
    assert result == game.story.message(1958)
    assert game.ansehen == start_ansehen + 1
    assert RUDER_CODE not in game.objects_carried()


def test_killing_tuatara_in_combat_advances_the_quest_and_appends_its_message(game):
    game.current_room = TUATARA_ENCOUNTER_ROOM
    weapon_prompt = game.attack("tuatara")
    assert weapon_prompt == game.WEAPON_PROMPT
    game._combat_monster_hp = 1  # force a one-hit kill, same trick as the troll tests
    game._combat_answer("Schwert")
    # target=Aszhanti, monster misses (attack=10, no damage dice consumed),
    # player hits (defense=10) for a 1d6+bonus killing blow.
    rng = _FakeRng([5, 1, 20, 6])
    result = game._combat_answer("Keinen", rng=rng)
    assert "besiegt" in result
    assert game.story.message(611) in result
    assert game._tuatara_quest_stage == 4


# --- Potidan's Mondscheinkraut quest (UPDATE 70, another of UPDATE 67's
# 8 confirmed Ansehen sources) ---


def test_frage_potidan_reveals_the_quest_on_first_ask(game):
    game.current_room = POTIDAN_ROOM
    result = game.frage("potidan")
    assert result == game.story.message(1516)
    assert game._potidan_quest_stage == 1


def test_frage_potidan_reminds_you_while_the_quest_is_outstanding(game):
    game.current_room = POTIDAN_ROOM
    game.frage("potidan")
    result = game.frage("potidan")
    assert result == game.story.message(1556)


def test_frage_potidan_has_no_other_job_once_done(game):
    game.current_room = POTIDAN_ROOM
    game._potidan_quest_stage = 2
    result = game.frage("potidan")
    assert result == game.story.message(1540)


def test_frage_without_potidan_present_is_refused(game):
    game.current_room = 1
    result = game.frage("potidan")
    assert result == "Das sehe ich hier nicht."


def test_klettere_through_the_passage_reaches_the_herb_valley(game):
    game.current_room = POTIDAN_PASSAGE_ROOM
    game.klettere(None)
    assert game.current_room == POTIDAN_HERB_VALLEY_ROOM


def test_klettere_back_through_the_passage_returns(game):
    game.current_room = POTIDAN_HERB_VALLEY_ROOM
    game.klettere(None)
    assert game.current_room == POTIDAN_PASSAGE_ROOM


def test_skelett_is_only_present_in_the_valley_at_night(game):
    assert game.objects_in_room(POTIDAN_HERB_VALLEY_ROOM) == []
    game.time_of_day = 0x80
    game._advance_day_night_roster()
    assert SKELETT_CODE in game.objects_in_room(POTIDAN_HERB_VALLEY_ROOM)


def test_killing_the_skelett_grants_the_mondscheinkraut(game):
    game.time_of_day = 0x80
    game._advance_day_night_roster()
    game.current_room = POTIDAN_HERB_VALLEY_ROOM
    weapon_prompt = game.attack("skelett")
    assert weapon_prompt == game.WEAPON_PROMPT
    game._combat_monster_hp = 1  # force a one-hit kill, same trick as the troll tests
    game._combat_answer("Schwert")
    # target=Aszhanti, monster misses (attack=9, no damage dice consumed),
    # player hits (defense=13) for a 1d6+bonus killing blow.
    rng = _FakeRng([5, 1, 20, 6])
    result = game._combat_answer("Keinen", rng=rng)
    assert "besiegt" in result
    assert MONDSCHEINKRAUT_CODE in game.objects_carried()


def test_give_mondscheinkraut_to_potidan_before_asking_is_refused(game):
    game.current_room = POTIDAN_ROOM
    game._move_object(MONDSCHEINKRAUT_CODE, LIMBO_CARRIED)
    result = game.give("mondscheinkraut potidan")
    assert result == "Das interessiert Potidan jetzt nicht."
    assert MONDSCHEINKRAUT_CODE in game.objects_carried()


def test_give_mondscheinkraut_to_potidan_pays_off(game):
    game.current_room = POTIDAN_ROOM
    game.frage("potidan")
    game._move_object(MONDSCHEINKRAUT_CODE, LIMBO_CARRIED)
    start_money = game.money
    start_ansehen = game.ansehen
    game.aszhanti_health = 1
    game.smirga_health = 1
    result = game.give("mondscheinkraut potidan")
    assert game.story.message(1538) in result
    assert game.story.message(1515) in result
    assert game.money == start_money + POTIDAN_QUEST_GERFS
    assert game.ansehen == start_ansehen + 2
    assert game.aszhanti_health == game.aszhanti_max_health
    assert game.smirga_health == game.smirga_max_health
    assert MONDSCHEINKRAUT_CODE not in game.objects_carried()


def test_give_mondscheinkraut_to_potidan_is_a_one_time_reward(game):
    game.current_room = POTIDAN_ROOM
    game.frage("potidan")
    game._move_object(MONDSCHEINKRAUT_CODE, LIMBO_CARRIED)
    game.give("mondscheinkraut potidan")
    game._move_object(MONDSCHEINKRAUT_CODE, LIMBO_CARRIED)  # hypothetically had a second one
    result = game.give("mondscheinkraut potidan")
    assert result == game.story.message(1540)


def test_give_potidan_anything_else_is_a_polite_refusal(game):
    game.current_room = POTIDAN_ROOM
    game.frage("potidan")
    game._move_object(RUDER_CODE, LIMBO_CARRIED)
    result = game.give("ruder potidan")
    assert result == game.story.message(1555)


def test_give_potidan_anything_else_before_asking_is_the_generic_refusal(game):
    game.current_room = POTIDAN_ROOM
    game._move_object(RUDER_CODE, LIMBO_CARRIED)
    result = game.give("ruder potidan")
    assert "kann damit nichts anfangen" in result


# --- BILD (F6/Entf picture viewer, UPDATE 71) ---


def test_bild_without_a_number_asks_which(game):
    result = game.bild(None)
    assert result == "Welches Bild? (1-22)"
    assert game._awaiting_picture_number is True


def test_bild_verb_is_reachable_via_the_parser(game):
    assert parse("bild").verb == "BILD"


def test_bild_with_a_valid_number_shows_it(game, monkeypatch):
    shown = []
    monkeypatch.setattr(pictures, "show_picture", lambda assets_dir, n: shown.append((assets_dir, n)))
    result = game.bild("5")
    assert shown == [(game.assets_dir, 5)]
    assert result == "[Bild 5]"
    assert game._awaiting_picture_number is False


def test_bild_with_an_out_of_range_number_is_the_confirmed_real_refusal(game, monkeypatch):
    monkeypatch.setattr(pictures, "show_picture", lambda assets_dir, n: (_ for _ in ()).throw(AssertionError("should not show")))
    result = game.bild("99")
    assert result == "Illegale Bild Nr.!"
    assert game._awaiting_picture_number is True


def test_bild_with_a_non_numeric_answer_is_refused(game, monkeypatch):
    monkeypatch.setattr(pictures, "show_picture", lambda assets_dir, n: (_ for _ in ()).throw(AssertionError("should not show")))
    result = game.bild("Har")
    assert result == "Illegale Bild Nr.!"


def test_awaiting_picture_number_bypasses_normal_parsing(game, monkeypatch):
    shown = []
    monkeypatch.setattr(pictures, "show_picture", lambda assets_dir, n: shown.append(n))
    game.execute_chain("bild")
    assert game._awaiting_picture_number is True
    results = game.execute_chain("12")
    assert shown == [12]
    assert results[0] == "[Bild 12]"


def test_save_load_round_trip_includes_awaiting_picture_number(game, tmp_path):
    game.bild(None)
    path = tmp_path / "save.json"
    game.save(path)

    from laas_port.game import DEFAULT_ASSETS_DIR, GameState

    fresh = GameState(DEFAULT_ASSETS_DIR)
    fresh.load_save(path)
    assert fresh._awaiting_picture_number is True


# --- the automatic room->picture trigger (ROOM_PICTURE_TABLE, UPDATE 72) ---


def test_the_starting_room_shows_its_picture_automatically_on_construction(monkeypatch):
    shown = []
    monkeypatch.setattr(pictures, "show_picture", lambda assets_dir, n: shown.append(n))
    monkeypatch.setattr("laas_port.game.SHOW_PICTURES", True)
    from laas_port.game import DEFAULT_ASSETS_DIR, GameState

    fresh = GameState(DEFAULT_ASSETS_DIR)
    assert fresh.current_room == 67
    assert shown == [ROOM_PICTURE_TABLE[67]]
    assert fresh._last_shown_picture == ROOM_PICTURE_TABLE[67]


def test_entering_a_different_picture_room_shows_it_once(game, monkeypatch):
    shown = []
    monkeypatch.setattr(pictures, "show_picture", lambda assets_dir, n: shown.append(n))
    monkeypatch.setattr("laas_port.game.SHOW_PICTURES", True)
    game.current_room = 4  # picture 3, confirmed different from the starting room's picture 1
    result = game._check_room_picture()
    assert result == "[Bild 3]"
    assert shown == [3]
    # staying in the same room doesn't re-fire
    again = game._check_room_picture()
    assert again is None
    assert shown == [3]


def test_a_room_with_no_confirmed_picture_never_fires(game, monkeypatch):
    shown = []
    monkeypatch.setattr(pictures, "show_picture", lambda assets_dir, n: shown.append(n))
    monkeypatch.setattr("laas_port.game.SHOW_PICTURES", True)
    game.current_room = 67  # not a typo: already the "last shown" room too
    assert game._check_room_picture() is None
    game.current_room = 3  # confirmed absent from ROOM_PICTURE_TABLE
    assert game._check_room_picture() is None
    assert shown == []


def test_returning_to_an_earlier_picture_room_fires_again(game, monkeypatch):
    shown = []
    monkeypatch.setattr(pictures, "show_picture", lambda assets_dir, n: shown.append(n))
    monkeypatch.setattr("laas_port.game.SHOW_PICTURES", True)
    game.current_room = 4
    game._check_room_picture()
    game.current_room = 67  # back to the starting room's own picture
    result = game._check_room_picture()
    assert result == "[Bild 1]"
    assert shown == [3, 1]


def test_execute_chain_fires_the_room_picture_check_as_a_tick(game, monkeypatch):
    shown = []
    monkeypatch.setattr(pictures, "show_picture", lambda assets_dir, n: shown.append(n))
    monkeypatch.setattr("laas_port.game.SHOW_PICTURES", True)
    game.current_room = 4
    results = game.execute_chain("schau")
    assert "[Bild 3]" in results
    assert shown == [3]


def test_room_picture_check_returns_its_message_even_when_display_is_disabled(game, monkeypatch):
    """SHOW_PICTURES defaults to False (the user's own addition, so the
    test suite doesn't pop up real windows) - the returned "[Bild N]"
    text and `_last_shown_picture` bookkeeping still happen either way,
    only the actual `pictures.show_picture()` call is skipped."""
    shown = []
    monkeypatch.setattr(pictures, "show_picture", lambda assets_dir, n: shown.append(n))
    game.current_room = 4
    result = game._check_room_picture()
    assert result == "[Bild 3]"
    assert game._last_shown_picture == 3
    assert shown == []


def test_save_load_round_trip_includes_last_shown_picture(game, tmp_path):
    game.current_room = 4
    game._check_room_picture()
    path = tmp_path / "save.json"
    game.save(path)

    from laas_port.game import DEFAULT_ASSETS_DIR, GameState

    fresh = GameState(DEFAULT_ASSETS_DIR)
    fresh.load_save(path)
    assert fresh._last_shown_picture == ROOM_PICTURE_TABLE[4]


# --- DEBUG (F7) - a port utility, not a real game feature ---


def test_debug_verb_is_reachable_via_the_parser(game):
    assert parse("debug").verb == "DEBUG"
    assert game.execute(parse("debug")) == game.debug_info()


def test_debug_info_shows_the_safe_zone_note_at_hyllok(game):
    """UPDATE 78: none of the 9 confirmed `MONSTER_ROOM_LISTS` entries
    include any Hyllok room, so the candidate pool here is genuinely
    empty on the real game's own data, not just this port's separate
    `SAFE_ZONE_ROOMS` constant - a nice independent cross-check. The
    debug view still correctly notes the safe zone suppresses the roll,
    even though there'd be nothing to roll against here regardless."""
    game.current_room = 67  # Hyllok village square - a confirmed safe zone
    info = game.debug_info()
    assert "Safe Zone: ja" in info
    assert game._ambush_candidates() == []
    assert "1 - 0.5^0 = 0.0%" in info
    assert "Safe Zone - kein Ambush-Wurf" in info


def test_debug_info_shows_the_confirmed_day_ambush_candidates_at_a_beginner_room(game):
    """UPDATE 78: user-reported that only Goblin and Raubfliege ambush
    by day anywhere before the bridge troll - room 11 is a real,
    confirmed entry in BOTH their `MONSTER_ROOM_LISTS`, and in neither
    Ork/Slime/Wildschwein/Werwolf/Kobold/Bandit's (whose own real lists
    all sit elsewhere on the map, see the tests below) - no synthetic
    region gate needed, the real per-monster data already matches the
    user's report exactly."""
    game.current_room = 11  # "Das Hügelland" - in the beginner region
    info = game.debug_info()
    assert "Safe Zone: nein" in info
    assert game._ambush_candidates() == [0, 36]
    assert "1 - 0.5^2 = 75.0%" in info
    assert "kein Ambush-Wurf" not in info


def test_debug_info_shows_a_single_confirmed_wanderer_near_felsklippe(game):
    """UPDATE 78: room 106 ("Felsklippe" - the exact room the user's own
    Ork-fight memory dump was captured in) is in Ork's confirmed
    `MONSTER_ROOM_LISTS` entry and nobody else's - not even Goblin or
    Raubfliege, whose own lists don't reach this far. This is the
    mirror image of the beginner-room test above: it's not that Ork
    shouldn't ambush at all, just not where the user was seeing it."""
    game.current_room = 106
    info = game.debug_info()
    assert "Safe Zone: nein" in info
    assert game._ambush_candidates() == [27]
    assert "1 - 0.5^1 = 50.0%" in info
    assert "kein Ambush-Wurf" not in info


def test_debug_info_shows_the_confirmed_night_ambush_candidates_and_probability(game):
    """UPDATE 74/75/76/77/78: room 17 is in both Goblin's (always
    active) and Zombie/87's (NIGHT_ROSTER) confirmed `MONSTER_ROOM_
    LISTS` entries - by day only Goblin is active there; at night
    Zombie joins it, exactly matching the user's own original report
    (Goblin by day, also Zombie by night, in the beginner area)."""
    game.current_room = 17
    assert game._ambush_candidates() == [0]
    game.time_of_day = 0x80
    game._advance_day_night_roster()
    info = game.debug_info()
    assert game._ambush_candidates() == [0, 2]
    assert "1 - 0.5^2 = 75.0%" in info
    assert "Nacht" in info


def test_debug_info_notes_an_active_fight_suppresses_the_ambush_roll(game):
    game.current_room = TROLL_ROOM
    game.attack("troll")
    info = game.debug_info()
    assert "Kampf läuft bereits - kein Ambush-Wurf" in info
    assert "Kampf: Bruckentroll" in info or "wartet_auf=weapon" in info


def test_debug_info_reflects_quest_and_stat_state(game):
    game.ansehen = 7
    game.money = 42
    game._farmer_quest_state = 1
    game._tuatara_quest_stage = 3
    game._potidan_quest_stage = 2
    game.aszhanti_known_spells = 2
    info = game.debug_info()
    assert "Ansehen: 7  Gerfs: 42" in info
    assert "Bauer-Quest: state=1" in info
    assert "Tuatara-Quest: stage=3" in info
    assert "Potidan-Quest: stage=2" in info
    assert "Bekannte Sprüche (Asz): 2" in info


# --- UPDATE 74: the ambush pool bug - the real scanner works by raw
# instance index, not object code, and a third of real eligible
# creatures have no object code mapped to them at all ---


def test_ambush_candidates_include_confirmed_instance_only_day_wanderers(game):
    """Ork/Slime/Wildschwein (PHASE0_FINDINGS.md UPDATE 49/74) are real,
    day-only wanderers with no object code usable for ambush - each
    checked in its own confirmed `MONSTER_ROOM_LISTS` room (UPDATE 78;
    they no longer share a single generic "post-bridge" room, since the
    real per-monster restriction turned out to put each in a distinct
    zone)."""
    for idx in DAY_ROSTER_BY_INSTANCE:
        assert game._object_code_for_instance(idx) is None
    game.current_room = 106  # Ork's own confirmed zone (Felsklippe)
    assert game._ambush_candidates() == [27]
    game.current_room = 93  # Slime's own confirmed zone
    assert game._ambush_candidates() == [28]
    game.current_room = 55  # shared with Werwolf (night-only) - see below
    assert game._ambush_candidates() == [30]


def test_ambush_candidates_switch_to_the_early_night_roster(game):
    """Room 43 is in Kobold's (31) confirmed `MONSTER_ROOM_LISTS` entry
    and nobody else's - active only before the Ansehen>=5 progression
    gate unlocks the late roster."""
    game.current_room = 43
    assert game._ambush_candidates() == []  # inactive by day
    game.time_of_day = 0x80
    game._advance_day_night_roster()
    assert game._ambush_candidates() == [31]


def test_ambush_candidates_switch_to_the_late_night_roster_once_unlocked(game):
    """Room 55 sits in BOTH Werwolf's (26) and Wildschwein's (30)
    confirmed `MONSTER_ROOM_LISTS` entries (UPDATE 78) - they share a
    territory but never coexist there: Wildschwein by day, Werwolf only
    once the late night roster unlocks (Ansehen>=5), nothing at all
    during an early-game night."""
    game.current_room = 55
    assert game._ambush_candidates() == [30]  # day: Wildschwein only
    game.time_of_day = 0x80
    game._advance_day_night_roster()
    assert game._ambush_candidates() == []  # early night: neither is active
    game.ansehen = ANSEHEN_LATE_ROSTER_THRESHOLD
    game._advance_day_night_roster()
    assert game._ambush_candidates() == [26]  # late night: Werwolf only


def test_instance_32_is_an_always_active_night_wanderer_not_gated_by_ansehen(game):
    """UPDATE 49's own table lists instance 32 (room 78, "Die
    Magiergilde") with no early/late qualifier, unlike 31 and 26 -
    confirmed unconditionally active every night regardless of Ansehen
    (a real gap in the first pass at this fix, caught during a user-
    driven follow-up investigation, UPDATE 75). Room 74 is in its own
    confirmed `MONSTER_ROOM_LISTS` entry (UPDATE 78) and nobody else's."""
    game.current_room = 74
    game.time_of_day = 0x80
    game._advance_day_night_roster()
    assert game._instance_location(32) == 78
    assert 32 in game._ambush_candidates()
    game.ansehen = ANSEHEN_LATE_ROSTER_THRESHOLD
    game._advance_day_night_roster()
    assert game._instance_location(32) == 78
    assert 32 in game._ambush_candidates()


def test_room_bound_instances_without_a_room_list_are_excluded(game):
    """25/29/35 (Höhlentroll/Treksis/Harpyie, rooms 64/101/108) sit at
    fixed, non-299 locations - real ambush-eligible creatures, but
    excluded from the wandering pool because `sub_C301` skips any
    instance with no room-list pointer (UPDATE 77 - see
    `ObjectInstance.has_room_list`), confirmed room-bound/fixed
    encounters rather than wanderers. The room choice is arbitrary -
    with no list at all, they're never a candidate anywhere."""
    game.current_room = 106
    for idx in (25, 29, 35):
        assert game.world.instances[idx].ambush_eligible
        assert not game.world.instances[idx].has_room_list
        assert game._instance_location(idx) != 299
        assert idx not in game._ambush_candidates()


def test_raubfliege_has_a_real_room_list_and_is_not_excluded(game):
    """UPDATE 77/78: unlike 25/29/35, Raubfliege (36) DOES have a real
    room-list pointer - it's a genuine wanderer, not a fixed encounter,
    matching the user's own report that it ambushes alongside Goblin in
    the early game. An earlier hand-curated exclusion list wrongly
    lumped it in with 25/29/35 anyway; that bug is what this guards.
    Room 16 is Raubfliege's own static default location and, per its
    confirmed `MONSTER_ROOM_LISTS` entry, the only wanderer valid
    there."""
    game.current_room = 16
    assert game.world.instances[36].has_room_list
    assert game._ambush_candidates() == [36]


def test_object_code_for_instance_round_trips_for_known_creatures(game):
    assert game._object_code_for_instance(14) == 162  # Oger
    assert game._object_code_for_instance(24) == 244  # Skelett


def test_instance_location_defaults_to_the_raw_static_value(game):
    assert game._instance_location(27) == game.world.instances[27].location


def test_move_instance_overrides_the_location(game):
    game._move_instance(27, 5)
    assert game._instance_location(27) == 5


def test_ambush_starts_a_fight_against_an_instance_only_monster(game):
    game.current_room = 55  # Wildschwein's own confirmed zone (UPDATE 78)
    rng = _FakeRng([6])
    result = game._check_ambush(rng=rng)
    assert "Wildschwein" in result
    assert game._combat_instance_idx == 30
    assert game._combat_monster_code is None
    assert game._instance_location(30) == 55  # moved to the ambush room


def test_ambush_names_the_goblin_correctly_not_steinkreuz(game):
    """UPDATE 76: instance 0 shares its combat-stat slot with object
    105 (Steinkreuz, a landmark) purely as a raw-data quirk - a live
    memory dump plus its own confirmed name table settled that the
    creature is really a "Goblin". Ambushing must show that name, not
    Steinkreuz, and must not relocate the actual Steinkreuz object."""
    game.current_room = 11
    rng = _FakeRng([6])  # instance 0 is first in ascending order
    result = game._check_ambush(rng=rng)
    assert "Goblin" in result
    assert "Steinkreuz" not in result
    assert game._combat_instance_idx == 0
    assert game._combat_monster_code is None
    assert game.object_location(105) == 26  # Steinkreuz stayed put


def test_combat_round_resolves_against_an_instance_only_monster(game):
    game._start_combat(code=None, instance_idx=27)
    game._combat_monster_hp = 1
    game._combat_answer("Schwert")
    rng = _FakeRng([5, 1, 20, 6])
    result = game._combat_answer("Keinen", rng=rng)
    assert "besiegt" in result
    assert "Ork" in result
    assert game._combat_instance_idx is None
    assert game.smirga_strength == game.monster_stats.strength_reward(27)


def test_flee_works_against_an_instance_only_monster(game):
    """Direct regression for a real bug this refactor introduced and
    caught by manual testing, not by the suite: flee() still checked
    the object code as its "am I fighting" signal after the rest of
    combat moved to `_combat_instance_idx`, so fleeing an instance-only
    monster incorrectly said "Ich kämpfe gerade nicht."."""
    game._start_combat(code=None, instance_idx=27)
    result = game.flee()
    assert result == "Mit aller Mühe gelingt es uns zu fliehen!"
    assert game._combat_instance_idx is None


def test_attack_reprompts_instead_of_restarting_an_instance_only_fight(game):
    game._start_combat(code=None, instance_idx=27)
    game._combat_awaiting = "spell"
    assert game.attack(None) == game.SPELL_PROMPT
    assert game._combat_instance_idx == 27


def test_save_load_round_trip_includes_instance_only_combat_state(game, tmp_path):
    game._start_combat(code=None, instance_idx=27)
    game._move_instance(30, 63)
    path = tmp_path / "save.json"
    game.save(path)

    from laas_port.game import DEFAULT_ASSETS_DIR, GameState

    fresh = GameState(DEFAULT_ASSETS_DIR)
    fresh.load_save(path)
    assert fresh._combat_instance_idx == 27
    assert fresh._combat_monster_code is None
    assert fresh._instance_location(30) == 63


def test_debug_info_labels_instance_only_candidates_by_their_confirmed_names(game):
    """UPDATE 76: 27/28/30 now have confirmed real names (INSTANCE_NAMES,
    from the live-memory-dump name table) even though none has an
    object code - the debug view shows the name, not "kein Code". Each
    now lives in its own distinct confirmed zone (UPDATE 78), so they're
    checked one room at a time rather than all at once."""
    game.current_room = 11
    assert "0(Goblin)" in game.debug_info()
    game.current_room = 106
    assert "27(Ork)" in game.debug_info()
    game.current_room = 93
    assert "28(Slime)" in game.debug_info()
    game.current_room = 55
    info = game.debug_info()
    assert "30(Wildschwein)" in info
    assert "kein Code" not in info


def test_debug_info_labels_object_87_as_zombie(game):
    """UPDATE 76: object 87 is now named via names.py (confirmed by
    the same live-memory-dump table) - shown via its own object-code
    path, not the INSTANCE_NAMES fallback. Room 17 is in object 87's
    own confirmed `MONSTER_ROOM_LISTS` entry (UPDATE 78)."""
    game.current_room = 17
    game.time_of_day = 0x80
    game._advance_day_night_roster()
    info = game.debug_info()
    assert "2(Zombie)" in info


def test_debug_info_shows_an_instance_only_fight(game):
    game._start_combat(code=None, instance_idx=27)
    info = game.debug_info()
    assert "Kampf: Ork (Instanz #27, Code=None)" in info
