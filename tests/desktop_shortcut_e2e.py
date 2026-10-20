#!/usr/bin/python3
"""Opt-in real Wayland/Nautilus keyboard test (no file actions are applied).

Run /usr/bin/python3 tests/desktop_shortcut_e2e.py after installing shortcuts and
restarting Nautilus with a clean system-Python PATH. Requires Hyprland, wtype,
GTK4/AT-SPI, and wl-paste. Creates/closes only test-owned windows, preserves the
clipboard byte-for-byte, and never copies files or invokes conversion actions.
Not collected by pytest: this deliberately drives the live desktop.
"""

from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import tempfile
import time
from pathlib import Path

import gi

gi.require_version("Atspi", "2.0")
from gi.repository import Atspi  # noqa: E402 — require_version must run first


def command(*args):
    return subprocess.check_output(args, text=True).strip()


def clients():
    return json.loads(command("hyprctl", "clients", "-j"))


def wait_for(fn, timeout=25):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = fn()
        if result:
            return result
        time.sleep(0.15)
    raise AssertionError(f"Timed out: {fn}")


def focus(client):
    command(
        "hyprctl",
        "eval",
        'hl.dispatch(hl.dsp.focus({window="address:' + client["address"] + '"}))',
    )
    wait_for(
        lambda: (
            json.loads(command("hyprctl", "activewindow", "-j")).get("address")
            == client["address"]
        )
    )


def key(name, *modifiers):
    args = ["wtype"]
    for mod in modifiers:
        args.extend(["-M", mod])
    # wtype -k resolves key names case-insensitively and builds a one-level
    # keymap (even -k E emits lowercase e). Literal E plus held Shift models
    # the actual uppercase key event and proves normal text entry still works.
    if len(name) == 1:
        args.append(name.upper() if "shift" in modifiers else name)
    else:
        args.extend(["-k", name])
    for mod in reversed(modifiers):
        args.extend(["-m", mod])
    subprocess.run(args, check=True)
    time.sleep(0.25)


def walk(node, depth=0):
    yield node
    if depth < 40:
        for i in range(node.get_child_count()):
            child = node.get_child_at_index(i)
            if child:
                yield from walk(child, depth + 1)


def nodes(client):
    current = next((c for c in clients() if c["address"] == client["address"]), client)
    for app in Atspi.get_desktop(0):
        if app and app.get_process_id() == client["pid"]:
            for frame in app:
                if frame and frame.get_name() == current["title"]:
                    return list(walk(frame))
    return []


def state(node, name):
    return node.get_state_set().contains(getattr(Atspi.StateType, name))


def selected(client):
    return sorted(
        n.get_name()
        for n in nodes(client)
        if n.get_role_name() in ("table row", "list item")
        and state(n, "SELECTED")
        and state(n, "SHOWING")
    )


def text(client):
    return [
        Atspi.Text.get_text(n, 0, -1)
        for n in nodes(client)
        if state(n, "FOCUSED") and n.get_role_name() in ("text", "entry")
    ]


def clipboard():
    types = subprocess.run(["wl-paste", "--list-types"], capture_output=True)
    result = {"types": types.stdout.decode(errors="replace"), "code": types.returncode}
    for mime in types.stdout.decode().splitlines():
        payload = subprocess.run(["wl-paste", "--type", mime], capture_output=True)
        result[mime] = [payload.returncode, hashlib.sha256(payload.stdout).hexdigest()]
    return result


def native_environment(client):
    try:
        return dict(
            part.split(b"=", 1)
            for part in Path(f"/proc/{client['pid']}/environ").read_bytes().split(b"\0")
            if b"=" in part
        )
    except (FileNotFoundError, ProcessLookupError):
        return {}


def native_uris(client):
    return (
        native_environment(client)
        .get(b"NAUTILUS_SCRIPT_SELECTED_URIS", b"")
        .decode()
        .splitlines()
    )


def typing_probe():
    """Separate app: prove ordinary Shift+E is not a global hotkey."""
    gi.require_version("Gtk", "4.0")
    from gi.repository import Gtk

    app = Gtk.Application(application_id="dev.kumquat.shortcuttypingprobe")

    def activate(app):
        win = Gtk.ApplicationWindow(
            application=app, title="Kumquat shortcut typing probe"
        )
        entry = Gtk.Entry()
        win.set_child(entry)
        win.present()
        entry.grab_focus()

    app.connect("activate", activate)
    app.run([])


def main():
    before_clipboard = clipboard()
    original = clients()
    old_addresses = {c["address"] for c in original}
    old_pids = {c["pid"] for c in original}
    test_dir = Path(
        tempfile.mkdtemp(prefix="kumquat-native-key-", dir=os.environ["TMPDIR"])
    )
    names = ["alpha selected # %.txt", "beta selected 日本語.txt"]
    for name in names:
        (test_dir / name).write_text("Synthetic shortcut test; no conversion.\n")
    env = {**os.environ, "PATH": str(Path.home() / ".local/bin") + ":/usr/bin:/bin"}
    for name in ("PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV"):
        env.pop(name, None)
    records = []
    owned_pids = set()
    nautilus = None
    probe = None

    def popup():
        return next(
            (
                c
                for c in clients()
                if c["class"] == "dev.kumquat.app"
                and c["address"] not in old_addresses
                and (
                    c["pid"] in owned_pids
                    or native_environment(c)
                    .get(b"NAUTILUS_SCRIPT_CURRENT_URI", b"")
                    .decode()
                    == test_dir.as_uri()
                    or any(
                        uri.startswith(test_dir.as_uri() + "/") for uri in native_uris(c)
                    )
                )
            ),
            None,
        )

    def close_popup(client):
        assert client["pid"] not in old_pids
        owned_pids.add(client["pid"])
        os.kill(client["pid"], signal.SIGTERM)
        wait_for(lambda: all(c["address"] != client["address"] for c in clients()))

    def launch_selection(expected, scenario):
        focus(nautilus)
        before_selection = selected(nautilus)
        assert len(before_selection) == len(expected), before_selection
        key("e", "shift")
        win = wait_for(popup)
        owned_pids.add(win["pid"])
        wait_for(lambda: any(n.get_name() == "Choose a file action" for n in nodes(win)))
        assert sorted(native_uris(win)) == sorted(p.as_uri() for p in expected)
        visible = [n.get_name() for n in nodes(win) if state(n, "SHOWING")]
        assert any(
            n.get_name() == "Actions"
            and n.get_role_name() == "toggle button"
            and state(n, "PRESSED")
            for n in nodes(win)
        )
        assert all(any(path.name in label for label in visible) for path in expected), (
            visible
        )
        records.append(
            {
                "scenario": scenario,
                "selection": before_selection,
                "native_uris": native_uris(win),
                "actions_active": True,
                "status_verified": True,
            }
        )
        close_popup(win)

    try:
        subprocess.Popen(
            ["nautilus", "--new-window", str(test_dir)],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        nautilus = wait_for(
            lambda: next(
                (
                    c
                    for c in clients()
                    if c["class"] == "org.gnome.Nautilus" and c["title"] == test_dir.name
                ),
                None,
            )
        )
        wait_for(lambda: len(nodes(nautilus)) > 30)
        focus(nautilus)
        key("Home")
        wait_for(lambda: any(names[0] in s for s in selected(nautilus)))
        launch_selection([test_dir / names[0]], "selection A")
        focus(nautilus)
        key("End")
        wait_for(lambda: any(names[1] in s for s in selected(nautilus)))
        launch_selection([test_dir / names[1]], "fresh selection B")
        focus(nautilus)
        key("a", "ctrl")
        wait_for(lambda: len(selected(nautilus)) == 2)
        launch_selection([test_dir / name for name in names], "exact multiple selection")

        focus(nautilus)
        # AT-SPI's public selection interface clears the current file list;
        # Ctrl+Shift+I is not routed by this Nautilus build's GTK class binding.
        file_list = next(
            n
            for n in nodes(nautilus)
            if n.get_role_name() == "list"
            and n.get_selection_iface()
            and n.get_selection_iface().get_n_selected_children() == 2
        )
        assert file_list.get_selection_iface().clear_selection()
        wait_for(lambda: not selected(nautilus))
        key("e", "shift")
        time.sleep(2)
        assert popup() is None
        records.append({"scenario": "no selection", "no_popup": True})

        # Never commit a rename; inspect typed text and cancel the popover.
        focus(nautilus)
        key("Home")
        key("F2")
        wait_for(lambda: bool(text(nautilus)))
        key("e", "shift")
        assert wait_for(lambda: text(nautilus)) == ["E.txt"], text(nautilus)
        assert popup() is None
        records.append({"scenario": "rename typing", "text": "E.txt", "no_popup": True})
        key("Escape")
        assert (test_dir / names[0]).exists()

        for shortcut, label in (("l", "location typing"), ("f", "search typing")):
            focus(nautilus)
            key(shortcut, "ctrl")
            if shortcut == "l":
                wait_for(lambda: bool(text(nautilus)))
            else:
                # Nautilus 51's custom SearchEntry exposes no AT-SPI Text
                # interface. Its live window title includes the exact query.
                wait_for(
                    lambda: any(
                        n.get_role_name() == "entry" and state(n, "SHOWING")
                        for n in nodes(nautilus)
                    )
                )
            key("a", "ctrl")
            key("e", "shift")
            if shortcut == "l":
                assert wait_for(lambda: text(nautilus)) == ["E"], text(nautilus)
            else:
                wait_for(
                    lambda: any(
                        c["address"] == nautilus["address"]
                        and c["title"] == "Search for “E”"
                        for c in clients()
                    )
                )
            assert popup() is None
            records.append({"scenario": label, "text": "E", "no_popup": True})
            key("Escape")

        # Super+E wtype attempts did not produce a window here. Exercise the
        # exact installed target and separately assert its live binding;
        # do not mislabel that as a real Super+E key test.
        browse = subprocess.Popen(
            [str(Path.home() / ".local/bin/kumquat"), "--gui"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        owned_pids.add(browse.pid)
        win = wait_for(popup)
        owned_pids.add(win["pid"])
        wait_for(
            lambda: any(
                n.get_name() == "Cancel" and state(n, "SHOWING") for n in nodes(win)
            )
        )
        assert all(
            any(
                n.get_name() == name
                and n.get_role_name() == "button"
                and state(n, "SHOWING")
                for n in nodes(win)
            )
            for name in ("↑", "⌂", "Cancel")
        )
        assert not any(
            n.get_name() == "Actions"
            and n.get_role_name() == "toggle button"
            and state(n, "SHOWING")
            for n in nodes(win)
        )
        records.append(
            {
                "scenario": "Super+E target",
                "browse_picker": True,
                "actual_global_key": "not verified: wtype not dispatched",
            }
        )
        close_popup(win)

        probe = subprocess.Popen(
            ["/usr/bin/python3", __file__, "--typing-probe"], env=env
        )
        probe_win = wait_for(
            lambda: next(
                (
                    c
                    for c in clients()
                    if c["pid"] == probe.pid
                    and c["title"] == "Kumquat shortcut typing probe"
                ),
                None,
            )
        )
        focus(probe_win)
        key("e", "shift")
        assert wait_for(lambda: text(probe_win)) == ["E"]
        assert popup() is None
        records.append(
            {"scenario": "other application typing", "text": "E", "no_popup": True}
        )
        probe.terminate()
        probe.wait(timeout=10)
        probe = None

        binds = json.loads(command("hyprctl", "binds", "-j"))
        assert any(
            b["key"] == "E"
            and b["modmask"] == 64
            and b["description"] == "Kumquat browser"
            for b in binds
        )
        assert any(
            b["key"] == "E" and b["modmask"] == 65 and b["description"] == "Email"
            for b in binds
        )
        assert not any(b["key"].lower() == "e" and b["modmask"] == 1 for b in binds)
        records.append(
            {
                "scenario": "Super+Shift+E",
                "live_binding": "Email",
                "no_global_Shift_E": True,
            }
        )
        assert clipboard() == before_clipboard, "Clipboard changed"
        records.append({"scenario": "clipboard", "all_mime_bytes_preserved": True})
        print(
            json.dumps(
                {"result": "PASS", "test_directory": str(test_dir), "records": records},
                indent=2,
            )
        )
    finally:
        if probe is not None:
            probe.terminate()
            probe.wait(timeout=10)
        for pid in owned_pids:
            if any(
                c["pid"] == pid and c["class"] == "dev.kumquat.app" for c in clients()
            ):
                os.kill(pid, signal.SIGTERM)
        if nautilus and any(c["address"] == nautilus["address"] for c in clients()):
            focus(nautilus)
            key("Escape")
            key("w", "ctrl")
        # Keep synthetic fixtures for inspecting failed runs; TMPDIR prunes later.


if __name__ == "__main__":
    import sys

    if sys.argv[1:] == ["--typing-probe"]:
        typing_probe()
    else:
        main()
