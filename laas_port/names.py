"""
names.py - a (small, growing) object-code -> German name(s) table, used
by the parser to resolve nouns typed by the player to real object
codes.

This is deliberately NOT derived from object descriptions (word_16C0):
those turned out to be tiny mid-sentence fragments of a room's flowing
prose (see objects.py's caveat), not standalone names - "examining"
object #32 doesn't return "Sklar", it returns a fragment like "f dem a"
cut out of room 1's own description. So names here are assigned by
REASONING about context (which room an object is tracked in, matching
a fan map's per-room NPC/item list - see room_text.py) rather than by
resolving text directly. Confidence varies entry to entry - see comments.

CAUTION (found while extending this table - do not repeat this
mistake): an object's own text-offset span being *adjacent to* a
recognizable noun in the room's flowing prose does NOT mean that
object code owns that noun. A previous entry here (object 35 ->
"tisch"/"holztisch") was wrong for exactly this reason: object 35's own
span is " Mitte des Raum" (part of "...der die Mitte des Raums
bildet", a relative clause describing an already-introduced table, not
the table itself), and the word "Holztisch" a few words earlier
actually splits mid-word across objects 33/34 ("Holzti" + "sch") - no
single object code owns the whole word. Checked several other
objects in the same room (20-45): EVERY span crosses word boundaries
arbitrarily; none contain one clean, complete noun. This means
proximity-based guessing from these fragments is unreliable in
general, not just for this one entry - don't extend this table via
"which object's span is textually near the noun I want" reasoning.
The real object<->typed-noun mapping most likely lives in the game's
per-room command handlers (the same kind of disassembly that found the
LOCK/UNLOCK key/gate object codes 0/1 in `game.py` - see
`seg005_batch5.md`), not in these description-table text spans - that's
the technique to use for real progress here, not text adjacency.

Multiple German words can map to the same code (synonyms/case forms);
matching is case-insensitive and diacritic-insensitive-ish (see
`normalize()`). Where an object's precise identity among 2+ candidates
in the same room isn't confirmed and no stronger evidence (real
gameplay text, a disassembled print-order trace, etc.) exists, it is
deliberately left OUT rather than guessed - see the comments for what's
missing and why.

Room 1's two tracked objects (32/33) and room 2's two tracked objects
(30/31) are both still-open pairs - NOT "Sklar/Phira" or "Agima/Har" as
an earlier, looser guess in this docstring once assumed. Room 1's own
STANDING description narrates "meine Eltern, Sklar und Phira" as fixed
scene-setting prose, and room 2 ("Smirgas Elternhaus", found via room
67's own West exit) is presumably Agima+Har's home by the same logic -
but that prose does NOT reliably describe which objects the engine
currently tracks as present (see PHASE0_FINDINGS.md UPDATE 25's
follow-up): Sklar and Har are both confirmed (object 26 and object 25
respectively, see below) to be NPCs that move between their home room
and Hyllok's shared village square (room 67) - real user-confirmed
gameplay behavior, not a guess. UPDATE 54 adds a third confirmed Har
location (room 8, the Speisekammer), so this movement is wider than a
simple two-room toggle - still entirely unmodeled in this port (Har/
Sklar aren't in `DAY_ROSTER`/`NIGHT_ROSTER`, they just sit static
wherever the bundled save left them). Whichever objects rooms 1/2
currently track in this project's bundled save (32/33 and 30/31) are a
separate, still-unconfirmed question - PROBABLY people, not household
items: a user hypothesis, tested and confirmed in PHASE0_FINDINGS.md
UPDATE 26, found that essentially every object with a tracked instance
(i.e. `world.py`'s `flags[code].has_instance`) is a person/creature,
while every confirmed portable ITEM (weapons, armor, tools - the 17
merchant-price-confirmed entries below) has NO tracked instance at all.
Since 32/33/30/31 DO have tracked instances, "Brot"/"Ei"/a coffee pot
(all real, user-observed takeable items at room 1) are now considered
UNLIKELY to be among them - more likely "Phira" (Aszhanti's mother) is
one of 32/33 and "Agima" is one of 30/31. **UPDATE 54**: both names are
now independently confirmed as real (not just room 1's flavor text or
`reference/map.json`'s room-2 listing) - a live memory dump of room 2
with only Agima present (Har having left for the Speisekammer) showed
the game's own composited "wer ist hier" buffer literally contained
"Agima ist hier.", and the same dump's memory also contains the game's
complete 39-entry name table with "Phira" as one of its entries. This
strengthens confidence both names are genuinely in play, but does NOT
by itself say which of 30/31 (or 32/33) is which - still not confirmed
by any method that resolves the specific code, so still not added here.
(CAUTION: don't try the "object's own instance-record name-pointer"
approach again to resolve this - conclusively shown unreliable in
UPDATE 26's correction, giving garbled mid-sentence fragments for
every object tried, including already-confirmed ones.)

FIRST REAL ENTRIES (this session): a fundamentally different, stronger
form of evidence than the discredited text-adjacency method above -
cross-referencing an object's TRACKED LOCATION (`world.object_location`,
ground truth from RESTORE) against `reference/map.json`'s per-room
named-object lists, restricted to rooms where there is EXACTLY ONE
tracked object AND EXACTLY ONE named NPC/item listed for that room (no
ambiguity to resolve, unlike room 1's still-open two-object pair).
Confirmed this way:
Foroll (Hyllok's blacksmith), the farmer at the cornfield, Oerli
(Scarbloom's innkeeper), a beggar at the market, Gultiba (the
shopkeeper), Nichidor (Scarbloom's blacksmith), Skeeve (the wizard),
and Potidan (the healer) - each is the sole tracked object in a room
whose fan-map entry lists exactly one matching NPC name. One further
entry (the bridge troll) has only single-source evidence (room 25 is
unambiguously "the troll blocks the bridge" scene and has exactly one
tracked object, but no independent fan-map object-list entry exists for
that specific node) - noted as slightly lower confidence. A later pass
added a stone cross, a lake creature (Tuatara), and both dragons
(Tatzelwurm, then Lindwurm for the second, three-headed one fought in
room 108) the same way, using each room's own confirmed text directly
where the fan map had no matching node to cross-check against.

INDEPENDENT CORROBORATION (found while investigating combat/shopping via
emulation - see the `laas` analysis project's PHASE0_FINDINGS.md UPDATE
16): 8 of these 13 codes (Foroll/34, Gultiba/188, Nichidor/194,
Skeeve/199, Potidan/243, the bridge troll/134, the stone cross/105, the
market beggar/183) also appear as object-code keys in the `WORLD` file's
Section 2 (item/NPC description-pointer table), and the farmer/99 in
Section 3 - a completely different data source than the room-location +
fan-map method that originally confirmed them, reached only because that
investigation happened to decode WORLD's other sections along the way.
Oerli/142, Tuatara/146, and both dragons (237/238) do NOT appear in
either section - plausibly because monsters/dragons and this specific
innkeeper use a different in-game description path, not because the
existing identifications are in doubt.
"""
from __future__ import annotations

OBJECT_NAMES: dict[int, list[str]] = {
    # Empty for the door-verb-adjacent codes 0/1 and the room-1/2 ambiguous NPC pairs -
    # see the CAUTION note above and the module docstring's room-1/2 note.
    34: ["foroll"],   # Hyllok's blacksmith - room 3 ("Schmiede") is his forge, confirmed:
              # sole tracked object there, matches map.json's "Schmiede" (Hyllok) -> ["Foroll"].
    99: ["bauer"],    # the farmer at the cornfield - room 20, sole tracked object, matches
              # map.json's "Kornfeld" -> ["Bauer"].
    162: ["oger"],    # a monster, confirmed via a DIRECT CODE reference, not room/fan-map
              # inference: FEBR's rare bonus-hit branch in sub_879F (see PHASE0_FINDINGS.md
              # UPDATE 38) is gated on `di == 0xe` (instance index 14, which resolves to
              # object 162) and its own success message (STORY message 660) explicitly names
              # the target "den Oger" twice ("blendet sie den Oger ein wenig und Smirga kann
              # einen Schlag plazieren, der dem Oger 1 Schadenspunkt zufügt"). Currently
              # off-stage (LIMBO_REMOVED) in this project's bundled save - a wandering
              # creature, not a fixed encounter.
    35: ["mygra"],    # the alchemist/"Scharlatan" - room 4 ("Mygras Haus" per its own
              # resolved text - potion equipment, herbs, alchemy tools, matching STORY
              # message 1617's description of Mygra as "ein alter Mann...der sich sein
              # Leben lang nur mit Kräutern, Tränken und Magie beschäftigt hat"), sole
              # tracked object there (found via UPDATE 26/27's follow-up systematic sweep
              # of the remaining unnamed instance-tracked codes - PHASE0_FINDINGS.md).
              # map.json's matching node ("Beim Scharlatan") lists TWO names, "Mygra" and
              # "Drachenblut" - the latter is an ITEM (dragon's blood, presumably a potion
              # ingredient), consistent with UPDATE 26's confirmed rule that items don't
              # get a tracked instance - explaining why only one object (this one) is
              # tracked here, and confirming it must be Mygra (the person), not the item.
    142: ["oerli"],   # Scarbloom's second-tavern innkeeper - room 72, sole tracked object,
              # matches map.json's "Taverne" -> ["Oerli"] (also self-confirmed in-game: the
              # NPC introduces himself by name, "isch bin Oerli, dèr Wirt dieses Hotèls").
    183: ["bettler"], # a beggar at Scarbloom's marketplace - room 70, sole tracked object,
              # matches map.json's "Marktplatz" -> ["Bettler"].
    188: ["gultiba"], # the shopkeeper - room 75 ("Laden"), sole tracked object, matches
              # map.json's "Laden" -> ["Gultiba"].
    194: ["nichidor"], # Scarbloom's blacksmith - room 86, sole tracked object, matches
              # map.json's second "Schmiede" entry -> ["Nichidor"] (distinct from Foroll's
              # Hyllok forge above - the fan map has two same-named "Schmiede" nodes with
              # different NPCs, room number is what disambiguates them).
    199: ["skeeve"],  # the wizard - room 61 (his living room), sole tracked object, matches
              # map.json's "Bei Skeeve" -> ["Skeeve"].
    243: ["potidan"], # the reclusive healer - room 27 (his hut), sole tracked object, matches
              # map.json's "Hütte" -> ["Potidan"].
    134: ["troll", "brueckentroll", "brückentroll"], # the bridge troll - room 25, sole
              # tracked object, and the room's entire text (messages 419-423) is about
              # nothing but this one creature blocking the bridge. Slightly lower confidence
              # than the entries above: no independent map.json object-list entry exists for
              # this specific node to cross-check against (the fan map's "Hütte des Trolls"
              # node has an empty object list).
    105: ["steinkreuz", "kreuz"], # an ancient moss-covered stone cross - room 26 (the
              # Baumgruppe), sole tracked object; message 476/479 in that room's handler
              # explicitly describe it ("ein etwa fünf Fuß hohes Steinkreuz...moosüberwuchert").
              # No independent map.json cross-check (its "Baumgruppe" node has an empty object
              # list) - same confidence tier as the bridge troll above.
    146: ["tuatara"], # the lake creature - room 39, sole tracked object; that room's handler
              # (messages 605-610) is entirely about this one creature swimming alongside the
              # boat. No independent map.json cross-check for this specific node.
    238: ["tatzelwurm", "drache"], # the first dragon - room 104 (its treasure hall), sole
              # tracked object; message 1370 names it explicitly ("Ein großer Drache, ein
              # Tatzelwurm, erhebt sich eben von seinen Schätzen"). No independent map.json
              # cross-check for this specific node (though a differently-named "Tatzelwurm"
              # node does exist in the fan map with an empty object list, consistent).
    237: ["lindwurm", "drache"], # the SECOND dragon (the three-headed one fought in room 108's
              # ruined castle) - tracked at room 109 (the edge-of-map/game-ending sentinel, see
              # room_text.py's comment on room 108), one code below confirmed object 238
              # (Tatzelwurm, the first dragon) - a natural adjacent-pair authoring pattern.
              # Named explicitly in room 108's own resolved combat messages (1409/1412/1418):
              # "der Lindwurm wohl gerade dabei ist..."/"der dritte Kopf des Drachen"/"Der
              # Lindwurm ist von geradezu furchteinflößenden Ausmaßen...seine drei Köpfe" -
              # distinct from "Tatzelwurm", confirming these are two differently-named
              # creatures, not the same dragon referred to two ways. No independent map.json
              # cross-check (its "Ruine" node lists different names, "Knochen"/"Harpyie" -
              # likely separate scenery/creature entries in that room, not this one).

    # CONFIRMED VIA A FOURTH, INDEPENDENT METHOD (user-supplied real gameplay
    # data, Laas_CS.xlsx's "Händler" sheet - real prices collected from both
    # in-game merchants, Yarom and Gultiba): cross-referenced against
    # item_stats.py's WORLD Section 1 records by matching all 4 price fields
    # simultaneously (buy-from-player and sell-to-player, for both
    # merchants) - a numeric 4-way match is far stronger evidence than any
    # single-field coincidence. See PHASE0_FINDINGS.md's newest UPDATE for
    # the full cross-reference and the corrected field semantics this
    # revealed (item_stats.py's docstring previously had field 2/4 merged
    # into one "buy price" - they're actually separate per-merchant buy
    # prices, Yarom's and Gultiba's respectively).
    233: ["agitor"],
    201: ["cape"],
    85: ["schuessel", "schüssel"],
    8: ["fackel"],
    46: ["feldflasche"],
    172: ["flasche"],
    154: ["heilkraut"],
    138: ["netz"],
    196: ["echsenpanzer"],  # CORRECTS an earlier misreading: this object code
              # was previously assumed to be an equipped WEAPON (one of three
              # values compared for a "weapon class" in the combat formula -
              # see unicorn_combat.py/PHASE0_FINDINGS.md UPDATE 17). It's
              # actually lizard-scale ARMOR - the combat mechanic is armor
              # class, not weapon class. Renamed throughout on discovery.
    171: ["axt"],
    206: ["skarabaeus", "skarabäus"],
    14: ["schild"],  # object 14 appears twice in WORLD Section 1 with
              # different stats (a real duplicate key, confirmed dead data
              # for the second occurrence - see item_stats.py); this name
              # matches the FIRST occurrence's prices exactly.
    241: ["schuppen"],
    108: ["seil"],
    227: ["zeron"],
    264: ["lederwams"],  # ALSO one of the three "armor class" values (see
              # echsenpanzer's note above) - cheap leather armor.
    52: ["kettenhemd"],  # ALSO one of the three "armor class" values -
              # chainmail, the most expensive of the three, matching it
              # being the highest-numbered armor class (biggest damage
              # reduction).
    # Two items share IDENTICAL prices in the real data (Ruder/oar and
    # Schwert/sword both price as (10,20,15,25)), so object codes 152 and 86
    # can't be told apart by price alone - deliberately left unmapped rather
    # than guessed, matching this file's established discipline.

    # CONFIRMED VIA A FIFTH METHOD (user-reported real gameplay text at
    # room 67 - "Har und Sklar sind hier" - combined with a direct
    # disassembly trace, not a guess): room 67 tracks exactly two objects,
    # 25 and 26. Found the actual "who's present" room-object-lister
    # function (flat 0xF21E-0xF35E in the `laas` analysis project) - it
    # iterates object codes in strict ASCENDING order (di = 0, 1, 2, ...,
    # checking each instance's own stored room field against the current
    # room) and only switches the trailing "ist hier"/"sind hier" text
    # based on how many objects were found, printing names in that same
    # ascending order. Since 25 < 26 and the confirmed text names "Har"
    # before "Sklar", object 25 = Har and object 26 = Sklar - not a
    # 50/50 guess, an order derived directly from the printing code.
    # NOTE: this corrects an earlier, vaguer assumption in this module's
    # own docstring/history that "Sklar" might be one of room 1's two
    # tracked objects (32/33, alongside a guessed "Phira") - Sklar is
    # now known to be object 26, not part of that still-unresolved pair.
    # Cross-checked against `reference/map.json`: "Smirgas Elternhaus"
    # lists ["Agima", "Har"] and "Aszhantis Elternhaus" lists ["Brot",
    # "Ei", "Sklar"] - consistent with Har being Smirga's father and
    # Sklar being Aszhanti's father, both currently standing in Hyllok's
    # village square (room 67) rather than their own houses in this
    # particular save state.
    25: ["har"],
    26: ["sklar"],

    # CONFIRMED VIA A SEVENTH METHOD (UPDATE 58): user-reported real
    # gameplay mechanic - a Salami sits in room 8 (Speisekammer) at the
    # start of the game, but Har takes it within the first few turns
    # unless the player gets there first. `reference/map.json` lists
    # room "Speisekammer" with exactly one object, "Salami"; room 8's
    # own STANDING description (already ported) independently mentions
    # "Eine große Salami hängt an einem Haken..."; and a walkthrough
    # comment already sitting in `room_text.py` cites "gleich am Anfang
    # die Salami nehmen, bevor Papi sie klaut" (Papi = Har). This
    # discovery led directly to fixing a real bug in `world.py`'s
    # `object_location()` (it silently returned None for every non-
    # instance-tracked object, discarding real location data) - object
    # 11 is the ONLY object code whose raw flags word reads exactly `8`
    # (room 8) in the bundled save, matching the fan map's single-object
    # room exactly. Independently confirmed via two user-supplied
    # screenshots of real gameplay showing the exact STORY text: "Har
    # steckt die Salami ein, die hier herumlag." (Har pockets the Salami
    # that was lying around here.)
    11: ["salami"],

    # CONFIRMED VIA AN EIGHTH METHOD (UPDATE 68, disassembly trace of
    # the farmer's harvest-help quest - see game.py's FARMER_* constants
    # and helfen()): the walkthrough's own text ("Vom Bauern kriegt Ihr
    # Schinken, wenn Ihr ihm auf dem Feld helft") is confirmed
    # word-for-word by STORY message 357 ("...läßt es sich der Bauer
    # nicht nehmen, uns einen großen Schinken einzupacken..."), and the
    # disassembly's own quest-completion code pushes object code 21
    # directly into a "give object" call right after printing that same
    # message. Object 21 itself is unnamed/unpriced/non-instance-
    # tracked in the raw data - consistent with a free reward item, not
    # independently corroborated by a second source the way some other
    # codes are.
    21: ["schinken"],

    # CONFIRMED VIA A NINTH METHOD (UPDATE 69, disassembly trace of the
    # Tuatara bounty/diplomacy quest - see game.py's TUATARA_* constants):
    # Phadraig (already named via UPDATE 54's master name-table find,
    # but never placed anywhere) is confirmed as instance index 12's...
    # no - confirmed as object 147 directly: the quest-offer dispatcher
    # gates its whole block on `cmp di, 0x93` (147) before the fishing-
    # village dialogue plays, and message 556 has him introduce himself
    # by name ("'Freut mich', erwidert er. 'Ich bin Phadraig.'").
    # Ruder (oar) is confirmed as object 152: the SAME dispatcher checks
    # `cmp si, 0x98` (152) specifically in the branch that prints
    # message 1958 ("...nimmt mir das Ruder aus der Hand"), resolving
    # the ambiguity this file's own price-collision note (152 vs 86)
    # had left open - Ruder is 152, leaving 86 for Schwert by
    # elimination (still not independently confirmed for 86 itself).
    147: ["phadraig"],
    152: ["ruder"],

    # CONFIRMED VIA A TENTH METHOD (UPDATE 70, disassembly trace of
    # Potidan's Mondscheinkraut quest - see game.py's POTIDAN_*
    # constants): the herb is confirmed as object 64 via the SAME
    # give-dispatch convention as Ruder/152 above - Potidan's own topic
    # dispatcher gates its reward branch on `cmp si, 0x40` (64). The
    # Skelett (skeleton) is confirmed as object 244 by cross-referencing
    # the ALREADY-PORTED `NIGHT_ROSTER` entry `244: 28` (previously
    # placed without a confirmed name) against room 28's own night-
    # arrival/dawn-departure message pair (1553/1552), which describe
    # exactly one creature: "ein Skelett mit blanken Knochen entsteigt
    # dem feuchten Erdreich" / "das Skelett wird zurück ins Erdreich
    # gesaugt".
    64: ["mondscheinkraut", "kraut"],
    244: ["skelett"],

    # CONFIRMED VIA AN ELEVENTH METHOD (UPDATE 76): a live memory dump
    # captured mid-fight (user-supplied, "MEMDUMP_in_fight_goblin.BIN")
    # contained a plain-text, NUL-separated, 39-entry name table in
    # exact instance-index order - cross-validated against every
    # already-confirmed identity with zero mismatches. Object 87 (an
    # already-placed but never-named `NIGHT_ROSTER` entry, `87: 23`)
    # sits at instance index 2, which that table names "Zombie".
    87: ["zombie"],

    # CONFIRMED VIA A SIXTH METHOD (direct disassembly trace of the price-
    # quote dialogue itself, not room/fan-map inference): the function at
    # flat 0xDD94 (the "make an offer" dialogue handler) contains a branch
    # gated on `cmp word ptr [bp-2], 0xA7` (167) that, after checking the
    # named item is one Yarom buys, calls a price-computation routine and on
    # success prints STORY message 1568 verbatim - "Yarom denkt kurz nach.
    # 'Also ich würde euch %d Gerfs dafür geben!'" - and on rejection prints
    # message matching dseg 0x9dd6, "Yarom schüttelt den Kopf. 'Damit kann
    # ich nichts anfangen.'". `[bp-2]` is loaded from dseg 0xaaf8/0xb3f4,
    # the same "current dialogue-partner object code" variable used
    # throughout seg005's dispatch handlers. This directly resolves the
    # previously-unidentified object 167 (see PHASE0_FINDINGS.md's earlier
    # "not resolved, not guessed at" note for 167/room 44 and 202/room 98) -
    # 167 is tracked at room 44 in this project's bundled save, a generic
    # wilderness room with no NPC named in its own static text, consistent
    # with Yarom being a wandering merchant who just happens to be passing
    # through there rather than living in a fixed shop like Gultiba.
    167: ["yarom"],

    # CONFIRMED VIA A SEVENTH METHOD (tracing the master per-turn "ambient
    # event" dispatcher, flat 0x64A3-0x6A5F in the `laas` analysis project -
    # see PHASE0_FINDINGS.md UPDATE 40): object 202, previously flagged
    # "not resolved, not guessed at" (tracked at room 98), is Sabrina, a
    # witch. The dispatcher's room-98 branch is a staged encounter whose
    # warning-stage message names her directly ("Wir wollen zur Türe
    # fliehen, doch Sabrina ist schon im Raum gelandet") and whose final
    # stage - right where her instance's location gets forced to the
    # confirmed LIMBO_REMOVED sentinel - describes her fleeing ("...schnappt
    # sich ihren Besen und zischt durch den Kamin davon", grabs her broom
    # and zips away through the chimney). Cross-checked against 20+ other
    # STORY messages: she's "die Hexe aus den Sümpfen" (the witch from the
    # swamps, message 1128), the target of a fetch-quest for Skeeve (199,
    # already confirmed) - and message 1150/1271 confirm Cape (201,
    # already confirmed) is specifically an invisibility cloak for sneaking
    # past her ("Es macht euch für einige Minuten unsichtbar...benutzt es
    # nur bei Sabrina!").
    202: ["sabrina", "hexe"],

    # CONFIRMED VIA A TWELFTH METHOD (UPDATE 84): user-supplied a pair
    # of live memory dumps bracketing a single, precise action - selling
    # the Dolch to Gultiba ("MEMDUMP_dolch_im_inventar.BIN" and
    # "MEMDUMP_dolch_verkauft.BIN") - closing a gap this project had
    # left explicitly unresolved since UPDATE 27 ("the real object
    # codes for Dolch/Schwert were investigated at length and are
    # UNRESOLVED"). Diffing the two dumps found exactly one 16-bit word
    # anywhere in either 640KB image reading the confirmed `LIMBO_
    # CARRIED` sentinel (150) in the "still carried" dump and something
    # else (69) in the "sold" one. That position sits at a confirmed
    # 48-byte stride (matching the object descriptor table's own record
    # size) from six OTHER positions still reading 150 unchanged in
    # both dumps - one of which is EXACTLY 21 strides away, landing
    # precisely on object 21 (Schinken, already confirmed above via a
    # separate method) - an internally-forced cross-check, not a
    # coincidence: if Schinken is really 21 strides higher, the vanished
    # position can only be object 0. Independently corroborated by
    # count alone: this same stride formula finds exactly 7 currently-
    # "carried" codes in the first dump and exactly 6 in the second -
    # matching the visible 7-item/6-item inventory exactly - and object
    # 0 has no entry at all in the generic merchant price table
    # (`item_stats.py`), consistent with Dolch already being confirmed
    # as Foroll's own scripted, non-catalog starter-weapon bundle item
    # rather than a normal shop good.
    0: ["dolch"],

    # CONFIRMED VIA A THIRTEENTH METHOD (UPDATE 85): the natural follow-
    # up to UPDATE 84 - user supplied a THIRD memory dump
    # ("MEMDUMP_schwert_verkauft.BIN"), bracketing "verkaufe schwert"
    # against the previous update's own "dolch_verkauft" dump as the
    # "before" state (Schwert still carried, 31 Gerfs). Identical
    # method, identical result shape: exactly one 16-bit word anywhere
    # in either 640KB image reads 150 (`LIMBO_CARRIED`) before and 69
    # (the same "sold to Gultiba" sentinel UPDATE 84 already saw for
    # Dolch) after - at file offset 0x2bbc3, exactly one 48-byte stride
    # above Dolch's own confirmed position (0x2bb93) - i.e. object code
    # 1, precisely the adjacent-pair guess UPDATE 84 flagged as
    # "tempting" but left unconfirmed. Money moved 31 -> 46 (+15 Gerfs,
    # Gultiba's own buy-back price for Schwert specifically), and the
    # same stride formula finds exactly 6 "carried" codes in the
    # "before" dump dropping to exactly 5 in the "after" one - matching
    # the screenshot's own visible 6-item/5-item inventory exactly.
    # Object 1 also has no entry at all in the generic merchant price
    # table, same as Dolch/0 - both starter weapons are Foroll's own
    # scripted, non-catalog bundle, never part of the regular shop
    # catalog.
    1: ["schwert"],

    # CONFIRMED VIA A FOURTEENTH METHOD (UPDATE 87): direct disassembly
    # of room 88's own handler (Gultiba's bedroom) - the four scripted
    # fixtures of the affair scene, identified by which object code
    # each of the room's own `si` (direct-object) comparisons targets,
    # cross-checked against their own STORY text (message 1052
    # describes "Die Frau"/the wife, 1053/2269 "Der Mann"/the lover,
    # 1049 the "Himmelbett", 1050 the "Fenster"). None are instance-
    # tracked (pure scenery, not combat) - see game.py's GULTIBA_*
    # constants for the full scene.
    186: ["frau", "gultibas frau"],
    145: ["mann", "liebhaber"],
    119: ["bett", "himmelbett"],
    9: ["fenster"],
}


def normalize(word: str) -> str:
    return word.strip().lower()


def resolve_name(word: str, candidate_codes: list[int]) -> int | None:
    """Given a typed word and a list of object codes to consider (e.g.
    objects present in the current room), return the matching code, or
    None if no name is known/matches. Candidate codes not in
    OBJECT_NAMES are silently skipped, not guessed."""
    w = normalize(word)
    for code in candidate_codes:
        names = OBJECT_NAMES.get(code, [])
        if w in names:
            return code
    return None
