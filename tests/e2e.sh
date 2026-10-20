#!/bin/bash
# End-to-end smoke: venv pytest + registry>=275 assert + --list smoke.
# Prints E2E-OK on success. Offline; missing optional backends skip, never fail.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== e2e: pytest =="
PYTHONPATH=src .venv/bin/python -m pytest -q

echo "== e2e: registry row count =="
COUNT=$(PYTHONPATH=src .venv/bin/python -c \
    "import kumquat.registry_data, kumquat.registry as r; print(len(r.REGISTRY))")
echo "registry rows: $COUNT"
[ "$COUNT" -ge 275 ] || { echo "E2E-FAIL: registry $COUNT < 275"; exit 1; }

echo "== e2e: --list smoke =="
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
printf 'fake' > "$TMP/photo.jpg"
OUT=$(PYTHONPATH=src .venv/bin/python -m kumquat.cli \
    --files "$TMP/photo.jpg" --list)
echo "$OUT" | grep -q "Convert to PNG" || { echo "E2E-FAIL: no Convert to PNG"; exit 1; }
echo "$OUT" | grep -q "Choose a conversion format" || { echo "E2E-FAIL: no prompt"; exit 1; }

echo "E2E-OK"
