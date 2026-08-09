"""
Tests for combat.py - the confirmed core melee formula ported from
sub_879F. See PHASE0_FINDINGS.md UPDATE 17/18/22/23/24/27/28 for the
disassembly trace this comes from, and combat.py's own docstring for
the deliberate simplifications (no weapon modifiers, no spells).
"""
import pytest

from laas_port import combat
from laas_port.world import ObjectInstance


class FakeRng:
    """Returns a fixed, pre-scripted sequence of randint() results -
    call order for resolve_round() is: target-select d20, monster
    attack-roll d20, [monster damage d6 x dice_count if it hits],
    player attack-roll d20, [player damage d6 if it hits]."""

    def __init__(self, values):
        self._values = list(values)

    def randint(self, a, b):
        return self._values.pop(0)


def make_monster(hp: int, attack: int, defense: int) -> ObjectInstance:
    raw = bytes([hp, attack, defense]) + bytes(29)
    return ObjectInstance(index=0, raw=raw)


def test_monster_hits_and_damage_is_reduced_by_armor():
    monster = make_monster(hp=20, attack=10, defense=10)
    # target-select(<=10 -> aszhanti), monster attack roll(20, hits),
    # monster damage die(6), player attack roll(1, misses)
    rng = FakeRng([5, 20, 6, 1])
    result = combat.resolve_round(
        monster, monster_hp_before=20, monster_dice_count=1, monster_dice_bonus=0,
        smirga_strength=0, aszhanti_armor_code=264, smirga_armor_code=None, rng=rng,
    )
    assert result.target == combat.ASZHANTI
    assert result.monster_hits is True
    assert result.monster_damage == 5  # 6 (die) - 1 (Lederwams armor class)
    assert result.monster_blocked is False
    assert result.player_hits is False
    assert result.player_damage == 0


def test_monster_damage_reduced_to_exactly_zero_is_a_block():
    monster = make_monster(hp=20, attack=10, defense=10)
    rng = FakeRng([5, 20, 1, 1])  # monster die=1, Kettenhemd (class 3) reduces to 0
    result = combat.resolve_round(
        monster, monster_hp_before=20, monster_dice_count=1, monster_dice_bonus=0,
        smirga_strength=0, aszhanti_armor_code=52, smirga_armor_code=None, rng=rng,
    )
    assert result.monster_hits is True
    assert result.monster_damage == 0
    assert result.monster_blocked is True


def test_monster_miss_deals_no_damage():
    monster = make_monster(hp=20, attack=15, defense=10)
    rng = FakeRng([5, 10, 1])  # monster roll 10 < attack stat 15 -> miss; player roll 1 -> miss
    result = combat.resolve_round(
        monster, monster_hp_before=20, monster_dice_count=1, monster_dice_bonus=0,
        smirga_strength=0, aszhanti_armor_code=None, smirga_armor_code=None, rng=rng,
    )
    assert result.monster_hits is False
    assert result.monster_damage == 0
    assert result.monster_blocked is False


def test_player_damage_includes_strength_and_weapon_bonus():
    monster = make_monster(hp=20, attack=99, defense=1)  # monster always misses, player always hits
    rng = FakeRng([5, 1, 20, 4])  # target-select, monster roll(miss), player roll(hits), player die=4
    result = combat.resolve_round(
        monster, monster_hp_before=20, monster_dice_count=1, monster_dice_bonus=0,
        smirga_strength=25, weapon_damage_bonus=2,
        aszhanti_armor_code=None, smirga_armor_code=None, rng=rng,
    )
    assert result.player_hits is True
    assert result.player_damage == 4 + 25 // 5 + 2  # die + Str/5 + weapon bonus = 11
    assert result.monster_hp_after == 20 - 11
    assert result.monster_killed is False


def test_monster_killed_when_hp_drops_to_zero_or_below():
    monster = make_monster(hp=1, attack=99, defense=1)
    rng = FakeRng([5, 1, 20, 6])
    result = combat.resolve_round(
        monster, monster_hp_before=1, monster_dice_count=1, monster_dice_bonus=0,
        smirga_strength=0, aszhanti_armor_code=None, smirga_armor_code=None, rng=rng,
    )
    assert result.player_damage == 6
    assert result.monster_hp_after <= 0
    assert result.monster_killed is True


def test_target_selection_uses_the_confirmed_threshold():
    monster = make_monster(hp=20, attack=99, defense=99)
    rng = FakeRng([10, 1, 1])  # exactly 10 -> Aszhanti (confirmed "<=10" boundary)
    result = combat.resolve_round(
        monster, monster_hp_before=20, monster_dice_count=1, monster_dice_bonus=0,
        smirga_strength=0, aszhanti_armor_code=None, smirga_armor_code=None, rng=rng,
    )
    assert result.target == combat.ASZHANTI

    rng2 = FakeRng([11, 1, 1])  # 11 -> Smirga
    result2 = combat.resolve_round(
        monster, monster_hp_before=20, monster_dice_count=1, monster_dice_bonus=0,
        smirga_strength=0, aszhanti_armor_code=None, smirga_armor_code=None, rng=rng2,
    )
    assert result2.target == combat.SMIRGA


def test_armor_reduction_lookup():
    assert combat.armor_reduction(264) == 1  # Lederwams
    assert combat.armor_reduction(196) == 2  # Echsenpanzer
    assert combat.armor_reduction(52) == 3   # Kettenhemd
    assert combat.armor_reduction(None) == 0
    assert combat.armor_reduction(9999) == 0  # unrecognized code, no armor


# --- LEVI (see PHASE0_FINDINGS.md UPDATE 34) ---
# call order for resolve_levi(): cast-roll d20, [power-roll d6 if the
# cast succeeds].


def test_levi_cast_fizzles_on_a_low_roll():
    rng = FakeRng([5])  # 5 + 0 Astral = 5, NOT > threshold(5) -> fizzles, no power roll needed
    result = combat.resolve_levi(monster_hp_before=20, aszhanti_astral=0, aszhanti_strength=0, rng=rng)
    assert result.cast_succeeded is False
    assert result.bonus_landed is False
    assert result.bonus_damage == 0
    assert result.monster_hp_after == 20


def test_levi_cast_succeeds_but_high_power_roll_lands_no_bonus():
    rng = FakeRng([6, 6])  # cast roll 6 > 5 succeeds; power roll 6 > threshold(2) -> no bonus
    result = combat.resolve_levi(monster_hp_before=20, aszhanti_astral=0, aszhanti_strength=0, rng=rng)
    assert result.cast_succeeded is True
    assert result.bonus_landed is False
    assert result.bonus_damage == 0
    assert result.monster_hp_after == 20


def test_levi_low_power_roll_lands_the_bonus_strike_using_its_own_value():
    rng = FakeRng([6, 2])  # cast succeeds; power roll 2 <= threshold(2) -> bonus damage = 2
    result = combat.resolve_levi(monster_hp_before=20, aszhanti_astral=0, aszhanti_strength=0, rng=rng)
    assert result.cast_succeeded is True
    assert result.bonus_landed is True
    assert result.bonus_damage == 2
    assert result.monster_hp_after == 18


def test_levi_astral_helps_the_cast_roll_and_strength_helps_the_power_roll():
    # cast roll die=1, +10 Astral = 11 > 5 -> succeeds regardless of a low die
    # power roll die=1, +25 Strength//5=5 = 6 -> exceeds threshold(2), no bonus
    rng = FakeRng([1, 1])
    result = combat.resolve_levi(monster_hp_before=20, aszhanti_astral=10, aszhanti_strength=25, rng=rng)
    assert result.cast_succeeded is True
    assert result.bonus_landed is False


def test_levi_can_kill_the_monster_via_the_bonus_strike():
    rng = FakeRng([6, 1])  # cast succeeds; power roll 1 <= threshold -> bonus damage = 1
    result = combat.resolve_levi(monster_hp_before=1, aszhanti_astral=0, aszhanti_strength=0, rng=rng)
    assert result.bonus_landed is True
    assert result.monster_hp_after == 0
    assert result.monster_killed is True


# --- KUBL (see PHASE0_FINDINGS.md UPDATE 36) ---
# call order for resolve_kubl(): cast-roll d20, [damage-roll d6 if the
# cast succeeds].


def test_kubl_cast_fizzles_on_a_low_roll():
    rng = FakeRng([5])  # 5 + 0 Astral = 5, NOT > threshold(5) -> fizzles
    result = combat.resolve_kubl(monster_hp_before=20, aszhanti_astral=0, aszhanti_strength=0, rng=rng)
    assert result.cast_succeeded is False
    assert result.damage == 0
    assert result.monster_hp_after == 20


def test_kubl_deals_damage_unconditionally_once_cast_succeeds():
    # cast roll 6 > 5 succeeds; damage die 4 + Strength//5(0) + Astral(0) = 4
    rng = FakeRng([6, 4])
    result = combat.resolve_kubl(monster_hp_before=20, aszhanti_astral=0, aszhanti_strength=0, rng=rng)
    assert result.cast_succeeded is True
    assert result.damage == 4
    assert result.monster_hp_after == 16


def test_kubl_damage_includes_astral_and_strength():
    # cast roll die=1 + Astral(10) = 11 > 5 -> succeeds
    # damage die=2 + Strength//5(25//5=5) + Astral(10) = 17
    rng = FakeRng([1, 2])
    result = combat.resolve_kubl(monster_hp_before=20, aszhanti_astral=10, aszhanti_strength=25, rng=rng)
    assert result.cast_succeeded is True
    assert result.damage == 17
    assert result.monster_hp_after == 3


def test_kubl_can_kill_the_monster():
    rng = FakeRng([6, 6])  # cast succeeds; damage die 6 -> kills a 5-hp monster
    result = combat.resolve_kubl(monster_hp_before=5, aszhanti_astral=0, aszhanti_strength=0, rng=rng)
    assert result.monster_hp_after <= 0
    assert result.monster_killed is True


# --- UNSI / TOPA (see PHASE0_FINDINGS.md UPDATE 37) - pure confusion/
# status spells: only the shared cast-success roll (1d20 + Astral),
# no damage roll at all, confirmed by the real disassembly never
# touching the monster's hp in this branch. ---


def test_unsi_fizzles_on_a_low_roll():
    rng = FakeRng([5])  # 5 + 0 Astral = 5, not > threshold(5)
    result = combat.resolve_unsi(aszhanti_astral=0, rng=rng)
    assert result.cast_succeeded is False


def test_unsi_succeeds_on_a_high_roll():
    rng = FakeRng([6])
    result = combat.resolve_unsi(aszhanti_astral=0, rng=rng)
    assert result.cast_succeeded is True


def test_topa_fizzles_on_a_low_roll():
    rng = FakeRng([5])
    result = combat.resolve_topa(aszhanti_astral=0, rng=rng)
    assert result.cast_succeeded is False


def test_topa_succeeds_on_a_high_roll():
    rng = FakeRng([6])
    result = combat.resolve_topa(aszhanti_astral=0, rng=rng)
    assert result.cast_succeeded is True


def test_topa_astral_helps_the_cast_roll():
    rng = FakeRng([1])  # die=1, +10 Astral = 11 > 5 -> succeeds despite a low die
    result = combat.resolve_topa(aszhanti_astral=10, rng=rng)
    assert result.cast_succeeded is True


# --- FEBR (see PHASE0_FINDINGS.md UPDATE 38) - flavor-only against
# every monster except one specific creature, "der Oger" (object 162),
# where a successful power roll lands a flat 1-point bonus hit. ---
OGER_CODE = combat.FEBR_TARGET_OBJECT_CODE
OTHER_MONSTER_CODE = 999  # any code that isn't the Oger


def test_febr_cast_fizzles_on_a_low_roll():
    rng = FakeRng([5])  # 5 + 0 Astral = 5, not > threshold(5)
    result = combat.resolve_febr(
        monster_code=OGER_CODE, monster_hp_before=20, aszhanti_astral=0, aszhanti_strength=0, rng=rng
    )
    assert result.cast_succeeded is False
    assert result.bonus_damage == 0


def test_febr_is_flavor_only_against_any_monster_that_is_not_the_oger():
    # cast succeeds (6 > 5) - but wrong monster means no power roll is
    # even attempted, matching the real code's own branch order.
    rng = FakeRng([6])
    result = combat.resolve_febr(
        monster_code=OTHER_MONSTER_CODE, monster_hp_before=20,
        aszhanti_astral=0, aszhanti_strength=0, rng=rng,
    )
    assert result.cast_succeeded is True
    assert result.bonus_landed is False
    assert result.bonus_damage == 0
    assert result.monster_hp_after == 20


def test_febr_lands_the_bonus_hit_against_the_oger_on_a_high_power_roll():
    # cast succeeds (6 > 5); power roll 3 >= threshold(3) -> bonus lands
    rng = FakeRng([6, 3])
    result = combat.resolve_febr(
        monster_code=OGER_CODE, monster_hp_before=20, aszhanti_astral=0, aszhanti_strength=0, rng=rng
    )
    assert result.cast_succeeded is True
    assert result.bonus_landed is True
    assert result.bonus_damage == 1  # always exactly 1, confirmed via the message text
    assert result.monster_hp_after == 19


def test_febr_misses_the_bonus_hit_against_the_oger_on_a_low_power_roll():
    rng = FakeRng([6, 2])  # power roll 2 < threshold(3) -> no bonus
    result = combat.resolve_febr(
        monster_code=OGER_CODE, monster_hp_before=20, aszhanti_astral=0, aszhanti_strength=0, rng=rng
    )
    assert result.bonus_landed is False
    assert result.monster_hp_after == 20


def test_febr_can_kill_the_oger_via_the_bonus_hit():
    rng = FakeRng([6, 3])
    result = combat.resolve_febr(
        monster_code=OGER_CODE, monster_hp_before=1, aszhanti_astral=0, aszhanti_strength=0, rng=rng
    )
    assert result.monster_hp_after == 0
    assert result.monster_killed is True
