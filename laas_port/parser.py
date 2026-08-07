"""
parser.py - a verb/noun command parser, now with a real port of the
original's comma-chaining behavior on top of a still-simplified
per-command parser.

`parse()` (single command) is NOT a port of the original's real
per-command grammar (that part is still a simple first-verb-then-rest
splitter). But `parse_chain()` IS a real port of the confirmed
chaining/tokenizing layer around it - see the `laas` analysis
project's PHASE0_FINDINGS.md "The parser: found, and it changes the
plan" section for the full derivation:

    sub_5882 (line-editor) -> sub_142C1 (line buffer) -> sub_1405C
    (tokenizer: inserts spaces around `,`/`.`/`?`/`"` so punctuation
    becomes its own token) -> sub_52A0 (abbreviation-expand, then
    dispatch) -> sub_14202 (splits chained commands on commas - e.g.
    "nimm schwert, öffne tür" - and sets an "explain" flag when the
    input ends in `?`)

Ported here: comma-splitting into multiple sequential commands, and
the trailing-`?` "explain" flag (exposed on `Command.explain` - what
the original actually DOES with this flag isn't documented precisely
enough to reproduce yet, so it's parsed but not acted on). NOT ported:
`sub_14354`'s abbreviation-expansion (not documented in enough detail
to reproduce faithfully - the existing VERB_ALIASES short forms like
"n"/"i"/"x" are this port's own stand-in, not a reconstruction of that
specific mechanism), and mid-sentence `.`/`"` tokenizing (only the
comma-chain-separator and trailing-`?` behaviors are confirmed clearly
enough to port; a bare `?` alone is still the HELP verb, unchanged).
"""
from __future__ import annotations

from dataclasses import dataclass

DIRECTION_WORDS = {
    "n": "N", "norden": "N", "nord": "N",
    "s": "S", "sueden": "S", "süden": "S", "sued": "S", "süd": "S",
    "e": "E", "o": "E", "osten": "E", "ost": "E",
    "w": "W", "westen": "W", "west": "W",
    "ne": "NE", "nordosten": "NE", "nordost": "NE",
    "se": "SE", "suedosten": "SE", "südosten": "SE", "suedost": "SE", "südost": "SE",
    "sw": "SW", "suedwesten": "SW", "südwesten": "SW", "suedwest": "SW", "südwest": "SW",
    "nw": "NW", "nordwesten": "NW", "nordwest": "NW",
}

VERB_ALIASES = {
    "look": "LOOK", "schau": "LOOK", "schaue": "LOOK", "l": "LOOK", "umsehen": "LOOK",
    "examine": "EXAMINE", "untersuche": "EXAMINE", "betrachte": "EXAMINE", "x": "EXAMINE",
    "take": "TAKE", "nimm": "TAKE", "nehme": "TAKE", "g": "TAKE",
    "drop": "DROP", "lege": "DROP", "leg": "DROP", "wirf": "DROP",
    "inventory": "INVENTORY", "inventar": "INVENTORY", "i": "INVENTORY",
    "quit": "QUIT", "ende": "QUIT", "exit": "QUIT",
    "gehe": "GO", "geh": "GO", "go": "GO",
    "open": "OPEN", "oeffne": "OPEN", "öffne": "OPEN",
    "close": "CLOSE", "schliesse": "CLOSE", "schließe": "CLOSE",
    "lock": "LOCK", "verschliesse": "LOCK", "verschließe": "LOCK", "schliesseab": "LOCK",
    "unlock": "UNLOCK", "aufschliessen": "UNLOCK",
    "save": "SAVE", "speichere": "SAVE", "speichern": "SAVE", "sichern": "SAVE",
    "load": "LOAD", "lade": "LOAD", "laden": "LOAD",
    "buy": "BUY", "kaufe": "BUY", "kaufen": "BUY",
    "sell": "SELL", "verkaufe": "SELL", "verkaufen": "SELL",
    # "zustand" matches the original's own STATUS menu item name (STORY
    # message 1456, "Zustandsübersicht.") - see levels.py/game.py.status().
    "zustand": "STATUS", "status": "STATUS",
    # ANLEGEN - the real, confirmed armor-equip verb (sub_133BE - see
    # PHASE0_FINDINGS.md UPDATE 23's follow-up / game.py's equip()).
    "equip": "EQUIP", "anlege": "EQUIP", "anlegen": "EQUIP", "ausruesten": "EQUIP",
    # PORT UTILITY verb spelling: the real typed trigger word for combat
    # (verb code 0x24 in sub_9F20's dispatch - see PHASE0_FINDINGS.md
    # UPDATE 24) was never identified, only the ambush/scripted trigger
    # path was. These are reasonable German choices, not a confirmed
    # in-game command - see combat.py/game.py.attack().
    "attack": "ATTACK", "attackiere": "ATTACK", "greife": "ATTACK", "kaempfe": "ATTACK",
    "flee": "FLEE", "fliehen": "FLEE", "flieh": "FLEE",
    # GIB - confirmed real verb (reference/walkthrough_de.txt: "Den
    # Skarabäus gibt man in Hyllok Mygra..." - see PHASE0_FINDINGS.md
    # UPDATE 45 / game.py's give()). "gib X Y" - noun is the whole
    # "<item> <recipient>" text; give() splits it itself.
    "give": "GIVE", "gib": "GIVE", "gebe": "GIVE",
    # SCHLAFEN - confirmed real verb (sub_10792 - see PHASE0_FINDINGS.md
    # UPDATE 50 / game.py's sleep()).
    "sleep": "SLEEP", "schlafe": "SLEEP", "schlaf": "SLEEP", "schlafen": "SLEEP",
    "uebernachte": "SLEEP", "übernachte": "SLEEP",
    # PORT UTILITY, not a reconstructed original verb - see characters.py's
    # docstring and game.py's CHARACTER handling: no evidence of an in-game
    # character-switch command was found in the disassembly (word_b722 is
    # set somewhere the analysis project hasn't traced), so this exists
    # only so a player/tester can view both narrator text variants.
    "character": "CHARACTER", "charakter": "CHARACTER", "wechsel": "CHARACTER",
    "help": "HELP", "hilfe": "HELP", "?": "HELP",
}

# "verschließe"/"schließe" are ambiguous with LOCK/CLOSE in German depending on
# what follows ("schließe ... auf" = unlock, "schließe ... ab" = lock, bare
# "schließe" = close) - handled specially in parse() below rather than via
# the plain alias table above.

INSTRUMENT_WORDS = {"mit", "with"}


@dataclass
class Command:
    verb: str               # canonical verb id, e.g. "TAKE", "GO", or a bare direction like "N"
    noun: str | None         # raw noun text as typed, or None
    instrument: str | None = None  # text after "mit"/"with", for verbs like LOCK/UNLOCK
    explain: bool = False    # set by parse_chain() when the whole input ended in "?"
                             # (sub_14202's confirmed behavior) - parsed but not acted on
                             # yet, see module docstring


def _split_instrument(words: list[str]) -> tuple[list[str], str | None]:
    for i, w in enumerate(words):
        if w in INSTRUMENT_WORDS:
            return words[:i], (" ".join(words[i + 1:]) or None)
    return words, None


def parse(raw: str) -> Command | None:
    words = raw.strip().lower().split()
    if not words:
        return None
    first = words[0]

    # bare direction, e.g. "n" or "norden"
    if first in DIRECTION_WORDS:
        return Command(verb=DIRECTION_WORDS[first], noun=None)

    # "schließe X auf" (unlock) / "schließe X ab" (lock) / "schließe X" (close)
    if first in ("schliesse", "schließe", "verschliesse", "verschließe"):
        # Split off "mit <instrument>" BEFORE checking for a trailing
        # "auf"/"ab" - otherwise "schließe X auf mit Y" looks at "Y" as
        # the last word instead of "auf", and silently falls through to
        # CLOSE (a real bug caught by tests/test_parser.py).
        rest_words, instrument = _split_instrument(words[1:])
        if rest_words and rest_words[-1] == "auf":
            rest_words = rest_words[:-1]
            verb = "UNLOCK"
        elif rest_words and rest_words[-1] == "ab":
            rest_words = rest_words[:-1]
            verb = "LOCK"
        else:
            verb = "LOCK" if first.startswith("ver") else "CLOSE"
        rest = " ".join(rest_words) or None
        return Command(verb=verb, noun=rest, instrument=instrument)

    verb = VERB_ALIASES.get(first)
    rest_words, instrument = _split_instrument(words[1:])
    rest = " ".join(rest_words) if rest_words else None

    if verb == "GO" and rest:
        direction_word = rest.strip().lower()
        if direction_word in DIRECTION_WORDS:
            return Command(verb=DIRECTION_WORDS[direction_word], noun=None)
        return Command(verb="GO", noun=rest)

    if verb is None:
        return Command(verb="UNKNOWN", noun=raw)

    return Command(verb=verb, noun=rest, instrument=instrument)


def parse_chain(raw: str) -> list[Command]:
    """Real port of sub_14202's chaining behavior: splits comma-
    separated chained commands (e.g. "nimm schwert, öffne tür") into a
    list of Commands, each parsed independently via parse() above. A
    trailing "?" on the WHOLE input (not part of any individual
    segment) sets `explain=True` on every resulting Command - matching
    sub_14202's confirmed behavior of gating this on the raw input's
    last character, before chain-splitting. A bare "?" (no other
    content) is left alone and still parses as the HELP verb via the
    plain alias table, not consumed as an explain-flag with zero
    commands."""
    raw = raw.strip()
    if not raw:
        return []
    explain = False
    if raw != "?" and raw.endswith("?"):
        explain = True
        raw = raw[:-1].strip()
    commands = []
    for segment in raw.split(","):
        segment = segment.strip()
        if not segment:
            continue
        cmd = parse(segment)
        if cmd is not None:
            cmd.explain = explain
            commands.append(cmd)
    return commands
