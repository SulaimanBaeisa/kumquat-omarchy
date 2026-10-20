"""App-local appearance preferences are independent of GTK and desktop config."""
from dataclasses import FrozenInstanceError

import pytest


def test_missing_file_uses_frozen_opaque_default(tmp_path):
    from kumquat.gui.appearance import Appearance, load_appearance

    appearance = load_appearance(tmp_path / "missing.toml")
    assert appearance == Appearance(style="opaque", opacity=0.90)
    with pytest.raises(FrozenInstanceError):
        appearance.style = "glass"


def test_reads_glass_preferences(tmp_path):
    from kumquat.gui.appearance import Appearance, load_appearance

    path = tmp_path / "appearance.toml"
    path.write_text('[appearance]\nstyle = "glass"\nopacity = 0.82\n')
    assert load_appearance(path) == Appearance(style="glass", opacity=0.82)


@pytest.mark.parametrize("text", [
    "broken {{", 'appearance = "glass"', '[appearance]\nstyle = "frosted"',
    '[appearance]\nstyle = ["glass"]', '[appearance]\nstyle = false',
    '[appearance]\nstyle = "glass; } * { opacity: 0"',
    '[appearance]\nstyle = "glass"\nopacity = 0.74',
    '[appearance]\nstyle = "glass"\nopacity = 1.01',
    '[appearance]\nstyle = "glass"\nopacity = nan',
    '[appearance]\nstyle = "glass"\nopacity = inf',
    '[appearance]\nstyle = "glass"\nopacity = true',
    '[appearance]\nstyle = "glass"\nopacity = "0.9); } * {"',
])
def test_invalid_file_falls_back_to_opaque(tmp_path, text):
    from kumquat.gui.appearance import Appearance, load_appearance

    path = tmp_path / "appearance.toml"
    path.write_text(text)
    assert load_appearance(path) == Appearance()


@pytest.mark.parametrize("opacity", [0.75, 0.90, 1])
def test_opacity_boundaries_are_accepted(tmp_path, opacity):
    from kumquat.gui.appearance import Appearance, load_appearance

    path = tmp_path / "appearance.toml"
    path.write_text(f'[appearance]\nstyle = "glass"\nopacity = {opacity}\n')
    assert load_appearance(path) == Appearance("glass", opacity)


def test_invalid_utf8_or_directory_falls_back(tmp_path):
    from kumquat.gui.appearance import Appearance, load_appearance

    path = tmp_path / "appearance.toml"
    path.write_bytes(b"\xff\xfe")
    assert load_appearance(path) == Appearance()
    assert load_appearance(tmp_path) == Appearance()


@pytest.mark.parametrize("xdg", [True, False])
def test_default_path_respects_xdg_or_home(tmp_path, monkeypatch, xdg):
    from kumquat.gui.appearance import Appearance, load_appearance

    monkeypatch.setenv("HOME", str(tmp_path))
    if xdg:
        root = tmp_path / "config"
        monkeypatch.setenv("XDG_CONFIG_HOME", str(root))
    else:
        root = tmp_path / ".config"
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    path = root / "kumquat/appearance.toml"
    path.parent.mkdir(parents=True)
    path.write_text('[appearance]\nstyle = "glass"\n')
    assert load_appearance() == Appearance("glass", 0.90)


@pytest.mark.parametrize("style, opacity", [
    ("glass; } * {", 0.9), ("GLASS", 0.9), ([], 0.9),
    ("glass", float("nan")), ("glass", float("inf")), ("glass", -1),
    ("glass", 1.1), ("glass", True), ("glass", "0.9"), ("glass", None),
])
def test_invalid_programmatic_preferences_raise(style, opacity):
    from kumquat.gui.appearance import Appearance

    with pytest.raises(ValueError):
        Appearance(style, opacity)


def test_old_config_folder_is_still_read_until_the_installer_migrates_it(
        tmp_path, monkeypatch):
    from kumquat.gui.appearance import Appearance, load_appearance

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    former = tmp_path / "tangerine-wheel/appearance.toml"
    former.parent.mkdir()
    former.write_text('[appearance]\nstyle = "glass"\nopacity = 0.8\n')
    assert load_appearance() == Appearance(style="glass", opacity=0.8)


def test_new_config_wins_over_the_old_one(tmp_path, monkeypatch):
    from kumquat.gui.appearance import load_appearance

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    for folder, style in (("tangerine-wheel", "glass"), ("kumquat", "opaque")):
        path = tmp_path / folder / "appearance.toml"
        path.parent.mkdir()
        path.write_text(f'[appearance]\nstyle = "{style}"\n')
    assert load_appearance().style == "opaque"
