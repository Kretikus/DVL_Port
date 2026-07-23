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
in the same room isn't confirmed (e.g. "one of these codes is Sklar,
the other is Phira, order unconfirmed"), it is deliberately left OUT
rather than guessed - see the comments for what's missing and why.

FIRST REAL ENTRIES (this session): a fundamentally different, stronger
form of evidence than the discredited text-adjacency method above -
cross-referencing an object's TRACKED LOCATION (`world.object_location`,
ground truth from RESTORE) against `reference/map.json`'s per-room
named-object lists, restricted to rooms where there is EXACTLY ONE
tracked object AND EXACTLY ONE named NPC/item listed for that room (no
ambiguity to resolve, unlike room 1/2's Sklar-Phira / Agima-Har
situations, which remain deliberately unnamed). Confirmed this way:
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
"""
from __future__ import annotations

OBJECT_NAMES: dict[int, list[str]] = {
    # Empty for the door-verb-adjacent codes 0/1 and the room-1/2 ambiguous NPC pairs -
    # see the CAUTION note above and the module docstring's room-1/2 note.
    34: ["foroll"],   # Hyllok's blacksmith - room 3 ("Schmiede") is his forge, confirmed:
              # sole tracked object there, matches map.json's "Schmiede" (Hyllok) -> ["Foroll"].
    99: ["bauer"],    # the farmer at the cornfield - room 20, sole tracked object, matches
              # map.json's "Kornfeld" -> ["Bauer"].
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
