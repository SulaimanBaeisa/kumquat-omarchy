"""GTK-free wheel logic: key -> mode map, status text, option dispatch.

`kumquat.gui.wheel` keeps everything that does not draw at module level so
it runs under the test venv, which has no `gi`.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from kumquat import cli
from kumquat.actions import ShareResult
from kumquat.gui import wheel
from kumquat.gui.wheel import (
    APPLY_KEYS,
    MODE_KEYS,
    MODES,
    TAB_KEYS,
    TAB_LABELS,
    apply_option,
    cycle_mode,
    elapsed_text,
    files_summary,
    mode_for_held,
    run_action,
    step_index,
)

SRC = Path(__file__).resolve().parents[1] / "src"


# --- key map ---


def test_modes_order():
    assert MODES == ("conversions", "tools", "actions")


@pytest.mark.parametrize(("key", "mode"), [
    ("Shift_L", 0), ("Shift_R", 0),
    ("Super_L", 1), ("Super_R", 1), ("Meta_L", 1), ("Meta_R", 1),
    ("Control_L", 2), ("Control_R", 2),
])
def test_single_modifier_selects_mode(key, mode):
    assert MODE_KEYS[key] == mode
    assert mode_for_held({key}) == mode


def test_both_sides_of_one_modifier_still_one_mode():
    assert mode_for_held({"Shift_L", "Shift_R"}) == 0


def test_two_different_modifiers_do_not_switch():
    assert mode_for_held({"Shift_L", "Control_L"}) is None
    assert mode_for_held({"Super_L", "Control_R", "Shift_L"}) is None


def test_nothing_or_non_modifiers_held_do_not_switch():
    assert mode_for_held(set()) is None
    assert mode_for_held({"a", "Return"}) is None


def test_apply_keys():
    assert {"Return", "KP_Enter", "space"} == set(APPLY_KEYS)


# --- tabs: Left/Right and A/D ----------------------------------------------------


def test_cycle_mode_wraps_both_ways():
    assert cycle_mode(0, 1) == 1
    assert cycle_mode(2, 1) == 0
    assert cycle_mode(0, -1) == 2


def test_tab_keys_cover_arrows_and_a_d_any_case():
    assert TAB_KEYS["Left"] == TAB_KEYS["a"] == TAB_KEYS["A"] == -1
    assert TAB_KEYS["Right"] == TAB_KEYS["d"] == TAB_KEYS["D"] == 1


def test_tab_labels_follow_modes():
    assert len(TAB_LABELS) == len(MODES)
    assert TAB_LABELS == ("Convert", "Tools", "Actions")


def test_elapsed_text():
    assert elapsed_text(0.4) == "Working… 0 s"
    assert elapsed_text(75.2) == "Working… 1 min 15 s"


# --- list navigation ----------------------------------------------------------


@pytest.mark.parametrize(("current", "delta", "count", "expected"), [
    (0, 1, 3, 1), (2, 1, 3, 2), (0, -1, 3, 0), (1, -1, 3, 0),
    (None, 1, 3, 0), (None, -1, 3, 0), (0, 1, 0, None),
])
def test_step_index_clamps(current, delta, count, expected):
    assert step_index(current, delta, count) == expected


# --- text ---------------------------------------------------------------------



def test_files_summary_names_up_to_three():
    assert files_summary(["/a/x.jpg", "/b/y.png"], False) == "x.jpg, y.png"
    many = [f"/d/{n}.jpg" for n in "abcde"]
    assert files_summary(many, False) == "a.jpg, b.jpg, c.jpg +2"


def test_files_summary_marks_clipboard_origin():
    assert files_summary(["/a/x.jpg"], True) == "x.jpg (from clipboard)"


# --- dispatch -----------------------------------------------------------------


def test_apply_option_conversion_reports_saved(monkeypatch, tmp_path):
    from kumquat import apply as apply_mod
    calls = []

    def fake(conv_id, src, dest, progress=None):
        calls.append((conv_id, Path(src), Path(dest)))
        return dest / "x.png"

    monkeypatch.setattr(apply_mod, "apply_conversion", fake)
    src = tmp_path / "x.jpg"
    msg = apply_option("conversions", "image-jpg-to-png", [str(src)])
    assert msg == "Saved x.png"
    assert calls == [("image-jpg-to-png", src, tmp_path)]


def test_apply_option_forwards_progress(monkeypatch):
    seen = {}

    def fake_apply(opt_id, src, dest, progress=None):
        seen["progress"] = progress
        return src.with_suffix(".png")

    monkeypatch.setattr(wheel._apply, "apply_conversion", fake_apply)
    marker = object()
    msg = wheel.apply_option("conversions", "x", ["/tmp/a.jpg"], progress=marker)
    assert seen["progress"] is marker
    assert msg == "Saved a.png"


def test_apply_option_tool_counts_multiple_outputs(monkeypatch, tmp_path):
    from kumquat import apply as apply_mod
    monkeypatch.setattr(apply_mod, "apply_tool",
                        lambda tid, srcs, dest: [dest / "1", dest / "2"])
    assert apply_option("tools", "splitPDF", [str(tmp_path / "a.pdf")]) == (
        "Saved 2 files")


def test_apply_option_tool_single_output(monkeypatch, tmp_path):
    from kumquat import apply as apply_mod
    monkeypatch.setattr(apply_mod, "apply_tool",
                        lambda tid, srcs, dest: dest / "small.jpg")
    assert apply_option("tools", "compress", [str(tmp_path / "a.jpg")]) == (
        "Saved small.jpg")


def test_apply_option_action_routes_to_run_action(monkeypatch):
    monkeypatch.setattr(wheel, "run_action", lambda aid, files: f"ran {aid}")
    assert apply_option("actions", "copy", ["/a/x.jpg"]) == "ran copy"


@pytest.mark.parametrize(("action", "func", "message"), [
    ("copy-path", "copy_paths", "Paths copied to clipboard."),
    ("copy", "copy_files", "Files copied to clipboard."),
])
def test_run_action_messages(monkeypatch, action, func, message):
    from kumquat import actions
    seen = []
    monkeypatch.setattr(actions, func, lambda paths: seen.append(paths))
    assert run_action(action, ["/a/x.jpg"]) == message
    assert seen == [[Path("/a/x.jpg")]]


@pytest.mark.parametrize(("result", "expected"), [
    (ShareResult(["localsend"], "app", True),
     "LocalSend opened. Your files are on the clipboard: press Ctrl+V there, "
     "or drag them in."),
    (ShareResult(["localsend"], "app", False),
     "LocalSend opened. Drag your files into it (clipboard tool not found)."),
    (ShareResult(["term", "localsend-cli"], "cli", False),
     "LocalSend device list opened in a terminal: pick a device to send."),
])
def test_run_action_share_tells_the_user_what_happened(monkeypatch, result, expected):
    from kumquat import actions
    monkeypatch.setattr(actions, "share", lambda paths: result)
    assert run_action("share", ["/a/x.jpg"]) == expected


def test_run_action_terminal_uses_first_file(monkeypatch):
    from kumquat import actions
    seen = []
    monkeypatch.setattr(actions, "open_terminal", seen.append)
    assert run_action("open-terminal", ["/a/x", "/b/y"]) == "Terminal opened."
    assert seen == [Path("/a/x")]


def test_run_action_float_reports_shelf(monkeypatch):
    from kumquat import actions
    monkeypatch.setattr(actions, "float_shelf", lambda paths: Path("/s/shelf"))
    assert run_action("float", ["/a/x"]) == "Shelf: /s/shelf"


def test_run_action_move_and_unknown():
    with pytest.raises(ValueError, match="Choose a destination folder"):
        run_action("move", ["/a/x"])
    assert run_action("nope", ["/a/x"]) == "Unknown action nope"


# --- main-loop delivery --------------------------------------------------------


class _FakeGLib:
    """Records idle sources; `run` drives them the way GLib would."""

    def __init__(self) -> None:
        self.sources = []

    def idle_add(self, fn):
        self.sources.append(fn)

    def run(self, max_calls=5):
        """Call each source until it returns falsy (GLib's repeat contract)."""
        for source in self.sources:
            for _ in range(max_calls):
                if not source():
                    break


def test_idle_once_runs_callback_exactly_once():
    glib, calls = _FakeGLib(), []
    post = wheel._idle_once(glib)
    post(lambda *args: calls.append(args) or True, "a", 1)  # truthy return
    glib.run()
    assert calls == [("a", 1)]


def test_idle_once_defers_until_main_loop_runs():
    glib, calls = _FakeGLib(), []
    wheel._idle_once(glib)(calls.append, "x")
    assert calls == []
    glib.run()
    assert calls == ["x"]


# --- import hygiene -----------------------------------------------------------


def test_cli_dispatches_to_gui_app_run_gui():
    from kumquat.gui import app
    assert cli.run_gui is app.run_gui


def test_gui_modules_import_without_gi():
    code = ("import sys; import kumquat.gui, kumquat.gui.wheel, "
            "kumquat.gui.app, kumquat.cli; "
            "assert 'gi' not in sys.modules, 'gi imported'")
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True,
                          text=True, env={"PYTHONPATH": str(SRC)})
    assert proc.returncode == 0, proc.stderr


def test_run_gui_without_gi_raises_runtime_error(monkeypatch):
    from kumquat.gui import app
    monkeypatch.setitem(sys.modules, "gi", None)
    with pytest.raises(RuntimeError, match="GTK wheel unavailable"):
        app.run_gui(["photo.jpg"])
