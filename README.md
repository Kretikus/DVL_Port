# Die Drachen von Laas — port (groundwork)

A from-scratch reimplementation of the 1991 German text adventure "Die
Drachen von Laas" (ATTIC Software), built from a full reverse-engineering
pass over the original `LAAS.EXE` (16-bit real-mode DOS, Borland C++,
large memory model). This repo is the **port** - a clean-room Python
reimplementation of confirmed game mechanics. It does not contain or
depend on the original disassembly/IDA project

## Status: groundwork, not a playable game yet

What works right now:
- Loads the real room graph (109 rooms, 8 exits each) from `RESTORE`.
- Loads the real 250-entry object table and can show object description
  text (decompressed from `STORY`, substituted through `ITEMS`'
  fragment table), now prefixed with the correct German indefinite
  article (`einen`/`eine`/`ein`, or deliberately none for 55 special-
  cased objects) - a real port of the original's `sub_4698`/`sub_7B9F`
  article logic, not a guess. See the important caveat in
  `laas_port/objects.py` about some raw spans still being fragments
  meant for concatenation, not always complete sentences - that part of
  the original mechanism (the exact sentence template and the raw
  span's true end boundary) remains genuinely unresolved, not just
  unported.
- Loads the real object-instance/location tracking for the 39 objects
  that can move (NPCs, monsters, portable items).
- **Real item shop prices** (`laas_port/item_stats.py`): the `WORLD`
  file's Section 1 stats table, looked up exactly the way the original
  game does (`sub_E6A1`'s linear search, confirmed byte-for-byte via
  direct Unicorn emulation of the real function - not reverse-derived
  from static analysis alone). Surfaced in EXAMINE's output for any
  object with a nonzero buy price.
- **Real room "look" descriptions for 91 of 109 rooms so far** - the
  entire Hyllok village cluster, the surrounding hill country out to
  the mountains, a farmstead with its cornfield, the bridge-troll
  encounter, Potidan the healer's hut, a lake/fishing village with its
  boathouse and two taverns, Skeeve the wizard's forest/garden/house
  (including his bedroom and laboratory), a cave troll's lair, a large
  chunk of the city of Scarbloom (gates, market, several alleys, a
  shop, the forum, palace portal, temple, a forge, and the mages'
  guild), and - the two big story-critical destinations - both dragon
  encounters (a cave leading to the first, a cliff-climb to a ruined
  castle for the second, three-headed one) - see
  `laas_port/room_text.py`. Originally established via real game
  screenshots cross-referenced against exit-graph topology, but that
  topology-based ROOM NUMBER inference turned out to be systematically
  wrong for about a third of these rooms (the MESSAGE each one showed
  was correctly identified, just assigned to the wrong room number) -
  since corrected using the room-handler dispatch table's real address
  formula directly (`0x7c20 + (room-1)*4`, confirmed in the `laas`
  analysis project's PHASE0_FINDINGS.md UPDATE 13), which reads each
  room's actual handler rather than inferring its identity from map
  shape. Rooms 48, 88, and 89-99 (11 rooms genuinely absent from the
  table-building code itself, not a bug) remain unresolved - see
  `room_text.py`'s docstring for specifics.
- **Short status-bar room titles** (`laas_port/room_titles.py`,
  `ROOM_TITLE` + `room_title()`) - the compact heading shown top-left
  on the real game's screen (e.g. "Das Hügelland."), distinct from the
  full "look" description above it. Found via a plain NUL-delimited
  string list (not part of STORY's message table) authored in
  room-number order, confirmed against a real screenshot the user
  provided plus many already-verified rooms. Wired into
  `GameState.look()`'s header line (`[Raum 12: Das Hügelland.]`).
- **Character-narrator modeling** (`laas_port/characters.py`): the
  player controls both Smirga and Aszhanti, and several room/object
  texts branch on which one is currently "narrating" (first-person
  "mein/meine" vs. third-person about the other party member's
  things) - confirmed by disassembling room 1's handler, which
  branches on a `word_b722` flag. `GameState.narrator` selects this at
  runtime; `room_text.look_text()` takes it as a parameter instead of
  defaulting to one fixed choice.
- **Confirmed compass-direction mapping** (`world.DIRECTION_NAMES`):
  clockwise-from-north (N, NE, E, SE, S, SW, W, NW), verified against 4
  independently-confirmed room-67 exits.
- **A first real verb layer** (`parser.py` + `names.py` +
  `GameState.execute()` in `game.py`): LOOK, EXAMINE, TAKE, DROP,
  INVENTORY, and movement, driven by a proper German verb/noun parser
  rather than hardcoded REPL branches. Object locations are now
  mutable at runtime (TAKE/DROP actually move things, on top of - not
  mutating - the loaded RESTORE data). Nouns resolve either by a
  (currently very small) known-name table or by explicit numeric code
  (e.g. `nimm #35`).
- **OPEN/CLOSE/LOCK/UNLOCK** (`GameState.open_door`/`close_door`/
  `lock_door`/`unlock_door`): a full port of the original's door-verb
  tetralogy, including the shared symmetric state mutation (opening a
  door updates both rooms it connects, matching `sub_EEC0` exactly) and
  the LOCK/UNLOCK key-object gate. Validated against the real shipped
  data: room `0x55` genuinely has a pre-locked door in `RESTORE` - this
  is a real, deliberate puzzle in the game, not just a documented
  mechanic. Needs `mit <item>` for LOCK/UNLOCK (e.g. `schließe n auf
  mit #1`) - the key/gate objects aren't known by name yet, only by
  their raw codes (see `game.py`'s module docstring).
- **SAVE/LOAD** (`GameState.save`/`load_save`): a JSON save file
  covering this port's own mutable state (current room, narrator,
  object-location overrides, door-state overrides) - NOT a port of
  RESTORE's binary format (see `game.py`'s docstring for why that
  wouldn't gain anything - this port always loads the real RESTORE for
  the static half of the world regardless).
- **BUY/SELL** (`GameState.buy`/`sell`, verbs `kaufe`/`verkaufe`): real
  shopping, using `item_stats.py`'s confirmed WORLD-file prices - buying
  from and selling to both merchants, Gultiba (fixed shop, object 188,
  room 75 "Laden") and Yarom (a traveling merchant, object 167 - see
  PHASE0_FINDINGS.md UPDATE 39 for the disassembly trace of his own
  price-quote dialogue that confirmed this). Yarom only trades when his
  tracked instance happens to be in the player's current room. Starting
  money is 0 - confirmed correct by the user (not just a guess) as part
  of the game's real opening structure (find pocket money, then buy your
  first weapons and spells).
- **Foroll's starter-weapon sale** (`GameState.buy_starter_weapons`,
  triggered via `kaufe waffen` in his forge): a real, hardcoded-price
  scripted event, confirmed byte-for-byte against a user-supplied DOSBox
  screenshot (see PHASE0_FINDINGS.md UPDATE 19) - costs exactly 7 Gerfs,
  one-time only. Also introduced `room_text.py`'s `ROOM_FIRST_VISIT_MESSAGE`
  + `GameState._visited_rooms` - a general, reusable "show this scripted
  scene once, then the normal room text" mechanism, not specific to this
  one room. KNOWN GAP: doesn't grant actual "Dolch"/"Schwert" objects
  yet - neither object code is confirmed (Dolch has no match anywhere in
  the shop price table at all; Schwert is still ambiguous between two
  candidates - see names.py) - documented directly in the method's
  docstring rather than guessed at.
- **STATUS/zustand** (`GameState.status`, `levels.py`, verb `zustand`):
  the full character-sheet - Gesundheit (HP), Stärke, Ansehen (party-
  wide), Astral, Hunger (party-wide), Durst (per character) - with
  thresholds found by disassembling the original's own
  "Zustandsübersicht" status screen (STORY message 1456). Surfaced a
  genuinely surprising detail along the way: the Strength/Astral title
  strings ("Milchbubi", "Gladiator", etc.) aren't in the STORY text
  system at all - they're raw ASCII bytes embedded directly in
  `LAAS.EXE`. A real DOSBox screenshot of the actual start-of-game
  screen (`Status_anfang.png`) caught two real bugs in this feature's
  first draft - a wrongly-guessed "Level 0" placeholder for Stärke/
  Astral that real gameplay never shows, and a misread of Smirga's
  Astral field (it's not a computed stat at all - it's a permanently
  fixed display, since he canonically never learns magic) - and
  confirmed exact column ownership and the Hunger/Durst mechanic split
  the user reported (Hunger is party-wide, Durst is per character) -
  see PHASE0_FINDINGS.md UPDATE 23 for the full trace and correction.
  A THIRD screenshot (after one won fight + eating) confirmed a second,
  hidden mechanic: max HP is a separate pair of globals, never shown
  directly on the status screen, that gets +1 for both party members
  per won fight regardless of who fought (matching the same "both
  gain Strength" pattern) - current HP only rises when healing clamps
  it back up to the new max. `GameState` now tracks
  `aszhanti_max_health`/`smirga_max_health` accordingly (see UPDATE 23's
  second correction). Max hp now gets its confirmed +1-per-kill from
  real combat (see the ATTACK/FLEE bullet below); nothing yet applies
  healing back up to it (no EAT verb - no food object has a confirmed
  code) or decrements Hunger/Durst over time.
  **UPDATE 62**: confirmed as the real game's "F3" shortcut (user-
  supplied screenshot) - every value already matched exactly, but the
  screen's own title line ("Zustandsübersicht.", STORY message 1456 -
  already identified in this feature's own docstring, just never
  actually printed) and a dashed header separator were missing; both
  added now.
- **INVENTORY is now the real "F4" screen** (`GameState.inventory`,
  UPDATE 63): user-supplied screenshot showed this port's version was
  wrong in more than wording - the real screen also reports each
  character's worn armor ("Smirga trägt normale Kleidung." /
  "Aszhanti trägt normale Kleidung.", STORY messages 1884/1885) below
  the confirmed carried-items line (message 121 empty-case, "Leider
  haben wir nichts." - exact match; message 120's real "Wir haben "
  prefix for the non-empty case). Once real armor is equipped, uses the
  confirmed companion message ("hat %s %s an.", messages 1878/1879)
  instead - discovered a much richer, still-untapped vein of real EQUIP
  dialogue text alongside these (put on/take off/already wearing/can't
  wear variants, messages 1875-1899) that `equip()`'s own confirmation
  line doesn't use yet.
- **SPELLS is the real "F5 Zaubersprüche" screen** (`GameState.spells`,
  verbs `zaubersprüche`/`spells`, UPDATE 64): confirmed via a user-
  supplied screenshot, exact match (title message 1460, header message
  322, and the "can't cast anything yet" fallback message 655, shown
  since a fresh Aszhanti is still "Scharlatan"). **KNOWN GAP**: the
  screen's other state - an actual list of known spell names once
  Aszhanti's astral level rises - has never been seen in a screenshot.
  The 5 real spell names (LEVI/KUBL/FEBR/UNSI/TOPA) are already
  confirmed elsewhere (`combat.py`'s `SPELL_PROMPT`), but which ones
  unlock at which level isn't, so this always shows the confirmed
  "nothing yet" text regardless of astral level rather than guessing.
- **ATTACK/FLEE** (`GameState.attack`/`flee`, `combat.py`,
  `monster_stats.py`): the confirmed core melee formula from `sub_879F`
  - hit rolls, armor-based damage reduction (including the "block"
  outcome - a hit reduced to exactly 0), per-round random character
  targeting, and the confirmed leveling-on-kill (Strength + max hp) -
  see PHASE0_FINDINGS.md UPDATE 29 for the full derivation, including a
  detail missed in every earlier pass: equipped weapons also modify the
  hit rolls themselves, not just outgoing damage. **The interaction
  model is a real, stateful Q&A flow matching the original exactly**
  (fixed in UPDATE 33 after a direct user correction of the first
  draft, which wrongly required an explicit `attackiere` each round): a
  fight starting (via ambush or a typed attack) immediately asks
  "Welche Waffe soll Smirga verwenden?", then "Welchen Zauber soll
  Aszhanti schleudern?", THEN resolves the round - and if the fight
  continues, the next round's weapon prompt appears automatically, with
  no further command needed. Plain typed answers ("Schwert", "LEVI")
  are routed straight to the pending prompt by `execute_chain()`, not
  parsed as verb commands. **The spell prompt shows the real magic
  words (LEVI, KUBL, FEBR, UNSI, TOPA) instead of the original's own
  vague "Spruch I, Spruch II..." labels** - confirmed via user report
  to be 1990s copy protection (the real names were only ever in the
  printed manual, never in the game's own text) - see PHASE0_FINDINGS.md
  UPDATE 35 for why a from-scratch port has no reason to reproduce that
  barrier. **LEVI is now a real, working spell** (see
  PHASE0_FINDINGS.md UPDATE 34, `combat.resolve_levi()`): a confirmed
  cast-chance roll (1d20 + Astral), and - on success - a confirmed
  "bonus strike" that lands on a LOW power roll (1d6 + Strength // 5,
  <=2), applying the roll's own value as damage; a genuinely
  counterintuitive detail (low roll = bonus lands, not high) confirmed
  directly against the disassembly, not assumed, and consistent with
  the real screenshots collected earlier (only 1 of 3 real casts landed
  the bonus, for exactly the damage the roll would produce). **KUBL is
  also ported** (see PHASE0_FINDINGS.md UPDATE 36, `combat.
  resolve_kubl()`) - a structurally simpler direct-damage spell,
  confirmed via the exact same dispatch block: the same shared cast-
  chance roll, then `(1d6 + Strength // 5) + Astral` damage applied
  unconditionally, no secondary threshold like LEVI's. **UNSI and TOPA
  are ported too** (UPDATE 37, `combat.resolve_unsi()`/`resolve_topa()`)
  - pure confusion/status spells confirmed to deal NO damage at all
  (verified by reading the branch instruction-by-instruction - no
  hp-modifying instruction exists in it), just the shared cast-success
  roll and flavor text of differing intensity ("stark verwirrt" vs.
  "sehr stark verwirrt"). **FEBR is ported too** (UPDATE 38,
  `combat.resolve_febr()`) - and turned out to NOT be purely flavor-
  only after all, contrary to the original working assumption: it can
  land a rare 1-point bonus hit, but only against one specific monster,
  "der Oger" (object **162**, a new, directly code-confirmed
  identification added to `names.py` along the way - not room-location
  inference like most of this project's other names). All 5 real
  spells are now implemented. KNOWN GAPS, clearly scoped rather than
  silently dropped: no weapon-specific modifiers yet (Dolch/Schwert's
  real object codes are still unresolved - UPDATE 27), no per-monster
  attack flavor text, and Fliehen always succeeds (the real success-
  chance formula wasn't traced). Works against any object with a
  tracked instance present in
  the room (see UPDATE 26 - almost always a
  person/creature). Tested
  with a fixed-sequence fake RNG driving the full weapon-answer/spell-
  answer/round-resolves sequence, against both synthetic monsters and
  the real, confirmed Brückentroll instance data, not real randomness -
  plus a manual multi-round fight against the Lindwurm to confirm the
  auto-reprompt loop in practice.
- **Character death is now modeled** (`GameState._check_player_death()`)
  - a real, previously-unhandled gap: melee damage could push
  `aszhanti_health`/`smirga_health` arbitrarily negative with zero
  in-game consequence. Confirmed via `sub_879F`'s own end-of-round
  check (flat `0x9100`-`0x9138`): if either character's HP drops to 0 or
  below, the fight ends in death with a confirmed, verbatim STORY
  message ("Die Attacke unseres Gegners hat uns den letzten Lebenshauch
  geraubt...") - see PHASE0_FINDINGS.md UPDATE 41. Reuses the existing
  `running=False` mechanism (the same one QUIT already used) rather
  than inventing a separate game-over flag.
- **Random ambushes** (`GameState._check_ambush()`, called from `go()`
  after every successful move): a port of the confirmed core of
  `sub_C301`, the real wandering-encounter trigger - see
  PHASE0_FINDINGS.md UPDATE 30, corrected in UPDATE 48. Confirmed: a
  per-candidate 1d6 roll, triggering on a clean `>3` (50%) chance,
  drawn from creatures with a confirmed `ambush_eligible` flag (checked
  against every named identity in this project - every static NPC is
  ineligible, every real combat creature is eligible) that are NOT
  currently at the `LIMBO_REMOVED` sentinel location. **This condition
  was flipped from an earlier draft**: `LIMBO_REMOVED` doesn't mean
  "off-stage, waiting to wander" (this project's first reading) - it
  means "not currently active for this time-of-day phase", confirmed
  directly against raw disassembly bytes (UPDATE 48) after the user
  asked for a deeper trace. **Hyllok is a confirmed safe
  zone** (`SAFE_ZONE_ROOMS` - rooms 1-9 and 67, matching room_text.py's
  already-confirmed room map exactly, with room 10 - "Vor Hyllok" -
  independently confirmed as the first room outside the village where
  combat can occur at all; user-confirmed, see PHASE0_FINDINGS.md
  UPDATE 47) - no ambush ever fires there, checked before anything else.
  KNOWN GAP outside Hyllok: the real game also restricts each creature
  to its own specific list of valid rooms beyond just "not in the
  village" (a far pointer whose target memory this project couldn't
  resolve - not a guess, a real, documented dead end) - not reproduced,
  so any currently-active eligible creature can ambush in any non-Hyllok
  room. Prints the confirmed STORY message 375 phrasing, by name where
  known (`names.py`) or numeric code otherwise. **`AMBUSH_EXCLUDED_CODES`
  excludes every confirmed room-bound creature/object** - Steinkreuz
  (105, a landmark), Bruckentroll (134, guards the bridge at room 25),
  Tuatara (146, the Fischerdorf lake creature tied to a peaceful,
  scripted fetch-quest), Lindwurm (237) and Tatzelwurm (238) (the two
  dragon bosses) - all of which have `ambush_eligible=True` in the raw
  data despite belonging to UPDATE 21's "room-bound" taxonomy, not the
  wandering pool. Harmless under the original backwards condition;
  user-reported as attacking the player once that condition was
  corrected, first for Steinkreuz (UPDATE 51), then generalized to all
  five once Tuatara turned out to have the identical bug shape
  (UPDATE 52) - a curated exclusion list, not a new mechanism.
- **A confirmed day/night NPC and monster roster is ported**
  (`DAY_ROSTER`/`NIGHT_ROSTER`, `GameState._advance_day_night_roster()`,
  called from `_advance_clock()` at the exact dawn/nightfall
  transitions - see PHASE0_FINDINGS.md UPDATE 49): the real game's own
  dawn/nightfall subroutines place each roster member at a specific
  room for its active phase and reset it to `LIMBO_REMOVED` for the
  other - exact mirror images of each other, confirmed instruction by
  instruction. This is what makes the ambush condition above meaningful
  in practice: Bauer (the farmer), Yarom, and the Bettler (market
  beggar) are all day-only by this same mechanism (not a bug - they're
  genuinely absent at night), the room-1/room-2 family members are
  placed there only during the day, and object 87/the Oger (162) only
  become ambush-active at night. **Known gap**: several more roster
  members exist in the real game (day instance indices 27/28/30, and
  night indices 26/31/32/33/34, one set gated behind a progression
  check) but have no object code this project could resolve - not
  guessed at with synthetic identifiers, left out until their real
  codes are found.
- **EQUIP/anlege** (`GameState.equip`): the confirmed real armor-equip
  mechanic (ANLEGEN, `sub_133BE`), setting `aszhanti_armor`/
  `smirga_armor` for whoever's currently narrating - see
  PHASE0_FINDINGS.md UPDATE 31 for why "which character equips" is a
  port decision, not a reconstructed one. Building this surfaced and
  fixed a real pre-existing bug: Lederwams's object code (264) exceeds
  the 250-entry flags table `objects_in_room()`/`objects_carried()`
  used to iterate, so it could be bought but never actually found in
  inventory - fixed with a small `_all_trackable_codes()` helper.
- **CHARACTER** (`GameState.character`): a PORT UTILITY, not a
  reconstructed original verb - no in-game character-switch command was
  found anywhere in the disassembly (`word_b722`, the real narrator
  flag, gets set somewhere this project hasn't traced - most likely by
  scripted story events, not player input). `charakter`/`wechsel` toggle
  or select which of Smirga/Aszhanti is narrating, purely so a player or
  tester can see both text variants on demand.
- A minimal REPL (`python -m laas_port.game`) - type `hilfe` or `?` for
  the full command list: `look`, `n`/`s`/`e`/`w`/`ne`/`se`/`sw`/`nw`
  (or `gehe norden` etc.) to move, `untersuche <name-or-#code>`, `nimm
  <...>`, `lege <...>`, `öffne <richtung>`, `schließe <richtung>`,
  `schließe <richtung> auf/ab mit <item>`, `inventar`, `speichern
  [datei]`, `laden [datei]`, `charakter [smirga|aszhanti]`, `wechsel`,
  `ende` - and chain several with commas in one line, e.g. `nimm
  schwert, öffne norden, n`.

What's deliberately NOT done yet (see docstrings in each module for
detail):
- **Room description text covers 91 of 109 rooms** (up from 13 at the
  start of this effort) - see the bullet above for how, and
  PHASE0_FINDINGS.md UPDATE 13 for a real methodological lesson learned
  along the way: inferring a room's NUMBER from exit-graph topology is
  fundamentally weaker evidence than reading its handler directly, even
  when the MESSAGE content match is solid. Room 88 (Gultiba's bedroom, a
  scripted affair/confrontation scene) was recovered by fixing a real
  bug in the extraction tool itself - message extraction was bounded by
  "the next handler's address" alone, which broke when that neighbor
  sat in a different overlay segment, reading into unmapped padding and
  silently returning zero messages (see PHASE0_FINDINGS.md UPDATE 15 and
  `tools/room_handler_by_address.py`'s `resolve_all_with_messages()`).
  Rooms 49, 58, 59, 66, 68, 69, and 89-99 (11 rooms) remain genuinely
  absent from the table-building code itself, confirmed by direct binary
  search rather than a scanner artifact - not pursued further.
- **Only 9 verbs exist** (LOOK, EXAMINE, TAKE, DROP, INVENTORY, movement,
  OPEN, CLOSE, LOCK, UNLOCK). The original game recognizes commands via ~80
  decentralized, per-object/per-room dispatch functions (combat,
  shopping, dialogue, puzzles, doors, etc.) - none of that logic is
  ported yet, only a generic LOOK/EXAMINE/TAKE/DROP/INVENTORY. The
  parser's PER-COMMAND grammar is still a simple first-word-is-the-verb
  splitter, though `parser.py`'s `parse_chain()` now IS a real port of
  the original's comma-chaining behavior (`sub_14202`) - "nimm schwert,
  öffne tür" runs as two commands in sequence (see `GameState.
  execute_chain()`), and a trailing "?" sets a parsed-but-not-yet-acted-
  on `explain` flag. Abbreviation-expansion (`sub_14354`) is not
  ported - not documented in enough detail to reproduce faithfully.
- **Object names cover 36 NPCs/creatures/items so far** (`names.py`) -
  Foroll, the cornfield farmer, Oerli, a market beggar, Gultiba,
  Nichidor, Skeeve, Potidan, and the bridge troll (found by
  cross-referencing each object's tracked location against the fan
  map's per-room NPC lists, restricted to rooms with exactly one
  tracked object and exactly one named NPC), plus a stone cross, the
  lake creature (Tuatara), and both dragons (Tatzelwurm, then Lindwurm
  for the second, three-headed one) - found the same way but using that
  room's own confirmed text directly where the fan map didn't have a
  matching entry to cross-check against. A later pass added 17 more
  (Agitor, Cape, Schüssel, Fackel, Feldflasche, Flasche, Heilkraut,
  Netz, Echsenpanzer, Axt, Skarabäus, Schild, Schuppen, Seil, Zeron,
  Lederwams, Kettenhemd) by cross-referencing real merchant prices the
  user collected in-game against `item_stats.py`'s data - a 4-way
  numeric match per item (see PHASE0_FINDINGS.md UPDATE 18). That same
  cross-reference **corrected a real mistake**: three of those items
  (Echsenpanzer/Lederwams/Kettenhemd) had been misidentified as an
  equipped WEAPON in the combat-emulation work below; they're actually
  equipped ARMOR. The real
  per-room noun-DISPATCH mechanism (how the original recognizes a typed
  word as referring to a specific object at all) still hasn't been
  found - see names.py's module docstring for what was tried and ruled
  out this session (no direct writes to the object-code globals
  anywhere in the binary, and a generic prologue search failed since
  different handlers use different registers for the same check).
  Portable items still need numeric codes (`nimm #35`); room 1 and room
  2's own two tracked objects each (32/33, 30/31) remain an unresolved
  identification question in their own right - see PHASE0_FINDINGS.md
  UPDATE 26's follow-up (a tested, confirmed hypothesis that instance-
  tracked objects are almost always people, not the household items
  they were first guessed to be).
- **Combat now has a real, confirmed core** (see the ATTACK/FLEE bullet
  above) but no spells, dialogue, or most of the puzzle mechanics
  documented in `reference/walkthrough_de.txt` are ported. Doors (OPEN/
  CLOSE/LOCK/UNLOCK) are ported (see the door tetralogy bullet above).
  Shopping has real BUY/SELL verbs using real prices, working with both
  Gultiba and Yarom (his object code, 167, is now confirmed - see
  PHASE0_FINDINGS.md UPDATE 39), but no shopkeeper dialogue beyond the
  buy/sell exchange itself.
- **Ambient "impatience" events are ported for Foroll and Oerli**
  (`GameState._advance_room_events()`, `ROOM_IMPATIENCE_EVENTS`, called
  once per executed command): the original game has a single master
  dispatcher (flat `0x64A3`-`0x6A5F`, called once per turn from the main
  game loop) driving ten per-room/global events off a turn counter
  rather than a first-visit flag - Foroll (room 3) and Oerli (room 72,
  his tavern) nag you with confirmed STORY text if you linger without
  buying/paying, escalating to a "get out" line. Simplified from the
  original: no RNG-gating (deterministic thresholds) and each stage
  fires once rather than repeating, since the original's exact
  probability/repeat behavior wasn't traced. `ROOM_FIRST_VISIT_MESSAGE`/
  `first_visit_text()` (room 3 only) remains a separate, simpler
  mechanism (see UPDATE 19).
- **The dragon-cult ambush and poison-gas cave trap are both ported too**
  (`GameState._check_fanatic_ambush()`/`_check_gas_trap()`, see
  PHASE0_FINDINGS.md UPDATE 40/41/43/44 for the full derivation chain -
  all ten of the master dispatcher's branches are now traced). Room 100
  (a stone plateau below the dragon's cliff): dragon-worshipping
  fanatics ambush the player during a confirmed night-into-dawn clock
  window, damaging both characters and destroying a carried Skarabäus
  (206) - swapping it for its near-certain depleted form, object 182
  (not added to `names.py`: its exact typed noun isn't confirmed, only
  its functional role). Rooms 102/103 (inside the cave): a poison-gas
  trap that's instantly fatal while carrying the depleted Skarabäus,
  otherwise gated on charge level (`scarabaeus_charge`) and a one-shot
  near-miss warning before a second exposure kills. Both reuse the same
  death mechanism described above (`_check_player_death()`).
- **GIB (give), and the Scarabäus recharge loop, are now closed**
  (`GameState.give()`, `_check_scarabaeus_recharge()`) - confirmed real
  verb, found directly in `reference/walkthrough_de.txt`: "Den Skarabäus
  gibt man in Hyllok Mygra und wartet einen Tag, bis er repariert ist."
  See PHASE0_FINDINGS.md UPDATE 45. `gib #182 mygra` (the depleted
  Skarabäus has no confirmed typed name, only its numeric code) hands it
  to Mygra (35, room 4) and starts a confirmed 10-turn deadline
  (`[0xAD5C]+10`); once it passes, the charge is restored to "protected"
  and the gas trap above stops being fatal. **Adaptation, clearly
  flagged, not a guess**: the real recharge-complete code doesn't
  obviously relocate the object at all - tracing it led to a per-object
  "type 9" internal sub-state table this session didn't fully chase
  down - so this port swaps the held object back from 182 to 206 on
  completion, a deliberate simplification that keeps the whole loop
  coherent (see UPDATE 45 for the full reasoning). `give()` itself is
  narrow and purpose-built for this one confirmed interaction, not a
  general give-to-any-NPC system.
- **A confirmed day/night clock is ported** (`GameState._advance_clock()`,
  `CLOCK_TRANSITIONS`, `time_of_day`/`day_count`): a real 0-255 wrapping
  cycle, advancing once every two turns, with four confirmed transition
  messages (dawn, noon, dusk, nightfall) - see PHASE0_FINDINGS.md UPDATE
  43 for the full derivation (a first pass had wrongly retracted this as
  "too widely used to be a simple clock"; a proper deep-dive reversed
  that - the wide usage turned out to be dozens of day/night dialogue
  variants in two major NPC conversation trees, not misuse). Starting
  value defaults to 0 (dawn) - not confirmed from any real save.
- **SLEEP is ported** (`GameState.sleep()`, verbs `schlafe`/`schlafen`/
  `übernachte`) - a real, night-only room-by-room mechanic (`sub_10792`),
  already mostly resolved in an earlier analysis pass and re-verified
  this session against the STORY text directly - see PHASE0_FINDINGS.md
  UPDATE 50. Most rooms are pure atmosphere (own bed, Hyllok, Skeeve's
  lab), but a few have real consequences: sleeping in the open street
  robs you of all your money, sleeping in the Lindwurm's lair (room 109)
  is fatal, and Sabrina's house (97/98) triggers a "turned into a frog"
  nightmare scene (flavor only - no further mechanical effect was
  confirmed). **Known gap**: room 72 (Oerli's tavern) has its own
  always-available scripted event in the real game that arms a "dragon
  threat" counter this port has no model for at all - simplified to the
  same daytime gate as every other room rather than guessed at.
- **Room presence now shows people as people, not "Objekte"**
  (`GameState._who_is_here_line()`): a port of the confirmed "wer ist
  hier" printer (`sub` at flat `0xF21E-0xF35E`) that was traced back in
  UPDATE 25 but never actually wired into `look()` - it just dumped
  every present object code, people included, under one generic
  "Objekte hier: #25, #26"-style line (user-reported: Har/Sklar at
  room 67 are people, not objects). Now instance-tracked objects
  (`flag.has_instance` - per UPDATE 26, almost always a person or
  creature) get their own line using the real sentence form; live
  memory dumps of room 67 the user supplied confirmed it exactly down
  to the byte - the raw buffer contained the literal composited text
  "Har und Sklar sind hier." (both present) and "Sklar ist hier."
  (Sklar alone) - see PHASE0_FINDINGS.md UPDATE 53. The
  "Objekte hier: ..." line still exists for genuine non-instance items,
  now using real names where known instead of raw `#code`s.
- **`World.object_location()` had a real, wide-reaching bug, now
  fixed**: it unconditionally returned `None` for any of the ~224
  objects without a tracked instance, on the assumption they're all
  static scenery. User-reported gameplay (a Salami in room 8 that Har
  steals if you're not quick) led straight to it - checking the raw
  flags array directly showed 108 non-instance codes hold a real room
  number (1-109) and one (a starter weapon, Axt) holds exactly
  `LIMBO_CARRIED`, meaning the port had been silently discarding real
  location data for non-instance items this whole time. Now returns it
  correctly (a separate, dense 110-298 value band - very likely unsold
  merchant stock - is still not understood and deliberately returns
  `None`, not guessed at). Side effects fixed along the way:
  `inventory()` had been unconditionally printing "Ich trage nichts bei
  mir." even while genuinely carrying the Axt the whole time, and now
  also prints real names instead of raw `#code`s, matching `look()`'s
  earlier fix. See PHASE0_FINDINGS.md UPDATE 58.
  **Correction (UPDATE 59)**: that fix was too broad - user-reported
  (with a screenshot) that room 10 ("Vor Hyllok") shows no Schild in
  the real game, despite its raw flags value also reading like a room
  number (10). Of the 108 "room-like" values, 9 belong to objects with
  a real merchant price (Schild included) - for those, the raw value is
  some kind of unbought shop-stock reference, not a placement.
  `GameState.object_location()` (which already has both `World` and
  `ItemStats` on hand) now treats any priced-but-not-yet-`LIMBO_CARRIED`
  object as unplaced, while `World.object_location()` itself is
  unchanged - it's still faithfully reporting the raw data, the
  correction just belongs one layer up, where the price data lives.
  **Further correction (UPDATE 60)**: still too broad - user asked what
  object #38 (newly showing in room 67) even was, having never seen
  anything pickable there. Turned out nearly every one of the 109 rooms
  has one of these non-instance "objects" once priced items are
  excluded - a dense, near-universal pattern far more consistent with
  some other general per-room engine structure than ~100 forgotten
  items, especially since real gameplay has only ever confirmed exactly
  ONE of them (Salami) and disproved a second (Schild). Tightened once
  more: a non-instance object's raw location is now only trusted when
  it's BOTH listed in `names.py` AND unpriced - currently just Salami.
  Any other real pickable item hiding in this data would need the same
  kind of direct evidence Salami got (a specific gameplay report) before
  this method surfaces it, rather than being guessed into visibility.
- **The Salami race is ported** (`SALAMI_CODE`/`SALAMI_ROOM`/
  `SALAMI_HOME_ROOM` in `game.py`): confirmed via two user-supplied
  screenshots - Har follows the player from room 2 into room 8 and
  immediately takes a Salami sitting there if it's still around
  ("Har steckt die Salami ein, die hier herumlag."), and the room's
  own description drops its "hanging Salami" sentence entirely once
  it's gone. **KNOWN SIMPLIFICATION**: only this one confirmed
  room2->room8 follow is modeled, triggered by the player's own move -
  not a general "NPCs follow the player" mechanic (no evidence exists
  for that beyond this one scene) and not a guessed turn-scheduled
  autonomous walk.
- **The real game's F1/F2 key shortcuts are ported** (`GameState.
  exits()`, verbs `exits`/`ausgänge` - this port has no raw function-key
  input, so they're typed commands instead; F1 was already covered by
  LOOK): confirmed real text, "Unmittelbare Ausgänge führen nach
  Norden, ...". **Corrected twice over (UPDATE 66), both times with
  real screenshots, not guesses**:
  - First (from room 2's F2 text): exit-table slot 7 - always labeled
    "NW" by an untested extrapolation of the clockwise slot pattern -
    is confirmed real "Oben" (a staircase up to Smirga's room)
    *for room 2 specifically*. Relabeling it "Oben" everywhere (this
    port's first fix) was the exact same kind of over-generalization
    being corrected - a second screenshot (room 18) proved the SAME
    slot is genuine "Nordwesten" elsewhere, independently reconfirmed
    by exit-graph reciprocity with room 11. `DIRECTION_NAMES` reverts
    to "NW" as the general label; `EXIT_LABEL_OVERRIDES` narrowly
    overrides just `(2, "NW")` for the F2 display - typing "nw" at
    room 2 still moves you there too, and `oben`/`hinauf`/`rauf` are
    just additional parser aliases for that same move, not a separate
    direction.
  - Second (same two screenshots): "nach" does NOT drop before every
    compound/diagonal direction word, as first thought from room 10's
    text alone - both new screenshots keep "nach" before Südosten/
    Südwesten/Nordwesten. Only room 10's own text omits it, specifically
    before "Nordosten" - a one-off, now special-cased
    (`EXIT_NACH_OMITTED`) rather than generalized into a rule.
  **A real, still-open mystery, not solved**: room 2 also has a
  confirmed Westen exit that isn't in this port's room graph at all -
  its raw exit-table value (`dest_room=0`) was always assumed to mean
  "no exit," but that assumption was never actually confirmed and is
  directly disproven here. Not guessed at or worked around -
  `GameState.exits()` will simply under-report room 2 until the real
  destination is confirmed by more evidence.
- **The farmer's harvest-help quest is ported** (`GameState.helfen()`,
  verbs `hilf`/`helfe`/`helfen` - a PORT UTILITY name, the real typed
  word was never confirmed; `_check_farmer_storm()`, UPDATE 68): found
  while tracing what raises/lowers Ansehen (see the reputation-system
  bullet above) and fully confirmed via disassembly - a real, complete
  timed race with a 3-state machine (unresolved/succeeded/failed). A
  per-turn counter advances while the player stays in room 20 with the
  quest unresolved; at 6 turns a storm destroys the crop and the quest
  fails PERMANENTLY (same per-room ambient-dispatcher mechanism this
  port already models for Foroll/Oerli). Helping in time triggers the
  full confirmed reward: +1 Ansehen, +2 Smirga/+1 Aszhanti Strength,
  +1 MAX hp to both party members (turned out to be the ALREADY-
  confirmed max-hp globals, not new state), Hunger/Durst reset to full,
  a farmhouse conversation that reacts to the player's current Ansehen
  tier using the exact same 4 thresholds as the status screen, and a
  Schinken (ham) reward matching the walkthrough word-for-word. Room
  20's own standing text now switches between 3 confirmed variants
  depending on quest state, the same pattern as the Salami room but a
  full replacement rather than one dropped sentence.
- **Phadraig's oar-return quest is ported, full quest, both endings**
  (`frage()`/`klettere()`/`rudere()`/`gruesse()`/`bitte()`/`danke()`,
  a `give()` branch, and an `_apply_kill()` hook for the combat ending -
  UPDATE 69): another Ansehen source that turned out to gate on a much
  bigger bounty/diplomacy quest than a simple item return. Phadraig (at
  the tavern, room 35) offers 150 Gerfs to deal with a Tuatara raiding
  the fishermen's nets and hands over the Ruder (oar) on acceptance;
  boarding the boat (room 36) and rowing out (rooms 37-39, confirmed
  "zero-compass-exit, `rudere`-only" rooms) triggers the encounter at
  the confirmed-closest room. Both confirmed endings - killing it in
  combat, or greeting it and asking it to stand down - pay the
  identical 150-Gerf bounty once you row back; rowing back having done
  neither confiscates the oar. Only then does giving Phadraig his oar
  back pay out the confirmed +1 Ansehen. Resolved two previously-
  unplaced objects along the way: 147 = Phadraig, 152 = Ruder (settling
  a long-standing price-collision ambiguity with Schwert/86 flagged in
  `names.py`'s own comments). Not modeled: the Harpune weapon (flavor
  text only - no object code found for it despite both description and
  price-table searches).
- **Potidan's Mondscheinkraut quest is ported** (`_frage_potidan()` via
  `frage()`, `_give_potidan()` via `give()`, a generalized `klettere()`
  that now also handles the passage climb into room 28, and a Skelett-
  specific `_apply_kill()` branch - UPDATE 70): another confirmed
  Ansehen source, this one a monster-loot fetch-quest tied to the
  day/night clock. Potidan (room 27) offers to heal the party in
  exchange for the rare Mondscheinkraut, guarded by a Skelett that only
  rises at night in a hidden valley (room 28 - zero compass exits,
  reached by climbing through room 47's own previously-unexplained
  dead-end exit). Killing the Skelett grants the herb; bringing it back
  to Potidan pays the confirmed 100 Gerfs, +2 Ansehen, and a full heal.
  Along the way, resolved a previously-unnamed `NIGHT_ROSTER` entry:
  object 244 (placed at room 28 every night since UPDATE 49, but never
  identified) is confirmed as the Skelett by cross-referencing two
  independent analysis passes that turned out to describe the same
  creature in the same room.
- **The real picture viewer is ported** (`laas_port/pictures.py`, the
  `BILD` verb/`GameState.bild()`, bound to **F6** - UPDATE 71): decodes
  the original `assets/LAASPIC/P1`-`P22` files at runtime, no
  pre-rendered images shipped. Along the way, found that these files
  actually use TWO compression algorithms chained together (one of them,
  `sub_1F97F`, had previously been assumed dead code - it's used by
  every single real file), and that they're a 4-plane EGA 320x200
  format rather than TITEL.VGA's chunky VGA mode - both fully traced
  and validated byte-for-byte against the real x86 machine code (see
  the `laas` analysis project's PHASE0_FINDINGS.md UPDATE 71 for the
  full derivation). The prompt reproduces the real, confirmed "What
  Picture ?" debug menu (adapted to German - the real string was an
  untranslated English dev leftover) - type a number 1-22, or "Illegale
  Bild Nr.!" (genuine real text) for anything else. Delete itself was
  already claimed by this port's own line editor (forward-delete),
  hence F6 rather than the real Entf key.
- **The real per-picture palette is now decoded too, not calibrated**
  (`pictures.picture_palette()` - UPDATE 73): a user-reported color
  mismatch (a real brown showing as a lavender/blue) turned out to have
  a structural cause - LAASPIC files don't share one palette at all,
  each has its own encoded in its own 32-byte header. Traced the real
  call chain (`sub_4365` -> `sub_4167`) that derives 16 EGA hardware
  palette-register values directly from that header and programs them
  via genuine BIOS INT 10h palette calls; converting a register to RGB
  is the standard, fixed EGA DAC formula, not a LAAS-specific table.
  This replaces UPDATE 71's screenshot-calibrated shared palette
  entirely - no reference screenshots needed at all anymore, every
  pixel AND every color now comes straight from decoding the real file.
- **The automatic per-room picture trigger is ALSO ported**
  (`ROOM_PICTURE_TABLE`, `GameState._check_room_picture()` - UPDATE 72):
  the room->picture lookup table UPDATE 71 had left uninvestigated
  turned out to be extractable directly from the real `WORLD` asset
  file (its own 13th and final data section - confirmed via the single
  write site for the pointer `sub_495a` reads, chained cleanly off the
  same 13 section-start pointers the "Asset file loaders" writeup
  already documented). Along the way, corrected that writeup's own
  documented WORLD header format (a leading total-blob-size field was
  being missed, silently shifting every section boundary by one field).
  The confirmed table (42 room->picture mappings) was cross-checked two
  ways: the confirmed starting room (67) maps to picture 1 (the
  farmhouse scene), and the two confirmed dragon-lair rooms (104/108)
  map to pictures 21/22, which decode to exactly what they should be -
  a rearing dragon and a winged dragon breathing fire on a knight. This
  is a real, deliberate behavior change (confirmed with the user first):
  like the original game, a picture now pops up **unprompted**,
  including once immediately at startup, the first time you're in a
  room that has one.
- **A DEBUG view is bound to F7** (`GameState.debug_info()`, verb
  `debug`): a PORT UTILITY, not a reproduction of any real game screen -
  dumps the internal counters and calculations behind this port's own
  mechanics on demand, including the confirmed ambush roll (1d6 per
  eligible candidate, ambush on a roll >3, first success wins - UPDATE
  30/48/49) as a LIVE calculation: the exact current candidate list (by
  instance index - see below) and the resulting probability
  (`1 - 0.5^n`). Also reports room/safe-zone status, active combat
  state, every quest's stage, and the usual stats/timers.
  `SHOW_PICTURES` (see above) is a similar debug-friendly addition - a
  module-level flag, off by default so the test suite never pops up
  real windows, flipped on only when actually running the REPL.
- **A real ambush-pool bug found and fixed via that same debug view**
  (UPDATE 74): a user report of near-total ambush loss traced back to
  this port's own `_check_ambush()` scanning by object code, while the
  real function scans all 39 raw instance records directly - silently
  losing every ambush-eligible creature with no object code mapped to
  it, a full third of the real total (20 real eligible instances, only
  ~8 reachable by code). 8 of the 12 missing ones turned out to be
  UPDATE 49's own already-fully-traced day/night roster members that
  were simply never wired up (`DAY_ROSTER_BY_INSTANCE`/`NIGHT_ROSTER_
  BY_INSTANCE_EARLY`/`_LATE`, including a confirmed Ansehen>=5
  progression gate that swaps the whole late-game night roster in).
  The other 4 sit at real, fixed rooms year-round - matching the
  already-established room-bound-creature pattern - and are excluded
  from the pool pending their own investigation; one is already
  identified as a "Höhlentroll" (cave troll) guarding room 64/65, a
  second, previously-unconnected troll encounter. Combat state itself
  needed a real refactor to support monsters with no object code at all
  (the "am I fighting" signal moved to a new `_combat_instance_idx`,
  always set regardless of whether a code exists; unnamed instance-only
  monsters display as "Kreatur #&lt;index&gt;"). 22 new regression
  tests.
- **A second missed night-roster member found via live gameplay
  report** (UPDATE 75): user-reported real encounters (Raubfliege and
  Goblin by day, Zombie by night, in the unsafe hill country west of
  the bridge) led to re-checking UPDATE 74's own source table line by
  line - instance 32 (room 78, "Die Magiergilde") is confirmed
  unconditionally active every night, independent of the Ansehen
  progression gate, and had been silently dropped in the first pass.
  Fixed (`NIGHT_ROSTER_BY_INSTANCE_ALWAYS`). Also confirmed the real
  STORY text for Goblin/Raubfliege/Zombie/Ork/Harpyie/Treksis/Kobold/
  Bandit/Golem/Dämon all genuinely exist in the game (matching the
  user's report closely) - but two separate attempts to connect a name
  to a SPECIFIC instance index (a disassembly dispatcher search, and a
  re-attempt at decoding each instance's own "name pointer" field,
  calibrated against the two names already known for certain) both
  came back negative, so the "Kreatur #&lt;index&gt;" fallback still
  displays for these - a known, honestly-flagged gap, not a guess.
- **That gap fully closed** (UPDATE 76): user supplied a screenshot of
  an actual Goblin fight AND a memory dump captured at that exact
  moment. The dump contained a complete, plain-text (not STORY-encoded)
  name table for all 39 combat instances in exact index order -
  cross-validated against every already-confirmed identity (11 for 11,
  zero mismatches) before trusting it for anything new. Also explains a
  "curious exception" flagged as far back as UPDATE 26: object 105
  (Steinkreuz, a landmark) has always shown `ambush_eligible=True`
  because its own data record happens to sit at instance 0 - whose real
  identity is "Goblin" (independently confirmed by the screenshot's own
  damage number: 9, the exact maximum of Goblin's confirmed 1d6+3
  formula). Excluding code 105 from the previous fix was solving the
  wrong problem - it was never stopping Steinkreuz (never reachable via
  ambush anyway), it was silently blocking the real Goblin. Fixed
  (`AMBUSH_INSTANCE_IGNORES_OBJECT_CODE`), and `INSTANCE_NAMES` now
  covers every remaining wanderer (Goblin, Höhlentroll, Werwolf, Ork,
  Slime, Treksis, Wildschwein, Kobold, Bandit, Golem, Dämon, Harpyie,
  Raubfliege) plus a newly-named object (87 = Zombie). No more
  "Kreatur #&lt;index&gt;" fallbacks anywhere in the current ambush
  pool.
- **Two more real ambush-pool bugs found via user follow-up, plus the
  real per-monster room-list check finally decoded as a presence flag**
  (UPDATE 77): the user reported that Ork/Slime shouldn't ambush in the
  beginner rooms before the bridge troll (only Raubfliege/Goblin by day,
  Zombie added at night), and that the probability seemed too high.
  Fully re-disassembling `sub_C301` (the real ambush trigger) confirmed
  it skips any instance whose per-monster room-list pointer is unset
  entirely, before even checking the current room. Checking that
  pointer for every ambush-eligible instance found a clean split: Oger,
  Skelett, Golem, and Dämon - all previously wired into the random
  ambush pool (UPDATE 74/75) - have no list at all and should never be
  randomly ambushed (only reachable by deliberately `attack()`ing them
  while physically present, unaffected by this). Conversely Raubfliege
  turns out to have a real list, meaning an earlier hand-curated
  exclusion (grouping it with three genuinely room-bound creatures on a
  "sits at one fixed room" heuristic) was itself a bug, wrongly keeping
  a real early-game wanderer out of the pool. `ObjectInstance.
  has_room_list` replaces both old curated exclusion lists with this
  single confirmed mechanism. The list's own CONTENTS were still
  unresolved at this point (the same static-analysis dead end UPDATE 30
  already hit, re-tried three ways this session, all unsuccessful) - so
  a stopgap, explicitly user-testimony-based fix (a BFS of this port's
  own room graph cut at the bridge troll's room) restricted the pool to
  Goblin/Zombie/Raubfliege specifically in the beginner region, matching
  what the user reported without decompiled backing. Also looked for a
  "daily encounter cap" the user suspected - found no threshold/gate
  logic in either of `sub_C301`'s two real call sites; a suspicious-
  looking computation in one of them turned out to be an unrelated
  per-turn display/counter update, not evidence of a cap. 9 tests
  updated, 2 new.
- **The real per-monster room-list CONTENTS, fully decoded** (UPDATE
  78) - superseding UPDATE 77's beginner-region heuristic with the
  actual mechanism. The user supplied a second memory dump, captured
  fighting an Ork at "Felsklippe", prompting another look at the far
  pointer UPDATE 30/77 had marked unreconstructable. Brute-force
  scanning the first memory dump for a base address where all 9
  wanderers' pointers simultaneously decode into `sub_C301`'s confirmed
  (tag, room) pair format - 9 independent constraints at once, an
  essentially unambiguous search - found one: byte-for-byte identical
  across all 12 memory dumps supplied over the life of this project,
  captured in entirely different rooms and sessions. Every decoded list
  independently matches something already confirmed: Goblin's list
  contains rooms 11/12 ("Das Hügelland", the exact room the user's
  ambush screenshot was taken in), Ork's contains room 106 ("Felsklippe",
  the exact room of the new dump), Zombie's contains its own
  `NIGHT_ROSTER` room, Werwolf's and Kobold's each contain their own
  `NIGHT_ROSTER_BY_INSTANCE_*` room. The lists also cluster exactly
  where expected: Goblin and Raubfliege sit in the beginner region
  (matching the user's report precisely, no heuristic needed anymore),
  while Werwolf/Wildschwein share a distinct territory (rooms 50-57),
  Ork sits near Felsklippe, Slime at 92-96, Kobold at 42-44, and Bandit
  near the Magiergilde - explaining exactly why Ork/Slime were wrongly
  ambushing in the beginner area before. `MONSTER_ROOM_LISTS` replaces
  the UPDATE 77 heuristic entirely. 15 tests updated.
- **Space bar fixed in the raw-mode line editor** (`repl_input.py`):
  user-reported that typing a verb followed by a noun ("nimm schwert")
  was impossible - the space just didn't appear. `pynput` reports Space
  as the special `keyboard.Key.space`, not a `KeyCode` with `.char` like
  ordinary printable keys, so it fell through every branch in
  `_prompt_pynput`'s key-handling loop and was silently dropped. Now
  handled explicitly, inserting a literal space into the buffer. 1 new
  regression test.
- **Room 4's missing first-visit scene and look-text continuation,
  fixed - and generalized** (UPDATE 79): user-reported, backed by real
  screenshots, that the first-ever visit to Mygra's shop was missing
  almost its entire scripted scene (including the exact closing two
  sentences of Mygra's monologue), and a later visit's standing text
  was missing a "Drachenblut" continuation. Running the `laas` analysis
  project's confirmed room-dispatch-table tool
  (`room_handler_by_address.py`) directly against room 4 immediately
  settled it: its real handler references messages 135/136/137/138
  (the whole first-visit scene, narrator-dependent greeting included)
  right before the already-known base text (139), and message 155
  (the Drachenblut sentence) right after it. The port already had a
  generic first-visit mechanism (`ROOM_FIRST_VISIT_MESSAGE`/
  `first_visit_text()`/`_visited_rooms`, built earlier for room 3's own
  scene) - it just didn't support narrator-dependent clauses the way
  `look_text()` did, so `first_visit_text()` was generalized to share
  the same tuple-resolution logic instead of duplicating it. A
  systematic sweep of the same tool across all 91 currently-mapped
  rooms found roughly 20 more with a similar unwired-leading-message
  shape - left as documented, NOT-YET-CONFIRMED candidates
  (PHASE0_FINDINGS.md UPDATE 79) rather than guessed at, since a single
  room handler often mixes LOOK text with other verbs' hardcoded
  responses in one function, and only a real screenshot can tell them
  apart reliably. 6 new tests.
- **Mygra's spell-teaching event, added** (UPDATE 81, corrected UPDATE
  82): user-supplied real DOSBox screenshot showed that giving Mygra
  money ("gebe geld") - in any amount - teaches Aszhanti "Spruch I und
  II" for a flat, non-negotiable 3 Gerfs ("'Nein, gebt mir nicht alles.
  Ich will nur 3 Gerfs.'"), the same "fixed scripted price regardless
  of amount offered" shape as Foroll's starter-weapon sale. Ported as a
  new `give()` special case (since "geld" isn't a real object - nothing
  to resolve via `objects_carried()`) plus a new `aszhanti_known_spells`
  counter, persisted in save/load the same way as
  `_bought_starter_weapons`. Message text keeps the port's own
  established substitution (UPDATE 35) of real spell names for the
  original's "Spruch N" copy-protection numbering.
  UPDATE 82 caught a real mistake in that first pass: "Spruch I/II"
  isn't the first two spells in `SPELL_PROMPT`'s own combat-menu order
  (LEVI, KUBL, FEBR, UNSI, TOPA) - the "Spell I-V" progression numbering
  is a completely separate sequence (user-confirmed: I=LEVI, II=FEBR,
  III=KUBL, IV=UNSI, V=TOPA; III-V require an entirely unmodeled
  "Magiergilde" mechanic). Fixed to say "Zaubersprüche LEVI und FEBR",
  with a new `SPELL_LEARN_ORDER` constant documenting the progression
  order separately from the menu order that caused the mix-up.
  Deliberately scoped narrow either way: this counter isn't wired into
  `SPELL_PROMPT` or actual spell-casting eligibility - both still treat
  all 5 spells as always available, exactly as before, since gating
  those throughout the rest of combat would need a confirmed starting
  spell-count for a brand-new game (not evidenced, same open status as
  `self.money`'s own starting value) and would be a much larger,
  test-suite-wide change beyond what's actually confirmed. 5 new tests.
- **Weapon-possession and spell-known checks, wired into combat**
  (UPDATE 83, user-requested): both prompts previously "accepted any
  text" with no validation at all. Choosing "Dolch"/"Schwert" at the
  weapon prompt is now refused (with a re-prompt) unless
  `_bought_starter_weapons` is set - the best available proxy for
  "does Smirga actually own a weapon", since the real object codes for
  Dolch/Schwert are themselves unresolved (UPDATE 27); "Hände" (bare
  hands) needs no check. Casting a real spell name Aszhanti hasn't
  learned yet (`aszhanti_known_spells`/`SPELL_LEARN_ORDER`, UPDATE
  81/82) now has no effect, exactly like typing an unrecognized spell
  name already did. Neither check invents new combat MATH - an owned
  weapon still contributes no damage bonus (the real per-weapon values
  are exactly UPDATE 27's own unresolved part, not touched here), and
  an unlearned spell's rejection reuses the exact same "no effect"
  behavior already used for garbage input. Required updating the
  shared test fixture: `_bought_starter_weapons` now defaults True
  there (not in real `GameState.__init__`, which still defaults False)
  since virtually the entire combat test suite used "Schwert" as its
  generic weapon answer - the handful of tests that specifically
  exercise the purchase flow itself now reset it to False explicitly.
  5 new tests, several existing ones adjusted for the new default.
- **Dolch/Schwert's real object codes found, then wired all the way
  through** (UPDATE 84/85/86): user supplied three memory dumps -
  bracketing "verkaufe dolch" then "verkaufe schwert" at Gultibas
  Laden, one action at a time - closing a gap left explicitly
  unresolved since UPDATE 27. Diffing each pair for the confirmed
  `LIMBO_CARRIED` sentinel disappearing found exactly one hit per pair,
  each cross-validated against Schinken's already-confirmed code (21)
  via a forced 48-byte stride relationship and an exact carried-item-
  count match: Dolch = 0, Schwert = 1. `buy_starter_weapons()` now
  actually hands over trackable objects instead of nothing; the
  UPDATE 83 weapon-possession check reads real inventory
  (`objects_carried()`) instead of the `_bought_starter_weapons` proxy
  flag, so selling or dropping a weapon correctly blocks choosing it in
  combat again; `sell()` gained `STARTER_WEAPON_SELL_PRICES` (5/15
  Gerfs, both confirmed via the same screenshots) since neither code
  has a generic merchant-table entry. A genuine surprise along the
  way: object codes 0/1 turned out to ALREADY be `UNLOCK_GATE_OBJECT`/
  `KEY_OBJECT_CODE` - a puzzle door's key requirements, confirmed years
  earlier via disassembly with their identities unknown at the time.
  Both derivations agree - the door's real key is the Schwert, and it
  can only be unlocked while NOT carrying the Dolch - so this is a
  genuine confirmation, not a conflict, closing that older gap too.
  Required updating the shared test fixture to grant the real objects,
  not just the flag, plus a few tests that collided with the newly-
  resolved codes (an "empty inventory" test, and the door-key test's
  own long-standing placeholder use of "object code 1").
- **Gultiba's bedroom (room 88), a full scripted encounter, ported**
  (UPDATE 87): the door behind that same puzzle leads into a scene the
  project had only partially resolved before (`test_room_88_gultibas_
  bedroom` already knew the text existed but not its full shape).
  Direct disassembly of room 88's own handler found the FULL scene:
  walking in for the first time catches Gultiba's wife and her lover
  together ("Ehebruch nennt man das glaube ich!" - now a proper
  `ROOM_FIRST_VISIT_MESSAGE` entry, same split as room 4's own scene),
  4 examinable fixtures (wife/lover/bed/window, none instance-tracked -
  pure scenery), and a confirmed ATTACK outcome: attacking the lover
  (verb 0x24, already a real verb in this port) kills him via a fatal
  "heart attack", drops Ansehen by 2, loses the Dolch to true limbo
  (not the Schwert key itself - matches message 2311's own "...
  vergessen sogar den Schlüssel"), and relocks the puzzle door behind
  you. Deliberately NOT wired in at the time: a second confirmed
  outcome (letting the lover go peacefully, Ansehen +2) whose real
  trigger condition hadn't been traced yet. 4 new tests.
- **The peaceful path, traced and ported** (UPDATE 88): asked to dig
  into that same untraced trigger. Found it isn't inside room 88's own
  handler at all - a separate parser-level verb-aliasing routine
  rewrites typed verb `0x67` to internal verb `0x40` (exactly what room
  88 checks) whenever its argument is object code `2`, also setting the
  flag room 88 reads. New `LASS` verb (parser.py) - a port-utility name,
  same caveat as ATTACK/HELFEN: the EFFECT is disassembly-solid, but
  the exact typed word behind `0x67` is inferred from context (the
  lover's own "Bitte, laßt mich gehen!" line), not independently
  confirmed. `release()` shares its consequence logic with the ATTACK
  outcome via a new `_resolve_gultibas_bedroom_encounter()` helper (same
  Dolch-loss/door-relock, opposite Ansehen sign), and a new
  `_gultiba_bedroom_resolved` one-time flag makes sure only ONE of the
  two outcomes can ever fire for a given game - attacking after already
  releasing (or vice versa) does nothing further. 6 new tests.

## Layout

```
laas-port/
  assets/              WORLD, RESTORE, ITEMS, STORY (original game data)
    ITEMS              (Not included)
    RESTORE            (Not included)
    STORY              (Not included)
    WORLD              (Not included)
    LAASPIC/P1`-`P22`  (Not included)
  laas_port/
    story.py           STORY decompression + ITEMS fragment substitution
    world.py           room graph + object-instance/location tracking + compass directions
    objects.py         250-entry object description table
    room_text.py        room-number -> "look" message-index map (growing, empirical)
    room_titles.py       room-number -> short status-bar title map
    names.py             object-code -> German name table
    characters.py        Smirga/Aszhanti narrator flag
    levels.py             Stärke/Astral/Ansehen title-progression thresholds
    item_stats.py         WORLD Section 1 - item prices
    monster_stats.py      WORLD Section 5 - per-creature combat dice stats
    combat.py             melee combat resolver (confirmed core of sub_879F)
    parser.py            verb/noun/instrument command parser
    game.py             minimal REPL / GameState
  reference/
    walkthrough_de.txt a full German walkthrough (found alongside the
                       original game files) - the best available source
                       for real quest/NPC/plot names and structure until
                       more of the original verb logic is decoded.
```

## Running it

```
cd laas-port
pip install -r requirements.txt  # pynput - cross-platform pre-filled combat prompt, see repl_input.py
python -m laas_port.game
```

## Testing

```
cd laas-port
python -m pytest tests/
```

