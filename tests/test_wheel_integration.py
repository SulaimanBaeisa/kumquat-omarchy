"""Integration seams for options collection and truthful empty states."""

from types import SimpleNamespace

from PIL import Image

from kumquat.gui import wheel


def test_validated_tool_options_reach_backend(monkeypatch, tmp_path):
    seen = {}

    def crop(tool_id, files, dest, **opts):
        seen.update(tool_id=tool_id, files=files, opts=opts)
        return dest / "photo-Cropped.png"

    monkeypatch.setattr(wheel._apply, "apply_tool", crop)
    src = tmp_path / "photo.png"
    result = wheel.apply_option("tools", "cropImage", [str(src)],
                                options={"aspect": "16:9"})
    assert seen["opts"] == {"aspect": "16:9"}
    assert seen["files"] == [src]
    assert result == "Saved photo-Cropped.png"


def test_move_action_returns_new_selection_with_explicit_destination(tmp_path):
    dest = tmp_path / "new-folder"
    src = tmp_path / "original.txt"
    src.write_text("Synthetic Move regression")
    result = wheel.apply_option("actions", "move", [str(src)],
                                options={"destination": str(dest)})
    assert result.selection == (str(dest / src.name),)
    assert result.message.startswith("Moved ")
    assert not src.exists()
    assert (dest / src.name).read_text() == "Synthetic Move regression"


def test_move_then_crop_uses_the_new_selection(tmp_path):
    src = tmp_path / "photo.png"
    Image.new("RGB", (80, 48), "orange").save(src)
    dest = tmp_path / "Destination"
    messages = []
    window = SimpleNamespace(
        files=[str(src)], _job=object(), _stop_progress=lambda: None,
        status=SimpleNamespace(set_text=messages.append))
    window.adopt = lambda paths: setattr(window, "files", list(paths))
    result = wheel.apply_option("actions", "move", window.files,
                                options={"destination": str(dest)})
    wheel.WheelWindow._on_done(window, result, None)
    assert window.files == [str(dest / src.name)]
    assert messages[-1].startswith("Moved ")
    assert window._job is None
    cropped = wheel.apply_option("tools", "cropImage", window.files,
                                 options={"aspect": "1:1"})
    assert cropped.startswith("Saved ")
    with Image.open(next(p for p in dest.glob("*.png") if p.name != src.name)) as im:
        assert im.size == (48, 48)


def test_failed_move_does_not_replace_the_selection():
    window = SimpleNamespace(
        _job=object(), _stop_progress=lambda: None,
        status=SimpleNamespace(set_text=lambda text: None))
    adopted = []
    window.adopt = adopted.append
    wheel.WheelWindow._on_done(
        window, None, FileExistsError("destination collision"))
    assert not adopted
    assert window._job is None


def test_empty_message_describes_the_active_tab():
    assert "No tools" in wheel.empty_message("tools")
    assert "No conversions" in wheel.empty_message("conversions")
    assert "No actions" in wheel.empty_message("actions")


def test_all_modes_are_known_to_empty_message():
    assert all(wheel.empty_message(mode) for mode in wheel.MODES)
