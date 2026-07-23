"""
Regression tests for objects.py - the 250-entry object description
table, notably its offset-boundary logic (a real bug this session).
"""


def test_object_boundaries_are_ranked_by_offset_not_by_code(objects, story):
    """Regression test: an earlier version used code+1's text_offset as
    the slicing boundary, which is wrong because offsets are sorted by
    VALUE, not by object code - a lower-numbered object can sit at a
    higher text offset than its neighbor. This silently produced
    garbled, mid-word text (caught via a real example: "staubte Gl").
    Confirm boundaries are still computed via the offset-sorted rank."""
    by_offset = sorted(objects.descriptors, key=lambda d: d.text_offset)
    for i, d in enumerate(by_offset):
        expected_next = by_offset[i + 1].text_offset if i + 1 < len(by_offset) else None
        assert objects._next_offset_by_code[d.code] == expected_next


def test_object_35_examine_text_is_a_fragment_not_a_word(objects, story):
    """Object 35's own span doesn't contain a clean word ("Tisch") - this
    is why names.py doesn't (and shouldn't) map any name to it. See
    names.py's CAUTION note. Locks in the known text so a future change
    to the offset logic doesn't silently "fix" this into something else
    without that being a deliberate, understood change."""
    assert objects.describe(35, story).strip() == "Mitte des Raum"


def test_describe_out_of_range_is_safe(objects, story):
    assert objects.describe(-1, story) == "(unknown object)"
    assert objects.describe(9999, story) == "(unknown object)"


# --- indefinite article (sub_4698/sub_7B9F port) ---


def test_article_by_obj_type(objects, story):
    """obj_type 1/2 get their own article word (einen/eine); confirmed via
    dseg_resolver.py against sub_7B9F's real string table - see
    objects.py's module docstring for the flat addresses."""
    assert objects.describe(0, story).startswith("einen ")  # obj_type 1
    assert objects.describe(1, story).startswith("eine ")   # obj_type 2


def test_article_defaults_to_ein_for_unmapped_type(objects, story):
    d = objects.descriptors[6]
    assert d.obj_type == 3
    assert objects.describe(6, story).startswith("ein ")


def test_article_empty_for_type_4_without_override(objects, story):
    d = objects.descriptors[38]
    assert d.obj_type == 4
    assert (d.handler_selector >> 8) != 0x18 and (d.handler_selector & 0xFF) != 0x13
    text = objects.describe(38, story)
    assert not text.startswith(("ein ", "eine ", "einen "))


def test_article_empty_when_handler_selector_overrides(objects, story):
    """Object 35's handler_selector high byte is 0x18 - sub_4698 forces an
    empty article regardless of obj_type, confirmed via laas.asm's sub_77C8
    disassembly. This is why object 35 reads as a bare fragment, not
    evidence the fragment problem is fixed."""
    d = objects.descriptors[35]
    assert (d.handler_selector >> 8) == 0x18
    assert objects.describe(35, story).strip() == "Mitte des Raum"
