"""
room_text.py - the (still very partial) room-number -> message-index
map for "look" descriptions.

Room descriptions turned out to live in the SAME NUL-delimited message
table as everything else (see story.py's module docstring / Story.message()),
dispatched via per-room hardcoded handler functions (checking verb==1)
rather than a clean lookup table - see the `laas` analysis project's
PHASE0_FINDINGS.md for the full derivation. Finding the real dispatch
mechanism (which function handles which room number) turned out to be
impractical to fully automate from static analysis alone.

Instead, these entries were established EMPIRICALLY: the user played the
real game in DOSBox, captured screenshots of specific rooms via OCR/by
hand, and those exact German strings were located inside decompressed
STORY (see `resolve_story_messages.py`'s technique) to get a message
index - then cross-referenced against `world.py`'s room graph (using
NPC/object presence and reciprocal-exit structure) to determine which
room number that message belongs to. This is real, verified ground
truth for each entry below, NOT inferred or guessed - see the comment
on each entry for how it was pinned down.

Extending this table: capture more real game text (DOSBox + screenshot,
or share the screenshot directly for OCR-free reading), find its
message index the same way, and confirm the room number via world.py's
room graph / NPC presence / reciprocal exits like the entries below.

A fan-made map (Trizbort-style JSON export, 103 named rooms + full
connectivity + per-room object/NPC lists, covering nearly the entire
game) is a second major cross-reference source: matching its room-graph
topology against `world.py`'s real exit graph (constraint propagation
seeded from the confirmed rooms below as anchors) can identify further
room numbers' real names even before their message text is found. This
only propagates a few hops from existing anchors before running out of
locally-unique topology (most of the graph needs either more anchors or
a real backtracking isomorphism search to resolve) - two solid new
matches came from one such pass: room 5 (resolving the earlier room
5-vs-6 ambiguity) and room 8 ("Speisekammer", Smirga's pantry - matches
the walkthrough's "Kaffeekanne in Smirgas Speisekammer"). CAUTION: a
degree-zero room can spuriously "match" any other unconnected node with
no real evidence - always sanity-check a propagated match has an actual
shared neighbor chain back to a real anchor, not just matching degree.

MULTI-PART DESCRIPTIONS: a room's full "look" text is often split
across several CONSECUTIVE message-table entries, not one - the
original game's per-room handler prints them with separate calls in
sequence (sometimes because a clause in the MIDDLE differs depending on
game state, e.g. which party member is narrating, so the shared
prefix/suffix are their own messages and only the differing middle
clause branches). Room 1 is a confirmed real example: the handler
(disassembled - see `characters.py` and PHASE0_FINDINGS.md UPDATE 12)
prints message (93 or 94, depending on `characters.Character`) + always
95 + (96 or 97, same branch) + always 98. `ROOM_LOOK_MESSAGE` entries
that vary by narrator are stored as a list of (message_or_pair) items
below; `look_text()` takes the narrator into account instead of
defaulting to one fixed choice.
"""
from __future__ import annotations

from .characters import Character, DEFAULT_NARRATOR

# room_number -> message index, a list of message indices to concatenate,
# or (for entries with a narrator-dependent clause) a list mixing plain
# ints with (smirga_message, aszhanti_message) tuples - see look_text().
ROOM_LOOK_MESSAGE: dict[int, int | list] = {
    67: 61,   # "Auf dem Dorfplatz" - confirmed: exact text match (start-of-game description)
    1: [(93, 94), 95, (96, 97), 98],  # "Aszhantis Elternhaus" - confirmed: exact text match,
              # + reciprocal exit from 67. Narrator-dependent clauses confirmed by disassembling
              # the room's handler (flat 0x147bd): `cmp word_b722, 0x1a` selects 93/96 (Smirga
              # narrating, third-person "seine Eltern") vs. 94/97 (Aszhanti narrating, first-person
              # "meine Eltern") - see characters.py. Message 99 right after this is the room's
              # separate first-entry EVENT text (parents' breakfast scene) - now wired in, see
              # ROOM_FIRST_VISIT_MESSAGE below (UPDATE 89).
              #
              # NEWLY FOUND, NOT wired in (UPDATE 89): the whole first-visit check is itself
              # nested inside a `byte_b40a` (dragon mood, confirmed elsewhere) gate - `mood>=0`
              # takes this whole path (base text + first-visit-gated 99); `mood<0` instead jumps
              # to an ENTIRELY DIFFERENT description (3 more messages at dseg 0xa68a/0xa690/0xa692,
              # not yet resolved to STORY message numbers - unlike every other far-pointer message
              # this project has decoded, these read as raw segment:offset pairs pointing outside
              # the confirmed message-table addressing scheme, needing new work to decode). This
              # port doesn't track dragon mood as live state at all yet (RESTORE's own saved byte
              # is +1 - satisfies the "good mood" branch by default, which is why skipping this
              # gate entirely is a safe simplification for now, not a guess).
    2: 110,   # "Smirgas Elternhaus" - confirmed: NPC count (2 tracked objects = "Har und Aqima sind hier")
    10: [227, 229, 230],  # "Vor Hyllok" / "Hügelland vor Hyllok" - CORRECTED (see below):
              # confirmed by degree-matching against the fan map (a real hub, degree 7 in the map:
              # connects to "Am Fluss", "Hügelland", "Kiesweg" etc; room 10 has 5 real exits: rooms
              # 11,14,17,18,67 - consistent with a hub, NOT a dead end) and by exact text match.
              # 3-part message like room 1: 227/228 is the character-name variant (Smirga/Aszhanti
              # narrating, defaults to 227), 229+230 are the shared continuation. Directly
              # cross-checked against two further user-provided screenshots ("An einem Fluß" x2,
              # messages 324/325) reachable from here.
    4: [139, 155],   # "Beim Scharlatan" (Mygra's house) - confirmed: object #35's text
              # fragment (" Mitte des Raum") matches "...der die Mitte des Raums bildet" in
              # this room's text. 155 (the Drachenblut/Notizzettel continuation) confirmed
              # via `room_handler_by_address.py` (immediately follows 139 in room 4's own
              # handler) AND a user-supplied screenshot showing this exact continuation
              # ("Eine große Lache dunkelroter Flüssigkeit...Unschwer identifiziere ich es
              # als Drachenblut!") right after 139's text, before "Mygra ist hier."
              #
              # NOT actually unconditional in the real game, but PROVEN to always evaluate
              # true - traced the exact gating check (PHASE0_FINDINGS.md UPDATE 80): room 4's
              # handler calls a shared helper (flat 0xABB0) with (object=0x23/35=Mygra,
              # room=word_b34e), which - since Mygra's `handler_selector` low byte is 9 -
              # searches her object descriptor's own embedded room-association list (the
              # "+0x0A+ variable per-object data" objects.py's own docstring flagged as an
              # unconfirmed, ambiguous field) for the current room, printing 155 only if
              # found. Mygra's list is exactly `[4]` (her own home, cross-checking the room
              # number independently) and nothing else - she has no day/night roster entry,
              # so this can never be any other value while room 4's own handler is running.
              # Genuinely conditional data, but a condition that can never actually go the
              # other way during real play - not a simplification after all.
              #
              # Message 152/153's "lick the blood"/"no more blood" pair is a SEPARATE,
              # still entirely unmodeled interaction, not traced this pass - a real gap,
              # just not one that affects whether 155 itself shows.
    3: 126,   # "Schmiede" (Foroll's forge) - confirmed: exact text match. Also resolves what room 3
              # actually is (the room 10 mixup above wrongly assumed it was "Vor Hyllok"); its
              # single-exit-back-to-67 structure matches a simple forge dead-end far better anyway.
    # --- MAJOR CORRECTION (see PHASE0_FINDINGS.md's newest addendum): the room-number
    # assignments below for the "An einem Fluß" / Baumgruppe / bridge-troll / farm / Scarbloom-
    # alley / Skeeve clusters were WRONG in an earlier pass of this file, despite each
    # individual MESSAGE having been correctly identified (via real screenshots or coherent
    # text matching) - the room NUMBER each message was pinned to was determined by exit-graph
    # topology reasoning, which turned out to be systematically off for this whole region. This
    # was caught and fixed by finding the game's actual room-handler dispatch mechanism is a
    # clean formula after all (`dseg 0x7c20 + (room_number-1)*4`, confirmed against all 12
    # original anchors) - once that's used to read a room's handler DIRECTLY (see
    # `tools/room_handler_by_address.py` in the `laas` analysis project), no graph-topology
    # inference is needed at all for these rooms; the correct room number falls straight out of
    # the disassembly. Every entry below marked "(direct handler lookup)" was confirmed this
    # way; entries without that phrase were unaffected by this correction.
    14: 273,  # (direct handler lookup) hilly meadows path, N->10/S->22 - text mentions the gravel
              # path and party banter ("Weg ins Abenteuer"). Previously wrongly held message 324
              # (an "An einem Fluß" room) - that message really belongs to room 17, far away on
              # the OTHER side of the Vor-Hyllok hub; the two clusters had been conflated by the
              # earlier topology-only pass.
    15: 274,  # (direct handler lookup) hills rising toward the mountains, N->10/S->23/W->16 - text:
              # "im Westen werden die Hügel immer höher und bilden...ein hohes Gebirge". Previously
              # wrongly held message 325 (really room 18's content).
    16: 275,  # (direct handler lookup) "Fuß des Gebirges" (foot of the mountains) - room16's only
              # exit is E->15 (dead end). Text: "Im Westen kann ich die kleine Grenzstation sehen" -
              # a border station glimpsed but never reached.
    17: 324,  # (direct handler lookup) "An einem Fluß" - room17's real exits {S:18, SW:10, W:11,
              # NW:26} match: SW back to the Vor-Hyllok hub, NW to the Baumgruppe (room 26 below).
              # Text: "Hier zerteilt ein breiter, reißender Fluß das Hügelland...", mentions fish
              # and a "Baumgruppe" visible - matches the NW exit to room 26 exactly.
    18: 325,  # (direct handler lookup) "An einem Fluß", the gravel-path river crossing - room18's
              # real exits {N:17, SW:14, W:10, NW:11} match; W back to the Vor-Hyllok hub. Text:
              # "Wir stehen auf einem ausgetretenen Kiesweg, der in einem weiten Bogen im Westen
              # nach Hyllok...führt".
    22: 407,  # (direct handler lookup) hill country flattens, path back toward the hub - room22's
              # real exits {N:14, S:24} match; text: "Langsam wird das Hügelland flacher. Der
              # Kiesweg...führt im Norden zurück ins Herz des Hügellands". Previously wrongly held
              # message 473 (the Baumgruppe) - that belongs to room 26.
    23: 415,  # (direct handler lookup) generic hill country, mountains W / endless hills E -
              # room23's real exits {N:15, SE:24} match. Previously wrongly held message 417
              # (really room 24's content).
    24: 417,  # (direct handler lookup) hill country ends at the bridge - room24's real exits
              # {N:22, SE:25, NW:23} match; text: "Hier endet das Hügelland...im Südosten sehe ich
              # eine Brücke mit einer Hütte daneben" - SE leads to the bridge-troll room (25).
              # Previously wrongly held message 423 (really room 25's content).
    25: 423,  # (direct handler lookup) the bridge / troll encounter itself - room25's real exits
              # {E:29, NW:24} match; text: "Wir stehen an einem Brückenaufgang. Die Brücke
              # überquert den Fluß...Ein riesiger Troll...steht breitbeinig in der Auffahrt" - one
              # of the most distinctive scenes in the game. Previously this content (and room
              # number "24") were conflated with room 23/24 above.
    26: 473,  # (direct handler lookup) "Unter einer Baumgruppe" - room26's real exits {SE:17,
              # NW:20} match (SE back to the river room, NW to the farm's dark field-path
              # entrance). Previously this content was wrongly assigned to room "22".
    7: 178,   # "Smirgas Zimmer" - confirmed: unique asymmetric msg_code 3/4 exit pair with room 2,
              # matching the spiral staircase described in Smirgas Elternhaus's text
    6: [(160, 161), 162, 163],  # "Aszhantis Zimmer" - CORRECTED (see below): an earlier pass
              # wrongly assigned this to room 5 via graph-isomorphism alone (matching a past
              # room-3/10 style mistake in this project). Room 1's own text says explicitly
              # "Ein Durchgang im Norden führt in [Aszhantis/mein] Zimmer", and room 1's real exit
              # graph has N -> room 6 (not room 5) - confirmed directly from world.py, no
              # isomorphism guessing needed. Same Smirga/Aszhanti narrator-pair pattern as room 1's
              # message 93/94 (see characters.py): 160 = third-person "Aszhantis Zimmer" (Smirga
              # narrating), 161 = first-person "mein Zimmer" (Aszhanti narrating).
    5: [157, 158],  # "Hühnerstall" (chicken coop) - confirmed: room 1's E exit (world.py) plus room
              # 1's own text mentioning "das aufgeregte Gegacker der Hühner...hinter dieser Türe" -
              # message 157 ("Wir stehen im Hühnerstall. Aufgeregt flattern die Hühner...") is an
              # exact thematic + textual match. This is the OTHER half of the room-5/6 correction
              # above: room 5 is the chicken coop, not Aszhanti's bedroom.
    8: [183, 184],  # "Speisekammer" (Smirga's pantry) - confirmed: exact text match from a real
              # screenshot (also independently suggested by the graph-isomorphism match above,
              # now verified directly). Message 184 (the hanging Salami) matches both the
              # walkthrough's "gleich am Anfang die Salami nehmen, bevor Papi sie klaut" and the
              # fan map's per-room object list ("Salami").

    # --- batch below: confirmed via the dispatch-table bulk text pass (PHASE0_FINDINGS.md
    # UPDATE 12) + FULL exit-graph reciprocity verification (every edge below round-trips
    # both directions in world.py - stronger evidence than degree-matching alone, since a
    # wrong assignment would break reciprocity somewhere in the chain, not just "happen to
    # have the right degree"). All chain from the pre-existing anchors 10 ("Vor Hyllok"),
    # 14/15 ("An einem Fluß" x2), and 22 ("Baumgruppe").
    9: 185,   # "im Brunnen" (in the well) - room 9 has ZERO compass exits in world.py, consistent
              # with a well being entered via a special action (jump/climb in), not normal
              # movement - matches the village square's (room 67) own text mentioning "der
              # schwere, hölzerne Eimer...über dem Brunnen".
    11: 232,  # hilly meadows north of room 10 (world.py: 10 -N-> 11); text mentions a small tree
              # grove visible ahead, consistent with neighboring room 12.
    12: [(234, 233), 235],  # "Auf einem Hügel" - reached 10-N->11-W->12 (all reciprocal). Text:
              # "...stehen auf einem der mächtigsten Hügel der Gegend...Im Süden sieht man die
              # hohen Dorfpalisaden Hylloks" - a hilltop with Hyllok's palisade visible south,
              # matching room 12's S exit back to the hub (room 10). ANOTHER narrator pair here
              # (see characters.py): message 234 ("Aszhanti und ich...") is said when SMIRGA is
              # narrating (referring to Aszhanti by name), message 233 ("Smirga und ich...") when
              # ASZHANTI is narrating - opposite naming convention from room 1/6's pairs, but the
              # same underlying mechanism.
    13: 236,  # Western Hügelland ends at the mountains - reached 12-W->13 (reciprocal). Text:
              # "Hier endet das Westliche Hügelland von Laas...nur ein schmales Tal führt weiter
              # nach Westen" - matches room 13's W exit being the "999" edge-of-map sentinel (a
              # narrated but unreachable valley - see world.py's sentinel note).
    19: 342,  # (direct handler lookup) hill country transitions to a plain, a turnip field
              # ("Rübenfeld") beside the path - room19's real exits {N:20, S:12} match (S back to
              # the "Auf einem Hügel" hub). Previously this room wrongly held message 273 (really
              # room 14's content, on the other side of the map).
    20: 344,  # (direct handler lookup) "Kornfeld" (cornfield, harvest scene with farmers) -
              # room20's real exits {N:21, SE:26, S:19} match; SE leads to the Baumgruppe (room 26).
              # Previously this content was wrongly assigned to room "64" - the farm cluster is
              # actually here, just north of room 19's turnip field, not down near the mountain
              # troll cave.
    21: 361,  # (direct handler lookup) farmyard (dung heap, rooster, barn door) - room21's only
              # exit is S->20 (dead end), matching the farm cluster's structure. Previously this
              # content was wrongly assigned to room "65" (the troll's actual lair, far away).
    29: 495,  # "Gabelung" (the gravel path forks) - reached 24-SE->25-E->29 (both reciprocal).
              # Text: "Der Weg gabelt sich hier...Ein Stückchen weiter im Westen beginnt die
              # Brücke, die zurück ins Hügelland führt" - explicitly describes being just west of
              # the bridge, matching the graph position exactly.

    # --- second batch: bulk-matched against the FULL 109-room exit graph (not just anchor
    # chains) - see PHASE0_FINDINGS.md UPDATE 12 addendum #2. Every assignment below was
    # independently re-verified (not just trusted from the matching pass): each room's real
    # exits (world.py) were checked to exactly match what its text describes, AND to
    # reciprocate the neighboring room's exit back to it. This resolves the gravel path from
    # the bridge fork all the way to Scarbloom's gates, Potidan's hut, the lake/fishing
    # village, Skeeve the wizard's forest/garden/house, the cave troll, and a large chunk of
    # Scarbloom itself (market, alleys, a shop, the forum, palace portal, temple, and a
    # forge) - all one connected, fully reciprocal chain from room 29 onward.
    30: 491,  # gravel path east of the bridge fork - reached 29-E->30 (reciprocal, room30's only
              # exits are E->40, W->29).
    31: 498,  # serpentine path descending into a valley, lake glimpsed below - reached 30-E->40? no:
              # reached via 29's chain continuing E; room31's real exits {SE:32, NW:29} reciprocate
              # room29's SE->31 exactly.
    32: 505,  # "Fischerdorf" (deserted fishing village) - reached 31-SE->32 (reciprocal). Text:
              # "Wir stehen in einem kleinen, ausgestorbenen Fischerdorf, dessen Hütten
              # halbkreisförmig um den See angelegt sind."
    33: 530,  # (direct handler lookup) the alley from the fishing village out to the lake shore -
              # room33's real exits {N:32, NE:34} match. Previously wrongly assigned to room "36"
              # (the actual boathouse, see below).
    34: 533,  # lakeside "Dorfplatz" with the tavern - room34's 4-way exits {E:36, SE:35, SW:33,
              # W:32} match a plaza connecting the boat dock (36/35), the village hub (33), and
              # the entry alley (32) exactly.
    35: 539,  # (direct handler lookup) the tavern "Zum singenden Barben" (the fishing village's
              # inn, innkeeper Berta) - room35's only exit NW->34 reciprocates the plaza's SE->35.
              # Previously this room's slot mistakenly held message 567 (the boathouse, see room
              # 36 below) - a brand-new room resolved by this correction pass, not previously in
              # ROOM_LOOK_MESSAGE at all.
    36: 567,  # (direct handler lookup) "Bootsschuppen" (boathouse) - room36's only exit W->34
              # reciprocates the plaza's E->36. Previously this content was wrongly assigned to
              # room "35" (the tavern is actually there, see above).
    37: 600,  # (direct handler lookup) "auf dem See" (out on the lake, rowing toward/away from the
              # Tuatara creature) - room37/38/39 are all zero-compass-exit special-action rooms
              # (entered/left via a "rudere"/row verb, not movement - matching the walkthrough's
              # "Dreimal durch das Wasser rudern") representing different rowing states; all three
              # share this same base "Wir sind auf dem See..." text, with the specific
              # Tuatara-encounter narration varying by state (not fully disambiguated here - see
              # PHASE0_FINDINGS.md).
    38: 600,  # (direct handler lookup) "auf dem See", another rowing state - see room 37 above.
    39: 600,  # (direct handler lookup) "auf dem See", another rowing state (closest to the
              # Tuatara - its own text mentions the creature swimming right alongside the boat) -
              # see room 37 above.
    40: 665,  # gravel path, dense dark forest E/W - room40's real exits are exactly {E:41, W:30},
              # matching the text's explicit "nach Westen und nach Osten" framing.
    41: 672,  # gravel path, forest ends, start of a huge moonlit plain (a cliff-edge/rope-climb
              # scene) - room41's real exits {NE:42, S:100, W:40}; S is the climb-down action to
              # the plain below (room 100).
    42: 685,  # meadow path bend, SW/NE - room42's real exits {NE:43, E:55, SW:41} match the
              # text's explicit "nach Südwesten und nach Nordosten" framing; E leads into
              # Skeeve's forest (below).
    43: 695,  # meadow path, Scarbloom's walls first sighted, comes from SW - room43's real exits
              # {N:44, SW:42, NW:48} match.
    44: 697,  # approach path, walls closer, N/S only - room44's real exits are exactly
              # {N:45, S:43}, matching the text's "von Süden her weiter nach Norden" framing.
    45: 738,  # Scarbloom's city gates (two guards) - room45's real exits {N:70, E:47, S:44,
              # W:46} match the text's described directions exactly; N is the gate itself.
    46: 1508, # dusty plain: Scarbloom's walls visible E, a small hut visible W - room46's real
              # exits are exactly {E:45, W:48}, matching "im Osten...Stadtmauern...im
              # Westen...eine kleine Hütte" precisely.
    47: 1523, # mountain ridge/pass, Scarbloom's walls visible back W - room47's real exits
              # {N:999 (edge-of-map sentinel), W:45} match "im Westen...Stadtmauern von
              # Scarbloom".
    48: 1500, # dusty path to Potidan the healer's hut - room48's real exits {N:27, E:46,
              # W:105} match "zwischen zwei ausgedehnten Ebenen im Osten und Westen"; N is the
              # hut's door.
    27: 1510, # Potidan's hut, interior (a reclusive healer, the "Mondscheinkraut"/moonlight-herb
              # fetch quest) - room27's only exit S->48 reciprocates the hut's own door.
    28: 1531, # (direct handler lookup) a mountain valley (source of the "Mondscheinkraut" Potidan
              # wants) - room28 has ZERO compass exits (a special-action-only room, entered via
              # the "Klettere durch Durchgang" climb action per the walkthrough, matching its own
              # text: "Deutlich ist im Westen der Durchgang im Berg zu sehen, durch den wir
              # hierher gefunden haben"). Previously this content was wrongly assigned to room
              # "62" (Skeeve's actual bedroom, see below).
    53: 1101, # (direct handler lookup) Skeeve's ancient forest, ambient sound description -
              # room53's real exits {N:50, NE:51, E:60, SE:56, S:55} match; E leads to Skeeve's
              # garden gate. Previously this room's slot held message 1076 (which really belongs
              # to room 50, one hop north).
    54: 1093, # (direct handler lookup) Skeeve's ancient forest, generic stretch (see room 51/52/
              # 56/57 below for the same shared "dense ancient forest" text, byte-identical across
              # several structurally-equivalent filler rooms in this cluster) - room54's real
              # exits {N:52, S:57, SW:56, NW:51} match. Previously this room's slot held the
              # garden-gate approach text, which really belongs to room 60 below.
    55: 1080, # forest, a fenced magical house glimpsed beyond the trees - room55's real exits
              # {N:53, E:56, W:42} reciprocate meadow-room 42's E->55 exactly.
    56: 1093, # (direct handler lookup) Skeeve's ancient forest, same generic text as room 54/57
              # (see above) - room56's real exits {NE:54, E:57, W:55, NW:53} match. Previously
              # this room's slot held the garden text, which really belongs to room 60 below.
    57: 1093, # (direct handler lookup) Skeeve's ancient forest, same generic text as room 54/56 -
              # room57's real exits {N:54, W:56} match. Previously this room's slot held Skeeve's
              # living-room text, which really belongs to room 61 below.
    60: 1105, # (direct handler lookup) Skeeve the wizard's garden (herb beds, a gravel path to
              # the door) - room60's real exits {E:61, W:53} match "Kiesweg...zur Eingangstür des
              # Hauses im Osten" (E->61) exactly. Previously this room's slot held the cave-troll
              # entrance text, which really belongs to room 64 below.
    61: 1131, # (direct handler lookup) Skeeve's living room (bookshelves, a magic-user's study) -
              # room61's real exits {E:62, S:63, W:60} match; W reciprocates the garden's E->61,
              # E leads to his bedroom, S to his laboratory. Previously this room's slot held the
              # troll's-lair text, which really belongs to room 65 below.
    62: 1158, # (direct handler lookup) Skeeve's bedroom - room62's only exit W->61 reciprocates
              # the living room's E->62. Resolves a previously-unsolved gap (this room's content
              # was known to exist from disassembly notes but had no confirmed room number until
              # this correction pass).
    63: 1166, # (direct handler lookup) Skeeve's laboratory ("Hier also betreibt Skeeve seine
              # Forschungen! Das Laboratorium ist wirklich tausendmal besser, als das von Mygra") -
              # room63's only exit N->61 reciprocates the living room's S->63. Resolves the other
              # previously-unsolved gap in this cluster.
    64: 1590, # (direct handler lookup) a cave entrance guarded by a cave troll - room64's real
              # exits {N:65, S:13} match (S reciprocates the confirmed hill-country room 13's own
              # N exit). Previously this content was wrongly assigned to room "60" (Skeeve's
              # actual garden, see above).
    65: 1599, # (direct handler lookup) the troll's own lair, inside the cave - room65's only exit
              # S->64 reciprocates the cave entrance's N->65. Previously this content was wrongly
              # assigned to room "61" (Skeeve's actual living room, see above).
    70: 776,  # "Marktplatz von Scarbloom" (the city marketplace) - room70's real exits
              # {N:74, E:71, S:45, W:83} match; S reciprocates the gate room's (45) N->70.
    71: 802,  # alley east of the market, forking to a dead end and a tavern - room71's real
              # exits {N:73, E:72, W:70} match the text's described branches.
    74: 841,  # north end of "the Forum" - a shop visible west - room74's real exits {N:76,
              # S:70, W:75} match; S reciprocates the market's N->74.
    75: 847,  # a small shop (a merchant offering goods) - room75's only exit E->74 reciprocates
              # 74's W->75.
    76: 892,  # a street crossing, an alley branching east - room76's real exits {N:79, E:77,
              # S:74} match; S reciprocates 74's N->76.
    77: 903,  # a dead-end alley before a large moonlit house - room77's real exits {E:78,
              # W:76} match; W reciprocates 76's E->77.
    79: 939,  # Scarbloom's main street bending west - room79's real exits {S:76, W:80} match;
              # S reciprocates 76's N->79.
    80: 950,  # the main street narrowing into small alleys - room80's real exits {N:81,
              # E:79} match; E reciprocates 79's W->80.
    81: 958,  # the palace portal (two guards) - room81's real exits {N:90, E:82, S:80} match;
              # S reciprocates 80's N->81; E leads to the temple.
    82: 970,  # a small temple (hooded priests around an altar) - room82's only exit W->81
              # reciprocates 81's E->82.
    83: 984,  # a dark alley along the city wall, back toward the market/gate - room83's real
              # exits {E:70, NW:84} match; E reciprocates the market's W->83. The text describes
              # a stairway going up "im Nordosten", and room 83's NE exit slot does exist
              # (msg_code 30) but has dest_room 0 - not a bug: the NE slot holds the flavor text
              # for LOOKING that way (the stairs are visible), while the actual walkable
              # connection to room 84 is the separate NW slot, presumably reached via a distinct
              # "climb the stairs" action rather than plain compass movement (same pattern as the
              # well at room 9 and the cliff rope-climb near room 41 - some connections in this
              # game aren't simple 8-way movement).
    84: 993,  # a shabby alley, a poorer quarter of Scarbloom - room84's real exits {N:85,
              # SW:83} match; SW reciprocates 83's NW->84.
    85: 998,  # a small square/courtyard behind the shabby houses - room85's real exits {N:88,
              # E:87, S:84, W:86} match; S reciprocates 84's N->85.
    86: 1014, # Nichidor's forge (a dark hall, a large fire) - room86's only exit E->85
              # reciprocates 85's W->86.
    88: 1048, # Gultiba's bedroom - the room's standing "look" text once inside ("Wir stehen in
              # Gultibas Schlafzimmer..."), shown on every visit after the first. The FIRST
              # visit's own scripted scene (message 1047 - "Ehebruch nennt man das glaube
              # ich!", catching Gultiba's wife and another man together) is a separate,
              # one-time event - see ROOM_FIRST_VISIT_MESSAGE below, same split as room 4's
              # own entry (UPDATE 79/87). Originally resolved via a genuine TOOL bug fix, not a
              # scanner artifact: this room's handler sits in a different overlay segment than
              # its next-by-address neighbor (room 100, already in the following segment), so
              # bounding message extraction purely by "next handler's address" read straight
              # through unmapped inter-segment padding, threw inside idc.GetManyBytes, and got
              # silently swallowed into an empty message list - room 88 looked like a handler
              # with no text at all (see tools/room_handler_by_address.py's
              # resolve_all_with_messages(), now bounded by min(next handler address, this
              # segment's own end)). Room 88's only real exit S->85 reciprocates confirmed
              # room85's N->88 (the confirmed locked door - see game.py's KEY_OBJECT_CODE/
              # UNLOCK_GATE_OBJECT/GULTIBA_BEDROOM_* constants).

    # --- third batch: Scarbloom's remaining alleys and mysteries, resolved/corrected by the
    # same direct-handler-lookup method (see the MAJOR CORRECTION note above room 14). 50/51/52
    # (Skeeve's forest) were unaffected by that correction and are unchanged from the earlier
    # bulk pass.
    50: [1095, 1081], # Skeeve's ancient forest, one hop N of confirmed room53 - explicitly
              # repeats room53's own "Pfad ... von Norden nach Süden durch den Wald" phrasing,
              # matching the direct reciprocal exit pair (53's N->50 / 50's S->53) exactly.
    51: 1093, # Skeeve's ancient forest, an unremarkable stretch - the generic "Wir sind nun
              # mitten in einem dichten Wald ... Stimmen der unterschiedlichsten Bewohner" text,
              # found byte-identical across several structurally-equivalent filler rooms in this
              # cluster (50's neighbor text, 54/56/57 above) - a legitimate case of one message
              # reused verbatim, same allowance used for the corridor chains (see module
              # docstring's multi-part note).
    52: 1093, # Skeeve's ancient forest, same generic text as room51 above - room52 dead-ends at
              # the map edge (E:999) with S:54 and W:51 its only real connections.
    72: 817,  # (direct handler lookup) Scarbloom's second tavern/inn (an innkeeper renting
              # rooms) - room72's only exit W->71 reciprocates confirmed room71's E->72. Resolves
              # a previously-unsolved gap (this room's content was known from disassembly notes
              # as "Oerli's inn" but had no confirmed room number). Previously this room's slot
              # wrongly held the generic dead-end-alley text, which really belongs to room 87.
    73: 837,  # (direct handler lookup) a dead-end alley opening onto a small courtyard (voices
              # and slamming doors heard, nobody visible) - room73's only exit S->71 reciprocates
              # confirmed room71's N->73. Previously this room's slot wrongly held message 1027
              # (really room 87's content, a different dead-end alley entirely).
    78: 913,  # (direct handler lookup) the Magiergilde (mages' guild) - room78's only exit
              # W->77 reciprocates confirmed room77's E->78. Resolves a previously-unsolved gap
              # (the mysterious woman/"die Schönheit" and spell-teaching content were known from
              # disassembly notes but had no confirmed room number). Previously this room's slot
              # wrongly held the courtyard-alley text, which really belongs to room 73 above.
    87: 1027, # (direct handler lookup) a dead-end alley abruptly ending at a wall, blank
              # windowless houses looming around it - room87's only exit W->85 reciprocates
              # confirmed room85's E->87. Previously this same content had been mistakenly split
              # across rooms "72"/"73" (which are actually the tavern and courtyard-alley above).

    # --- fourth batch: the FIRST DRAGON's lair (via room 41's cliff-climb) and the SECOND,
    # three-headed dragon's lair (via room 48's plain and a cliff climb) - resolved using a
    # third room-handler overlay segment (0x1dc9, found while investigating why rooms 100-108
    # had no data under the direct-lookup method - see PHASE0_FINDINGS.md's newest addendum).
    # Rooms 89-99 remain genuinely absent from the table-building code itself (not a bug to
    # keep chasing - the compiler simply never wrote those slots).
    100: 1326, # a bare stone plateau at the foot of a cliff - room100's real exits {N:41, NE:101}
               # match (N reciprocates room41's own S->100 cliff-climb). Text: "Wir stehen auf
               # einem Plateau...In unserem Rücken erhebt sich thronend die Felswand".
    101: 1340, # a cave entrance in the rock face, tracks leading in - room101's real exits
               # {N:102, SW:100} match (SW reciprocates 100's NE->101).
    102: 1349, # inside the cave, a small dim hall - room102's real exits {N:103, S:101} match.
    103: 1363, # deeper in the cave, a collapsed treasure chamber with a dragon's tail visible -
               # room103's real exits {N:104, S:102} match. This is the Tatzelwurm (the walkthrough's
               # "1. Drache") kill scene: cutting the tail, bathing in and drinking its blood,
               # cutting scales (messages 1423-1438) all live in this room's handler.
    104: [1368, 1370], # the Tatzelwurm's treasure hall itself ("Wir kommen in eine große
               # Halle...Der gesamte Boden ist mit Goldstücken...") - room104's only exit S->103
               # reciprocates. Message 1369 (a companion's-reaction interjection, "als mich %s am
               # Arm zurückhält") is skipped - it has an unsubstituted "%s" party-member-name
               # placeholder and reads as an event/reaction line, not part of the base room
               # description (same pattern as room 1's excluded message 99) - message 1370 (the
               # dragon's full reveal) picks up the description directly afterward.
    105: 1383, # a sunlit plain - room105's real exits {E:48, NW:106} match; text: "Im Osten kann
               # ich die Hütte des Heilers erkennen" (Potidan's hut, visible east, matching E->48)
               # "und im Nordwesten erhebt sich...eine hohe Felsklippe" (matching NW->106).
    106: 1394, # the foot of a sheer cliff, farmers with a cow (a fourth-wall joke about "die Kuh
               # vom Lindwurm" a couple messages later) - room106's real exits {N:107, SE:105}
               # match; SE reciprocates 105's NW->106.
    107: 1402, # partway up the cliff's switchback path - room107's real exits {N:108, S:106}
               # match.
    108: 1406, # near the top of the cliff, ruins of an old keep - room108's only real exit
               # S->107 reciprocates (its N exit target, room 109, is the edge-of-map/game-ending
               # sentinel - see world.py). This is the SECOND dragon's lair: a three-headed
               # dragon ("der dritte Kopf des Drachen") in a ruined castle, matching the
               # walkthrough's "2. Drache" boss fight.
}


# FIRST-VISIT scripted scenes - shown once, the first time a room is
# entered, instead of the room's normal look text (ROOM_LOOK_MESSAGE
# above). Confirmed via a user-supplied real DOSBox screenshot (entering
# Forolls Schmiede for the first time) matched byte-for-byte against
# messages 123-124 in decompressed STORY - see PHASE0_FINDINGS.md's
# newest addendum. Distinct from ROOM_LOOK_MESSAGE's room 3 entry (126),
# which is the STANDING text shown on every later visit.
ROOM_FIRST_VISIT_MESSAGE: dict[int, int | list] = {
    # "Aszhantis Elternhaus" (room 1) - UPDATE 89, the ORIGINAL flagged
    # gap this whole dict started from (see ROOM_LOOK_MESSAGE's own
    # comment on room 1). Confirmed via direct disassembly (flat
    # 0x147bd) that this room's shape is DIFFERENT from every other
    # entry here: the base description (93-98, same narrator-dependent
    # structure as ROOM_LOOK_MESSAGE[1]) is printed UNCONDITIONALLY,
    # THEN message 99 (Sklar/Phira's breakfast-table scene) is
    # APPENDED - not swapped in - the first time only. Duplicating the
    # base structure here (rather than changing first_visit_text()'s
    # own "replace, don't append" semantics, which room 3/4/88 all
    # correctly rely on) keeps every other entry's behavior unchanged.
    1: [(93, 94), 95, (96, 97), 98, 99],
    3: [123, 124],  # door creaks open (123) + Foroll's full greeting,
                    # ending in the exact confirmed line "'Tja, habts er
                    # denn auch Geld? Macht genau 7 Gerfs.'" - the
                    # hardcoded, scripted price for the starting
                    # dagger+sword bundle (see GameState.buy_starter_weapons,
                    # game.py - NOT part of the generic item_stats.py shop
                    # table, confirmed absent from WORLD Section 1 for
                    # "Dolch" specifically).

    # "Beim Scharlatan" (room 4) - confirmed via `room_handler_by_address.py`
    # (the `laas` analysis project's confirmed room-dispatch-table lookup,
    # PHASE0_FINDINGS.md UPDATE 13): running it directly against room 4
    # returns its handler's REAL message references in disassembly order -
    # 135, 137, 136, 138, 139, 155, ... - confirming 135-138 are part of
    # THIS room's own handler (not a separate room; see ROOM_LOOK_MESSAGE's
    # entry for 4 below), sitting immediately before the already-known
    # base look message (139), matching the exact same "first-visit scene
    # precedes the base description" shape as room 3's entry above. Two
    # user-supplied DOSBox screenshots of a first-ever visit (entering
    # from the Dorfplatz, paginated across a "(Taste)" prompt) matched
    # messages 135 (entry narration) + 138 (Mygra's monologue) byte-for-
    # byte, including the exact two closing sentences the port was
    # missing entirely ("Als er seinen Monolog endlich beendet
    # hat...'Ja was wollt ihr denn?'..."). 136/137 is message 138's
    # narrator-dependent greeting clause, same tuple convention as
    # ROOM_LOOK_MESSAGE's room-1 entry: 137 uses third person ("...grüßt
    # ihn Aszhanti...er erwidert...") for Smirga narrating, 136 first
    # person ("...grüße ich ihn...") for Aszhanti - `(137, 136)` =
    # (smirga_message, aszhanti_message).
    4: [135, (137, 136), 138],

    # Gultiba's bedroom (room 88) - confirmed via `room_handler_by_
    # address.py` (PHASE0_FINDINGS.md UPDATE 87), the exact same
    # "leading messages precede the already-known base look message"
    # shape as room 4's own entry above, and one of UPDATE 79's own
    # flagged-but-unconfirmed candidate rooms - now confirmed. Message
    # 1047 is the full "walk in on Gultiba's wife and her lover" scene,
    # word-for-word ending in "'Ehebruch nennt man das glaube ich!'" -
    # shown once, replaced by the room's plain standing text (1048,
    # ROOM_LOOK_MESSAGE) on every later visit. No narrator branch found
    # in the handler for this one, unlike room 4's greeting clause.
    88: 1047,
}


# UNCONFIRMED CANDIDATES for more rooms with the same "unwired leading
# first-visit messages" shape as room 4 above (PHASE0_FINDINGS.md UPDATE
# 79) - found by running `room_handler_by_address.py`'s full pipeline
# across every room in ROOM_LOOK_MESSAGE and checking for real message
# indices (below 2360, STORY's own total message count - anything at or
# above that is a confirmed noise value from the tool's own addressing
# quirk) referenced BEFORE each room's already-known base look message.
# Deliberately NOT wired in: a single room handler often mixes LOOK text
# with other verbs' hardcoded responses in one compiled function, so an
# earlier-appearing message reference doesn't reliably mean "first-visit
# event" without a real screenshot to confirm against. Rooms:
# 2, 7, 8, 10, 20, 21, 25, 27, 32, 41, 50, 55, 61, 63, 64, 65, 77, 79,
# 103, 106 - re-run the tool against any of these and match the result
# against real gameplay text before wiring one in. (1 and 88 were on
# this list too - UPDATE 87/89 confirmed and wired both in, see
# ROOM_FIRST_VISIT_MESSAGE above.)


def _resolve_message_items(entry, narrator: Character) -> list[int]:
    """Shared by `look_text()`/`first_visit_text()`: normalize a
    ROOM_LOOK_MESSAGE/ROOM_FIRST_VISIT_MESSAGE entry (a bare int, a list,
    or a list mixing plain ints with (smirga_msg, aszhanti_msg) narrator
    tuples) into a flat list of concrete message indices for `narrator`."""
    items = entry if isinstance(entry, list) else [entry]
    indices = []
    for item in items:
        if isinstance(item, tuple):
            smirga_msg, aszhanti_msg = item
            indices.append(smirga_msg if narrator == Character.SMIRGA else aszhanti_msg)
        else:
            indices.append(item)
    return indices


def first_visit_text(story, room_number: int, narrator: Character = DEFAULT_NARRATOR) -> str | None:
    """Full concatenated FIRST-VISIT text for `room_number`, or None if
    this room has no confirmed scripted first-visit scene. `narrator`
    selects the active party member for any narrator-dependent clause
    (see room 4's entry above), same convention as `look_text()`."""
    entry = ROOM_FIRST_VISIT_MESSAGE.get(room_number)
    if entry is None:
        return None
    indices = _resolve_message_items(entry, narrator)
    return " ".join(story.message(i) for i in indices)


def look_text(story, room_number: int, narrator: Character = DEFAULT_NARRATOR) -> str | None:
    """Full concatenated "look" text for `room_number`, or None if not
    yet mapped. `story` is a story.Story instance. `narrator` selects
    the active party member for any narrator-dependent clause (see
    characters.py) - defaults to Aszhanti."""
    entry = ROOM_LOOK_MESSAGE.get(room_number)
    if entry is None:
        return None
    indices = _resolve_message_items(entry, narrator)
    # Adjacent messages split mid-sentence at a word boundary with no
    # space baked into either fragment (e.g. message 94 ends "...einem",
    # message 95 starts "kleinen...") - join with a space, not directly.
    return " ".join(story.message(i) for i in indices)
