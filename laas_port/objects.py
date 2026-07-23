"""
objects.py - the 250-entry object/description table (RESTORE's
"descriptions" chunk, offset 0x1280, size 0x2EE0 = 250 x 48 bytes).

Record layout (see the `laas` analysis project's PHASE0_FINDINGS.md,
"UPDATE 5", for the full derivation):

    +0x00  u16  handler/category selector (not yet mapped to real
                behavior - clusters around a handful of values)
    +0x02  u8   object type (1-4; not yet mapped to real category names)
    +0x03  u8   constant 0xFF across all 250 records (padding/flag)
    +0x04  u16  always 0 in the shipped save (unused here, or only
                populated for objects with contents - unconfirmed)
    +0x06  u16  text offset - see below
    +0x08  u16  text "segment" - in the original 16-bit binary this
                pointed into whatever farheap segment the decompressed
                STORY buffer landed in at runtime (constant across all
                250 records); here we only have one flat `Story.decoded`
                buffer, so this field is ignored - `+0x06`'s offset is
                used directly as an index into it.
    +0x0A+     variable per-object data. TESTED AND NOT CONFIRMED as a
                general "container contents list": object 3's tail
                happens to decode as 17 clean ascending object codes
                (all <=97, several matching the confirmed shared-scene
                object range 33-39), but other objects' tails mix in
                suspiciously round values (32768/8192/4096/...) matching
                the known "high bit = room-instance flag" convention,
                which doesn't fit a contents-list schema. See
                PHASE0_FINDINGS.md's newest UPDATE for the full negative
                result (map.json's own per-object `content` field is
                also empty everywhere, so there's no independent
                fan-authored confirmation either) - not implementing a
                container/PUT mechanic on this basis.

The `+0x06` offsets are monotonically increasing and 250-way distinct
across the table (by *offset*, not by object code - object N's span
neighbor in the text is usually NOT object N+1), so object i's text is
`decoded_STORY[offset[i]:next_offset]` where `next_offset` is the
smallest offset greater than `offset[i]` across the WHOLE table.

CAVEAT discovered while building this port (not yet resolved - see
PHASE0_FINDINGS.md for anything newer): concatenating a run of
consecutive-by-offset entries does reconstruct grammatically perfect,
flowing German prose (confirmed during reverse engineering, e.g. a
complete wizard's-study scene description) - but that means many
INDIVIDUAL objects' own spans are tiny sub-sentence fragments (a few
bytes, sometimes splitting mid-word), not self-contained descriptions.
Some other objects DO get a complete, well-formed sentence in one span
(e.g. object descriptions for major portable items). It looks like the
original game may concatenate several objects' fragments together
(possibly all "scenery" objects present in one room, in offset order)
to build one combined description, rather than showing each object's
raw span in isolation - but the real assembly rule hasn't been traced
yet. `ObjectTable.describe()` below returns the raw per-object span
as-is; callers should not assume it's always a complete sentence.

UPDATE - the generic EXAMINE handler is real and now understood at the
instruction level: `sub_4698`/flat `0x77C8` (see PHASE0_FINDINGS.md for
the full derivation) ALWAYS builds its output from two pieces - an
indefinite article selected by `sub_7B9F` (flat `0x7B9F`) from this
record's `+0x02` `obj_type` byte, and this record's own `+0x06`/`+0x08`
text span (unchanged, still the same raw span `describe()` always
returned). So the raw span genuinely IS the original's intended
per-object text, at least by the original's own design - the "tiny
fragment" problem above is real but is a separate, still-open question
about how that raw span's *end* boundary works, not evidence the span
itself is meaningless.

`sub_7B9F`'s article table was resolved directly from dseg (via
tools/dseg_resolver.py): obj_type 1 -> "einen" (flat 0x20554), 2 ->
"eine" (flat 0x20566), anything else (3, or unlisted) -> "ein" (flat
0x2057c, IDA's `aEin`), 4 -> "" (flat 0x203ca, an empty string - almost
certainly a plural/mass-noun class that takes no indefinite article).
Separately, `sub_4698` OVERRIDES this to the same empty string whenever
`handler_selector`'s high byte is `0x18` or low byte is `0x13`
(confirmed: object 35's handler_selector is `0x1809` - high byte
`0x18` - which is exactly why its raw span "Mitte des Raum" reads oddly
in isolation: the original shows it with NO article at all, not
"ein(e/en) Mitte des Raum"). `_indefinite_article()` below ports this
exactly. The surrounding fixed sentence template (`sub_4698` also
pushes a fixed message pair, dseg globals `word_28902`/`word_28904`) is
NOT resolved - both are `dw 0` in the static image with no `mov`
instruction writing to them anywhere in the disassembly, meaning
they're patched at EXE load time via DOS's relocation table, which
static analysis of `laas.asm` alone can't recover. Not chasing this
further per this project's norm of not fabricating unconfirmed detail;
the port simply prepends "<article> " to the raw span instead of
reproducing the exact original sentence.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path

from .story import Story

RECORD_SIZE = 48
RECORD_COUNT = 250
CHUNK_OFFSET = 0x1280
CHUNK_SIZE = 0x2EE0

# sub_7B9F's article table (flat addresses resolved via dseg_resolver.py -
# see this module's docstring). obj_type values not listed here (i.e. 3,
# or any other unmapped value) fall through to sub_7B9F's own default,
# "ein" (flat 0x2057c / IDA's aEin).
_INDEFINITE_ARTICLE_BY_TYPE = {
    1: "einen",  # flat 0x20554
    2: "eine",   # flat 0x20566
    4: "",       # flat 0x203ca - empty string; no article (plural/mass noun)
}
_DEFAULT_INDEFINITE_ARTICLE = "ein"


def _indefinite_article(obj_type: int, handler_selector: int) -> str:
    """Port of sub_4698's article selection (see module docstring): normally
    sub_7B9F(obj_type), but sub_4698 overrides to an empty string whenever
    handler_selector's high byte is 0x18 or low byte is 0x13 - confirmed via
    laas.asm's sub_77C8 disassembly (cmp byte ptr [si+1], 18h / cmp byte ptr
    [si], 13h, both branching to the same empty-string case)."""
    if (handler_selector >> 8) == 0x18 or (handler_selector & 0xFF) == 0x13:
        return ""
    return _INDEFINITE_ARTICLE_BY_TYPE.get(obj_type, _DEFAULT_INDEFINITE_ARTICLE)


@dataclass
class ObjectDescriptor:
    code: int
    handler_selector: int
    obj_type: int
    text_offset: int
    tail: bytes  # bytes from +0x0A onward, not yet decoded

    def describe(self, story: Story, next_text_offset: int | None) -> str:
        end = next_text_offset if next_text_offset is not None else self.text_offset + 200
        text = story.raw_span(self.text_offset, end)
        article = _indefinite_article(self.obj_type, self.handler_selector)
        return f"{article} {text}".strip() if article else text


@dataclass
class ObjectTable:
    descriptors: list[ObjectDescriptor]
    _next_offset_by_code: dict[int, int | None] = field(default_factory=dict, repr=False)

    @classmethod
    def load(cls, assets_dir: Path) -> "ObjectTable":
        data = (assets_dir / "RESTORE").read_bytes()
        chunk = data[CHUNK_OFFSET : CHUNK_OFFSET + CHUNK_SIZE]
        descriptors = []
        for i in range(RECORD_COUNT):
            rec = chunk[i * RECORD_SIZE : (i + 1) * RECORD_SIZE]
            handler_selector = struct.unpack_from("<H", rec, 0)[0]
            obj_type = rec[2]
            text_offset = struct.unpack_from("<H", rec, 6)[0]
            descriptors.append(
                ObjectDescriptor(
                    code=i,
                    handler_selector=handler_selector,
                    obj_type=obj_type,
                    text_offset=text_offset,
                    tail=rec[10:],
                )
            )

        # Text offsets are monotonically increasing across the table but
        # NOT in step with object code order (a lower object code can sit
        # at a higher text offset than a higher-numbered one) - each
        # object's real span ends where the NEXT HIGHER offset begins,
        # regardless of which object code owns it. Rank by offset once,
        # up front, rather than naively using code+1's offset (which
        # silently mid-word-slices the wrong neighbor's text).
        by_offset = sorted(descriptors, key=lambda d: d.text_offset)
        next_offset_by_code: dict[int, int | None] = {}
        for i, d in enumerate(by_offset):
            nxt = by_offset[i + 1].text_offset if i + 1 < len(by_offset) else None
            next_offset_by_code[d.code] = nxt

        return cls(descriptors=descriptors, _next_offset_by_code=next_offset_by_code)

    def describe(self, code: int, story: Story) -> str:
        if code < 0 or code >= len(self.descriptors):
            return "(unknown object)"
        desc = self.descriptors[code]
        next_offset = self._next_offset_by_code.get(code)
        return desc.describe(story, next_offset)
