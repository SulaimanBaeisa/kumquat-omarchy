"""User shortcut installation preserves other apps' configuration."""

import runpy
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/install-shortcuts.py"


def installer():
    return runpy.run_path(str(SCRIPT))


def test_invalid_checkout_does_not_change_configuration(tmp_path):
    api = installer()
    with pytest.raises(ValueError, match="complete Kumquat checkout"):
        api["install"](tmp_path / "missing-repo", tmp_path)
    assert not (tmp_path / ".config/hypr/bindings.lua").exists()


def test_install_both_shortcuts_and_preserve_other_configuration(tmp_path):
    api = installer()
    bindings = tmp_path / ".config/hypr/bindings.lua"
    bindings.parent.mkdir(parents=True)
    original = (
        'o.bind("SUPER + H", "My terminal", "foot")\n'
        'o.bind("SUPER + E", "Kumquat", "kumquat --gui")\n'
    )
    bindings.write_text(original)
    accels = tmp_path / ".config/nautilus/scripts-accels"
    accels.parent.mkdir(parents=True)
    accels.write_text("<Control>F12 Another script\n")
    api["install"](SCRIPT.parents[1], tmp_path)
    content = bindings.read_text()
    assert 'o.bind("SUPER + H", "My terminal", "foot")' in content
    assert 'hl.unbind("SUPER + SHIFT + E")' not in content
    assert content.count('o.bind("SUPER + E"') == 1
    assert 'o.bind("SUPER + SHIFT + E"' not in content
    # The capture controller, not a window-wide native accelerator, owns E.
    assert accels.read_text() == "<Control>F12 Another script\n"
    extension = tmp_path / ".local/share/nautilus-python/extensions/nautilus-kumquat.py"
    assert (
        extension.read_text()
        == (SCRIPT.parents[1] / "extensions/nautilus-kumquat.py").read_text()
    )
    script = tmp_path / ".local/share/nautilus/scripts/Kumquat Actions"
    assert script.stat().st_mode & 0o111
    assert "--gui --from-nautilus --tab actions" in script.read_text()
    assert "wl-copy" not in script.read_text()
    assert "wl-paste" not in script.read_text()
    backups = list(bindings.parent.glob("bindings.lua.bak.*"))
    assert any(p.read_text() == original for p in backups)


def test_installer_is_idempotent(tmp_path):
    api = installer()
    api["install"](SCRIPT.parents[1], tmp_path)
    target = tmp_path / ".config/hypr/bindings.lua"
    first = target.read_text()
    api["install"](SCRIPT.parents[1], tmp_path)
    assert target.read_text() == first
    accels = tmp_path / ".config/nautilus/scripts-accels"
    assert accels.read_text().count("Kumquat Actions") == 0
    assert not list(target.parent.glob("*.bak.*"))


def test_conflicting_nautilus_accelerator_does_not_get_overwritten(tmp_path):
    api = installer()
    accels = tmp_path / ".config/nautilus/scripts-accels"
    accels.parent.mkdir(parents=True)
    original = "<Shift>e Existing script\n"
    accels.write_text(original)
    with pytest.raises(ValueError, match="already assigned"):
        api["install"](SCRIPT.parents[1], tmp_path)
    assert accels.read_text() == original
    assert not (tmp_path / ".local/bin/kumquat").exists()


# --- migration from the product's former name -------------------------------

OLD_RULE = (
    'o.window("^(dev\\\\.tangerine\\\\.wheel)$", '
    "{ float = true, center = true, size = { 520, 640 } })\n"
)
NEW_RULE = (
    'o.window("^(dev\\\\.kumquat\\\\.app)$", '
    "{ float = true, center = true, size = { 520, 640 } })\n"
)


def _former_install(home):
    """What a user of the old 'Tangerine' build has on disk."""
    hypr = home / ".config/hypr"
    hypr.mkdir(parents=True)
    (hypr / "bindings.lua").write_text(
        'o.bind("SUPER + H", "My terminal", "foot")\n'
        "-- BEGIN Tangerine shortcuts (managed)\n"
        'hl.unbind("SUPER + E")\n'
        'o.bind("SUPER + E", "Tangerine browser", "/h/.local/bin/old --gui")\n'
        "-- END Tangerine shortcuts (managed)\n"
    )
    (hypr / "hyprland.lua").write_text(
        'o.window("^(other)$", { float = true })\n' + OLD_RULE
    )
    launcher = home / ".local/bin/tangerine-wheel"
    script = home / ".local/share/nautilus/scripts/Tangerine Actions"
    extension = home / ".local/share/nautilus-python/extensions/nautilus-tangerine.py"
    for path, text in (
        (launcher, "old launcher"),
        (script, "old script"),
        (extension, "old extension"),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    accels = home / ".config/nautilus/scripts-accels"
    accels.parent.mkdir(parents=True, exist_ok=True)
    accels.write_text("<Shift>e Tangerine Actions\n<Control>F12 Another script\n")
    appearance = home / ".config/tangerine-wheel/appearance.toml"
    appearance.parent.mkdir(parents=True)
    appearance.write_text('[appearance]\nstyle = "glass"\nopacity = 0.90\n')
    return launcher, script, extension, accels, appearance


def test_former_binding_block_is_replaced_not_duplicated(tmp_path):
    _former_install(tmp_path)
    installer()["install"](SCRIPT.parents[1], tmp_path)
    content = (tmp_path / ".config/hypr/bindings.lua").read_text()
    assert 'o.bind("SUPER + H", "My terminal", "foot")' in content
    assert content.count('o.bind("SUPER + E"') == 1
    assert "Tangerine" not in content and "tangerine" not in content
    assert "BEGIN Kumquat shortcuts (managed)" in content


def test_former_files_are_retired_with_a_backup_copy(tmp_path):
    launcher, script, extension, accels, _ = _former_install(tmp_path)
    installer()["install"](SCRIPT.parents[1], tmp_path)
    for old in (launcher, script, extension):
        assert not old.exists(), old
    kept = {
        p.name: p.read_text()
        for p in (tmp_path / ".local/share/kumquat/legacy-backup").rglob("*")
        if p.is_file()
    }
    assert kept == {
        "tangerine-wheel": "old launcher",
        "Tangerine Actions": "old script",
        "nautilus-tangerine.py": "old extension",
    }
    assert accels.read_text() == "<Control>F12 Another script\n"
    assert (tmp_path / ".local/bin/kumquat").exists()


def test_appearance_choice_moves_to_the_new_config_folder(tmp_path):
    *_, appearance = _former_install(tmp_path)
    installer()["install"](SCRIPT.parents[1], tmp_path)
    new = tmp_path / ".config/kumquat/appearance.toml"
    assert new.read_text() == appearance.read_text()
    assert appearance.exists()  # copied, never deleted


def test_appearance_already_in_the_new_folder_is_not_overwritten(tmp_path):
    _former_install(tmp_path)
    new = tmp_path / ".config/kumquat/appearance.toml"
    new.parent.mkdir(parents=True)
    new.write_text('[appearance]\nstyle = "opaque"\n')
    installer()["install"](SCRIPT.parents[1], tmp_path)
    assert new.read_text() == '[appearance]\nstyle = "opaque"\n'


def test_window_rule_for_the_old_class_is_updated(tmp_path):
    _former_install(tmp_path)
    installer()["install"](SCRIPT.parents[1], tmp_path)
    rules = tmp_path / ".config/hypr/hyprland.lua"
    assert rules.read_text() == 'o.window("^(other)$", { float = true })\n' + NEW_RULE
    assert list(rules.parent.glob("hyprland.lua.bak.*"))


RULE_LINE = (
    'o.window("^(dev\\\\.kumquat\\\\.app)$", '
    "{ float = true, center = true, size = { 520, 640 } })"
)
OTHER_RULE = 'o.window("^(other)$", { float = true })\n'


def test_missing_window_rule_is_added_in_a_marked_block(tmp_path, capsys):
    """Users should not have to paste Lua into a file by hand."""
    hypr = tmp_path / ".config/hypr"
    hypr.mkdir(parents=True)
    (hypr / "hyprland.lua").write_text(OTHER_RULE)
    installer()["install"](SCRIPT.parents[1], tmp_path)
    text = (hypr / "hyprland.lua").read_text()
    assert text.startswith(OTHER_RULE), "existing configuration must stay first"
    assert "-- BEGIN Kumquat window rule (managed)" in text
    assert "-- END Kumquat window rule (managed)" in text
    assert text.count(RULE_LINE) == 1
    assert list(hypr.glob("hyprland.lua.bak.*")), "a backup copy must be kept"
    assert "floating-window rule" in capsys.readouterr().out


def test_window_rule_is_not_added_twice(tmp_path):
    hypr = tmp_path / ".config/hypr"
    hypr.mkdir(parents=True)
    (hypr / "hyprland.lua").write_text(OTHER_RULE)
    api = installer()
    api["install"](SCRIPT.parents[1], tmp_path)
    once = (hypr / "hyprland.lua").read_text()
    api["install"](SCRIPT.parents[1], tmp_path)
    assert (hypr / "hyprland.lua").read_text() == once


def test_a_handwritten_window_rule_is_left_alone(tmp_path):
    hypr = tmp_path / ".config/hypr"
    hypr.mkdir(parents=True)
    mine = OTHER_RULE + "-- my popup\n" + RULE_LINE.replace("520, 640", "700, 500") + "\n"
    (hypr / "hyprland.lua").write_text(mine)
    installer()["install"](SCRIPT.parents[1], tmp_path)
    assert (hypr / "hyprland.lua").read_text() == mine


def test_no_hyprland_config_is_never_created(tmp_path, capsys):
    """On a system without Omarchy's hyprland.lua, do not invent one."""
    installer()["install"](SCRIPT.parents[1], tmp_path)
    assert not (tmp_path / ".config/hypr/hyprland.lua").exists()
    assert "hyprland.lua" in capsys.readouterr().out


def _tree(home):
    """Every file's text, ignoring backups, which legitimately grow per run."""
    return {
        path: path.read_text()
        for path in home.rglob("*")
        if path.is_file()
        and ".bak." not in path.name
        and "legacy-backup" not in str(path)
    }


def test_migration_is_idempotent(tmp_path):
    _former_install(tmp_path)
    api = installer()
    api["install"](SCRIPT.parents[1], tmp_path)
    snapshot = _tree(tmp_path)
    api["install"](SCRIPT.parents[1], tmp_path)
    assert _tree(tmp_path) == snapshot
