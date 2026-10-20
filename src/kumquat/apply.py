"""Dispatch a wheel option (conversion id or tool id) to its converter.

The registry declares *what* the wheel offers; the converters know *how*;
this module is the only place that maps one to the other. Without it the
wheel could list options but never act on them.

Design:
- `apply_conversion(conv_id, src, dest_dir, progress=None)` -> Path; progress
  is forwarded only to converters that can measure work (PROGRESS_AWARE).
- `apply_tool(tool_id, srcs, dest_dir, **opts)` -> Path | list[Path]
- `find_conversion(conv_id)` -> Conversion from the populated registry.

Originals are never modified: every function writes into `dest_dir`.
Absent optional backends raise BackendMissing from the converter, which
callers surface as a skip/message rather than a crash.
"""

from __future__ import annotations

from pathlib import Path

from . import registry_data as _registry_data  # noqa: F401 -- populates REGISTRY
from .converters_archives import convert_archive
from .converters_av import convert_media
from .converters_docs import convert_doc, convert_sheet, convert_sub
from .converters_images import convert_image
from .converters_pdf import convert_pdf
from .converters_slides import convert_slide
from .progress import ProgressCallback
from .registry import REGISTRY, Conversion

# category -> converter function (uniform signature: src, dest_ext, dest_dir)
_CONVERTERS = {
    "images": convert_image,
    "audio": convert_media,
    "video": convert_media,
    "pdf": convert_pdf,
    "documents": convert_doc,
    "spreadsheets": convert_sheet,
    "subtitles": convert_sub,
    "archives": convert_archive,
    "slides": convert_slide,
}

# categories whose converter accepts a `progress=` callback
PROGRESS_AWARE: frozenset[str] = frozenset({"audio", "video", "pdf"})

_BY_ID: dict[str, Conversion] = {c.id: c for c in REGISTRY}


def find_conversion(conv_id: str) -> Conversion:
    """Look up a conversion by id (raises KeyError with a helpful message)."""
    try:
        return _BY_ID[conv_id]
    except KeyError:
        raise KeyError(
            f"unknown conversion id {conv_id!r}; "
            f"use --list to see valid ids") from None


def apply_conversion(conv_id: str, src: str | Path, dest_dir: str | Path,
                     progress: ProgressCallback | None = None) -> Path:
    """Run one conversion. Returns the new file's path; source is untouched."""
    conv = find_conversion(conv_id)
    fn = _CONVERTERS.get(conv.category)
    if fn is None:  # pragma: no cover - registry and table drift guard
        raise KeyError(f"no converter for category {conv.category!r}")
    if progress is not None and conv.category in PROGRESS_AWARE:
        return fn(Path(src), conv.output_ext, Path(dest_dir), progress=progress)
    return fn(Path(src), conv.output_ext, Path(dest_dir))


def apply_tool(tool_id: str, srcs: list[str] | list[Path],
               dest_dir: str | Path, **opts):
    """Run one file tool. Returns a path (or list of paths for split tools)."""
    from . import tools_images as ti
    from . import tools_media as tm
    from . import tools_pdf as tp

    srcs = [Path(s) for s in srcs]
    dest_dir = Path(dest_dir)
    if not srcs:
        raise ValueError("no input files")
    combined = {"createCollage", "createPDF", "mergePDF", "joinVideos"}
    if len(srcs) > 1 and tool_id not in combined:
        outputs = []
        for path in srcs:
            result = apply_tool(tool_id, [path], dest_dir, **opts)
            outputs.extend(result if isinstance(result, list) else [result])
        return outputs
    src = srcs[0]
    required = {
        "trimVideo": ("start", "end"),
        "trimAudio": ("start", "end"),
        "redactAudio": ("start", "end"),
        "changeVideoSpeed": ("factor",),
        "splitVideo": ("segment_time",),
        "organizePDF": ("spec",),
    }
    if any(opts.get(key) is None for key in required.get(tool_id, ())):
        raise ValueError(f"{tool_id} needs {', '.join(required[tool_id])}")

    if src.suffix.lower() == ".gif" and tool_id != "compress":
        return ti.transform_gif(tool_id, srcs, dest_dir, **opts)

    # --- images ---------------------------------------------------------
    if tool_id == "compress":
        target = opts.get("max_bytes")
        if target is not None and (not isinstance(target, int) or target <= 0):
            raise ValueError("compression target max_bytes must be a positive integer")
        quality = int(opts.get("quality", 75))
        if not 1 <= quality <= 100:
            raise ValueError("quality must be 1-100")
        if src.suffix.lower() == ".gif":
            result = ti.transform_gif(tool_id, srcs, dest_dir, **opts)
        elif src.suffix.lower() == ".pdf":
            result = tp.compress_pdf(src, dest_dir)
        elif src.suffix.lower() in {".mp3", ".m4a", ".wav", ".flac", ".mp4",
                                    ".mov", ".mkv", ".webm", ".avi", ".wmv"}:
            result = tm.compress_media(src, dest_dir, quality=quality)
        else:
            result = ti.compress_image(src, dest_dir, quality=quality,
                                       max_w=int(opts.get("max_w", 0)))
        if target is not None and result.stat().st_size > target:
            size = result.stat().st_size
            result.unlink()
            raise ValueError(f"compression target {target} bytes not achievable with "
                             f"these settings (encoded {size}); lower quality or size")
        return result
    if tool_id == "removeMetadata":
        if src.suffix.lower() == ".pdf":
            return tp.strip_metadata(src, dest_dir)
        if src.suffix.lower() in {".mp3", ".m4a", ".wav", ".flac", ".mp4",
                                  ".mov", ".mkv", ".webm", ".avi", ".wmv"}:
            return tm.strip_metadata(src, dest_dir)
        return ti.strip_metadata(src, dest_dir)
    if tool_id == "cropImage":
        return ti.crop_image(src, dest_dir, box=opts.get("box"),
                             aspect=opts.get("aspect"))
    if tool_id == "frameImage":
        return ti.frame_image(src, dest_dir, **opts)
    if tool_id == "createCollage":
        return ti.create_collage(srcs, dest_dir, **opts)
    if tool_id == "createPDF":
        return ti.images_to_pdf(srcs, dest_dir / (src.stem + ".pdf"))
    if tool_id in ("annotateImage", "redactImage", "editImage"):
        return getattr(ti, {
            "annotateImage": "annotate_image",
            "redactImage": "redact_image",
            "editImage": "edit_image",
        }[tool_id])(src, dest_dir, **opts)

    # --- media ----------------------------------------------------------
    if tool_id == "trimVideo":
        return tm.trim_video(src, dest_dir,
                             float(opts.get("start", 0)),
                             float(opts.get("end", 0)))
    if tool_id == "trimAudio":
        return tm.trim_audio(src, dest_dir,
                             float(opts.get("start", 0)),
                             float(opts.get("end", 0)))
    if tool_id == "cropVideo":
        box = opts.get("box")
        if box is None:
            raise ValueError("cropVideo needs box=(left, upper, right, lower)")
        return tm.crop_video(src, dest_dir, tuple(box))
    if tool_id == "changeVideoSpeed":
        return tm.change_speed(src, dest_dir, float(opts.get("factor", 2.0)))
    if tool_id == "joinVideos":
        return tm.join_mp4(srcs, dest_dir)
    if tool_id == "videoSnapshots":
        return tm.snapshot_video(src, dest_dir, float(opts.get("at", 0)))
    if tool_id == "splitVideo":
        return tm.split_video(src, dest_dir,
                              float(opts.get("segment_time", 60.0)))
    if tool_id == "muteVideo":
        return tm.mute_video(src, dest_dir)
    if tool_id == "redactVideo":
        return tm.redact_video(src, dest_dir, boxes=opts.get("boxes"))
    if tool_id == "audioToVideo":
        return tm.audio_visualizer(src, dest_dir, size=opts.get("size", "320x240"))
    if tool_id == "normalizeAudio":
        return tm.normalize_audio(src, dest_dir)
    if tool_id == "to_mono" or tool_id == "audioChannels":
        return tm.to_mono(src, dest_dir)
    if tool_id == "redactAudio":
        return tm.bleep_audio(src, dest_dir,
                              float(opts.get("start", 0)),
                              float(opts.get("end", 0)))

    # --- pdf ------------------------------------------------------------
    if tool_id == "mergePDF":
        return tp.merge_pdfs(srcs, dest_dir)
    if tool_id == "splitPDF":
        return tp.split_pdf(src, dest_dir)
    if tool_id == "organizePDF":
        return tp.organize_pdf(src, dest_dir, opts.get("spec"), require_change=True)

    # --- archives -------------------------------------------------------
    if tool_id == "extractArchive":
        from .converters_archives import _base, extract_archive

        folder = ti.unique_path(dest_dir / f"{_base(src)}-Extracted")
        folder.mkdir(parents=True, exist_ok=False)
        return extract_archive(src, folder)

    raise KeyError(f"unknown tool id {tool_id!r}")
