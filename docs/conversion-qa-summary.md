# Conversion QA — 2026-10-20

The real-format sweep completed with exit **0**. `tests/qa_matrix.json` is the machine-readable result, not a claim that every advertised format is implemented.

| Scope | PASS | FAIL | UNSUPPORTED | UNTESTED | Total |
|---|---:|---:|---:|---:|---:|
| Registered routes | 240 | 0 | 6 | 29 | 275 |
| Route/input-key cells, including aliases | 279 | 0 | 7 | 29 | 315 |
| Conversion edge cases | 29 | 0 | 0 | 0 | 29 |
| Declared tools/actions inventory only | 0 | 0 | 0 | 910 | 910 |

Every registry ID is represented once in `routes`; every registered route/input-key pair is represented once in `conversions`. Counts and uniqueness were independently recomputed against the live registry. All 286 exercised conversion cells have equal before/after source SHA-256 hashes; all 48 genuine generated fixtures remained unchanged. Missing fixtures are not counted as exercised.

## Unavailable and untested formats

- **UNSUPPORTED:** Six routes to Apple Pages explicitly refuse export in this implementation/environment: PDF, DOCX, Markdown, RTF, EPUB and TXT to Pages. Markdown's `.md` and `.markdown` aliases make seven cells. This is an observed implementation limitation, not a claim about every possible Linux tool.
- **UNTESTED:** Eight Pages-input routes, nine RTFD-input routes, nine textclipping-input routes and three RAR-input routes lack genuine fixtures. No unrelated files were renamed to simulate these formats. Installed 7z extracts but does not author RAR.
- The JSON records every affected ID and concrete reason in `nonpass_by_reason`. There are no failing conversion cells or edges.

## What was checked

Conversions run through `apply_conversion`, not a parallel hand-written dispatcher. Inputs have Unicode/spaces in filenames. Validation decodes image pixels and checks dimensions; probes and decodes media with duration/stream checks; checks PDF pages/text/nonblank renders; checks DOCX body text, spreadsheet cells and EPUB body content; validates subtitle cues and numeric text; and extracts archives to verify payload and safe membership.

PDF-to-PPTX was round-tripped through LibreOffice: two slides, correct landscape size, substantive text and lower-right edge text retained. A representative synthetic render was also visually inspected. Both PPT and PPTX image exports now produce **every slide**, not just the first; the two generated slides must produce distinct, correctly sized images.

Edges cover traversal rejection, output collisions and corrupt inputs across converter families, simulated backend absence, palette PNG-to-JPEG, the private ODS-to-TSV bridge and cue-less subtitle rejection. Backend-absence fault injection is labelled simulated, not evidence that an installed backend is unavailable.

The sweep writes an atomic progress JSON before fixture generation and after each route, with pending cells explicitly `UNTESTED`. Conversion/validation workers have bounded lifetimes and process-group cleanup; fault-injection tests prove both direct backend children and helper-launched backend children terminate on timeout. LibreOffice fixture runs use isolated profiles.

## Verification

- Full project suite: `1168 passed in 37.36s`, exit 0 (fresh post-concurrency recheck).
- Converter modules plus QA regressions: `343 passed in 23.62s`, exit 0.
- Ruff over converter modules, `_loshell.py`, converter tests and the sweep: clean, exit 0.
- Final sweep: 76.55 seconds, exit 0.
- Matrix SHA-256: `1ef27b1be5d582fe3b8ecd5af35bb432deef02236a5d58a5c1a36a2c486ef7d2`.

The JSON includes the executed converter/harness code hashes. The source snapshot was checked against the current files after execution.

## Re-run

From the repository root:

```sh
PYTHONPATH=src .venv/bin/python tests/qa_full_sweep.py \
  --json "$TMPDIR/kumquat-conversion-matrix.json" \
  --work-dir "$TMPDIR/kumquat-conversion-corpus-new"
```

`--work-dir` must be empty. Fixtures and rendered outputs stay in scratch; no user documents are read. The shipped matrix contains synthetic relative names and hashes, not the local corpus.

## Scope boundary

The 910 tools/actions entries are **inventory only**, for single selections and homogeneous pairs over registered input keys. They remain explicitly `UNTESTED` in this conversion artifact. It does not establish tool effects, mixed selections, directories, physical GUI input, installed-package behavior or platform integrations. The separate tools/actions worker must provide its own effect evidence; its results have not been silently credited here.
