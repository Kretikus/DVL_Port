"""
repl_input.py - a small "pre-filled, editable" input prompt for the
REPL.

Motivation: the combat interaction re-prompts for a weapon/spell every
round (see game.py's "combat" section), and retyping the same answer
("Schwert") each time is tedious. This shows the previous answer
pre-filled in the input line - press Enter to repeat it verbatim, or
edit it first.

Uses `readline`'s insert-on-startup trick where available (Unix/Mac -
and Windows too, if something like pyreadline3 happens to be
installed), and a small raw-mode line editor built on the third-party
`pynput` library as the cross-platform fallback (Windows/Mac/Linux,
replacing an earlier `msvcrt`-only Windows editor that left every other
platform without one). Falls back further to plain `input()` with the
previous answer shown as a bracketed hint if neither editing method is
usable (e.g. piped/non-interactive input, or `pynput` failing to
install its OS-level hook - missing Accessibility/Input-Monitoring
permission on macOS, no display server on a headless Linux box, etc.)
- so the REPL never simply breaks.
"""
import sys
import time

starting_window_title = None  # type: ignore[assignment]

def init_repl_input() -> None:
    """Initialize the REPL input system. Currently a no-op, but may be
    used in the future to pre-load `pynput` or other resources so the
    first prompt doesn't have to pay that cost."""
    if sys.platform != "win32":
        return
    global starting_window_title
    starting_window_title = get_foreground_window_title()    


def prompt_with_default(prompt: str, default: str) -> str:
    """Prompt for a line of input, pre-filled with `default` (typically
    the last command the player typed) so they can press Enter to
    repeat it or edit it first. Falls back to a plain prompt (with the
    default shown as a hint) if no interactive line-editing is
    available - including when stdin isn't a real terminal at all
    (piped/redirected input): a raw keyboard hook has nothing to attach
    to there and would otherwise block forever waiting for a keypress
    that can never come - confirmed by hand with the old msvcrt editor
    (piping input into the REPL hung indefinitely before this check),
    and `pynput` has the same fundamental issue since it isn't reading
    from stdin at all, but the OS keyboard directly."""
#    if not default:
#        return input(prompt)
#    if not sys.stdin.isatty():
#        return input(f"{prompt}[{default}] ")
#
#    try:
#        return _prompt_readline(prompt, default)
#    except ImportError:
#        pass

    try:
        return _prompt_pynput(prompt, default)
    except Exception:
        # Broad on purpose: pynput's failure modes here aren't just
        # ImportError (not installed) - a missing macOS Accessibility/
        # Input-Monitoring grant, no X11/Wayland input backend on a
        # headless Linux box, etc. all surface as other exception types
        # at listener-start time. Any of them should fall through to
        # the plain prompt below, never crash the REPL.
        pass

    return input(f"{prompt}[{default}] ")


def _prompt_readline(prompt: str, default: str) -> str:
    import readline  # Unix/Mac stdlib; not on stock Windows - caller catches ImportError

    def _insert() -> None:
        readline.insert_text(default)
        readline.redisplay()

    readline.set_startup_hook(_insert)
    try:
        return input(prompt)
    finally:
        readline.set_startup_hook()


def _redraw(prompt: str, text: str, cursor: int, prev_len: int) -> None:
    """Redraw the whole input line using only '\\r' and '\\b' - no ANSI
    escapes needed, so this works in any terminal, including a plain
    Windows console. `prev_len` lets a shorter new buffer erase
    whatever's left over from a longer previous one."""
    
    pad = max(prev_len - len(text), 0)
    sys.stdout.write("\r" + prompt + text + (" " * pad))
    back = pad + (len(text) - cursor)
    if back:
        sys.stdout.write("\b" * back)
    sys.stdout.flush()


def get_foreground_window_title():
    if sys.platform != "win32":
        return ""

    import ctypes
    # Get handle to the foreground window
    hwnd = ctypes.windll.user32.GetForegroundWindow()
    
    # Get the length of the window text
    length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
    
    # Create a buffer and retrieve the text
    buf = ctypes.create_unicode_buffer(length + 1)
    ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
    
    return buf.value

def _is_prompt_window_foreground_impl() -> bool:
    """Best-effort foreground check for the current prompt window.

    On Windows consoles, compares the current foreground window against
    this process' console window handle. If unavailable (non-Windows,
    pseudo terminals, or API errors), return True so input still works.
    """
    if sys.platform != "win32":
        return True

    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        user32 = ctypes.windll.user32
        console_hwnd = kernel32.GetConsoleWindow()
        if not console_hwnd:
            return True
        # Pseudo terminals (e.g. VS Code integrated terminal) may not
        # expose a meaningful visible console window for this process.
        # In that case, skip focus gating entirely.
        if not user32.IsWindowVisible(console_hwnd):
            return True

        foreground_hwnd = user32.GetForegroundWindow()
        if not foreground_hwnd:
            return True

        import win32gui
        # handle windows terminal with multiple tabs, where the foreground window is the tab, not the console window
        if "CASCADIA_HOSTING_WINDOW_CLASS" == win32gui.GetClassName(win32gui.GetForegroundWindow()):
            return starting_window_title == get_foreground_window_title()

        return foreground_hwnd == console_hwnd
    except Exception:
        return True

def _is_prompt_window_foreground() -> bool:
    ret = _is_prompt_window_foreground_impl()
    return ret

def _prompt_pynput(prompt: str, default: str) -> str:
    """Minimal raw-mode line editor built on the third-party `pynput`
    library: printable chars, Backspace/Delete, Left/Right/Home/End.
    Enough to comfortably edit or accept a pre-filled command - not a
    full readline reimplementation.

    `pynput` is a GLOBAL OS keyboard hook, not a per-terminal reader
    like the `msvcrt.getwch()` this replaces - two consequences worth
    knowing:
    - `suppress=True` is required, or the OS's own terminal driver
      would ALSO see and echo every keystroke normally, on top of this
      function's own manual buffer+redraw - doubling every character
      typed. The side effect: while this prompt is active, keystrokes
      are suppressed system-wide (not delivered to any other window),
      for as long as it takes to answer one prompt.
    - It needs OS permission to install that hook: already granted on
      Windows and most Linux setups, but macOS requires the terminal/
      Python process to have Accessibility (and, on newer macOS,
      Input Monitoring) access under System Settings first, or the
      listener raises at start time - caught by `prompt_with_default`'s
      broad `except Exception`, falling back to a plain prompt rather
      than hanging or crashing.

    Key events arrive on a background thread (pynput's own listener
    thread) via `on_press`; funneled through a `queue.Queue` so this
    function can keep reading them one at a time, synchronously, the
    same way `msvcrt.getwch()` used to."""
    import queue

    from pynput import keyboard

    buffer = list(default)
    cursor = len(buffer)
    prev_len = len(buffer)
    sys.stdout.write(prompt + "".join(buffer))
    sys.stdout.flush()

    events: "queue.Queue" = queue.Queue()
    listener = None
    esc_pressed = False

    def _drain_events() -> None:
        while True:
            try:
                events.get_nowait()
            except queue.Empty:
                return

    def _start_listener() -> keyboard.Listener:
        new_listener = keyboard.Listener(on_press=events.put, suppress=True)
        new_listener.start()
        return new_listener

    def _stop_listener(active_listener) -> None:
        if active_listener is None:
            return
        active_listener.stop()
        _drain_events()

    if _is_prompt_window_foreground():
        listener = _start_listener()

    try:
        while True:
            if _is_prompt_window_foreground():
                if listener is None:
                    listener = _start_listener()
            elif listener is not None:
                _stop_listener(listener)
                listener = None

            if listener is None:
                time.sleep(0.05)
                continue

            try:
                key = events.get(timeout=0.1)
            except queue.Empty:
                continue

            if key == keyboard.Key.esc:
                if not esc_pressed:
                    esc_pressed = True
                    print("\nDrücke Esc erneut, um Spiel zu beenden, oder eine andere Taste, um fortzufahren.")
                    continue
                print("Esc erneut gedrückt - Spiel wird beendet.")
                sys.exit(0)
            esc_pressed = True

            if key == keyboard.Key.f1:
                print("Sieh dich um.")
                return "Schau"
            if key == keyboard.Key.f2:
                print("Exists.")
                return "Exits"
            if key == keyboard.Key.f3:
                print("Zustandsübersicht.")
                return "STATUS"
            if key == keyboard.Key.f4:
                print("Inventar.")
                return "Inventar"
            if key == keyboard.Key.f5:
                print("Zaubersprüche.")
                return "Zaubersprüche"
            if key == keyboard.Key.f6:
                print("Bild ansehen.")
                return "BILD"

            if key == keyboard.Key.enter:
                sys.stdout.write("\n")
                return "".join(buffer)

            char = getattr(key, "char", None)

            if char == "\x03":  # Ctrl+C
                raise KeyboardInterrupt
            if char in ("\x04", "\x1a"):  # Ctrl+D (Unix) / Ctrl+Z (Windows) EOF
                raise EOFError

            if key == keyboard.Key.backspace:
                if cursor > 0:
                    del buffer[cursor - 1]
                    cursor -= 1
            elif key == keyboard.Key.delete:
                if cursor < len(buffer):
                    del buffer[cursor]
            elif key == keyboard.Key.left:
                cursor = max(0, cursor - 1)
            elif key == keyboard.Key.right:
                cursor = min(len(buffer), cursor + 1)
            elif key == keyboard.Key.home:
                cursor = 0
            elif key == keyboard.Key.end:
                cursor = len(buffer)
            elif char is not None and char.isprintable():
                buffer.insert(cursor, char)
                cursor += 1
            # other special keys (Up/Down/Insert/function keys/...) are ignored
            text = "".join(buffer)
            _redraw(prompt, text, cursor, prev_len)
            prev_len = len(text)
    finally:
        _stop_listener(listener)
