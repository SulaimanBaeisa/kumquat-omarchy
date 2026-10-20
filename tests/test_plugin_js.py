"""Run the Node tests for Launch.js from pytest, so one command covers everything.

Skipped when Node.js is not installed; CI runs `node --test` directly as well.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_launch_js_node_tests_pass():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    tests = sorted((ROOT / "tests/js").glob("*.test.mjs"))
    assert tests, "no Node tests found"
    done = subprocess.run(
        [node, "--test", *map(str, tests)], capture_output=True, text=True, timeout=120
    )
    assert done.returncode == 0, done.stdout[-3000:] + done.stderr[-1000:]
