from pathlib import Path

import pytest

from laas_port import pictures
from laas_port.game import DEFAULT_ASSETS_DIR, DOLCH_CODE, SCHWERT_CODE, GameState
from laas_port.objects import ObjectTable
from laas_port.story import Story
from laas_port.world import LIMBO_CARRIED, World

ASSETS_DIR = DEFAULT_ASSETS_DIR


@pytest.fixture(autouse=True)
def _never_actually_open_a_picture_window(monkeypatch):
    """GameState.__init__ fires the automatic room->picture check (see
    ROOM_PICTURE_TABLE) immediately, since the confirmed real starting
    room (67) has one - without this, every single test constructing a
    GameState would pop open a real Tk window. Individual tests that
    want to observe/assert on picture-showing re-monkeypatch this
    themselves, which composes fine (same per-test monkeypatch
    instance)."""
    monkeypatch.setattr(pictures, "show_picture", lambda assets_dir, n: None)


@pytest.fixture(scope="session")
def story() -> Story:
    return Story.load(ASSETS_DIR)


@pytest.fixture(scope="session")
def world() -> World:
    return World.load(ASSETS_DIR)


@pytest.fixture(scope="session")
def objects(story) -> ObjectTable:
    return ObjectTable.load(ASSETS_DIR)


@pytest.fixture
def game() -> GameState:
    """A fresh GameState per test - deliberately NOT session-scoped, since
    verbs mutate runtime state (location/door overrides) and tests must
    not leak state into each other.

    `_bought_starter_weapons` starts True, and Dolch/Schwert start
    carried, here (UPDATE 83's weapon-possession check at the combat
    weapon prompt would otherwise refuse every test's "Schwert" answer,
    and virtually the entire combat test suite uses that as its generic
    weapon choice - the tests that specifically exercise the purchase
    flow itself, buy_starter_weapons(), explicitly reset all three
    first). Since UPDATE 84/85 resolved DOLCH_CODE/SCHWERT_CODE, the
    weapon check reads real inventory rather than the flag alone, so
    granting just the flag is no longer enough. Same rationale as every
    other RESTORE-based default this fixture carries: a mid-game save
    is far more likely to already have this basic, near-mandatory early
    purchase done than not - not a claim about a brand-new game's real
    starting state, which GameState's own default (False, no weapons
    carried) still reflects for actual play."""
    gs = GameState(ASSETS_DIR)
    gs._bought_starter_weapons = True
    gs._move_object(DOLCH_CODE, LIMBO_CARRIED)
    gs._move_object(SCHWERT_CODE, LIMBO_CARRIED)
    return gs
