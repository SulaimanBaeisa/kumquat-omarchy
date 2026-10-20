"""bin/kumquat: the one launcher behind the bar button, summon and the wrapper."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def plugin(tmp_path):
    """A pristine copy of the plugin in a folder whose name needs quoting."""
    dest = tmp_path / "my plugin é"
    shutil.copytree(
        ROOT,
        dest,
        ignore=shutil.ignore_patterns(
            ".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache"
        ),
    )
    return dest


def launch(launcher, home, *args, cwd=None, **env):
    environment = {
        "PATH": os.environ["PATH"],
        "HOME": str(home),
        "KUMQUAT_PYTHON": sys.executable,
        **env,
    }
    return subprocess.run(
        ["/bin/sh", str(launcher), *args],
        capture_output=True,
        text=True,
        env=environment,
        cwd=cwd,
        timeout=60,
    )


def sample(tmp_path):
    photo = tmp_path / "photo.jpg"
    photo.write_bytes(b"only the name is used")
    return photo


def test_lists_conversions_from_any_directory(plugin, tmp_path):
    done = launch(
        plugin / "bin/kumquat",
        tmp_path / "home",
        "--files",
        str(sample(tmp_path)),
        "--list",
        cwd="/",
    )
    assert done.returncode == 0, done.stderr
    assert "Convert to PNG" in done.stdout


def test_arguments_with_spaces_and_quotes_arrive_intact(plugin, tmp_path):
    awkward = tmp_path / 'it\'s a "photo" $(x).jpg'
    awkward.write_bytes(b"x")
    done = launch(
        plugin / "bin/kumquat", tmp_path / "home", "--files", str(awkward), "--list"
    )
    assert done.returncode == 0, done.stderr
    assert str(awkward) in done.stdout


def test_works_through_a_symlink(plugin, tmp_path):
    link = tmp_path / "bin-on-path"
    link.symlink_to(plugin / "bin/kumquat")
    done = launch(link, tmp_path / "home", "--files", str(sample(tmp_path)), "--list")
    assert done.returncode == 0, done.stderr
    assert "Convert to PNG" in done.stdout


def test_exit_status_of_the_app_is_passed_on(plugin, tmp_path):
    done = launch(plugin / "bin/kumquat", tmp_path / "home", "--no-such-option")
    assert done.returncode == 2
    assert "usage: kumquat" in done.stderr


def test_nothing_is_written_into_the_plugin_folder(plugin, tmp_path):
    """Bytecode goes to the cache folder, so the checkout stays clean."""
    before = sorted(p.relative_to(plugin) for p in plugin.rglob("*"))
    home = tmp_path / "home"
    done = launch(
        plugin / "bin/kumquat", home, "--files", str(sample(tmp_path)), "--list"
    )
    assert done.returncode == 0, done.stderr
    assert sorted(p.relative_to(plugin) for p in plugin.rglob("*")) == before
    assert not list(plugin.rglob("__pycache__"))
    assert list((home / ".cache/kumquat/pycache").rglob("*.pyc")), (
        "bytecode should be cached"
    )


def test_cache_location_follows_xdg_cache_home(plugin, tmp_path):
    cache = tmp_path / "xdg"
    done = launch(
        plugin / "bin/kumquat",
        tmp_path / "home",
        "--files",
        str(sample(tmp_path)),
        "--list",
        XDG_CACHE_HOME=str(cache),
    )
    assert done.returncode == 0, done.stderr
    assert list((cache / "kumquat/pycache").rglob("*.pyc"))
    assert not (tmp_path / "home/.cache").exists()


def test_a_missing_interpreter_falls_back_to_python3_on_the_path(plugin, tmp_path):
    done = launch(
        plugin / "bin/kumquat",
        tmp_path / "home",
        "--files",
        str(sample(tmp_path)),
        "--list",
        KUMQUAT_PYTHON="/nonexistent/python",
        PATH=f"{Path(sys.executable).parent}:{os.environ['PATH']}",
    )
    assert done.returncode == 0, done.stderr


def test_no_python_at_all_gives_a_clear_message(plugin, tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    for tool in ("dirname", "readlink"):
        (empty / tool).symlink_to(shutil.which(tool))
    done = launch(
        plugin / "bin/kumquat",
        tmp_path / "home",
        "--list",
        KUMQUAT_PYTHON="/nonexistent/python",
        PATH=str(empty),
    )
    assert done.returncode == 127
    assert "python3 was not found" in done.stderr
