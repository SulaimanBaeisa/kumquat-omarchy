# Contributing to Kumquat (Omarchy plugin)

Thanks for helping. This is a small project; the goal is a converter that does what it says
and says honestly when it cannot.

## Set up

```bash
git clone https://github.com/SulaimanBaeisa/omarchy-plugin-kumquat.git && cd omarchy-plugin-kumquat
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt ruff PySide6-Essentials
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check src tests scripts
node --test tests/js/*.test.mjs
python3 scripts/validate-plugin.py
```

GUI checks need a Wayland session and the system Python that has PyGObject (`/usr/bin/python3`);
the README's *Development* section lists them. Run them from a terminal, not a headless shell.

## How changes are accepted

Suggestions and pull requests are welcome, but **only the maintainer changes the code**:
`main` is protected, direct pushes are not accepted, and every pull request needs the
maintainer's approval (see `.github/CODEOWNERS`). For anything bigger than a small fix, open a
*Suggestion* issue first so we can agree on the idea before you spend time on it.

## Ground rules

- **Test first.** Add a failing test, then the fix. Bug fixes need a regression test that fails
  without the fix.
- **Prove effects, not exit codes.** A converter test should open the output and check its
  content, not only that a file appeared. Report results as PASS / FAIL / UNSUPPORTED /
  UNTESTED; never count an untested case as working.
- **Real fixtures only.** Do not rename a file to fake a format. If you cannot produce a genuine
  sample, leave the case UNTESTED and say why.
- **Never touch the user's originals.** Outputs go beside the source with collision-safe names;
  existing files are never overwritten. *Move* is the single explicit exception.
- **Local only.** No network calls, telemetry or uploads.
- **No personal data in the repo.** Screenshots must come from `tests/make_screenshots.py`
  (synthetic files, widget snapshots), not a screen capture. Check images and logs for home
  paths, usernames and emails before committing.
- **Keep the plugin small and honest.** The QML the shell loads runs unsandboxed inside the user's
  shell. It may only start Kumquat's own launcher; it must not read files, open network
  connections, run installers or use `sudo`. Installing the plugin must change nothing outside its
  folder, and only the opt-in `scripts/install-shortcuts.py` (with a matching `--uninstall`) may edit
  user configuration, backing up first.
- **Mind the marketplace limits.** At most 1,000 files, 8 MiB in total and 512 KiB per file, no
  symlinks, no downloaded text piped into a shell. `scripts/validate-plugin.py` checks all of it.
- **Keep the shortcut contract.** `Super+E` browses; `Shift+E` works only inside Files;
  `Super+Shift+E` stays Omarchy's Email. No global `Shift+E`.
- Themes: colours come from Omarchy's `colors.toml`; anything read from a theme file is
  untrusted and must be validated (see `src/kumquat/gui/theme.py`).

## Pull requests

Keep them small and focused. Describe what you ran and what it printed. Include before/after
screenshots for UI changes (regenerated with the script above, using a stock theme such as
`--theme tokyo-night`).

## Reporting problems

Open an issue with your Omarchy/Arch version, the file type, the exact message shown, and the
output of `hyprctl configerrors` if a shortcut is involved. **Do not attach private documents.**
For a security problem, see [SECURITY.md](SECURITY.md).
