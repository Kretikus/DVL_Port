"""
repl_input.py - a small, dependency-free "pre-filled, editable" input
prompt for the REPL.

Motivation: the combat interaction re-prompts for a weapon/spell every
round (see game.py's "combat" section), and retyping the same answer
("Schwert") each time is tedious. This shows the previous answer
pre-filled in the input line - press Enter to repeat it verbatim, or
edit it first.

No third-party dependency: uses `readline`'s insert-on-startup trick
where available (Unix/Mac - and Windows too, if something like
pyreadline3 happens to be installed), and a small raw-mode line editor
built on the stdlib `msvcrt` module as the Windows fallback (the stock
Windows Python has no `readline`). Falls back further to plain
`input()` with the previous answer shown as a bracketed hint if neither
editing method is usable (e.g. piped/non-interactive input, or an
unsupported platform) - so the REPL never simply breaks.
"""
import sys


def prompt_with_default(prompt: str, default: str) -> str:
    """Prompt for a line of input, pre-filled with `default` (typically
    the last command the player typed) so they can press Enter to
    repeat it or edit it first. Falls back to a plain prompt (with the
    default shown as a hint) if no interactive line-editing is
    available - including when stdin isn't a real terminal at all
    (piped/redirected input): `msvcrt.getwch()` reads from the console
    device directly, not from redirected stdin, and blocks forever
    waiting for a keypress that can never come - confirmed by hand
    (piping input into the REPL hung indefinitely before this check)."""
    if not default:
        return input(prompt)
    if not sys.stdin.isatty():
        return input(f"{prompt}[{default}] ")

    try:
        return _prompt_readline(prompt, default)
    except ImportError:
        pass

    if sys.platform == "win32":
        try:
            return _prompt_msvcrt(prompt, default)
        except ImportError:
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


def _prompt_msvcrt(prompt: str, default: str) -> str:
    """Minimal raw-mode line editor for Windows: printable chars,
    Backspace/Delete, Left/Right/Home/End. Enough to comfortably edit
    or accept a pre-filled command - not a full readline reimplementation."""
    import msvcrt  # Windows-only - caller catches ImportError on other platforms

    buffer = list(default)
    cursor = len(buffer)
    prev_len = len(buffer)
    sys.stdout.write(prompt + "".join(buffer))
    sys.stdout.flush()
    while True:
        ch = msvcrt.getwch()
        if ch in ("\r", "\n"):
            sys.stdout.write("\n")
            return "".join(buffer)
        if ch == "\x03":  # Ctrl+C
            raise KeyboardInterrupt
        if ch == "\x1a":  # Ctrl+Z - Windows console EOF
            raise EOFError
        if ch == "\x08":  # Backspace
            if cursor > 0:
                del buffer[cursor - 1]
                cursor -= 1
        elif ch in ("\x00", "\xe0"):  # arrow/nav key prefix
            ch2 = msvcrt.getwch()
            if ch2 == "K":  # Left
                cursor = max(0, cursor - 1)
            elif ch2 == "M":  # Right
                cursor = min(len(buffer), cursor + 1)
            elif ch2 == "G":  # Home
                cursor = 0
            elif ch2 == "O":  # End
                cursor = len(buffer)
            elif ch2 == "S":  # Delete
                if cursor < len(buffer):
                    del buffer[cursor]
            # other special keys (Up/Down/Insert/...) are ignored
        elif ch.isprintable():
            buffer.insert(cursor, ch)
            cursor += 1
        text = "".join(buffer)
        _redraw(prompt, text, cursor, prev_len)
        prev_len = len(text)
