"""scripts/doctor.py reports what is missing, using only what it can see.

Every external lookup is faked, so these tests do not depend on this machine's
GTK, LibreOffice or Omarchy installation.
"""

import runpy
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/doctor.py"


@pytest.fixture
def doctor():
    return runpy.run_path(str(SCRIPT))


def completed(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


def patch(doctor, monkeypatch, *, which=(), run=None, environ=None):
    """Make the script's `shutil.which` / `subprocess.run` / environment fake."""
    available = set(which)
    shutil_module = doctor["shutil"]
    monkeypatch.setattr(
        shutil_module,
        "which",
        lambda name: f"/fake/{name}" if name in available else None,
    )
    if run is not None:
        monkeypatch.setattr(doctor["subprocess"], "run", run)
    env = doctor["os"].environ
    monkeypatch.setattr(doctor["os"], "environ", {**env, **(environ or {})})


def test_gtk_check_reports_the_version(doctor, monkeypatch):
    patch(doctor, monkeypatch, run=lambda *a, **k: completed(0, "4.14.2\n"))
    status, label, detail = doctor["check_gtk"]("/usr/bin/python3")
    assert status == "OK"
    assert "4.14.2" in detail


def test_gtk_check_flags_an_old_gtk(doctor, monkeypatch):
    patch(doctor, monkeypatch, run=lambda *a, **k: completed(3, "4.10.1\n"))
    status, _, detail = doctor["check_gtk"]("/usr/bin/python3")
    assert status == "FAIL"
    assert "too old" in detail


def test_gtk_check_explains_a_missing_binding(doctor, monkeypatch):
    patch(
        doctor,
        monkeypatch,
        run=lambda *a, **k: completed(
            1, "", "Traceback\nModuleNotFoundError: No module named 'gi'\n"
        ),
    )
    status, _, detail = doctor["check_gtk"]("/usr/bin/python3")
    assert status == "FAIL"
    assert "No module named 'gi'" in detail
    assert "python-gobject" in detail


def test_missing_interpreter_is_a_failure_not_a_crash(doctor, monkeypatch):
    def boom(*args, **kwargs):
        raise FileNotFoundError("no such interpreter")

    patch(doctor, monkeypatch, run=boom)
    assert doctor["check_gtk"]("/nope")[0] == "FAIL"
    assert doctor["check_python_modules"]("/nope")[0] == "FAIL"


def test_required_tools_fail_and_optional_ones_only_note(doctor, monkeypatch):
    patch(doctor, monkeypatch, which=())
    by_status = {}
    for status, label, _ in doctor["check_tools"]():
        by_status.setdefault(status, []).append(label)
    assert any("ffmpeg" in label for label in by_status["FAIL"])
    assert any("ffprobe" in label for label in by_status["FAIL"])
    assert any("soffice" in label for label in by_status["note"])
    assert all("soffice" not in label for label in by_status["FAIL"])


def test_any_one_alias_satisfies_an_optional_tool(doctor, monkeypatch):
    patch(doctor, monkeypatch, which={"ffmpeg", "ffprobe", "bsdtar"})
    results = {label: status for status, label, _ in doctor["check_tools"]()}
    assert results["7z (RAR archives)"] == "OK"


def test_optional_modules_are_notes(doctor, monkeypatch):
    patch(
        doctor, monkeypatch, run=lambda *a, **k: completed(1, "", "ModuleNotFoundError")
    )
    results = doctor["check_optional_modules"]("/usr/bin/python3")
    assert results
    assert {status for status, _, _ in results} == {"note"}


def test_launcher_check_runs_the_real_launcher(doctor, monkeypatch):
    monkeypatch.setenv("KUMQUAT_PYTHON", sys.executable)
    status, _, detail = doctor["check_launcher"]()
    assert status == "OK", detail


def test_launcher_check_reports_a_broken_launcher(doctor, monkeypatch):
    patch(doctor, monkeypatch, run=lambda *a, **k: completed(1, "", "ImportError: gi"))
    status, _, detail = doctor["check_launcher"]()
    assert status == "FAIL"
    assert "ImportError" in detail


def test_omarchy_absent_is_only_a_note(doctor, monkeypatch):
    patch(doctor, monkeypatch, which=())
    [(status, label, _)] = doctor["check_omarchy"]()
    assert status == "note"
    assert "omarchy" in label


def test_plugin_listed_by_omarchy(doctor, monkeypatch):
    listing = (
        "omarchy.clock  enabled\nio.github.sulaimanbaeisa.kumquat   0.1.0   enabled\n"
    )
    patch(
        doctor, monkeypatch, which={"omarchy"}, run=lambda *a, **k: completed(0, listing)
    )
    [(status, _, detail)] = doctor["check_omarchy"]()
    assert status == "OK"
    assert "enabled" in detail


def test_plugin_not_listed_tells_you_how_to_add_it(doctor, monkeypatch):
    patch(
        doctor,
        monkeypatch,
        which={"omarchy"},
        run=lambda *a, **k: completed(0, "omarchy.clock\n"),
    )
    [(status, _, detail)] = doctor["check_omarchy"]()
    assert status == "note"
    assert "omarchy plugin add" in detail


def test_omarchy_command_failure_is_a_note(doctor, monkeypatch):
    patch(
        doctor,
        monkeypatch,
        which={"omarchy"},
        run=lambda *a, **k: completed(2, "", "boom"),
    )
    assert doctor["check_omarchy"]()[0][0] == "note"


def test_session_check(doctor, monkeypatch):
    patch(doctor, monkeypatch, environ={"WAYLAND_DISPLAY": "wayland-1"})
    assert doctor["check_session"]()[0] == "OK"
    monkeypatch.delitem(doctor["os"].environ, "WAYLAND_DISPLAY")
    assert doctor["check_session"]()[0] == "note"


def test_exit_status_follows_the_required_checks(doctor, monkeypatch, capsys):
    ok = [("OK", "a", "x"), ("note", "b", "y")]
    monkeypatch.setitem(doctor["main"].__globals__, "run_checks", lambda: ok)
    assert doctor["main"]() == 0
    assert "All required checks passed" in capsys.readouterr().out
    bad = ok + [("FAIL", "c", "z")]
    monkeypatch.setitem(doctor["main"].__globals__, "run_checks", lambda: bad)
    assert doctor["main"]() == 1
    out = capsys.readouterr().out
    assert "[FAIL] c" in out
    assert "1 required check(s) failed" in out


def test_runs_as_a_script_and_never_edits_anything(tmp_path):
    before = sorted(
        p.name for p in ROOT.rglob("*") if p.is_file() and ".git" not in p.parts
    )
    done = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
        env={
            "PATH": "/usr/bin:/bin",
            "HOME": str(tmp_path),
            "KUMQUAT_PYTHON": sys.executable,
        },
        timeout=120,
    )
    assert done.returncode in (0, 1), done.stderr
    assert "Python with GTK" in done.stdout
    after = sorted(
        p.name for p in ROOT.rglob("*") if p.is_file() and ".git" not in p.parts
    )
    assert [n for n in after if not n.endswith(".pyc")] == [
        n for n in before if not n.endswith(".pyc")
    ]


def _fake_gi(root, minor):
    """A stand-in `gi` package whose Gtk reports version 4.<minor>.2."""
    package = root / "gi"
    (package / "repository").mkdir(parents=True)
    (package / "__init__.py").write_text(
        "def require_version(namespace, version):\n    pass\n"
    )
    (package / "repository/__init__.py").write_text("")
    (package / "repository/Gtk.py").write_text(
        "get_major_version = lambda: 4\n"
        f"get_minor_version = lambda: {minor}\n"
        "get_micro_version = lambda: 2\n"
    )


def test_the_real_gtk_probe_runs_and_judges_the_version(doctor, tmp_path, monkeypatch):
    """The probe is a code string; run it as real Python against a fake gi."""
    new, old = tmp_path / "new", tmp_path / "old"
    _fake_gi(new, 14)
    _fake_gi(old, 10)
    monkeypatch.setenv("PYTHONPATH", str(new))
    status, _, detail = doctor["check_gtk"](sys.executable)
    assert (status, "4.14.2" in detail) == ("OK", True)
    monkeypatch.setenv("PYTHONPATH", str(old))
    status, _, detail = doctor["check_gtk"](sys.executable)
    assert status == "FAIL"
    assert "4.10.2" in detail
    assert "too old" in detail
