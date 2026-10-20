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


# --- plugin launcher wrapper and --uninstall --------------------------------

import os  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402

REPO = SCRIPT.parents[1]
PLUGIN_ID = "io.github.sulaimanbaeisa.kumquat"


def _checkout(tmp_path):
    """A private copy of the plugin, so a test may delete or chmod its files."""
    dest = tmp_path / "plugin"
    shutil.copytree(
        REPO,
        dest,
        ignore=shutil.ignore_patterns(".git", ".venv", "__pycache__", ".pytest_cache"),
    )
    return dest


def _run_launcher(launcher, *args):
    env = {**os.environ, "KUMQUAT_PYTHON": sys.executable}
    return subprocess.run(
        [str(launcher), *args], capture_output=True, text=True, env=env, timeout=60
    )


def test_installed_launcher_runs_the_plugin_checkout(tmp_path):
    home = tmp_path / "home"
    checkout = _checkout(tmp_path)
    installer()["install"](checkout, home)
    launcher = home / ".local/bin/kumquat"
    assert launcher.stat().st_mode & 0o111
    photo = tmp_path / "photo.jpg"
    photo.write_bytes(b"fake")
    done = _run_launcher(launcher, "--files", str(photo), "--list")
    assert done.returncode == 0, done.stderr
    assert "Convert to PNG" in done.stdout


def test_installed_launcher_does_not_need_the_executable_bit(tmp_path):
    home = tmp_path / "home"
    checkout = _checkout(tmp_path)
    installer()["install"](checkout, home)
    (checkout / "bin/kumquat").chmod(0o644)
    photo = tmp_path / "photo.jpg"
    photo.write_bytes(b"fake")
    done = _run_launcher(home / ".local/bin/kumquat", "--files", str(photo), "--list")
    assert done.returncode == 0, done.stderr
    assert "Convert to PNG" in done.stdout


def test_installed_launcher_explains_a_removed_plugin(tmp_path):
    home = tmp_path / "home"
    checkout = _checkout(tmp_path)
    installer()["install"](checkout, home)
    shutil.rmtree(checkout)
    done = _run_launcher(home / ".local/bin/kumquat", "--gui")
    assert done.returncode == 127
    assert "was not found" in done.stderr
    assert "omarchy plugin add" in done.stderr


def test_a_checkout_without_the_launcher_is_refused(tmp_path):
    checkout = _checkout(tmp_path)
    (checkout / "bin/kumquat").unlink()
    with pytest.raises(ValueError, match="complete Kumquat checkout"):
        installer()["install"](checkout, tmp_path / "home")
    assert not (tmp_path / "home/.config/hypr/bindings.lua").exists()


def _seed_home(home):
    hypr = home / ".config/hypr"
    hypr.mkdir(parents=True)
    (hypr / "bindings.lua").write_text('o.bind("SUPER + H", "My terminal", "foot")\n')
    (hypr / "hyprland.lua").write_text('o.window("^(other)$", { float = true })\n')
    accels = home / ".config/nautilus/scripts-accels"
    accels.parent.mkdir(parents=True)
    accels.write_text("<Control>F12 Another script\n")
    appearance = home / ".config/kumquat/appearance.toml"
    appearance.parent.mkdir(parents=True)
    appearance.write_text('[appearance]\nstyle = "glass"\n')


def _snapshot(home):
    return {
        str(path.relative_to(home)): path.read_text()
        for path in sorted(home.rglob("*"))
        if path.is_file() and ".bak." not in path.name
    }


def test_uninstall_restores_the_files_the_installer_changed(tmp_path):
    home = tmp_path / "home"
    _seed_home(home)
    before = _snapshot(home)
    api = installer()
    api["install"](REPO, home)
    assert _snapshot(home) != before
    api["uninstall"](home)
    assert _snapshot(home) == before


def test_uninstall_keeps_backups_and_user_data(tmp_path):
    home = tmp_path / "home"
    _seed_home(home)
    api = installer()
    api["install"](REPO, home)
    backups = {p.name for p in home.rglob("*.bak.*")}
    assert backups, "install must have backed up the files it changed"
    api["uninstall"](home)
    assert backups <= {p.name for p in home.rglob("*.bak.*")}
    assert (home / ".config/kumquat/appearance.toml").read_text() == (
        '[appearance]\nstyle = "glass"\n'
    )


def test_uninstall_leaves_things_it_did_not_write(tmp_path):
    home = tmp_path / "home"
    _seed_home(home)
    mine = home / ".local/bin/kumquat"
    mine.parent.mkdir(parents=True)
    mine.write_text("#!/bin/sh\necho my own wrapper\n")
    hand_rule = RULE_LINE.replace("520, 640", "700, 500")
    rules = home / ".config/hypr/hyprland.lua"
    rules.write_text(rules.read_text() + "-- my popup\n" + hand_rule + "\n")
    api = installer()
    api["uninstall"](home)
    assert mine.read_text() == "#!/bin/sh\necho my own wrapper\n"
    assert hand_rule in rules.read_text()


def test_uninstall_is_idempotent_and_safe_on_an_empty_home(tmp_path, capsys):
    home = tmp_path / "home"
    home.mkdir()
    api = installer()
    api["uninstall"](home)
    api["uninstall"](home)
    assert _snapshot(home) == {}
    assert f"omarchy plugin remove {PLUGIN_ID}" in capsys.readouterr().out


def test_uninstall_after_install_twice_matches_a_single_uninstall(tmp_path):
    home = tmp_path / "home"
    _seed_home(home)
    before = _snapshot(home)
    api = installer()
    api["install"](REPO, home)
    api["install"](REPO, home)
    api["uninstall"](home)
    api["uninstall"](home)
    assert _snapshot(home) == before


def test_command_line_uninstall_flag(tmp_path):
    home = tmp_path / "home"
    _seed_home(home)
    before = _snapshot(home)
    env = {**os.environ, "HOME": str(home)}
    subprocess.run(
        [sys.executable, str(SCRIPT)], env=env, check=True, capture_output=True
    )
    assert _snapshot(home) != before
    done = subprocess.run(
        [sys.executable, str(SCRIPT), "--uninstall"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert done.returncode == 0, done.stderr
    assert _snapshot(home) == before


def test_a_user_of_the_standalone_checkout_is_moved_onto_the_plugin(tmp_path):
    """Installing the plugin's shortcuts over the old standalone ones replaces them."""
    home = tmp_path / "home"
    launcher = home / ".local/bin/kumquat"
    launcher.parent.mkdir(parents=True)
    old_launcher = (
        "#!/bin/sh\n"
        "# User install: system Python for GTK, source from this checkout.\n"
        "exec /usr/bin/python3 -c 'old standalone code' \"$@\"\n"
    )
    launcher.write_text(old_launcher)
    bindings = home / ".config/hypr/bindings.lua"
    bindings.parent.mkdir(parents=True)
    bindings.write_text(
        'o.bind("SUPER + H", "My terminal", "foot")\n'
        "-- BEGIN Kumquat shortcuts (managed)\n"
        'hl.unbind("SUPER + E")\n'
        'o.bind("SUPER + E", "Kumquat browser", "/old/path/kumquat --gui")\n'
        "-- END Kumquat shortcuts (managed)\n"
    )
    installer()["install"](REPO, home)
    assert "old standalone code" not in launcher.read_text()
    assert str(REPO / "bin/kumquat") in launcher.read_text()
    assert any(
        p.read_text() == old_launcher for p in launcher.parent.glob("kumquat.bak.*")
    )
    content = bindings.read_text()
    assert content.count('o.bind("SUPER + E"') == 1
    assert "/old/path" not in content
    assert 'o.bind("SUPER + H", "My terminal", "foot")' in content
