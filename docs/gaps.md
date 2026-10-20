# Gaps — explicitly out of MVP scope (YAGNI)

Per TASK-031 ruling: annotate/redact/collage-GUI and photo-edit sliders
are not built in v1. CLI equivalents ship instead; GUI work is deferred here.

## Media tools (TASK-031)

- Video (`trimVideo/cropVideo/changeVideoSpeed/joinVideos/videoSnapshots/
  splitVideo/muteVideo`): ffmpeg re-encode (`libx264`/`aac`); `tt()` naming
  `Trimmed / Cropped / Speed <f>x / Snapshot->png / Clips->folder / Muted`.
  `joinVideos` has no `tt()` entry — `<first-stem>-joined.mp4` fallback.
- Audio (`trimAudio/normalizeAudio/audioChannels/redactAudio/audioToVideo`):
  ffmpeg; single-pass `loudnorm`; stereo→mono; bleep grafts a delayed sine
  onto the muted range; `showwaves` visualizer keeps the audio track.
  `tt()` naming `Trimmed / Normalized / Mono / Bleeped / Visualizer->mp4`.
- `redactVideo` (video bleep/blur-over-range): deferred — needs either a
  GUI region selector (same deferral as image redact) or a spec decision
  on blur-vs-bleep for video; no CLI equivalent shipped in v1.
- `compress`/`removeMetadata` on audio/video reuse the existing
  converters (ffmpeg re-encode / stream-copy); no separate tool wrappers.

## PDF tools (TASK-031)

- `merge_pdfs` (`mergePDF`): re-exported from `converters_pdf` — no
  `tt()` entry observed, `<first-stem>-merged.pdf` stays.
- `split_pdf` (`splitPDF`): `tt()` is `Pages->folder` — parts live in
  `<stem>-Pages/` as `<stem>-<n>.pdf`.
- `organize_pdf` (`organizePDF`): JSON spec (`reorder`/`drop`/`dup`/
  `rotate`) → `<stem>-Organized.pdf` per `tt()` (`Organized`).
  (Note: pre-existing `converters_pdf.organize_pdf` used lowercase
  `-organized`; the tool layer is the `tt()`-authoritative name.)

## Image tools (TASK-030)

- `edit_image` (`editImage` → `Edited` per ledger Q3 `tt()`): slider-based
  photo edit needs an interactive editor. Stub in
  `src/kumquat/tools_images.py` raising
  `BackendMissing("GUI editor deferred")` — tests SKIP, never fail.
- `annotate_image` (`annotateImage`): freehand/text annotation needs an
  interactive editor. Stub in `src/kumquat/tools_images.py` raising
  `BackendMissing("GUI editor deferred")` — tests SKIP, never fail.
- `redact_image` (`redactImage`): region-select redact needs the same
  editor. Same stub treatment.
- `create_collage` / `images_to_pdf` (`createCollage` / `createPDF`):
  CLI equivalents shipped (Pillow grid/row/column tiling, Pillow PDF
  merge). No `tt()` output-naming entry was observed in the REA source
  for either id (ledger Q3, minor unknown); naming falls back to
  `<first-stem>-Collage<ext>` / `<first-stem>.pdf`.
- `frame_image` (`frameImage`): solid/blur background + padding + rounded
  corners shipped (`<stem>-Background<ext>` per `tt()`).
- `strip_metadata` (`removeMetadata`): `exiftool` is absent on this host
  (sudo locked) — Pillow pixel-rewrite fallback drops all metadata and is
  covered by test; `exiftool -all=` path is used automatically when present.
