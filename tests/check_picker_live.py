"""Manual live check: SUPER+E must open exactly ONE window.

Run by hand on a Hyprland/Wayland session:

    cd omarchy-plugin-kumquat      # your checkout
    PYTHONPATH=src /usr/bin/python3 tests/check_picker_live.py; echo rc=$?

The check puts plain text on the clipboard first (otherwise `--gui` adopts a
stale copied file instead of showing the embedded browser), launches
`/usr/bin/python3 -m kumquat.cli --gui`, then polls `hyprctl -j clients`.
It passes only when the launched pid owns exactly one window, titled
"Kumquat", and no window titled "Choose files for Kumquat" exists
anywhere -- the old build opened that separate GTK chooser dialog, whose
single click only selected a file / jumped to its location (the user's bug).

It also prints whether Hyprland applied the persistent window rule
(float, 520x640) to class `dev.kumquat.app`; that line is informational.
What the browser looks like still needs a human look (or tests/gui_e2e.py,
which drives the click -> conversions flow in-process).

Exit code 0 = pass, 1 = fail (the reason is printed).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from typing import TextIO

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
WHEEL_TITLE = "kumquat"
LEGACY_DIALOG_TITLE = "choose files for kumquat"
WHEEL_CLASS = "dev.kumquat.app"
LAUNCH_TIMEOUT_S = 12.0
POLL_INTERVAL_S = 0.5
SETTLE_S = 1.0
KILL_TIMEOUT_S = 5.0
STDERR_TAIL_CHARS = 1200


def build_env() -> dict[str, str]:
    """Environment for the child: repo ``src`` on the path, display set."""
    env = dict(os.environ)
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = SRC + (os.pathsep + existing if existing else "")
    env.setdefault("WAYLAND_DISPLAY", "wayland-1")
    return env


def list_windows(env: dict[str, str]) -> list[dict]:
    """All Hyprland clients, or ``[]`` when ``hyprctl`` cannot answer."""
    try:
        result = subprocess.run(
            ["hyprctl", "-j", "clients"], capture_output=True, text=True,
            env=env, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return []
    try:
        data = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [win for win in data if isinstance(win, dict)]


def window_title(win: dict) -> str:
    return str(win.get("title") or "")


def is_wheel(win: dict) -> bool:
    """True for the wheel surface. Matches Zen's 'kumquat-omarchy' never."""
    return window_title(win).lower() == WHEEL_TITLE


def is_ours(win: dict, pid: int) -> bool:
    """True for surfaces this launch owns, including the old chooser dialog.

    The dialog and the wheel share the child's pid, so pid matching catches
    the dialog even though GTK gives it the generic ``python3`` class and a
    title that does not mention the wheel.
    """
    return (win.get("pid") == pid
            or LEGACY_DIALOG_TITLE in window_title(win).lower()
            or str(win.get("class") or "").lower() == WHEEL_CLASS)


def describe(win: dict) -> str:
    return (f"{window_title(win)!r} (class={win.get('class')!r}, "
            f"pid={win.get('pid')}, floating={win.get('floating')})")


def fail(reason: str, stream: TextIO | None = None) -> int:
    """Print a specific failure reason, plus any child traceback, and fail."""
    print(f"FAIL: {reason}")
    if stream is not None:
        stream.seek(0)
        tail = stream.read()[-STDERR_TAIL_CHARS:].strip()
        if tail:
            print("--- child stderr (tail) ---")
            print(tail)
    return 1


def main() -> int:
    if shutil.which("hyprctl") is None:
        return fail("hyprctl not found; this check needs a Hyprland session")
    if shutil.which("wl-copy") is None:
        return fail("wl-copy not found; cannot clear the clipboard first")

    env = build_env()
    # wl-copy forks a clipboard server; detach its stdio or it keeps the
    # caller's pipe open and anything reading our output never sees EOF.
    subprocess.run(["wl-copy"], input="plain", text=True, env=env,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   timeout=10, check=False)

    with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as err:
        proc = subprocess.Popen(
            ["/usr/bin/python3", "-m", "kumquat.cli", "--gui"],
            cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=err)
        try:
            deadline = time.monotonic() + LAUNCH_TIMEOUT_S
            wheel: dict | None = None
            while time.monotonic() < deadline:
                time.sleep(POLL_INTERVAL_S)
                if proc.poll() is not None:
                    return fail(
                        f"GUI exited with rc={proc.returncode} before any "
                        "window appeared", err)
                wheels = [win for win in list_windows(env) if is_wheel(win)]
                if wheels:
                    wheel = wheels[0]
                    break
            if wheel is None:
                return fail(
                    f"no 'Kumquat' window appeared within "
                    f"{LAUNCH_TIMEOUT_S:.0f}s", err)

            # Give a (regressed) build time to pop a second surface.
            time.sleep(SETTLE_S)
            windows = list_windows(env)
            legacy = [win for win in windows
                      if LEGACY_DIALOG_TITLE in window_title(win).lower()]
            if legacy:
                seen = "; ".join(describe(win) for win in legacy)
                return fail(
                    f"the old 'Choose files for Kumquat' dialog is open: "
                    f"{seen}. The browser must be embedded in the wheel "
                    "window", err)
            mine = [win for win in windows if win.get("pid") == proc.pid]
            if len(mine) != 1 or not is_wheel(mine[0]):
                seen = "; ".join(describe(win) for win in mine) or "none"
                return fail(
                    f"expected exactly 1 window ('Kumquat') for pid "
                    f"{proc.pid}, saw {len(mine)}: {seen}", err)
            wheels = [win for win in windows if is_wheel(win)]
            if len(wheels) != 1:
                seen = "; ".join(describe(win) for win in wheels)
                return fail(
                    f"expected exactly 1 'Kumquat' window, saw "
                    f"{len(wheels)}: {seen}. Close stale Kumquat instances "
                    "and re-run", err)
            strays = [win for win in windows
                      if not is_wheel(win) and is_ours(win, proc.pid)]
            if strays:
                seen = "; ".join(describe(win) for win in strays)
                return fail(
                    f"{len(strays)} stray app window(s): {seen}. The picker "
                    "must be embedded in the wheel window, not a separate "
                    "dialog", err)

            win = mine[0]
            ruled = (bool(win.get("floating"))
                     and list(win.get("size") or []) == [520, 640])
            print(f"info: wheel window {describe(win)} size={win.get('size')}"
                  " -> Hyprland rule " + ("applied" if ruled else
                  "NOT applied (see README, Omarchy setup)"))
            print("PASS: exactly one 'Kumquat' window, no chooser dialog")
            return 0
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=KILL_TIMEOUT_S)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=KILL_TIMEOUT_S)


if __name__ == "__main__":
    sys.exit(main())
