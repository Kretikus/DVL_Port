"""
Regression tests for story.py - STORY decompression, message-table
splitting, and ITEMS fragment substitution.
"""


def test_message_61_is_the_village_square(story):
    """message 61 - the very first ground-truth anchor this whole
    project's room-text mapping was built from (exact text match against
    a real DOSBox screenshot of the game's starting room)."""
    text = story.message(61)
    assert "Dorfplatz von Hyllok" in text


def test_message_text_uses_newlines_not_bare_cr():
    """Regression test: Story.text() used to return bare \\r (0x0D)
    line-wrap characters, which don't reliably render as line breaks on
    real terminals. Fixed by replacing \\r with \\n."""
    from laas_port.story import Story
    from laas_port.game import DEFAULT_ASSETS_DIR

    s = Story.load(DEFAULT_ASSETS_DIR)
    # message 95 (part of room 1's description) is known to contain a
    # mid-sentence line wrap in the original encoding.
    text = s.message(95)
    assert "\r" not in text


def test_message_count_is_positive(story):
    assert story.message_count() > 2000
