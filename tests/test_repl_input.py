"""
Regression tests for repl_input.py - the pre-filled/editable prompt
used by GameState.repl() (see game.py's "combat" section for why:
retyping the same weapon/spell answer every round was tedious), plus
the pynput-based function-key shortcuts (F1-F5) and window-focus-aware
keyboard hook.

IMPORTANT: every test that reaches `_prompt_pynput` MUST mock both
`pynput.keyboard.Listener` (so no real OS-level keyboard hook is ever
installed) and `repl_input._is_prompt_window_foreground` (so the
listener start/stop loop doesn't depend on this machine's actual
window-focus state at test-run time, which is both unrelated to what's
being tested and a real source of flakiness/hangs otherwise).
"""
import sys

import pytest
from pynput import keyboard

from laas_port import repl_input


def _fake_listener_factory(keys):
    """Test double for `pynput.keyboard.Listener`: feeds a scripted key
    sequence synchronously into `on_press` when started, instead of
    installing a real OS-level keyboard hook."""

    class _FakeListener:
        def __init__(self, on_press=None, on_release=None, suppress=False):
            self._on_press = on_press
            self.stopped = False

        def start(self):
            for key in keys:
                self._on_press(key)

        def stop(self):
            self.stopped = True

    return _FakeListener


def _always_foreground(monkeypatch):
    monkeypatch.setattr(repl_input, "_is_prompt_window_foreground", lambda: True)


# --- prompt_with_default() - the outer fallback wrapper ---


def test_empty_default_still_goes_through_pynput_first(monkeypatch):
    """Documents current behavior, not a guess: prompt_with_default()
    always tries _prompt_pynput first regardless of `default` - the
    earlier "empty default skips straight to input()" short-circuit is
    gone now that this port is pynput-only (see the module docstring)."""
    _always_foreground(monkeypatch)
    monkeypatch.setattr("pynput.keyboard.Listener", _fake_listener_factory([keyboard.Key.enter]))
    result = repl_input.prompt_with_default("> ", "")
    assert result == ""


def test_falls_back_to_a_hinted_prompt_when_pynput_fails(monkeypatch):
    """With pynput unavailable/failing (not installed, a missing macOS
    Accessibility permission, no display server, ...), the default is
    still shown - as a bracketed hint the user can retype - rather than
    silently dropped or hanging."""
    def _raise(prompt, default):
        raise OSError("pynput could not install its keyboard hook in this test")

    monkeypatch.setattr(repl_input, "_prompt_pynput", _raise)
    calls = []
    monkeypatch.setattr("builtins.input", lambda prompt="": calls.append(prompt) or "schwert")
    result = repl_input.prompt_with_default("> ", "schwert")
    assert result == "schwert"
    assert calls == ["> [schwert] "]


def test_prompt_with_default_uses_pynput_when_it_succeeds(monkeypatch):
    _always_foreground(monkeypatch)
    monkeypatch.setattr("pynput.keyboard.Listener", _fake_listener_factory([keyboard.Key.enter]))
    result = repl_input.prompt_with_default("> ", "schwert")
    assert result == "schwert"


# --- _redraw() - pure string-building, no I/O to mock ---


def test_redraw_erases_leftover_characters_from_a_longer_previous_buffer(capsys):
    # buffer shrank from "schwert" (7 chars) to "sch" (3 chars) - the
    # leftover "wert" must be blanked out, not left on screen.
    repl_input._redraw("> ", "sch", cursor=3, prev_len=7)
    out = capsys.readouterr().out
    assert out == "\r> sch" + (" " * 4) + ("\b" * 4)  # pad=7-3=4, cursor already at the end


def test_redraw_repositions_cursor_when_not_at_the_end(capsys):
    repl_input._redraw("> ", "schwert", cursor=3, prev_len=7)
    out = capsys.readouterr().out
    assert out == "\r> schwert" + "\b" * 4  # back = 0 pad + (7 - 3) = 4


# --- _prompt_pynput() - line editing ---


def test_pynput_editor_accepts_the_default_on_enter(monkeypatch):
    _always_foreground(monkeypatch)
    monkeypatch.setattr("pynput.keyboard.Listener", _fake_listener_factory([keyboard.Key.enter]))
    result = repl_input._prompt_pynput("> ", "schwert")
    assert result == "schwert"


def test_pynput_editor_supports_backspace_and_appending(monkeypatch):
    _always_foreground(monkeypatch)
    # default "schwert" (cursor starts at the end) -> Backspace x3 removes
    # "ert", leaving "schw" -> type "ild" -> Enter
    keys = [keyboard.Key.backspace] * 3 + [
        keyboard.KeyCode.from_char("i"),
        keyboard.KeyCode.from_char("l"),
        keyboard.KeyCode.from_char("d"),
        keyboard.Key.enter,
    ]
    monkeypatch.setattr("pynput.keyboard.Listener", _fake_listener_factory(keys))
    result = repl_input._prompt_pynput("> ", "schwert")
    assert result == "schwild"


def test_pynput_editor_supports_left_arrow_and_insert(monkeypatch):
    _always_foreground(monkeypatch)
    # default "schwert", Left arrow x4 (cursor before "wert"), insert "X"
    keys = [keyboard.Key.left] * 4 + [keyboard.KeyCode.from_char("X"), keyboard.Key.enter]
    monkeypatch.setattr("pynput.keyboard.Listener", _fake_listener_factory(keys))
    result = repl_input._prompt_pynput("> ", "schwert")
    assert result == "schXwert"


def test_pynput_editor_ctrl_c_raises_keyboard_interrupt(monkeypatch):
    _always_foreground(monkeypatch)
    keys = [keyboard.KeyCode.from_char("\x03")]
    monkeypatch.setattr("pynput.keyboard.Listener", _fake_listener_factory(keys))
    with pytest.raises(KeyboardInterrupt):
        repl_input._prompt_pynput("> ", "schwert")


def test_pynput_editor_ctrl_d_raises_eof(monkeypatch):
    _always_foreground(monkeypatch)
    keys = [keyboard.KeyCode.from_char("\x04")]
    monkeypatch.setattr("pynput.keyboard.Listener", _fake_listener_factory(keys))
    with pytest.raises(EOFError):
        repl_input._prompt_pynput("> ", "schwert")


def test_pynput_editor_ctrl_z_raises_eof(monkeypatch):
    _always_foreground(monkeypatch)
    keys = [keyboard.KeyCode.from_char("\x1a")]
    monkeypatch.setattr("pynput.keyboard.Listener", _fake_listener_factory(keys))
    with pytest.raises(EOFError):
        repl_input._prompt_pynput("> ", "schwert")


# --- _prompt_pynput() - F1-F6 shortcuts and ESC (user-implemented) ---


@pytest.mark.parametrize(
    ("key", "expected_result", "expected_print"),
    [
        (keyboard.Key.f1, "Schau", "Sieh dich um."),
        (keyboard.Key.f2, "Exits", "Exists."),
        (keyboard.Key.f3, "STATUS", "Zustandsübersicht."),
        (keyboard.Key.f4, "Inventar", "Inventar."),
        (keyboard.Key.f5, "Zaubersprüche", "Zaubersprüche."),
        (keyboard.Key.f6, "BILD", "Bild ansehen."),
    ],
)
def test_pynput_function_key_shortcuts(monkeypatch, capsys, key, expected_result, expected_print):
    _always_foreground(monkeypatch)
    monkeypatch.setattr("pynput.keyboard.Listener", _fake_listener_factory([key]))
    result = repl_input._prompt_pynput("> ", "")
    assert result == expected_result
    assert expected_print in capsys.readouterr().out


def test_pynput_esc_exits_the_process(monkeypatch, capsys):
    _always_foreground(monkeypatch)
    monkeypatch.setattr("pynput.keyboard.Listener", _fake_listener_factory([keyboard.Key.esc, keyboard.Key.esc]))
    with pytest.raises(SystemExit) as exc_info:
        repl_input._prompt_pynput("> ", "")
    assert exc_info.value.code == 0
    print(capsys.readouterr().out)
    assert "Spiel wird beendet" in capsys.readouterr().out


def test_pynput_esc_stops_the_listener_before_exiting(monkeypatch):
    """The `finally` block must still run and release the keyboard hook
    even when the process is about to exit - otherwise a real run would
    leave input suppressed system-wide after quitting."""
    _always_foreground(monkeypatch)
    fake_cls = _fake_listener_factory([keyboard.Key.esc, keyboard.Key.esc])
    monkeypatch.setattr("pynput.keyboard.Listener", fake_cls)
    listeners = []
    original_init = fake_cls.__init__

    def tracking_init(self, *a, **kw):
        original_init(self, *a, **kw)
        listeners.append(self)

    fake_cls.__init__ = tracking_init
    with pytest.raises(SystemExit):
        repl_input._prompt_pynput("> ", "")
    assert len(listeners) == 1
    assert listeners[0].stopped is True


# --- _prompt_pynput() - window-focus-aware listener start/stop ---


def test_pynput_waits_for_foreground_before_starting_the_listener(monkeypatch):
    """While the prompt's window isn't in the foreground, no listener
    should be running at all (keystrokes must reach whatever window
    actually IS focused) - it should just poll until focus returns."""
    foreground_calls = {"n": 0}

    def fake_foreground():
        foreground_calls["n"] += 1
        return foreground_calls["n"] > 2  # False, False, then True

    monkeypatch.setattr(repl_input, "_is_prompt_window_foreground", fake_foreground)
    monkeypatch.setattr("time.sleep", lambda s: None)  # don't actually wait in tests
    monkeypatch.setattr("pynput.keyboard.Listener", _fake_listener_factory([keyboard.Key.enter]))
    result = repl_input._prompt_pynput("> ", "schwert")
    assert result == "schwert"
    assert foreground_calls["n"] > 2


def test_pynput_stops_the_listener_when_focus_is_lost_mid_prompt(monkeypatch):
    """If the window loses focus partway through typing, the listener
    (and its global `suppress`) must be released, not left grabbing
    every keystroke system-wide while some other window is focused -
    then re-acquired once focus returns."""
    monkeypatch.setattr("time.sleep", lambda s: None)

    # foreground: True (starts listener #1) -> False (must stop it) ->
    # True (starts listener #2) -> True (stays running)
    foreground_sequence = iter([True, False, True])

    def fake_foreground():
        try:
            return next(foreground_sequence)
        except StopIteration:
            return True

    monkeypatch.setattr(repl_input, "_is_prompt_window_foreground", fake_foreground)

    starts = {"n": 0}
    stopped_first_listener = {"value": False}

    class _TrackingListener:
        def __init__(self, on_press=None, on_release=None, suppress=False):
            self._on_press = on_press
            starts["n"] += 1
            self._is_first = starts["n"] == 1

        def start(self):
            if not self._is_first:
                # the second listener (created after the focus-loss/
                # regain cycle) delivers the actual keypress
                self._on_press(keyboard.Key.enter)

        def stop(self):
            if self._is_first:
                stopped_first_listener["value"] = True

    monkeypatch.setattr("pynput.keyboard.Listener", _TrackingListener)
    result = repl_input._prompt_pynput("> ", "schwert")
    assert result == "schwert"
    assert starts["n"] == 2  # a fresh listener was created after focus returned
    assert stopped_first_listener["value"] is True  # the first one was released on focus loss


# --- get_foreground_window_title() / _is_prompt_window_foreground_impl() ---


def test_get_foreground_window_title_is_empty_off_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    assert repl_input.get_foreground_window_title() == ""


def test_is_prompt_window_foreground_is_always_true_off_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    assert repl_input._is_prompt_window_foreground_impl() is True


def test_is_prompt_window_foreground_fails_open_on_any_error(monkeypatch):
    """Best-effort focus check: any unexpected error (a ctypes call
    failing, pywin32 not installed, ...) must not block input - it
    should behave as if the window IS in the foreground."""
    monkeypatch.setattr(sys, "platform", "win32")

    class _BoomKernel32:
        def GetConsoleWindow(self):
            raise OSError("boom")

    import ctypes
    monkeypatch.setattr(ctypes, "windll", type("W", (), {"kernel32": _BoomKernel32(), "user32": None})())
    assert repl_input._is_prompt_window_foreground_impl() is True


def test_init_repl_input_is_a_noop_off_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    repl_input.starting_window_title = None
    repl_input.init_repl_input()
    assert repl_input.starting_window_title is None
