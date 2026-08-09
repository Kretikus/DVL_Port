"""
Regression tests for pictures.py - the LAASPIC/Pn decoder (UPDATE 71).

These decode the REAL shipped asset files (assets/LAASPIC/P1..P22), the
same way the confirmed disassembly-derived algorithm was cross-checked
against Unicorn ground truth during development - see pictures.py's own
module docstring for the full derivation.
"""
import pytest

from laas_port.game import DEFAULT_ASSETS_DIR
from laas_port import pictures


@pytest.mark.parametrize("number", range(1, pictures.PICTURE_COUNT + 1))
def test_every_picture_decodes_to_a_full_frame(number):
    rgb = pictures.decode_picture_rgb(DEFAULT_ASSETS_DIR, number)
    assert len(rgb) == 320 * 200 * 3


def test_decoding_is_deterministic():
    first = pictures.decode_picture_rgb(DEFAULT_ASSETS_DIR, 1)
    second = pictures.decode_picture_rgb(DEFAULT_ASSETS_DIR, 1)
    assert first == second


def test_different_pictures_decode_to_different_content():
    p1 = pictures.decode_picture_rgb(DEFAULT_ASSETS_DIR, 1)
    p2 = pictures.decode_picture_rgb(DEFAULT_ASSETS_DIR, 2)
    assert p1 != p2


def test_out_of_range_picture_number_is_rejected():
    with pytest.raises(ValueError):
        pictures.decode_picture_rgb(DEFAULT_ASSETS_DIR, 0)
    with pytest.raises(ValueError):
        pictures.decode_picture_rgb(DEFAULT_ASSETS_DIR, 23)


def test_picture_to_ppm_wraps_a_valid_header():
    rgb = pictures.decode_picture_rgb(DEFAULT_ASSETS_DIR, 1)
    ppm = pictures.picture_to_ppm(rgb)
    assert ppm.startswith(b"P6\n320 200\n255\n")
    assert len(ppm) == len(b"P6\n320 200\n255\n") + len(rgb)


def test_picture_palette_has_sixteen_entries():
    header = (0).to_bytes(32, "little")
    palette = pictures.picture_palette(header)
    assert len(palette) == 16


def test_every_picture_has_its_own_distinct_palette():
    # UPDATE 73: each LAASPIC file carries its own 16-color palette in
    # its own 32-byte header - there's no single shared palette.
    palettes = []
    for n in range(1, pictures.PICTURE_COUNT + 1):
        path = DEFAULT_ASSETS_DIR / "LAASPIC" / f"P{n}"
        with open(path, "rb") as f:
            header = f.read(32)
        palettes.append(tuple(pictures.picture_palette(header)))
    assert len(set(palettes)) > 1


def test_ega_register_conversion_only_produces_the_four_standard_dac_levels():
    header = bytes(range(32))  # arbitrary, real-looking bytes
    palette = pictures.picture_palette(header)
    valid_levels = {0x00, 0x55, 0xAA, 0xFF}
    for r, g, b in palette:
        assert r in valid_levels
        assert g in valid_levels
        assert b in valid_levels


def test_header_word_zero_is_black():
    assert pictures._header_word_to_ega_register(0x0000) == 0
    assert pictures._ega_register_to_rgb(0) == (0, 0, 0)


def test_header_word_full_levels_gives_white():
    # nibble value 7 -> //2 == 3 -> both primary+secondary bits set,
    # for all three channels (bits 0-3 red, 12-15 green, 8-11 blue).
    word = 0x7 | (0x7 << 8) | (0x7 << 12)
    register = pictures._header_word_to_ega_register(word)
    assert pictures._ega_register_to_rgb(register) == (255, 255, 255)
