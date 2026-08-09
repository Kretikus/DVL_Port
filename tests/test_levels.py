"""
Unit tests for levels.py's confirmed threshold ladders - see
PHASE0_FINDINGS.md UPDATE 23 for the disassembly trace these come from.
"""
from laas_port import levels


def test_strength_thresholds():
    # Confirmed by a real fresh-game screenshot: value 0 genuinely falls
    # through to "Milchbubi" like any other value <= 17, no special case.
    assert levels.strength_title(0) == "Milchbubi"
    assert levels.strength_title(1) == "Milchbubi"
    assert levels.strength_title(17) == "Milchbubi"
    assert levels.strength_title(18) == "Schaumschläger"
    assert levels.strength_title(26) == "Schaumschläger"
    assert levels.strength_title(27) == "Kraftprotz"
    assert levels.strength_title(37) == "Kraftprotz"
    assert levels.strength_title(38) == "Gladiator"
    assert levels.strength_title(1000) == "Gladiator"


def test_astral_thresholds():
    # This is Aszhanti's track (the only one computed via a ladder at
    # all - Smirga's Astral is a fixed constant, SMIRGA_ASTRAL_TITLE,
    # not tested here since it takes no value). Confirmed by the real
    # fresh-game screenshot: value 0 falls through to "Scharlatan".
    assert levels.astral_title(0) == "Scharlatan"
    assert levels.astral_title(1) == "Scharlatan"
    assert levels.astral_title(2) == "Scharlatan"
    assert levels.astral_title(3) == "Kleriker"
    assert levels.astral_title(4) == "Kleriker"
    assert levels.astral_title(5) == "Illusionist"
    assert levels.astral_title(6) == "Illusionist"
    assert levels.astral_title(7) == "Magier"


def test_ansehen_thresholds():
    assert levels.ansehen_title(0) == "Niemand"
    assert levels.ansehen_title(2) == "Niemand"
    assert levels.ansehen_title(3) == "Leicht zu übersehen"
    assert levels.ansehen_title(4) == "Leicht zu übersehen"
    assert levels.ansehen_title(5) == "Beachtlich"
    assert levels.ansehen_title(6) == "Beachtlich"
    assert levels.ansehen_title(7) == "Bekannt"
    assert levels.ansehen_title(9) == "Bekannt"
    assert levels.ansehen_title(10) == "Heldenhaft"


def test_hunger_thresholds():
    # Party-wide track - confirmed via the user's own gameplay
    # observation (hunger is shared, unlike thirst which is per-character).
    assert levels.hunger_title(0) == "Am Verhungern"
    assert levels.hunger_title(50) == "Sehr hungrig"
    assert levels.hunger_title(51) == "Hungrig"
    assert levels.hunger_title(100) == "Hungrig"
    assert levels.hunger_title(101) == "Satt"


def test_durst_thresholds():
    assert levels.durst_title(0) == "Am Verdursten"
    assert levels.durst_title(30) == "Sehr durstig"
    assert levels.durst_title(31) == "Durstig"
    assert levels.durst_title(60) == "Durstig"
    assert levels.durst_title(61) == "Kein Durst"
