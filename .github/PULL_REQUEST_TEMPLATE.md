## What this changes

<!-- One or two sentences. Link the suggestion/issue if there is one. -->

## How I checked it

<!-- Commands you ran and what they printed, e.g. pytest, ruff, the real-GTK scripts. -->

- [ ] `pytest`, `ruff check src tests scripts`, `node --test tests/js/*.test.mjs` and `python3 scripts/validate-plugin.py` pass
- [ ] New behaviour has a test (a bug fix has a regression test)
- [ ] No personal data: no home paths, usernames, emails, or real documents in code, tests or images
- [ ] UI changes include screenshots made with `tests/make_screenshots.py`
- [ ] Changes to `manifest.json`, `*.qml` or `Launch.js` keep `tests/test_plugin_qml.py` and `tests/js/` passing, and `version` in `manifest.json` and `pyproject.toml` match

The maintainer reviews every pull request; nothing is merged without approval.
