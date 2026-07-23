"""
story.py - decompresses STORY and resolves its text, two different ways.

STORY.DAT-style compression (LAAS.EXE's `sub_1FCE5`) is a bit-accumulator/
prefix-code scheme with a 256-byte symbol table and a 40-byte ring buffer
seeded from the tail of the source stream, writing output backward (high to
low address). Ported and verified against the real game's machine code
(executed under the Unicorn CPU emulator) during reverse engineering -
see the `laas` analysis project's `tools/picture_decoder.py` and
`tools/unicorn_ground_truth.py` for the full derivation and proof.

Once decompressed, STORY is a stream of *indices* (0-255), not literal
text - each index is looked up in a fragment table built from ITEMS (a
NUL-separated blob of German word/phrase fragments) and concatenated.
This module implements both the decompression and the substitution.

On top of that, individual game messages (combat lines, dialogue, etc.)
are referenced elsewhere in the original binary as pointers into a
*second* structure: a table of NUL-delimited message boundaries within
the decompressed STORY blob, built at the real game's startup by
`sub_36DF` (a blob splitter) and read out here as `messages()`.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

RING_BASE = 0x51F
RING_SIZE = 0x28  # 40


def _bswap16(w: int) -> int:
    return ((w & 0xFF) << 8) | (w >> 8)


def _read_delta32(data: bytes, pos: int) -> int:
    w0 = _bswap16(data[pos] | (data[pos + 1] << 8))
    w1 = _bswap16(data[pos + 2] | (data[pos + 3] << 8))
    val = (w0 << 16) | w1
    if val & 0x80000000:
        val -= 0x100000000
    return val


def _shift_pair(hi: int, lo: int, cl: int) -> tuple[int, int]:
    if cl == 0:
        return hi, lo
    hi_signed = hi - 0x10000 if (hi & 0x8000) else hi
    if cl < 16:
        new_lo = ((lo >> cl) | ((hi << (16 - cl)) & 0xFFFF)) & 0xFFFF
        new_hi = (hi_signed >> cl) & 0xFFFF
        return new_hi, new_lo
    cl2 = cl - 16
    new_lo = (hi_signed >> cl2) & 0xFFFF
    new_hi = 0xFFFF if (hi & 0x8000) else 0x0000
    return new_hi, new_lo


class _Ring:
    def __init__(self, seed_40_bytes: bytes):
        assert len(seed_40_bytes) == RING_SIZE
        self.mem = bytearray(seed_40_bytes)
        self.si = RING_BASE + RING_SIZE

    def wrap_if_needed(self):
        if self.si <= RING_BASE:
            self.si = RING_BASE + RING_SIZE

    def word_at(self, addr: int) -> int:
        i = addr - RING_BASE
        return self.mem[i] | (self.mem[i + 1] << 8)

    def word_set(self, addr: int, value: int):
        i = addr - RING_BASE
        self.mem[i] = value & 0xFF
        self.mem[i + 1] = (value >> 8) & 0xFF


def decompress(data: bytes, header_pos: int = 0) -> bytes:
    """Decompress one selector-0 chunk starting at `header_pos`. `data`
    must have enough bytes before `header_pos` to seed the ring/symtab
    (governed by the chunk's own internal deltaA). STORY's own leading
    byte (a chunk-continuation/type flag - always 0 for STORY, see the
    game's own loader) must not be included in the delta computation;
    callers should zero it first, matching what the real loader does
    before invoking the decompressor."""
    deltaA = _read_delta32(data, header_pos)
    deltaB = _read_delta32(data, header_pos + 4)

    p_a = header_pos + deltaA
    out_end = header_pos + deltaB
    out_bound = header_pos

    symtab_start = p_a - 256
    symtab = bytearray(data[symtab_start:p_a])

    ring_start = symtab_start - RING_SIZE
    ring = _Ring(data[ring_start:symtab_start])

    src_pos = ring_start

    out = bytearray(data)
    if out_end + 2 >= len(out):
        out.extend(b'\x00' * (out_end - len(out) + 3))

    def src_pull_word_raw():
        nonlocal src_pos
        src_pos -= 2
        return data[src_pos] | (data[src_pos + 1] << 8)

    ring.si -= 2
    w = ring.word_at(ring.si)
    out_pos = out_end - 2
    out[out_pos] = w & 0xFF
    out[out_pos + 1] = (w >> 8) & 0xFF
    ring.word_set(ring.si, src_pull_word_raw())

    ring.si -= 4
    addr_hi = ring.si
    addr_lo = ring.si + 2
    hi = _bswap16(ring.word_at(addr_hi))
    lo = _bswap16(ring.word_at(addr_lo))
    ring.word_set(addr_lo, src_pull_word_raw())
    ring.word_set(addr_hi, src_pull_word_raw())

    avail = 16

    def refill_and_shift_in():
        ring.si -= 2
        addr = ring.si
        w = _bswap16(ring.word_at(addr))
        ring.word_set(addr, src_pull_word_raw())
        ring.wrap_if_needed()
        return w

    def consume(dx):
        nonlocal hi, lo, avail
        if avail > dx:
            hi, lo = _shift_pair(hi, lo, dx)
            avail -= dx
            return
        old_avail = avail
        hi, lo = _shift_pair(hi, lo, old_avail)
        new_word = refill_and_shift_in()
        hi = new_word
        avail = 16
        deficit = dx - old_avail
        hi, lo = _shift_pair(hi, lo, deficit)
        avail -= deficit

    def consume_escape_first_stage():
        nonlocal hi, lo, avail, src_pos
        dx = 0xB
        if avail > dx:
            hi, lo = _shift_pair(hi, lo, dx)
            avail -= dx
            return
        old_avail = avail
        hi, lo = _shift_pair(hi, lo, old_avail)
        ring.si -= 2
        addr = ring.si
        w = _bswap16(ring.word_at(addr))
        src_pos -= 1
        ring.word_set(addr, data[src_pos] | (data[src_pos + 1] << 8))
        ring.wrap_if_needed()
        hi = w
        avail = 16
        deficit = dx - old_avail
        hi, lo = _shift_pair(hi, lo, deficit)
        avail -= deficit

    while True:
        cur = lo
        if (cur & 1) == 0:
            idx = (cur >> 1) & 3
            val = symtab[0 + idx]
            dx = 3
        elif (cur & 2) == 0:
            idx = (cur >> 2) & 7
            val = symtab[4 + idx]
            dx = 5
        elif (cur & 4) == 0:
            idx = (cur >> 3) & 0x1F
            val = symtab[0xC + idx]
            dx = 8
        elif (cur & 8) == 0:
            idx = (cur >> 4) & 0x3F
            val = symtab[0x2C + idx]
            dx = 0xA
        else:
            peek7 = (cur >> 4) & 0x7F
            if peek7 < 0x7E:
                idx = peek7
                val = symtab[0x6C + idx]
                dx = 0xB
            elif peek7 & 1:
                low16 = cur & 0xFFFF
                rotated = ((low16 << 5) | (low16 >> (16 - 5))) & 0xFFFF
                idx = rotated & 0x1F
                val = symtab[0xE0 + idx]
                dx = 0x10
            else:
                consume_escape_first_stage()
                val = lo & 0xFF
                dx = 0xA

        consume(dx)

        out_pos -= 1
        out[out_pos] = val

        if out_pos <= out_bound:
            break

    return bytes(out[out_pos:out_end])


def load_fragment_table(items_path: Path) -> list[bytes]:
    """ITEMS' layout: an 8-byte header (two 32-bit sizes) followed by a
    NUL-separated blob of fragments; table[i] = the i-th fragment."""
    data = items_path.read_bytes()
    blob = data[8:]
    return blob.split(b'\x00')


def substitute_fragments(byte_stream: bytes, table: list[bytes]) -> bytes:
    """Every byte in decompressed STORY is an index into `table` (built
    from ITEMS) - replace and concatenate. Index 0 -> table[0], which is
    the empty string (a natural no-op/terminator)."""
    out = bytearray()
    for b in byte_stream:
        if b < len(table):
            out.extend(table[b])
        else:
            out.append(b)
    return bytes(out)


@dataclass
class Story:
    """Loads STORY+ITEMS once and exposes both text-resolution schemes
    used throughout the original game."""

    decoded: bytes           # decompressed STORY, index-byte stream
    fragment_table: list[bytes]
    _messages: list[bytes]   # decoded.split(b'\\x00') - see messages()

    MESSAGE_TABLE_DSEG_BASE = 0x855E  # sub_36DF's output array base, for reference

    @classmethod
    def load(cls, assets_dir: Path) -> "Story":
        story_path = assets_dir / "STORY"
        items_path = assets_dir / "ITEMS"
        raw = bytearray(story_path.read_bytes())
        raw[0] = 0  # the leading chunk-type/continuation byte; see decompress()
        decoded = decompress(bytes(raw), 0)
        fragment_table = load_fragment_table(items_path)
        messages = decoded.split(b"\x00")
        return cls(decoded=decoded, fragment_table=fragment_table, _messages=messages)

    def text(self, raw_bytes: bytes) -> str:
        """Substitute a raw index-byte run into real text (cp850).

        The original game hard-wraps prose at a fixed column width using
        bare `\\r` (0x0D, CR) bytes as the line-break - not `\\r\\n`, and
        with no space on either side (the CR itself is the only
        separator between the last word of one line and the first word
        of the next). Left as literal `\\r` here it just overwrites
        rather than visibly breaking lines on most modern terminals, so
        it's normalized to `\\n` for display."""
        substituted = substitute_fragments(raw_bytes, self.fragment_table)
        decoded = substituted.decode("cp850", errors="replace")
        return decoded.replace("\r", "\n")

    def message(self, index: int) -> str:
        """Resolve message #`index` from the NUL-delimited message
        table (matches `sub_36DF`'s splitting of decompressed STORY -
        see module docstring). This is what most in-game event/combat/
        dialogue strings use."""
        return self.text(self._messages[index])

    def message_count(self) -> int:
        return len(self._messages)

    def raw_span(self, start: int, end: int) -> str:
        """Resolve a message addressed by raw byte offsets directly
        into decompressed STORY (NOT NUL-delimited) - this is the
        addressing scheme object base descriptions use (see
        objects.py); `start`/`end` are byte offsets, `end` exclusive."""
        return self.text(self.decoded[start:end])
