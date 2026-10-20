#!/usr/bin/env python3
"""Install the two Kumquat shortcuts for this user, without root.

Nautilus owns Shift+E in its file view and supplies its current selection.
Hyprland owns Super+E (browse); Super+Shift+E remains the Email shortcut.
No clipboard bridge or synthetic Ctrl+C is used.

The per-user launcher loads this checkout's source with the system Python
(which supplies GTK). Keep the checkout in place, or reinstall after moving it.
"""

from __future__ import annotations

import argparse
import re
import shlex
import shutil
from datetime import datetime
from pathlib import Path

BEGIN = "-- BEGIN Kumquat shortcuts (managed)"
END = "-- END Kumquat shortcuts (managed)"
SCRIPT_NAME = "Kumquat Actions"
ACCEL = "<Shift>e"

# The product was called "Tangerine" before it was renamed. A user who installed
# that build has these on disk; they are migrated, never left to fight the new ones.
FORMER_BEGIN = "-- BEGIN Tangerine shortcuts (managed)"
FORMER_END = "-- END Tangerine shortcuts (managed)"
FORMER_SCRIPT_NAME = "Tangerine Actions"
KNOWN_SUPER_E = (
    '"Kumquat"',
    '"Kumquat browser"',
    '"Tangerine wheel"',
    '"Tangerine browser"',
)
# Hyprland's Lua rule needs the dot escaped twice (Lua string, then regex).
FORMER_WINDOW_CLASS = "dev\\\\.tangerine\\\\.wheel"
WINDOW_CLASS = "dev\\\\.kumquat\\\\.app"
RULE_BEGIN = "-- BEGIN Kumquat window rule (managed)"
RULE_END = "-- END Kumquat window rule (managed)"
WINDOW_RULE = (
    f'o.window("^({WINDOW_CLASS})$", '
    "{ float = true, center = true, size = { 520, 640 } })"
)


def render_bindings(original: str, launcher: Path) -> str:
    """Replace only our known binding/block; preserve other configuration."""
    for begin, end in ((BEGIN, END), (FORMER_BEGIN, FORMER_END)):
        original = re.sub(
            re.escape(begin) + r".*?" + re.escape(end) + r"\n?", "", original, flags=re.S
        )
    lines = []
    for line in original.splitlines():
        if re.match(r'^\s*o\.bind\("SUPER \+ E",', line):
            if not any(name in line for name in KNOWN_SUPER_E):
                raise ValueError(
                    "Super+E has an unknown binding; review it before install"
                )
            continue
        lines.append(line)
    # Lua accepts the same escaping needed by JSON's quoted strings.
    import json

    command = json.dumps(f"{shlex.quote(str(launcher))} --gui")
    block = (
        f"{BEGIN}\n"
        "-- Browse launch always starts in Kumquat, not on a clipboard file.\n"
        'hl.unbind("SUPER + E")\n'
        f'o.bind("SUPER + E", "Kumquat browser", {command})\n'
        "-- Super+Shift+E remains Email; Shift+E is local to Nautilus.\n"
        f"{END}\n"
    )
    return "\n".join(lines).rstrip() + "\n\n" + block


def merge_accels(original: str) -> str:
    """Remove our old window-wide accel, leaving focus-local capture routing.

    A native printable-key accelerator could steal E from text entries on
    other Nautilus versions. Keep other scripts and refuse their conflicts.
    """
    lines = []
    for line in original.splitlines():
        pair = line.split(" ", 1)
        if len(pair) == 2 and pair[1] in (SCRIPT_NAME, FORMER_SCRIPT_NAME):
            continue
        # GTK modifier names are case-insensitive.
        if len(pair) == 2 and pair[0].lower() == ACCEL.lower():
            raise ValueError("Shift+E is already assigned to a Nautilus script")
        lines.append(line)
    return "\n".join(lines) + ("\n" if lines else "")


def _read(path: Path) -> str:
    return path.read_text() if path.exists() else ""


def _write(path: Path, content: str, executable: bool = False) -> None:
    """Back up before changing an existing file, and verify the exact target."""
    if path.exists() and path.read_text() != content:
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S_%f")
        backup = path.with_name(f"{path.name}.bak.{stamp}")
        shutil.copy2(path, backup)
        print(f"Backup: {backup}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    if executable:
        path.chmod(0o755)
    if path.read_text() != content:
        raise OSError(f"Could not verify write: {path}")
    print(f"Installed: {path}")


def migrate_window_rule(original: str) -> str | None:
    """Point the old window-class rule at the new class; None when nothing to do."""
    if FORMER_WINDOW_CLASS not in original:
        return None
    return original.replace(FORMER_WINDOW_CLASS, WINDOW_CLASS)


def add_window_rule(original: str) -> str | None:
    """Append the popup size/placement rule once; None when one already exists.

    Any line that already mentions the window class counts, so a rule the user
    wrote by hand (maybe with a different size) is never duplicated or changed.
    """
    if WINDOW_CLASS in original:
        return None
    lead = "" if not original or original.endswith("\n") else "\n"
    gap = "\n" if original else ""
    block = (
        f"{RULE_BEGIN}\n"
        "-- Small centred floating popup for Kumquat. Delete this block to undo.\n"
        f"{WINDOW_RULE}\n"
        f"{RULE_END}\n"
    )
    return original + lead + gap + block


def retire_former_files(home: Path) -> None:
    """Move the old build's launcher/script/extension aside (never just delete)."""
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    vault = home / ".local/share/kumquat/legacy-backup" / stamp
    for former in (
        home / ".local/bin/tangerine-wheel",
        home / ".local/share/nautilus/scripts" / FORMER_SCRIPT_NAME,
        home / ".local/share/nautilus-python/extensions/nautilus-tangerine.py",
    ):
        if not former.exists():
            continue
        vault.mkdir(parents=True, exist_ok=True)
        shutil.copy2(former, vault / former.name)
        former.unlink()
        print(f"Retired old file (copy kept in {vault}): {former}")


def migrate_appearance(home: Path) -> None:
    """Copy the old appearance.toml to its new folder, keeping the original."""
    former = home / ".config/tangerine-wheel/appearance.toml"
    new = home / ".config/kumquat/appearance.toml"
    if former.exists() and not new.exists():
        _write(new, former.read_text())


def install(repo: Path, home: Path) -> None:
    """Install only after preflighting conflicts; never replace Email."""
    repo, home = repo.resolve(), home.resolve()
    if not (repo / "src/kumquat/cli.py").is_file():
        raise ValueError("Run this installer from a complete Kumquat checkout")
    launcher = home / ".local/bin/kumquat"
    bindings = home / ".config/hypr/bindings.lua"
    accels = home / ".config/nautilus/scripts-accels"
    script = home / ".local/share/nautilus/scripts" / SCRIPT_NAME
    # Preflight everything BEFORE writing any user configuration.
    new_bindings = render_bindings(_read(bindings), launcher)
    new_accels = merge_accels(_read(accels))
    extension = home / ".local/share/nautilus-python/extensions/nautilus-kumquat.py"
    extension_text = (repo / "extensions/nautilus-kumquat.py").read_text()
    code = (
        f"import sys; sys.path.insert(0, {str(repo / 'src')!r}); "
        "from kumquat.cli import main; raise SystemExit(main())"
    )
    launch_text = (
        "#!/bin/sh\n"
        "# User install: system Python for GTK, source from this checkout.\n"
        f'exec /usr/bin/python3 -c {shlex.quote(code)} "$@"\n'
    )
    script_text = (
        "#!/bin/sh\n"
        "# Nautilus supplies the current selection, never the clipboard.\n"
        f"exec {shlex.quote(str(launcher))} "
        "--gui --from-nautilus --tab actions\n"
    )
    rules = home / ".config/hypr/hyprland.lua"
    rules_text = _read(rules)
    new_rules = migrate_window_rule(rules_text)
    rule_added = False
    if new_rules is None and rules.exists():  # never invent a config on non-Omarchy
        new_rules = add_window_rule(rules_text)
        rule_added = new_rules is not None
    retire_former_files(home)
    _write(launcher, launch_text, executable=True)
    _write(script, script_text, executable=True)
    _write(extension, extension_text)
    _write(accels, new_accels)
    _write(bindings, new_bindings)
    migrate_appearance(home)
    if new_rules is not None:
        _write(rules, new_rules)
        if rule_added:
            print(f"Added a floating-window rule for the popup to {rules}")
    elif not rules.exists():
        print(
            f"No {rules} found (not an Omarchy/Hyprland setup?), so the optional "
            "popup-size rule was skipped. The shortcuts still work."
        )
    print(
        "Next: hyprctl reload; restart Files once to load the nautilus-python extension."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        install(Path(__file__).resolve().parents[1], Path.home())
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
