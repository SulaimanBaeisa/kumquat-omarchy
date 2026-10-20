"""The repository is a valid Omarchy plugin, and the validator really enforces the rules.

Positive fixtures for the risky patterns are assembled from fragments at run time,
so this file never contains the text the marketplace's static scan looks for.
"""

import json
import re
import runpy
import shutil
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
api = runpy.run_path(str(ROOT / "scripts/validate-plugin.py"))
validate = api["validate"]

GOOD_MANIFEST = {
    "schemaVersion": 1,
    "id": "io.github.someone.example",
    "name": "Example",
    "version": "1.0.0",
    "author": "Someone",
    "description": "Does one thing.",
    "kinds": ["overlay", "bar-widget"],
    "entryPoints": {"overlay": "Overlay.qml", "barWidget": "BarWidget.qml"},
    "barWidget": {
        "displayName": "Example",
        "category": "Tools",
        "allowMultiple": False,
        "defaultSection": "right",
    },
}
GOOD_README = "# Example\n\n## Install\n\nx\n\n## Remove\n\nx\n\n## Dependencies\n\nx\n"


@pytest.fixture
def plugin(tmp_path):
    """A minimal plugin that passes; tests then break one thing at a time."""
    (tmp_path / "manifest.json").write_text(json.dumps(GOOD_MANIFEST))
    (tmp_path / "Overlay.qml").write_text("import QtQuick\nItem {}\n")
    (tmp_path / "BarWidget.qml").write_text("import QtQuick\nItem {}\n")
    (tmp_path / "README.md").write_text(GOOD_README)
    (tmp_path / "LICENSE").write_text("MIT\n")
    return tmp_path


def edit_manifest(plugin, change):
    path = plugin / "manifest.json"
    data = json.loads(path.read_text())
    change(data)
    path.write_text(json.dumps(data))


def problems(plugin):
    return "\n".join(validate(plugin))


# --- this repository --------------------------------------------------------


def test_this_repository_passes():
    assert validate(ROOT) == []


def test_version_is_the_same_everywhere():
    manifest = json.loads((ROOT / "manifest.json").read_text())
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert manifest["version"] == pyproject["project"]["version"]


def test_installer_and_manifest_agree_on_the_plugin_id():
    manifest = json.loads((ROOT / "manifest.json").read_text())
    installer = runpy.run_path(str(ROOT / "scripts/install-shortcuts.py"))
    assert installer["PLUGIN_ID"] == manifest["id"]
    assert manifest["id"] in (ROOT / "README.md").read_text()


def test_the_launcher_is_what_the_entry_points_start():
    assert (ROOT / "bin/kumquat").is_file()
    for name in ("Overlay.qml", "BarWidget.qml"):
        assert '"bin/kumquat"' in (ROOT / name).read_text()


def test_manifest_kinds_match_the_shipped_entry_points():
    manifest = json.loads((ROOT / "manifest.json").read_text())
    assert sorted(manifest["kinds"]) == ["bar-widget", "overlay"]
    assert manifest["entryPoints"] == {
        "overlay": "Overlay.qml",
        "barWidget": "BarWidget.qml",
    }


# --- the validator ----------------------------------------------------------


def test_a_minimal_plugin_passes(plugin):
    assert validate(plugin) == []


def test_not_a_directory(tmp_path):
    assert "not a directory" in problems(tmp_path / "nope")


@pytest.mark.parametrize(
    "field", ["id", "name", "version", "author", "description", "kinds", "entryPoints"]
)
def test_every_required_field_is_required(plugin, field):
    edit_manifest(plugin, lambda m: m.pop(field))
    assert f"missing required field: {field}" in problems(plugin)


def test_manifest_must_exist_and_parse(plugin):
    (plugin / "manifest.json").write_text("{nope")
    assert "not valid JSON" in problems(plugin)
    (plugin / "manifest.json").unlink()
    assert "manifest.json must be a regular file" in problems(plugin)
    (plugin / "manifest.json").write_text("[]")
    assert "JSON object" in problems(plugin)


def test_schema_version_must_be_1(plugin):
    edit_manifest(plugin, lambda m: m.update(schemaVersion=2))
    assert "schemaVersion must be 1" in problems(plugin)


@pytest.mark.parametrize(
    ("plugin_id", "expected"),
    [
        ("omarchy.mine", "reserved"),
        ("plain", "namespaced"),
        ("Io.Github.Me.Thing", "namespaced"),
        ("io.github.me.thing_x", "namespaced"),
        ("io..github", "namespaced"),
        ("", "non-empty"),
    ],
)
def test_ids_must_be_namespaced_lowercase_and_not_reserved(plugin, plugin_id, expected):
    edit_manifest(plugin, lambda m: m.update(id=plugin_id))
    assert expected in problems(plugin)


def test_version_length_is_limited_for_marketplace_display(plugin):
    edit_manifest(plugin, lambda m: m.update(version="1" * 65))
    assert "version is longer than 64" in problems(plugin)
    edit_manifest(plugin, lambda m: m.update(version="1" * 64))
    assert validate(plugin) == []


def test_description_stays_short(plugin):
    edit_manifest(plugin, lambda m: m.update(description="x" * 201))
    assert "description is longer" in problems(plugin)


def test_unknown_and_duplicate_kinds(plugin):
    edit_manifest(plugin, lambda m: m.update(kinds=["overlay", "overlay", "dock"]))
    text = problems(plugin)
    assert "twice" in text
    assert "unknown kind 'dock'" in text


def test_each_kind_needs_its_entry_point(plugin):
    edit_manifest(plugin, lambda m: m["entryPoints"].pop("overlay"))
    assert "kind 'overlay' needs entryPoints.overlay" in problems(plugin)


def test_entry_points_without_a_kind_are_rejected(plugin):
    edit_manifest(plugin, lambda m: m["entryPoints"].update(panel="Overlay.qml"))
    assert "entryPoints.panel has no matching entry in kinds" in problems(plugin)


@pytest.mark.parametrize(
    "bad", ["/etc/passwd", "../outside.qml", "a/../../b.qml", "", "a\\b.qml"]
)
def test_entry_points_must_be_safe_relative_paths(plugin, bad):
    edit_manifest(plugin, lambda m: m["entryPoints"].update(overlay=bad))
    assert "safe relative path" in problems(plugin)


def test_entry_point_files_must_exist(plugin):
    (plugin / "Overlay.qml").unlink()
    assert "not a regular file" in problems(plugin)


def test_bar_widget_needs_its_block(plugin):
    edit_manifest(plugin, lambda m: m.pop("barWidget"))
    assert "needs a barWidget object" in problems(plugin)


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        (lambda w: w.update(displayName=""), "barWidget.displayName"),
        (lambda w: w.pop("category"), "barWidget.category"),
        (lambda w: w.update(allowMultiple="no"), "allowMultiple"),
        (lambda w: w.update(defaultSection="middle"), "defaultSection"),
    ],
)
def test_bar_widget_block_is_checked(plugin, change, expected):
    edit_manifest(plugin, lambda m: change(m["barWidget"]))
    assert expected in problems(plugin)


def test_overlay_only_plugin_needs_no_bar_widget_block(plugin):
    def overlay_only(m):
        m["kinds"] = ["overlay"]
        m["entryPoints"] = {"overlay": "Overlay.qml"}
        m.pop("barWidget")

    edit_manifest(plugin, overlay_only)
    assert validate(plugin) == []


# --- files, links and the scan limits ---------------------------------------


def test_symlinks_are_rejected(plugin):
    (plugin / "link.qml").symlink_to(plugin / "Overlay.qml")
    assert "link.qml: symlinks are not allowed" in problems(plugin)


def test_symlinked_manifest_is_rejected(plugin):
    real = plugin / "real.json"
    (plugin / "manifest.json").rename(real)
    (plugin / "manifest.json").symlink_to(real)
    assert "manifest.json must be a regular file" in problems(plugin)


def test_per_file_limit(plugin):
    (plugin / "big.bin").write_bytes(b"x" * (512 * 1024))
    assert validate(plugin) == []
    (plugin / "big.bin").write_bytes(b"x" * (512 * 1024 + 1))
    assert "per-file scan limit" in problems(plugin)


def test_total_size_limit(plugin):
    for index in range(17):
        (plugin / f"part{index}.bin").write_bytes(b"x" * (500 * 1024))
    assert "-byte scan limit" in problems(plugin)


def test_file_count_limit(plugin):
    for index in range(1000):
        (plugin / f"f{index}.txt").write_text("x")
    assert "file scan limit" in problems(plugin)


def test_tool_folders_are_not_counted(plugin):
    cache = plugin / ".git"
    cache.mkdir()
    (cache / "huge").write_bytes(b"x" * (9 * 1024 * 1024))
    (plugin / "__pycache__").mkdir()
    (plugin / "__pycache__" / "x.pyc").write_bytes(b"x" * (600 * 1024))
    assert validate(plugin) == []


# --- documentation ----------------------------------------------------------


def test_license_and_readme_are_required(plugin):
    (plugin / "LICENSE").unlink()
    assert "license file" in problems(plugin)
    (plugin / "README.md").unlink()
    assert "README.md is required" in problems(plugin)


@pytest.mark.parametrize(
    ("heading", "label"),
    [
        ("Install", "install steps"),
        ("Remove", "removal steps"),
        ("Dependencies", "external dependencies"),
    ],
)
def test_readme_must_cover_install_removal_and_dependencies(plugin, heading, label):
    (plugin / "README.md").write_text(GOOD_README.replace(f"## {heading}", "## Other"))
    assert f"README.md needs a heading for {label}" in problems(plugin)


def test_uninstall_and_requirements_headings_also_count(plugin):
    (plugin / "README.md").write_text(
        "# X\n\n## Installing\n\n## Uninstall\n\n## Requirements\n"
    )
    assert validate(plugin) == []


# --- the marketplace's static security baseline -----------------------------

FETCH = "cu" + "rl"
GET = "w" + "get"
SH = "s" + "h"
SUDO = "su" + "do"
CARGO = "car" + "go"


@pytest.mark.parametrize(
    ("text", "label"),
    [
        (f"{FETCH} -fsSL https://example.com/i | {SH}\n", "piped into a shell"),
        (f"{GET} -qO- https://example.com/i | {SUDO} bash\n", "piped into a shell"),
        (f"{FETCH} https://example.com/i | bash -s\n", "piped into a shell"),
        (f"bash <({FETCH} -s https://example.com/i)\n", "process substitution"),
        (f"{CARGO} install --git https://example.com/x\n", "commit pin"),
        (f"{CARGO} install --git https://example.com/x --rev abc123\n", "commit pin"),
        ("me ALL=(ALL) NO" + "PASSWD: ALL\n", "sudoers"),
        (f'{SUDO} kill "$(cat /tmp/app.pid)"\n', "pid file"),
        (f"{SUDO} kill $(cat /tmp/run/daemon.pid)\n", "pid file"),
    ],
)
def test_baseline_patterns_are_reported(plugin, text, label):
    (plugin / "setup.txt").write_text("line one\n" + text)
    found = problems(plugin)
    assert label in found
    assert "setup.txt:2" in found


@pytest.mark.parametrize(
    "text",
    [
        f"{SUDO} pacman -S --needed python gtk4\n",
        f"{FETCH} -o file.tgz https://example.com/f.tgz\n",
        f"{CARGO} install --git https://example.com/x --rev " + "a" * 40 + "\n",
        "kill $(cat ~/.cache/app.pid)\n",
        "echo hello | grep h\n",
    ],
)
def test_ordinary_text_is_not_flagged(plugin, text):
    (plugin / "notes.txt").write_text(text)
    assert validate(plugin) == []


def test_binary_files_are_not_scanned_as_text(plugin):
    (plugin / "image.png").write_bytes(
        b"\x89PNG\r\n\x1a\n\x00" + f"{FETCH} x | {SH}".encode()
    )
    assert validate(plugin) == []


def test_command_line_exit_codes(plugin, tmp_path, capsys):
    main = api["main"]
    assert main([str(plugin)]) == 0
    assert "OK" in capsys.readouterr().out
    (plugin / "README.md").unlink()
    assert main([str(plugin)]) == 1
    assert "FAIL: README.md is required" in capsys.readouterr().err


def test_copying_the_repository_keeps_it_valid(tmp_path):
    """No hidden dependency on being inside the original checkout."""
    dest = tmp_path / "copy"
    shutil.copytree(
        ROOT,
        dest,
        ignore=shutil.ignore_patterns(".git", ".venv", "__pycache__", ".pytest_cache"),
    )
    assert validate(dest) == []


# --- documentation links ----------------------------------------------------

MARKDOWN_FILES = sorted(
    [ROOT / "README.md", ROOT / "CONTRIBUTING.md", ROOT / "SECURITY.md"]
    + list((ROOT / "docs").glob("*.md"))
)


def _slug(heading: str) -> str:
    """GitHub's anchor for a heading: lowercase, no punctuation, spaces to hyphens."""
    text = re.sub(r"[`*]", "", heading.strip().lower())
    return re.sub(r"[^\w\- ]", "", text).replace(" ", "-")


def _anchors(path: Path) -> set[str]:
    in_fence = False
    found = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("```"):
            in_fence = not in_fence
        elif not in_fence and re.match(r"#{1,6} ", line):
            found.add(_slug(line.lstrip("#")))
    return found


def _links(path: Path):
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"```.*?```", "", text, flags=re.S)  # code samples are not links
    yield from re.findall(r"\]\(([^)\s]+)\)", text)
    yield from re.findall(r'(?:src|href)="([^"]+)"', text)


@pytest.mark.parametrize("doc", MARKDOWN_FILES, ids=lambda p: str(p.relative_to(ROOT)))
def test_relative_links_and_anchors_resolve(doc):
    broken = []
    for target in _links(doc):
        if re.match(r"[a-z][a-z0-9+.-]*:", target):  # https:, mailto:, ...
            continue
        name, _, anchor = target.partition("#")
        destination = (doc.parent / name).resolve() if name else doc
        if not destination.exists():
            broken.append(f"{target} (no such file)")
        elif (
            anchor and destination.suffix == ".md" and anchor not in _anchors(destination)
        ):
            broken.append(f"{target} (no such heading)")
    assert not broken, broken


def test_readme_names_every_command_it_tells_users_to_run():
    """The id and the repository URL in the README must be the real ones."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    manifest = json.loads((ROOT / "manifest.json").read_text())
    assert (
        "omarchy plugin add https://github.com/SulaimanBaeisa/omarchy-plugin-kumquat.git"
        in readme
    )
    for command in ("omarchy plugin remove", "omarchy plugin update", "omarchy bar move"):
        assert f"{command} {manifest['id']}" in readme
    assert "install-shortcuts.py --uninstall" in readme
