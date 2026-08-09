"""
pictures.py - decodes the 22 LAASPIC/Pn illustration files (the real DOS
game's "Entf"/Delete-key picture viewer, confirmed via its "What Picture ?"
debug prompt - PHASE0_FINDINGS.md UPDATE 71) - INCLUDING each picture's
own real, per-picture EGA palette (UPDATE 73).

Each file is: a 32-byte pre-header, then a chain of 1-2 compressed chunks
using the SAME two algorithms already confirmed for STORY/ATTIC.DAT/
TITEL.VGA:

  - type 2 (`sub_1FCE5`, already ported in the `laas` analysis project's
    tools/picture_decoder.py): a symbol-table/ring-buffer LZ scheme.
  - type 1 (`sub_1F97F`, newly traced this session): a simpler
    control-byte RLE/copy-through scheme the analysis project had
    previously (wrongly) assumed was unused by any real file - 6 of the
    22 LAASPIC files use it as their ONLY chunk, and all 16 others use it
    as chunk 2 (chunk 2's own header is self-referentially embedded in
    chunk 1's decoded output - see `_decode_chunks` below).

Both algorithms were validated BYTE-FOR-BYTE against the real x86 machine
code (extracted from LAAS.EXE, run under the Unicorn CPU emulator) for
all 22 real files before being ported here - see the `laas` analysis
project's PHASE0_FINDINGS.md UPDATE 71 for the full derivation and cross-
check methodology.

**Confirmed real pixel format**: 4-plane EGA, 320x200, 40 bytes/row/plane
(32000 bytes total) - NOT the VGA chunky mode TITEL.VGA uses. Confirmed
via row-to-row smoothness autocorrelation (period 40 = 320px/8) and by
visually matching a real screenshot pixel-for-pixel in composition.

**The palette - now the REAL one, not a calibration (UPDATE 73)**:
UPDATE 71 shipped an empirically-calibrated single shared 16-color
palette (the disassembly's own confirmed VGA DAC palette, used for
TITEL's splash screens, doesn't match these pictures at all). That was
always going to be wrong in a specific, structural way a user caught
directly (one real color rendering as a completely different one): each
LAASPIC file has its OWN 16-color palette, not a shared one, so no
single global LUT could ever fit all 22 pictures.

Traced this session: `sub_42d7` (the shared loader, UPDATE 71) calls
`sub_4365(header_ptr)` right after decoding, which for the EGA path (the
confirmed real format) forwards straight to `sub_4167` - and THAT
function reads the picture's own 32-byte pre-header as 16 words (one per
palette index) and derives a 6-bit EGA hardware palette register value
from each: bits 0-3 of the word select the RED level, bits 12-15 select
GREEN, bits 8-11 select BLUE (bits 4-7 are read but never used) - each
nibble integer-divided by 2 and only the results 1/2/3 doing anything
(-> secondary-only / primary-only / both-bits-set; 0 and 4-7 all mean
"channel off"). The resulting 6-bit value is a standard IBM EGA palette
register index (bit layout secR,secG,secB,R,G,B), converted to RGB via
the well-documented, fixed EGA DAC formula (each bit contributes 0x55,
so a channel is 0x00/0x55/0xAA/0xFF depending on its primary+secondary
bits) - not a LAAS-specific table, standard EGA hardware behavior.
Confirmed correct by re-rendering against the user's own screenshots:
colors now match (sky blue, grass green, wood brown) picture after
picture, including the specific color the user flagged as wrong under
the old shared-palette approach.
"""
from __future__ import annotations

import struct

from pathlib import Path

RING_SIZE = 0x28

# --- type 2 (sub_1FCE5) - word-granularity ring + symbol table ---
# Ported verbatim from the `laas` analysis project's
# tools/picture_decoder.py (CONFIRMED CORRECT there via Unicorn ground
# truth against real STORY/ATTIC.DAT/TITEL.VGA bytes).

_RING2_BASE = 0x51F


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


class _Ring2:
    def __init__(self, seed_40_bytes: bytes):
        self.mem = bytearray(seed_40_bytes)
        self.si = _RING2_BASE + RING_SIZE

    def wrap_if_needed(self) -> None:
        if self.si <= _RING2_BASE:
            self.si = _RING2_BASE + RING_SIZE

    def word_at(self, addr: int) -> int:
        i = addr - _RING2_BASE
        return self.mem[i] | (self.mem[i + 1] << 8)

    def word_set(self, addr: int, value: int) -> None:
        i = addr - _RING2_BASE
        self.mem[i] = value & 0xFF
        self.mem[i + 1] = (value >> 8) & 0xFF


def _decompress_type2(data: bytes, header_pos: int) -> bytes:
    deltaA = _read_delta32(data, header_pos)
    deltaB = _read_delta32(data, header_pos + 4)

    p_a = header_pos + deltaA
    out_end = header_pos + deltaB
    out_bound = header_pos

    symtab_start = p_a - 256
    symtab = bytearray(data[symtab_start:p_a])

    ring_start = symtab_start - RING_SIZE
    ring = _Ring2(data[ring_start:symtab_start])

    src_pos = ring_start

    out = bytearray(data)
    if out_end + 2 >= len(out):
        out.extend(b"\x00" * (out_end - len(out) + 3))

    def src_pull_word_raw() -> int:
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

    def refill_and_shift_in() -> int:
        ring.si -= 2
        addr = ring.si
        w = _bswap16(ring.word_at(addr))
        ring.word_set(addr, src_pull_word_raw())
        ring.wrap_if_needed()
        return w

    def consume(dx: int) -> None:
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

    def consume_escape_first_stage() -> None:
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


# --- type 1 (sub_1F97F) - byte-granularity ring, control-byte RLE/copy ---
# Newly traced this session (PHASE0_FINDINGS.md UPDATE 71) - previously
# assumed unused by any real file, but 22/22 LAASPIC files use it (6 as
# their only chunk, 16 as chunk 2). Validated byte-for-byte against
# Unicorn ground truth for all 6 single-chunk files and all 16 two-chunk
# files (as chunk 2) before being ported here.


class _Ring1:
    def __init__(self, seed_40_bytes: bytes):
        self.mem = bytearray(seed_40_bytes)
        self.si = _RING2_BASE + RING_SIZE

    def wrap_if_needed(self) -> None:
        if self.si <= _RING2_BASE:
            self.si = _RING2_BASE + RING_SIZE

    def byte_at(self, addr: int) -> int:
        return self.mem[addr - _RING2_BASE]

    def byte_set(self, addr: int, value: int) -> None:
        self.mem[addr - _RING2_BASE] = value & 0xFF


def _decompress_type1(data: bytes, header_pos: int) -> tuple[bytes, tuple[int, bytes]]:
    """Returns (decoded_image_bytes, (trailer_pos, trailer_bytes)).

    The trailer write is sub_1F97F's own tail: it copies its 12 raw
    header bytes (header_pos+0xc..+0x17) back over header_pos+0..+0xb.
    That falls entirely OUTSIDE [out_pos, out_end) - real-mode in-place-
    decode memory bookkeeping, not image content - but for a 2-chunk
    file it's exactly what leaves chunk 2's own header (embedded in
    chunk 1's decoded output) reading back as 0x00 afterward, which is
    what tells the outer chunk loop to stop. Callers chaining multiple
    chunks must apply it; callers treating this as the only/last chunk
    can ignore it."""
    deltaA = _read_delta32(data, header_pos)
    deltaB = _read_delta32(data, header_pos + 4)
    word8 = _bswap16(data[header_pos + 8] | (data[header_pos + 9] << 8))
    if word8 != 0:
        # Confirmed real but never triggered by any of the 22 shipped
        # LAASPIC files (all have word8==0) - a stride-based XOR delta
        # pass between two regions of the output, sub_1F97F's own
        # 0x1fb5a-0x1fb98. Not implemented since nothing exercises it.
        raise NotImplementedError("type-1 XOR delta stage not implemented (unused by any real LAASPIC file)")

    p_a = header_pos + deltaA
    out_end = header_pos + deltaB
    out_bound = header_pos + 0xC

    ring_start = p_a - RING_SIZE
    ring = _Ring1(data[ring_start:p_a])
    src_pos = ring_start

    out = bytearray(data)
    if out_end + 2 >= len(out):
        out.extend(b"\x00" * (out_end - len(out) + 3))

    def src_pull_byte() -> int:
        nonlocal src_pos
        src_pos -= 1
        return data[src_pos]

    out_pos = out_end

    def emit(val: int) -> None:
        nonlocal out_pos
        out_pos -= 1
        out[out_pos] = val

    def ring_pull_and_refill() -> int:
        ring.si -= 1
        val = ring.byte_at(ring.si)
        ring.byte_set(ring.si, src_pull_byte())
        ring.wrap_if_needed()
        return val

    while True:
        ring.si -= 1
        control = ring.byte_at(ring.si)
        ring.byte_set(ring.si, src_pull_byte())
        ring.wrap_if_needed()

        if control & 0x80 == 0:
            if control != 0:
                for bit in (6, 5, 4, 3, 2, 1, 0):
                    if control & (1 << bit):
                        emit(ring_pull_and_refill())
                    else:
                        emit(0)
            else:
                literal_val = ring_pull_and_refill()
                count = ring_pull_and_refill() + 7
                for _ in range(count):
                    emit(literal_val)
        else:
            count = (control & 0x3F) + 7
            if control & 0x40:
                for _ in range(count):
                    emit(ring_pull_and_refill())
            else:
                for _ in range(count):
                    emit(0)

        if out_pos <= out_bound:
            break

    trailer = bytes(data[header_pos + 0xC:header_pos + 0x18])
    return bytes(out[out_pos:out_end]), (header_pos, trailer)


def _decode_chunks(raw_after_preheader: bytes) -> bytes:
    """Port of sub_20048's outer loop: reads a type byte at a FIXED
    position (re-read fresh each iteration, never advanced - confirmed
    from the real disassembly, not assumed), dispatches by type, and
    loops while the top bit was set. Real files here are either a
    single type-1 chunk, or type-2 then type-1 - chunk 2's own header is
    self-referentially embedded in chunk 1's decoded output, landing
    exactly at the same fixed position sub_20048 re-reads from."""
    buf = bytearray(raw_after_preheader)
    buf.extend(b"\x00" * 40000)  # decompression expands well past the file's own length
    pos = 0
    for _ in range(8):  # generous bound - real files use 1-2 chunks
        type_byte = buf[pos]
        if type_byte == 0:
            break
        top_bit = type_byte & 0x80
        chunk_type = type_byte & 0x7F
        buf[pos] = 0
        data = bytes(buf)
        if chunk_type == 1:
            out, (trailer_pos, trailer) = _decompress_type1(data, pos)
        elif 2 <= chunk_type <= 4:
            out = _decompress_type2(data, pos)
            trailer_pos = trailer = None
        else:
            raise ValueError(f"unknown LAASPIC chunk type {chunk_type} at {pos}")
        out_end = pos + _read_delta32(data, pos + 4)
        out_pos = out_end - len(out)
        buf[out_pos:out_end] = out
        if trailer is not None:
            buf[trailer_pos:trailer_pos + len(trailer)] = trailer
        if not top_bit:
            break
    else:
        raise RuntimeError("LAASPIC chunk chain did not terminate")
    return bytes(buf[:32000])


# --- 4-plane EGA -> chunky pixel conversion (confirmed 320x200,
# 40 bytes/row/plane - see this module's own docstring) ---

_WIDTH = 320
_HEIGHT = 200
_BYTES_PER_ROW = 40
_PLANE_SIZE = _BYTES_PER_ROW * _HEIGHT


def _planes_to_indices(decoded: bytes) -> bytearray:
    planes = [decoded[p * _PLANE_SIZE:(p + 1) * _PLANE_SIZE] for p in range(4)]
    pixels = bytearray(_WIDTH * _HEIGHT)
    for row in range(_HEIGHT):
        row_off = row * _BYTES_PER_ROW
        for bytecol in range(_BYTES_PER_ROW):
            b = [planes[p][row_off + bytecol] for p in range(4)]
            base_x = bytecol * 8
            for bit in range(8):
                mask = 0x80 >> bit
                val = 0
                for p in range(4):
                    if b[p] & mask:
                        val |= 1 << p
                pixels[row * _WIDTH + base_x + bit] = val
    return pixels


# --- the real per-picture EGA palette (sub_4167, see this module's own
# docstring for the full derivation) ---


def _header_word_to_ega_register(word: int) -> int:
    """One palette index's raw header word -> a 6-bit EGA hardware
    palette register value (bit layout: secR,secG,secB,R,G,B, standard
    IBM EGA order). Confirmed real algorithm (flat 0x4175-0x4245):
    bits 0-3 of the word -> RED, bits 12-15 -> GREEN, bits 8-11 -> BLUE
    (bits 4-7 are read by nothing - genuinely unused); each nibble is
    integer-divided by 2 and only 1/2/3 do anything (secondary-only /
    primary-only / both bits set - 0 and 4-7 all mean "channel off")."""
    red_level = (word & 0xF) // 2
    blue_level = ((word >> 8) & 0xF) // 2
    green_level = ((word >> 12) & 0xF) // 2

    register = 0
    if red_level == 1:
        register |= 0x20
    elif red_level == 2:
        register |= 0x04
    elif red_level == 3:
        register |= 0x24
    if green_level == 1:
        register |= 0x10
    elif green_level == 2:
        register |= 0x02
    elif green_level == 3:
        register |= 0x12
    if blue_level == 1:
        register |= 0x08
    elif blue_level == 2:
        register |= 0x01
    elif blue_level == 3:
        register |= 0x09
    return register


def _ega_register_to_rgb(register: int) -> tuple[int, int, int]:
    """Standard IBM EGA DAC conversion (not LAAS-specific) - each of
    the 6 bits contributes 0x55 to its channel, so every channel lands
    on 0x00/0x55/0xAA/0xFF depending on its primary+secondary bits."""
    r = ((register >> 2) & 1) * 0xAA + ((register >> 5) & 1) * 0x55
    g = ((register >> 1) & 1) * 0xAA + ((register >> 4) & 1) * 0x55
    b = ((register >> 0) & 1) * 0xAA + ((register >> 3) & 1) * 0x55
    return (r, g, b)


def picture_palette(header: bytes) -> list[tuple[int, int, int]]:
    """The confirmed real 16-color palette for one LAASPIC file, derived
    from its own 32-byte pre-header (16 little-endian words, one per
    palette index) - every picture has its OWN palette, not a shared
    one."""
    words = struct.unpack("<16H", header[:32])
    return [_ega_register_to_rgb(_header_word_to_ega_register(w)) for w in words]


PICTURE_COUNT = 22


def decode_picture_rgb(assets_dir: Path, number: int) -> bytes:
    """Decodes LAASPIC/P<number> and returns raw 320x200 RGB bytes
    (row-major, 3 bytes/pixel) - the real pixel data AND the real
    per-picture palette, both decoded fresh from the original
    compressed file every call."""
    if not 1 <= number <= PICTURE_COUNT:
        raise ValueError(f"picture number must be 1-{PICTURE_COUNT}, got {number}")
    path = Path(assets_dir) / "LAASPIC" / f"P{number}"
    raw = path.read_bytes()
    palette = picture_palette(raw[:32])
    decoded = _decode_chunks(raw[0x20:])
    indices = _planes_to_indices(decoded)
    rgb = bytearray(_WIDTH * _HEIGHT * 3)
    for i, idx in enumerate(indices):
        r, g, b = palette[idx]
        o = i * 3
        rgb[o] = r
        rgb[o + 1] = g
        rgb[o + 2] = b
    return bytes(rgb)


def picture_to_ppm(rgb: bytes, width: int = _WIDTH, height: int = _HEIGHT) -> bytes:
    """Wraps raw RGB bytes as a binary PPM (P6) image - tkinter's
    PhotoImage reads this natively, so no image library dependency is
    needed just to display a picture."""
    header = f"P6\n{width} {height}\n255\n".encode("ascii")
    return header + rgb


def show_picture(assets_dir: Path, number: int) -> None:
    """Opens a small Tk window showing LAASPIC/P<number>, closable by
    the player (window close button, Escape, or any key)."""
    import tkinter as tk

    rgb = decode_picture_rgb(assets_dir, number)
    ppm = picture_to_ppm(rgb)

    root = tk.Tk()
    root.title(f"Bild {number}")
    image = tk.PhotoImage(data=ppm)
    # integer-only zoom keeps pixel art crisp; 2x matches the roughly
    # 640x400 window size real DOSBox captures of this game show it at
    image = image.zoom(2, 2)
    label = tk.Label(root, image=image, borderwidth=0)
    label.image = image  # keep a reference alive
    label.pack()
    root.bind("<Escape>", lambda _event: root.destroy())
    root.bind("<Key>", lambda _event: root.destroy())
    root.focus_force()
    root.mainloop()
