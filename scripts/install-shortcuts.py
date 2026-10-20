#!/usr/bin/env python3
"""Install (or remove) the optional Kumquat shortcuts for this user, without root.

Installing the Omarchy plugin changes nothing outside the plugin folder. This
script is the opt-in step that adds the desktop shortcuts:

* Hyprland owns Super+E (browse); Super+Shift+E remains the Email shortcut.
* Nautilus owns Shift+E in its file view and supplies its current selection.
* A small ``~/.local/bin/kumquat`` wrapper runs the plugin checkout's
  ``bin/kumquat``; the Files integration and the CLI use it.
* A window rule makes the popup a small floating window.

No clipboard bridge or synthetic Ctrl+C is used. Every file it changes is backed up
first, and ``--uninstall`` removes exactly what it added. Keep the plugin folder in
place, or run the installer again after moving it.
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
PLUGIN_ID = "io.github.sulaimanbaeisa.kumquat"
PLUGIN_URL = "https://github.com/SulaimanBaeisa/omarchy-plugin-kumquat"
# First lines of the files we write, so --uninstall only removes our own.
LAUNCHER_MARK = "# Kumquat launcher (managed by scripts/install-shortcuts.py)"
OLD_LAUNCHER_MARK = "# User install: system Python for GTK, source from this checkout."
SCRIPT_MARK = "# Nautilus supplies the current selection, never the clipboard."
EXTENSION_MARK = "KumquatWheelExtension"

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


def _write(
    path: Path, content: str, executable: bool = False, verb: str = "Installed"
) -> None:
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
    print(f"{verb}: {path}")


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
    required = (repo / "src/kumquat/cli.py", repo / "bin/kumquat")
    if not all(path.is_file() for path in required):
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
    # The real launcher is the plugin's bin/kumquat; this wrapper only gives it a
    # stable name on PATH. Run through sh so a lost executable bit does not matter.
    launch_text = (
        "#!/bin/sh\n"
        f"{LAUNCHER_MARK}\n"
        f"target={shlex.quote(str(repo / 'bin/kumquat'))}\n"
        '[ -f "$target" ] || {\n'
        '    echo "kumquat: $target was not found (plugin removed or moved?)." >&2\n'
        f'    echo "Install it again: omarchy plugin add {PLUGIN_URL} --enable" >&2\n'
        "    exit 127\n"
        "}\n"
        'exec /bin/sh "$target" "$@"\n'
    )
    script_text = (
        "#!/bin/sh\n"
        f"{SCRIPT_MARK}\n"
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


def _without_block(text: str, begin: str, end: str) -> str:
    """`text` minus one managed block and the blank line install put before it."""
    pattern = re.escape(begin) + r".*?" + re.escape(end) + r"\n?"
    stripped = re.sub(pattern, "", text, flags=re.S)
    if stripped == text:
        return text
    stripped = stripped.rstrip("\n")
    return stripped + "\n" if stripped else ""


def _remove_ours(path: Path, marks: tuple[str, ...], what: str) -> None:
    """Delete `path` only when it carries one of our markers."""
    if not path.exists():
        return
    if any(mark in _read(path) for mark in marks):
        path.unlink()
        print(f"Removed {what}: {path}")
    else:
        print(f"Left alone (not written by this installer): {path}")


def uninstall(home: Path) -> None:
    """Undo install(): remove only what it added, keep user data and backups.

    Never touches ``~/.config/kumquat`` (your appearance choice), converted
    files, the ``*.bak.*`` backups, or any binding, rule or script of yours.
    """
    home = home.resolve()
    hypr = home / ".config/hypr"
    for path, begin, end, what in (
        (hypr / "bindings.lua", BEGIN, END, "the Super+E binding"),
        (hypr / "hyprland.lua", RULE_BEGIN, RULE_END, "the popup window rule"),
    ):
        text = _read(path)
        cleaned = _without_block(text, begin, end)
        if cleaned != text:
            _write(path, cleaned, verb="Updated")
            print(f"Removed {what} from {path}")
    marks = (LAUNCHER_MARK, OLD_LAUNCHER_MARK)
    _remove_ours(home / ".local/bin/kumquat", marks, "launcher")
    scripts = home / ".local/share/nautilus/scripts"
    _remove_ours(scripts / SCRIPT_NAME, (SCRIPT_MARK,), "Files script")
    _remove_ours(
        home / ".local/share/nautilus-python/extensions/nautilus-kumquat.py",
        (EXTENSION_MARK,),
        "Files extension",
    )
    print(
        "Next: hyprctl reload; restart Files once.\n"
        f"Then remove the plugin itself with: omarchy plugin remove {PLUGIN_ID}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--uninstall",
        action="store_true",
        help="remove the shortcuts, launcher and window rule this script added",
    )
    args = parser.parse_args()
    if args.uninstall:
        uninstall(Path.home())
        return
    try:
        install(Path(__file__).resolve().parents[1], Path.home())
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
