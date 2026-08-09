from pathlib import Path

import pytest

from laas_port import pictures
from laas_port.game import DEFAULT_ASSETS_DIR, GameState
from laas_port.objects import ObjectTable
from laas_port.story import Story
from laas_port.world import World

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
    not leak state into each other."""
    return GameState(ASSETS_DIR)
