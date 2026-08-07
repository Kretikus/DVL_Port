"""
combat.py - melee combat resolution, a port of the confirmed core of
`sub_879F` (the real game's one and only fight resolver - see the
`laas` analysis project's PHASE0_FINDINGS.md UPDATE 17, 18, 22, 23, 24,
27, 28 for the full multi-session derivation).

CONFIRMED PER-ROUND FORMULA (this module implements this faithfully):

  - Smirga always swings the weapon; Aszhanti always casts the spell -
    confirmed by every real combat message template and screenshot
    ("Smirga holt weit aus...", "Welche Waffe soll Smirga verwenden?" /
    "Welchen Zauber soll Aszhanti schleudern?").
  - Player's outgoing damage = 1d6 + (Smirga's Strength // 5).
  - Monster's outgoing damage = (monster's own dice count) x 1d6 +
    (monster's own flat bonus) - both from `monster_stats.py` (WORLD
    Section 5) - then reduced by the TARGETED character's armor class
    (1/2/3 points, see ARMOR_CLASS below), floored at 0. A result of
    exactly 0 after armor reduction is a "block" (the real game prints
    a distinct "Rüstung bewahrt ihn vor Schaden" message instead of a
    damage line for this - see UPDATE 24) - not a separate roll at all.
  - Hit checks are two independent 1d20-vs-stat compares, one per
    combatant, both resolved every round (so a round can show BOTH a
    monster miss/block AND a player hit/miss, matching every real
    screenshot exactly):
      monster hits if 1d20 >= monster.attack   (the monster's own
                                                 instance-record byte)
      player hits  if 1d20 >= monster.defense  (ditto)
    NOTE the comparison direction is "roll >= stat", which reads
    backwards from typical RPG intuition (a HIGHER "attack" stat here
    makes a creature HARDER to land a hit with, not easier) - this is
    exactly what the disassembly does, not a guessed convention.
  - Which character the monster's attack targets is an independent
    1d20 coin-flip each round: <=10 -> Aszhanti, else Smirga.
  - On a kill: Aszhanti's Strength +1 (flat), Smirga's Strength +=
    monster's own "strength reward" byte (`monster_stats.py`, same
    table as the dice stats), and BOTH characters' MAX hp +1 (see
    UPDATE 23's second correction) - confirmed to apply regardless of
    who actually landed the blow.

KNOWN, DELIBERATE SIMPLIFICATIONS (not guessed at, not silently
dropped - real pieces of the original mechanic this module does NOT
reproduce):
  - No weapon-table parry/accuracy/damage modifiers. The real formula
    adds a per-equipped-weapon byte to each hit roll and to outgoing
    damage (via a runtime table position, `sub_925E`) - but the real
    object codes for Dolch/Schwert were investigated at length and are
    UNRESOLVED (see UPDATE 27), so `weapon_damage_bonus` here is a
    plain parameter defaulting to 0, not tied to any real item.
  - No boss-room x8 damage multiplier (tied to the same unresolved
    weapon-table indexing).
  - All 5 real spells are now ported: LEVI, KUBL, UNSI, TOPA (see
    `resolve_levi()`/`resolve_kubl()`/`resolve_unsi()`/`resolve_topa()`
    and PHASE0_FINDINGS.md UPDATE 34/36/37), and FEBR (`resolve_febr()`,
    UPDATE 38 - flavor-only against every monster EXCEPT one specific
    creature, "der Oger"/object 162, where it can land a 1-point bonus
    hit). Typing anything other than one of these 5 names at the spell
    prompt has no effect.
  - No instance-index-11 hardcoded 100hp override (`cmp di,0xb; ...
    word_8128=0x64` in the real code) - a narrow special case for one
    specific, unidentified monster.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from .world import ObjectInstance

# Lederwams / Echsenpanzer / Kettenhemd - confirmed armor items, see
# names.py and PHASE0_FINDINGS.md UPDATE 18. The armor CLASS NUMBER
# itself (1/2/3) is the exact point reduction applied to incoming
# damage - not a separate lookup table.
ARMOR_CLASS = {264: 1, 196: 2, 52: 3}

ASZHANTI = "aszhanti"
SMIRGA = "smirga"


def armor_reduction(equipped_object_code: int | None) -> int:
    if equipped_object_code is None:
        return 0
    return ARMOR_CLASS.get(equipped_object_code, 0)


def d20(rng: random.Random = random) -> int:
    return rng.randint(1, 20)


def d6(rng: random.Random = random) -> int:
    return rng.randint(1, 6)


@dataclass
class RoundResult:
    target: str  # ASZHANTI or SMIRGA - who the monster's attack targeted
    monster_attack_roll: int
    monster_hits: bool
    monster_damage: int  # 0 if miss or blocked
    monster_blocked: bool  # armor reduced a real hit to exactly 0
    player_attack_roll: int
    player_hits: bool
    player_damage: int  # 0 if miss
    monster_hp_after: int
    monster_killed: bool


def resolve_round(
    monster: ObjectInstance,
    monster_hp_before: int,
    monster_dice_count: int,
    monster_dice_bonus: int,
    smirga_strength: int,
    aszhanti_armor_code: int | None,
    smirga_armor_code: int | None,
    weapon_damage_bonus: int = 0,
    rng: random.Random = random,
) -> RoundResult:
    """One round of melee combat. `monster_hp_before` is passed in
    (rather than read from `monster.hp`) since that's the creature's
    STARTING hp, not its current hp mid-fight - callers own the
    running total (see GameState's combat fields)."""
    target = ASZHANTI if d20(rng) <= 10 else SMIRGA
    target_armor = aszhanti_armor_code if target == ASZHANTI else smirga_armor_code

    monster_attack_roll = d20(rng)
    monster_hits = monster_attack_roll >= monster.attack
    monster_damage = 0
    monster_blocked = False
    if monster_hits:
        raw_damage = sum(d6(rng) for _ in range(monster_dice_count)) + monster_dice_bonus
        monster_damage = max(0, raw_damage - armor_reduction(target_armor))
        monster_blocked = monster_damage == 0 and raw_damage > 0

    player_attack_roll = d20(rng)
    player_hits = player_attack_roll >= monster.defense
    player_damage = 0
    if player_hits:
        player_damage = d6(rng) + smirga_strength // 5 + weapon_damage_bonus

    monster_hp_after = monster_hp_before - player_damage
    return RoundResult(
        target=target,
        monster_attack_roll=monster_attack_roll,
        monster_hits=monster_hits,
        monster_damage=monster_damage,
        monster_blocked=monster_blocked,
        player_attack_roll=player_attack_roll,
        player_hits=player_hits,
        player_damage=player_damage,
        monster_hp_after=monster_hp_after,
        monster_killed=monster_hp_after <= 0,
    )


# LEVI ("flight-path confusion") - see PHASE0_FINDINGS.md UPDATE 34 for
# the full derivation, direct-traced (not guessed) against the real
# disassembly and confirmed to match three real screenshots, including
# a genuinely counterintuitive detail: the "bonus strike" narrated as
# Smirga capitalizing on the opening ("...schlägt Smirga unvermittelt
# zu und verletzt sie für N Hitpoints") is mechanically just Aszhanti's
# OWN spell-power roll applied directly as damage - there is no second,
# independent attack roll. It only lands on a LOW power roll, not a
# high one (see the module's own note below on why this reads
# backwards from typical intuition).
LEVI_CAST_THRESHOLD = 5   # 1d20 + Astral must exceed this or the whole cast fizzles
LEVI_POWER_THRESHOLD = 2  # 1d6 + Strength//5 must be <= this for the bonus strike to land


@dataclass
class LeviResult:
    cast_succeeded: bool  # False -> "Aszhanti spricht einen Zauber aus, doch nichts passiert."
    bonus_landed: bool    # only meaningful if cast_succeeded
    bonus_damage: int     # 0 unless bonus_landed
    monster_hp_after: int
    monster_killed: bool


def resolve_levi(
    monster_hp_before: int,
    aszhanti_astral: int,
    aszhanti_strength: int,
    rng: random.Random = random,
) -> LeviResult:
    """Confirmed formula:
      cast roll  = 1d20 + Aszhanti's Astral - must EXCEED
                   LEVI_CAST_THRESHOLD (5) or the attempt fizzles
                   entirely (no confusion, no bonus strike).
      power roll = 1d6 + Aszhanti's Strength // 5 - if this is <=
                   LEVI_POWER_THRESHOLD (2), the roll's own VALUE is
                   applied directly as bonus damage (narrated as a
                   Smirga strike, but mechanically Aszhanti's spell-
                   power roll, not a separate attack) - a real, if
                   initially surprising, disassembly finding: a LOW
                   power roll is what lands the bonus hit, not a high
                   one. Otherwise: confusion is attempted but "nichts
                   weiter passiert" - no damage.
    Does not touch leveling/game state - callers apply that same as
    for `resolve_round()`'s kills."""
    cast_roll = d20(rng) + aszhanti_astral
    if cast_roll <= LEVI_CAST_THRESHOLD:
        return LeviResult(
            cast_succeeded=False, bonus_landed=False, bonus_damage=0,
            monster_hp_after=monster_hp_before, monster_killed=monster_hp_before <= 0,
        )
    power = d6(rng) + aszhanti_strength // 5
    bonus_landed = power <= LEVI_POWER_THRESHOLD
    bonus_damage = power if bonus_landed else 0
    monster_hp_after = monster_hp_before - bonus_damage
    return LeviResult(
        cast_succeeded=True, bonus_landed=bonus_landed, bonus_damage=bonus_damage,
        monster_hp_after=monster_hp_after, monster_killed=monster_hp_after <= 0,
    )


# KUBL - a direct-damage spell, confirmed via the exact same dispatch
# block as LEVI (see PHASE0_FINDINGS.md UPDATE 36) - resolves to STORY
# message 1907 verbatim: "Aszhanti schleudert einen KUBL auf %s %s, der
# das Monster für %d Hitpoints verletzt." Structurally simpler than
# LEVI: once the shared cast-success gate passes, damage is applied
# UNCONDITIONALLY - no secondary chance/threshold roll on top.
KUBL_CAST_THRESHOLD = 5  # the same general per-spell cast gate LEVI uses


@dataclass
class KublResult:
    cast_succeeded: bool  # False -> "Aszhanti spricht einen Zauber aus, doch nichts passiert."
    damage: int           # 0 unless cast_succeeded
    monster_hp_after: int
    monster_killed: bool


def resolve_kubl(
    monster_hp_before: int,
    aszhanti_astral: int,
    aszhanti_strength: int,
    rng: random.Random = random,
) -> KublResult:
    """Confirmed formula:
      cast roll = 1d20 + Aszhanti's Astral - must EXCEED
                  KUBL_CAST_THRESHOLD (5) or the attempt fizzles
                  entirely, same as every other spell.
      damage = (1d6 + Aszhanti's Strength // 5) + Aszhanti's Astral -
               applied UNCONDITIONALLY to the monster once cast
               succeeds (unlike LEVI, no further threshold check)."""
    cast_roll = d20(rng) + aszhanti_astral
    if cast_roll <= KUBL_CAST_THRESHOLD:
        return KublResult(
            cast_succeeded=False, damage=0,
            monster_hp_after=monster_hp_before, monster_killed=monster_hp_before <= 0,
        )
    damage = d6(rng) + aszhanti_strength // 5 + aszhanti_astral
    monster_hp_after = monster_hp_before - damage
    return KublResult(
        cast_succeeded=True, damage=damage,
        monster_hp_after=monster_hp_after, monster_killed=monster_hp_after <= 0,
    )


# UNSI and TOPA - pure confusion/status spells, confirmed via the exact
# dispatch branch checked (and initially left unidentified) while
# tracing KUBL - see PHASE0_FINDINGS.md UPDATE 37. Both resolve to real
# STORY messages verbatim ("...wird stark verwirrt!" / "...wird sehr
# stark verwirrt!") and share IDENTICAL mechanics - only the flavor
# text differs. Confirmed by reading the branch instruction-by-
# instruction: NEITHER touches the monster's hp at all (no `sub
# word_8128` anywhere in this branch, unlike LEVI/KUBL) - both are
# purely narrative status effects with no numeric combat consequence
# in this function, once the shared cast-success gate passes.
UNSI_CAST_THRESHOLD = 5
TOPA_CAST_THRESHOLD = 5


@dataclass
class ConfusionSpellResult:
    cast_succeeded: bool  # False -> "Aszhanti spricht einen Zauber aus, doch nichts passiert."


def resolve_unsi(aszhanti_astral: int, rng: random.Random = random) -> ConfusionSpellResult:
    """"Aszhanti schleudert einen UNSI und tatsächlich wird %s %s stark
    verwirrt!" (STORY message resolved via the same dispatch branch as
    TOPA). No damage - see this section's own module-level note."""
    cast_roll = d20(rng) + aszhanti_astral
    return ConfusionSpellResult(cast_succeeded=cast_roll > UNSI_CAST_THRESHOLD)


def resolve_topa(aszhanti_astral: int, rng: random.Random = random) -> ConfusionSpellResult:
    """"Aszhanti schleudert seinen TOPA und %s %s wird sehr stark
    verwirrt!" (STORY message 659, confirmed verbatim). No damage - see
    this section's own module-level note."""
    cast_roll = d20(rng) + aszhanti_astral
    return ConfusionSpellResult(cast_succeeded=cast_roll > TOPA_CAST_THRESHOLD)


# FEBR - confirmed via a user-supplied real message (STORY 660) that
# UPDATE 36 had already found the CODE for, while tracing KUBL, but
# couldn't identify: a `di == 0xe` (instance index 14, object code 162
# - see names.py's "oger" entry) special case dealing exactly 1
# damage point. See PHASE0_FINDINGS.md UPDATE 38 for the full trace.
#
# Contrary to UPDATE 24's original assumption (based only on the
# generic flavor message, STORY 468, "Aszhanti beschwört einen FEBR
# und hält dann eine kleine Flamme in der hohlen Hand.") FEBR is NOT
# purely cosmetic - it's flavor-only against every creature EXCEPT one
# specific monster ("der Oger", object 162), where a successful power
# roll lets the flame's light blind it just enough for Smirga to land
# a free hit for exactly 1 point of damage (STORY 660: "...blendet sie
# den Oger ein wenig und Smirga kann einen Schlag plazieren, der dem
# Oger 1 Schadenspunkt zufügt."). Checked directly for an explicit day/
# night condition in the branch (the message's own "die Nacht leicht
# erhellt" phrasing raises the question) - found none; this reads as
# flavor text, not a checked game-state condition.
FEBR_CAST_THRESHOLD = 5   # the same general per-spell cast gate every spell uses
FEBR_TARGET_OBJECT_CODE = 162  # "der Oger" - the ONLY monster this can ever affect
FEBR_POWER_THRESHOLD = 3  # 1d6 + Strength // 5 must reach this (>=, not <=) for the bonus hit
FEBR_BONUS_DAMAGE = 1     # always exactly 1 point - confirmed via the message's own text


@dataclass
class FebrResult:
    cast_succeeded: bool  # False -> "Aszhanti spricht einen Zauber aus, doch nichts passiert."
    bonus_landed: bool    # only ever True against the Oger specifically
    bonus_damage: int     # 0 unless bonus_landed (always FEBR_BONUS_DAMAGE when it is)
    monster_hp_after: int
    monster_killed: bool


def resolve_febr(
    monster_code: int,
    monster_hp_before: int,
    aszhanti_astral: int,
    aszhanti_strength: int,
    rng: random.Random = random,
) -> FebrResult:
    """Confirmed formula:
      cast roll = 1d20 + Astral - must EXCEED FEBR_CAST_THRESHOLD (5),
                  same shared gate as every spell, else fizzles.
      If `monster_code != FEBR_TARGET_OBJECT_CODE` (162, "der Oger"):
        ALWAYS just the flavor-only flame, no damage, no further roll -
        matches the real code's own branch order (the power roll isn't
        even computed for any other monster).
      Otherwise (fighting the Oger specifically):
        power roll = 1d6 + Strength // 5 - if this reaches
        FEBR_POWER_THRESHOLD (3) OR HIGHER, a flat FEBR_BONUS_DAMAGE
        (1) point is dealt; below that, still just the flame."""
    cast_roll = d20(rng) + aszhanti_astral
    if cast_roll <= FEBR_CAST_THRESHOLD:
        return FebrResult(
            cast_succeeded=False, bonus_landed=False, bonus_damage=0,
            monster_hp_after=monster_hp_before, monster_killed=monster_hp_before <= 0,
        )
    if monster_code != FEBR_TARGET_OBJECT_CODE:
        return FebrResult(
            cast_succeeded=True, bonus_landed=False, bonus_damage=0,
            monster_hp_after=monster_hp_before, monster_killed=monster_hp_before <= 0,
        )
    power = d6(rng) + aszhanti_strength // 5
    bonus_landed = power >= FEBR_POWER_THRESHOLD
    bonus_damage = FEBR_BONUS_DAMAGE if bonus_landed else 0
    monster_hp_after = monster_hp_before - bonus_damage
    return FebrResult(
        cast_succeeded=True, bonus_landed=bonus_landed, bonus_damage=bonus_damage,
        monster_hp_after=monster_hp_after, monster_killed=monster_hp_after <= 0,
    )
