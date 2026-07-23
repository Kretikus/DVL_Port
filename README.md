# Die Drachen von Laas — port (groundwork)

A from-scratch reimplementation of the 1991 German text adventure "Die
Drachen von Laas" (ATTIC Software), built from a full reverse-engineering
pass over the original `LAAS.EXE` (16-bit real-mode DOS, Borland C++,
large memory model). This repo is the **port** - a clean-room Python
reimplementation of confirmed game mechanics. It does not contain or
depend on the original disassembly/IDA project; see `reference/` for
background material and `assets/` for the original data files the game
itself needs to run (these were always freely distributable game data,
not code).

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
- **Object names cover 13 NPCs/creatures/items so far** (`names.py`) -
  Foroll, the cornfield farmer, Oerli, a market beggar, Gultiba,
  Nichidor, Skeeve, Potidan, and the bridge troll (found by
  cross-referencing each object's tracked location against the fan
  map's per-room NPC lists, restricted to rooms with exactly one
  tracked object and exactly one named NPC), plus a stone cross, the
  lake creature (Tuatara), and both dragons (Tatzelwurm, then Lindwurm
  for the second, three-headed one) - found the same way but using that
  room's own confirmed text directly where the fan map didn't have a
  matching entry to cross-check against. The real
  per-room noun-DISPATCH mechanism (how the original recognizes a typed
  word as referring to a specific object at all) still hasn't been
  found - see names.py's module docstring for what was tried and ruled
  out this session (no direct writes to the object-code globals
  anywhere in the binary, and a generic prologue search failed since
  different handlers use different registers for the same check).
  Portable items and the ambiguous room-1/2 NPC pairs (Sklar/Phira,
  Agima/Har) still need numeric codes (`nimm #35`).
- **No combat, dialogue, spells, or most of the puzzle mechanics**
  documented in `reference/walkthrough_de.txt`. Doors (OPEN/CLOSE/LOCK/
  UNLOCK) are ported (see the door tetralogy bullet above). Shopping's
  price data is now real (`item_stats.py`, surfaced via EXAMINE) but
  there's no BUY/SELL verb or shopkeeper dialogue yet.

## Layout

```
laas-port/
  assets/              WORLD, RESTORE, ITEMS, STORY (original game data)
  laas_port/
    story.py           STORY decompression + ITEMS fragment substitution
    world.py           room graph + object-instance/location tracking + compass directions
    objects.py         250-entry object description table
    room_text.py        room-number -> "look" message-index map (growing, empirical)
    room_titles.py       room-number -> short status-bar title map
    names.py             object-code -> German name table
    characters.py        Smirga/Aszhanti narrator flag
    parser.py            verb/noun/instrument command parser
    game.py             minimal REPL / GameState
  reference/
    walkthrough_de.txt a full German walkthrough (found alongside the
                       original game files) - the best available source
                       for real quest/NPC/plot names and structure until
                       more of the original verb logic is decoded.
    map.json / map.png a fan-made Trizbort-style map (103 named rooms +
                       full connectivity + per-room object/NPC lists) -
                       used to cross-reference room numbers to real names
                       via graph-topology matching (see room_text.py).
```

## Running it

```
cd laas-port
python -m laas_port.game
```

## Testing

```
cd laas-port
python -m pytest tests/
```

A regression suite covering the confirmed mechanics: STORY decompression,
the object-table offset-boundary logic, the room exit graph and compass
mapping, room-text narrator branching, the parser, all verbs (movement,
take/drop/examine/inventory, the door tetralogy, save/load), and a
`test_traversal.py` that BFS-walks the entire real exit graph (96 of 109
rooms) via the actual parser+execute() path. Several tests exist
specifically to lock in real bugs found and fixed during development
(documented in each test's docstring):
- the room-5/6 swap and the object-35 naming mistake (both pre-existing
  this test suite, caught earlier by manual verification);
- a parser bug where "schließe X auf mit Y" fell through to CLOSE
  instead of UNLOCK because the "auf" suffix check ran before the
  instrument clause was split off;
- a `GameState.go()` crash: exit `dest_room` values of `999` and `109`
  are sentinels (a real "can't go that way" dead end, and a likely
  unimplemented game-ending trigger, respectively - see world.py's
  module docstring), not real rooms, but `Exit.usable` didn't exclude
  them, so navigating into one crashed with an `IndexError` instead of
  a sensible refusal message. Found by `test_traversal.py`, the first
  test to actually walk the full graph via real navigation instead of
  jumping directly to a room number.

## Where the ground truth comes from

Every mechanic here was independently verified during reverse
engineering (not guessed): the STORY decompression algorithm was
confirmed by executing the real extracted x86 machine code under the
Unicorn CPU emulator and diffing output byte-for-byte against this
Python port; the room graph was validated by checking that 96% of
non-self destination edges are reciprocal (the shape of a real
hand-built map); and the object table was validated by reconstructing
multi-sentence, grammatically coherent German prose from consecutive
table entries. See the sibling reverse-engineering project's
`decompiled/PHASE0_FINDINGS.md` for the full derivation history if you
have access to it - this repo intentionally doesn't duplicate that
(very long) analysis log, only the mechanics it proved out.

## Suggested next steps

1. Port more verb handlers from `decompiled/seg005_batch*.md` into
   `GameState.execute()`, using `reference/walkthrough_de.txt` to
   cross-check behavior. UPDATE: shopping's price table is no longer
   blocked - `item_stats.py` ports the real `WORLD` Section 1 lookup
   (`sub_E6A1`), confirmed byte-for-byte via direct Unicorn emulation
   of the real function (136/136 checks against every record/field in
   the shipped data - see PHASE0_FINDINGS.md "UPDATE 16" and
   `tools/unicorn_price.py`), and is now wired into EXAMINE's output.
   Combat remains blocked - the same emulation attempt on the combat
   resolver (`sub_879F`) got much further than static analysis alone
   (past the RNG, into real per-instruction execution) but needs a
   properly-populated object-instance table (itself runtime-loaded
   from a save file, not yet traced) to go further; don't fabricate
   placeholder damage numbers to fill that gap in the meantime.
2. Keep extending `room_text.py`'s coverage (rooms 49, 58, 59, 66, 68,
   69, and 89-99 remain genuinely uncompiled, though the room-title
   list's "Marschland"/"Hexenhaus"/"Sumpf" entries strongly hint 89-99
   is a swamp/witch's-house area - see room_text.py's docstring) and
   `names.py`'s object-name coverage (13 entries so far via
   room-location + fan-map cross-referencing).
   The same investigation that found room_titles.py's data also
   surfaced the game's real 250-word generic-object vocabulary (flat
   `0x22800`+ in the `laas` analysis project, right after the room
   titles) - genuine, confirmed words for essentially every
   walkthrough-relevant item (`Kettenhemd`, `Spruchrolle`, `Scarabäus`,
   `Salami`, ...), but its list ORDER does NOT correspond to object
   codes (tested against 3 independently-confirmed codes - one matched,
   two didn't, ruling out a simple index-based mapping - see
   PHASE0_FINDINGS.md UPDATE 14's addendum). Useful as a
   word-validation reference, not a shortcut to codes; the real
   per-room noun-dispatch mechanism connecting words to codes is still
   unfound despite two sessions' worth of attempts (`sub_2477` call
   sites, direct global writes, prologue-pattern search).
3. ~~Add save/load~~ - done (JSON, this port's own format - see `game.py`).
4. ~~Extend character/party modeling~~ - `GameState.character` (the
   `charakter`/`wechsel` verbs) lets a player/tester switch narrator on
   demand, though it's a port utility rather than a reconstructed
   original command (see its docstring). Aszhanti's own flag constant
   still hasn't been traced - only the comparison against Smirga's is
   confirmed, which is all the port currently needs.
