# Tool and action QA summary

## Reproduce

```sh
PYTHONPATH=src .venv/bin/python tests/qa_tools_sweep.py
# Optional: --json /path/to/scratch/tools.json --work-dir /path/to/empty/scratch-dir
.venv/bin/python -m pytest -q tests/test_tools_images.py tests/test_tools_media.py tests/test_tools_pdf.py tests/test_actions.py tests/test_tool_regressions.py tests/test_apply.py
```

The sweep generates a real local corpus using the generators in
`tests/qa_full_sweep.py`, derives its inventory from `files_listing` and
`tools_for`, and asserts that all 26 tool IDs and six action IDs are accounted
for. The 52 registered input keys include their genuine aliases. A cell is an
operation/input-key/selection-cardinality combination; single and homogeneous
pair selections are exercised **only where advertised**. Multi-only joins are
not credited as single-select support.

It returns nonzero on FAIL. The default result and corpus are under the runtime
scratch directory; the script refuses a nonempty `--work-dir`. It does not read
user documents, transfer files, launch terminals, modify the real clipboard, or
change compositor state. Move tests operate on disposable copies, not the corpus.
Every tool writes beside those disposable sources, then runs a second time to
check collision-safe names and unchanged original/output hashes.

## Verified snapshot

| Scope | PASS | FAIL | UNSUPPORTED | UNTESTED |
| --- | ---: | ---: | ---: | ---: |
| Tool cells | 285 | 0 | 1 | 0 |
| Action cells | 98 | 0 | 0 | 526 |
| All 910 advertised cells | 383 | 0 | 1 | 526 |
| Separate safety/fault-injection checks | 45 | 0 | 0 | 0 |

- Full pytest gate: **1,304 passed** (exit 0), including 4 tests for the RAR fixture.
- Ruff gate over owned sources/tests and the new sweep: **All checks passed!**
  (exit 0).
- Corpus hashes preserved: **true**. Every attempted tool also checks its
  disposable input hashes, including error paths.
- All 26 tool IDs have at least one real content/effect PASS. This does **not**
  mean all advertised cells, codecs, platform interactions, or variants work.
- The machine-readable result contains the complete per-cell list, evidence,
  options kwargs, per-operation totals, and nonpass reasons. Runtime artifacts
  are not committed. The verified matrix contains no host-specific home paths.

## Per-operation results

| Operation | PASS | FAIL | UNSUPPORTED | UNTESTED |
| --- | ---: | ---: | ---: | ---: |
| `compress` | 43 | 0 | 0 | 0 |
| `removeMetadata` | 44 | 0 | 0 | 0 |
| `editImage` | 10 | 0 | 0 | 0 |
| `annotateImage` | 10 | 0 | 0 | 0 |
| `frameImage` | 10 | 0 | 0 | 0 |
| `cropImage` | 20 | 0 | 0 | 0 |
| `redactImage` | 10 | 0 | 0 | 0 |
| `createCollage` | 11 | 0 | 0 | 0 |
| `trimVideo` | 13 | 0 | 0 | 0 |
| `cropVideo` | 13 | 0 | 0 | 0 |
| `changeVideoSpeed` | 13 | 0 | 0 | 0 |
| `joinVideos` | 7 | 0 | 0 | 0 |
| `videoSnapshots` | 6 | 0 | 0 | 0 |
| `splitVideo` | 6 | 0 | 0 | 0 |
| `redactVideo` | 6 | 0 | 0 | 0 |
| `muteVideo` | 12 | 0 | 1 | 0 |
| `normalizeAudio` | 8 | 0 | 0 | 0 |
| `audioToVideo` | 4 | 0 | 0 | 0 |
| `trimAudio` | 4 | 0 | 0 | 0 |
| `audioChannels` | 4 | 0 | 0 | 0 |
| `redactAudio` | 4 | 0 | 0 | 0 |
| `mergePDF` | 1 | 0 | 0 | 0 |
| `organizePDF` | 1 | 0 | 0 | 0 |
| `splitPDF` | 2 | 0 | 0 | 0 |
| `extractArchive` | 12 | 0 | 0 | 0 |
| `createPDF` | 11 | 0 | 0 | 0 |
| `share` | 0 | 0 | 0 | 98 |
| `float` | 0 | 0 | 0 | 98 |
| `copy` | 0 | 0 | 0 | 98 |
| `move` | 98 | 0 | 0 | 6 |
| `copy-path` | 0 | 0 | 0 | 98 |
| `open-terminal` | 0 | 0 | 0 | 98 |

## Why cells remain nonpassing

- **98 cells** — UNTESTED: No real transfer/device picker invoked; argv unit tests only (Share → LocalSend)
- **98 cells** — UNTESTED: User window/compositor deliberately untouched; manifest unit tests do not prove a shelf
- **196 cells** — UNTESTED: Real clipboard deliberately untouched; payload unit tests only
- **98 cells** — UNTESTED: No real desktop terminal invoked; spawn/cwd unit tests only
- **1 cell** — UNSUPPORTED: GIF cannot contain audio; Mute is unavailable for GIF
- **12 cells each** — UNTESTED: no genuine native Apple Pages, RTFD bundle or macOS text-clipping
  fixture is available; none was fabricated (each format blocks all six actions, 2 cells per action)

The four previously untested **tool** cells are closed:

- **RAR extract (2 cells) and RAR Move (2 cells).** No RAR encoder exists here, so
  `tests/rar_fixture.py` writes a stored RAR5 archive to the public format. It is
  accepted as genuine only because 7-Zip lists, tests and extracts it byte-for-byte
  and rejects a flipped byte (`tests/test_rar_fixture.py`). The archive is
  uncompressed; this does not prove Kumquat reads RAR compressed with RAR's own algorithm.
- **BMP metadata removal (2 cells).** BMP has no EXIF/XMP/text fields, so there is
  nothing to strip. These cells now check that pixels are unchanged and the file
  carries no bytes beyond its declared size. That is a weaker claim than the
  tagged-image cases and is worded that way on purpose.

The five external action integrations remain UNTESTED even though executables
are installed. Their intercepted-process unit tests are not counted as desktop
PASS. In particular, Float currently writes a manifest and toggles an active
window; those steps do not prove an actual usable shelf. Clipboard restoration
was unnecessary because no real clipboard write occurred.

## Effects and repairs

- Crop validates exact integer bounds. Video crop rejects odd dimensions that
  the chosen codecs would round, and requests exact offsets. Extreme image
  aspect/resize shapes cannot silently become zero-pixel outputs.
- Text annotation, rectangle image/video redaction and image enhancement apply
  actual pixel changes. Missing choices, invisible annotation, quantized-away
  image edits, and identity PDF organization fail visibly instead of saying Saved.
- Compression uses the proper image/media/PDF backend. Requested byte ceilings
  are hard limits with oversized outputs removed on failure. HEIC/HEIF/AVIF
  honor quality; TIFF uses actual lossless deflate compression. PDF retains page
  geometry/text and is compacted rather than sent through an image handler.
- Metadata tests seed genuine EXIF Artist, media title and PDF Info/XMP tags.
  TIFF removal uses a pixel rewrite because exiftool can report success yet
  retain IFD0 Artist. Palette/alpha/16-bit multipage TIFF cases have regression
  proof, and unary image edits preserve their pages.
- GIF tools preserve composed animation frames and timing. GIF trim, crop,
  speed and joins no longer invoke incompatible H.264 output or drop animation.
  GIF Mute explicitly reports unavailable because GIF cannot contain audio.
- Trim and bleep ranges/snapshot times cannot extend past readable input
  duration. Speed affects both video timestamps and decoded audio duration;
  nonfinite speed factors cannot enter an infinite tempo-filter loop.
- Normalize resamples and bounds audio frames before FLAC encoding, avoiding
  the reproduced invalid-block-size failure. Mono channel count, bleep's 1 kHz
  replacement interval and visualizer's nonblank video/audio are checked.
- Join stages safe literal filenames, including apostrophes. Split clips have
  numeric order beyond nine parts and do not treat source brackets as globs.
- Extract reserves a fresh per-input directory before calling the archive
  backend. Previously a member could overwrite a file beside the archive,
  including the selected source archive itself. Repeated and batch extraction
  now use isolated collision-safe directories. Archive converter internals are
  owned and tested separately.
- Move preflights duplicate destination names, dangling target symlinks,
  directory-into-itself and overlapping selections before moving anything.
  Runtime I/O failures are not promised to be transactional.

## Limits of this proof

This is real backend processing plus the pure GUI options-schema translation,
not live GTK widget or physical desktop-input proof. Every parameterized tool
uses `validate_options` output, so kwargs compatibility is exercised; the parent
integration has separate GTK tests. No GUI module was modified by this backend
work. Synthetic files and homogeneous pairs do not establish correctness for
all mixed-format selections, heterogeneous join codecs, encrypted PDFs, or
arbitrary production metadata/animation variants. Lossless WAV re-encoding need
not shrink the file; its explicit byte ceiling and decoded duration/content
are checked. ASF/WMAV2 duration checks allow 0.25 s for codec-block padding;
other video formats use 0.18 s and speed also checks decoded audio duration.
