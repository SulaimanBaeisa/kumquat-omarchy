"""Content-level regressions for the advertised tool dispatcher.

Fixtures are generated locally. No network, desktop, or clipboard interactions.
"""

import hashlib
import json
import subprocess

import fitz
import pytest
from PIL import Image

from kumquat.apply import apply_tool


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def image(path):
    im = Image.new("RGB", (96, 64), "red")
    im.paste("blue", (48, 0, 96, 64))
    im.save(path)
    return path


def pdf(path):
    with fitz.open() as doc:
        for n in range(3):
            doc.new_page(width=400, height=240).insert_text((20, 40), f"Page {n}")
        doc.set_metadata({"author": "Synthetic private author", "title": "Fixture"})
        doc.save(path)
    return path


def run(*args):
    return subprocess.run(args, capture_output=True, check=True, timeout=60)


def probe(path):
    return json.loads(
        run(
            "ffprobe",
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(path),
        ).stdout
    )


def media(path):
    cmd = ["ffmpeg", "-v", "error", "-f", "lavfi"]
    if path.suffix in {".wav", ".mp3", ".m4a", ".flac"}:
        cmd += ["-i", "sine=frequency=440:duration=2", "-ac", "2"]
    else:
        cmd += [
            "-i",
            "testsrc2=size=96x64:rate=20:duration=2",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=2",
        ]
        if path.suffix == ".webm":
            cmd += ["-c:v", "libvpx-vp9", "-c:a", "libopus"]
        elif path.suffix == ".wmv":
            cmd += ["-c:v", "wmv2", "-c:a", "wmav2"]
        else:
            cmd += ["-c:v", "libx264", "-c:a", "aac"]
    cmd += ["-metadata", "title=Synthetic private title", str(path)]
    run(*cmd)
    return path


@pytest.mark.parametrize(
    ("tool", "opts", "message"),
    [
        ("cropImage", {}, "exactly one"),
        ("cropVideo", {}, "box"),
        ("trimVideo", {}, "start.*end"),
        ("trimAudio", {}, "start.*end"),
        ("redactAudio", {}, "start.*end"),
        ("changeVideoSpeed", {}, "factor"),
        ("splitVideo", {}, "segment_time"),
        ("organizePDF", {}, "spec"),
    ],
)
def test_dispatch_requires_user_choices(tmp_path, tool, opts, message):
    src = pdf(tmp_path / "fixture.pdf")
    before = sha(src)
    with pytest.raises(ValueError, match=message):
        apply_tool(tool, [src], tmp_path / "out", **opts)
    assert sha(src) == before
    assert not list((tmp_path / "out").rglob("*"))


@pytest.mark.parametrize(
    "tool",
    [
        "cropImage",
        "createPDF",
        "mergePDF",
        "splitPDF",
        "organizePDF",
        "trimVideo",
        "splitVideo",
    ],
)
def test_repeat_operations_never_clobber_outputs(tmp_path, tool):
    if tool in {"cropImage", "createPDF"}:
        src = image(tmp_path / "صورة fixture.png")
    elif tool in {"trimVideo", "splitVideo"}:
        src = media(tmp_path / "فيديو fixture.mp4")
    else:
        src = pdf(tmp_path / "صفحة fixture.pdf")
    opts = {
        "cropImage": {"box": (48, 0, 96, 64)},
        "organizePDF": {"spec": {"drop": [1]}},
        "trimVideo": {"start": 0.25, "end": 1.25},
        "splitVideo": {"segment_time": 1},
    }.get(tool, {})
    before = sha(src)
    first = apply_tool(tool, [src], tmp_path, **opts)
    paths = first if isinstance(first, list) else [first]
    saved = {p: sha(p) for p in paths}
    second = apply_tool(tool, [src], tmp_path, **opts)
    newer = second if isinstance(second, list) else [second]
    assert set(paths).isdisjoint(newer)
    assert {p: sha(p) for p in paths} == saved
    assert sha(src) == before


def test_batch_crop_processes_every_selected_input(tmp_path):
    srcs = [image(tmp_path / f"fixture {n}.png") for n in range(2)]
    before = [sha(p) for p in srcs]
    outputs = apply_tool("cropImage", srcs, tmp_path, box=(48, 0, 96, 64))
    assert isinstance(outputs, list) and len(outputs) == 2
    for out in outputs:
        with Image.open(out) as im:
            assert im.size == (48, 64)
            assert im.getpixel((10, 10)) == (0, 0, 255)
    assert [sha(p) for p in srcs] == before


@pytest.mark.parametrize(
    "ext", ["pdf", "mp3", "m4a", "wav", "flac", "mp4", "mov", "mkv", "webm", "avi", "wmv"]
)
def test_metadata_dispatch_removes_descriptive_tags(tmp_path, ext):
    src = (pdf if ext == "pdf" else media)(tmp_path / f"tagged.{ext}")
    before = sha(src)
    if ext == "pdf":
        with fitz.open(src) as doc:
            assert doc.metadata["author"]
    else:
        assert probe(src)["format"]["tags"]["title"] == "Synthetic private title"
    out = apply_tool("removeMetadata", [src], tmp_path)
    if ext == "pdf":
        assert b"Synthetic private author" not in out.read_bytes()
        with fitz.open(out) as doc:
            assert not doc.metadata["author"] and not doc.metadata["title"]
            assert "Page 0" in doc[0].get_text()
    else:
        info = probe(out)
        assert not info["format"].get("tags", {}).get("title")
        assert float(info["format"]["duration"]) == pytest.approx(2, abs=0.2)
    assert sha(src) == before


@pytest.mark.parametrize(
    "ext", ["pdf", "mp3", "m4a", "wav", "flac", "mp4", "mov", "mkv", "webm", "avi", "wmv"]
)
def test_compress_dispatch_uses_family_backend_and_enforces_target(tmp_path, ext):
    src = (pdf if ext == "pdf" else media)(tmp_path / f"fixture.{ext}")
    before = sha(src)
    out = apply_tool("compress", [src], tmp_path / "out", quality=30, max_bytes=1_000_000)
    assert out.stat().st_size <= 1_000_000
    if ext == "pdf":
        with fitz.open(out) as doc:
            assert doc.page_count == 3 and "Page 0" in doc[0].get_text()
    else:
        assert float(probe(out)["format"]["duration"]) == pytest.approx(2, abs=0.25)
    with pytest.raises(ValueError, match="target"):
        apply_tool("compress", [src], tmp_path / "impossible", max_bytes=16)
    assert not list((tmp_path / "impossible").rglob("*"))
    assert sha(src) == before


@pytest.mark.parametrize("ext", ["mp4", "mov", "mkv", "webm", "avi", "wmv"])
@pytest.mark.parametrize(
    "tool", ["trimVideo", "cropVideo", "changeVideoSpeed", "splitVideo"]
)
def test_video_effects_for_offered_containers(tmp_path, ext, tool):
    src = media(tmp_path / f"video.{ext}")
    before = sha(src)
    opts = {
        "trimVideo": {"start": 0.5, "end": 1.5},
        "cropVideo": {"box": (0, 0, 48, 32)},
        "changeVideoSpeed": {"factor": 2},
        "splitVideo": {"segment_time": 1},
    }[tool]
    out = apply_tool(tool, [src], tmp_path, **opts)
    paths = out if isinstance(out, list) else [out]
    assert len(paths) == (2 if tool == "splitVideo" else 1)
    for path in paths:
        info = probe(path)
        v = next(s for s in info["streams"] if s["codec_type"] == "video")
        assert any(s["codec_type"] == "audio" for s in info["streams"])
        assert (v["width"], v["height"]) == (
            (48, 32) if tool == "cropVideo" else (96, 64)
        )
        expected = 2 if tool == "cropVideo" else 1
        assert float(info["format"]["duration"]) == pytest.approx(expected, abs=0.3)
    assert sha(src) == before


@pytest.mark.parametrize(
    ("tool", "opts"),
    [
        ("annotateImage", {"text": "TEST", "xy": (4, 4), "color": "white"}),
        ("redactImage", {"boxes": [(0, 0, 48, 64)]}),
        ("editImage", {"brightness": 0.5}),
    ],
)
def test_image_editors_apply_requested_effects(tmp_path, tool, opts):
    src = image(tmp_path / "fixture.png")
    before = sha(src)
    out = apply_tool(tool, [src], tmp_path, **opts)
    with Image.open(out) as result, Image.open(src) as original:
        assert result.size == original.size
        assert result.tobytes() != original.tobytes()
        if tool == "redactImage":
            assert result.getpixel((10, 10)) == (0, 0, 0)
            assert result.getpixel((70, 10)) == (0, 0, 255)
        if tool == "editImage":
            assert result.getpixel((10, 10)) == (127, 0, 0)
    assert sha(src) == before


@pytest.mark.parametrize("tool", ["annotateImage", "redactImage", "editImage"])
def test_image_editors_require_meaningful_choices(tmp_path, tool):
    src = image(tmp_path / "fixture.png")
    with pytest.raises(ValueError):
        apply_tool(tool, [src], tmp_path)


@pytest.mark.parametrize("ext", ["mp4", "mov", "mkv", "webm", "avi", "wmv"])
def test_video_redaction_replaces_pixels(tmp_path, ext):
    src = media(tmp_path / f"fixture.{ext}")
    before = sha(src)
    with pytest.raises(ValueError, match="boxes"):
        apply_tool("redactVideo", [src], tmp_path)
    out = apply_tool("redactVideo", [src], tmp_path, boxes=[(0, 0, 96, 64)])
    frame = run(
        "ffmpeg",
        "-v",
        "error",
        "-i",
        str(out),
        "-frames:v",
        "1",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-",
    ).stdout
    assert len(frame) == 96 * 64 * 3
    assert max(frame) < 10
    assert any(s["codec_type"] == "audio" for s in probe(out)["streams"])
    assert sha(src) == before


@pytest.mark.parametrize("ext", ["mp3", "m4a", "wav", "flac"])
def test_audio_visualizer_is_routed_and_keeps_audio(tmp_path, ext):
    src = media(tmp_path / f"fixture.{ext}")
    before = sha(src)
    out = apply_tool("audioToVideo", [src], tmp_path, size="160x120")
    info = probe(out)
    video = next(s for s in info["streams"] if s["codec_type"] == "video")
    assert (video["width"], video["height"]) == (160, 120)
    assert any(s["codec_type"] == "audio" for s in info["streams"])
    assert float(info["format"]["duration"]) == pytest.approx(2, abs=0.2)
    assert sha(src) == before


def test_frame_and_collage_forward_user_options(tmp_path):
    src = image(tmp_path / "fixture.png")
    frame = apply_tool("frameImage", [src], tmp_path, pad=10, color=(0, 255, 0))
    with Image.open(frame) as im:
        assert im.size == (116, 84)
        assert im.getpixel((0, 0)) == (0, 255, 0)
    collage = apply_tool(
        "createCollage", [src, src], tmp_path, layout="row", thumb=(32, 24)
    )
    with Image.open(collage) as im:
        assert im.size == (64, 24)


def test_extract_archive_isolates_members_and_repeated_outputs(tmp_path):
    import zipfile

    src = tmp_path / "archive.zip"
    sentinel = tmp_path / "keep.txt"
    sentinel.write_bytes(b"preserve user bytes")
    with zipfile.ZipFile(src, "w") as archive:
        archive.writestr("keep.txt", b"archive contents")
        archive.writestr("archive.zip", b"not the source archive")
    before = {p: sha(p) for p in (src, sentinel)}
    first = apply_tool("extractArchive", [src], tmp_path)
    assert first != tmp_path
    assert (first / "keep.txt").read_bytes() == b"archive contents"
    second = apply_tool("extractArchive", [src], tmp_path)
    assert first != second
    assert (second / "keep.txt").read_bytes() == b"archive contents"
    assert {p: sha(p) for p in (src, sentinel)} == before


@pytest.mark.parametrize("mode", ["P", "RGBA", "L", "I;16"])
def test_tiff_pixel_rewrite_preserves_modes_and_pages(tmp_path, mode):
    src = tmp_path / "pages.tiff"
    frames = [Image.new(mode, (13, 257), v) for v in (1, 2)]
    if mode == "P":
        for frame in frames:
            frame.putpalette([0, 0, 0, 255, 0, 0, 0, 0, 255] + [0, 0, 0] * 253)
    tags = Image.Exif()
    tags[315] = "Private artist"
    frames[0].save(src, save_all=True, append_images=frames[1:], exif=tags)
    before = sha(src)
    out = apply_tool("removeMetadata", [src], tmp_path)
    with Image.open(out) as result, Image.open(src) as original:
        assert result.n_frames == original.n_frames == 2
        for n in range(2):
            result.seek(n)
            original.seek(n)
            assert result.mode == original.mode
            assert result.tobytes() == original.tobytes()
            assert result.convert("RGB").tobytes() == original.convert("RGB").tobytes()
            assert not result.getexif().get(315)
    assert sha(src) == before


@pytest.mark.parametrize("tool", ["cropImage", "cropVideo"])
def test_crop_rejects_fractional_coordinates_instead_of_truncating(tmp_path, tool):
    src = (image if tool == "cropImage" else media)(
        tmp_path / ("a.png" if tool == "cropImage" else "a.mp4")
    )
    with pytest.raises(ValueError, match="integer"):
        apply_tool(tool, [src], tmp_path, box=(0.5, 0, 48, 32))


def test_extreme_image_shapes_never_produce_zero_dimensions(tmp_path):
    src = tmp_path / "thin.png"
    Image.new("RGB", (200, 1), "red").save(src)
    out = apply_tool("compress", [src], tmp_path, max_w=1)
    with Image.open(out) as result:
        assert result.size == (1, 1)
    with pytest.raises(ValueError, match="aspect|pixel"):
        apply_tool("cropImage", [src], tmp_path, aspect="1:1000000")


@pytest.mark.parametrize("ext", ["heic", "heif", "avif"])
def test_heif_avif_compression_honors_quality(tmp_path, ext):
    import random

    import pillow_heif

    pillow_heif.register_heif_opener()
    source = tmp_path / f"noise.{ext}"
    noise = random.Random(42).randbytes(96 * 64 * 3)
    Image.frombytes("RGB", (96, 64), noise).save(source, quality=98)
    before = sha(source)
    lower = apply_tool("compress", [source], tmp_path, quality=10)
    higher = apply_tool("compress", [source], tmp_path, quality=90)
    assert lower.stat().st_size < higher.stat().st_size
    assert sha(source) == before


def test_tiff_lossless_compression_reduces_bytes_without_dropping_pages(tmp_path):
    source = tmp_path / "pages.tiff"
    frames = [Image.new("RGB", (48, 96), c) for c in ("red", "blue")]
    frames[0].save(source, save_all=True, append_images=frames[1:])
    out = apply_tool("compress", [source], tmp_path)
    assert out.stat().st_size < source.stat().st_size
    with Image.open(source) as original, Image.open(out) as result:
        assert result.n_frames == 2
        for n in range(2):
            original.seek(n)
            result.seek(n)
            assert original.tobytes() == result.tobytes()


def test_video_crop_does_not_silently_round_odd_dimensions(tmp_path):
    src = media(tmp_path / "fixture.mp4")
    with pytest.raises(ValueError, match="even"):
        apply_tool("cropVideo", [src], tmp_path, box=(0, 0, 47, 31))


def test_join_handles_literal_apostrophes_in_source_names(tmp_path):
    src = media(tmp_path / "فيديو O'Brien.mp4")
    before = sha(src)
    result = apply_tool("joinVideos", [src, src], tmp_path)
    assert float(probe(result)["format"]["duration"]) == pytest.approx(4, abs=0.2)
    assert sha(src) == before


def test_split_preserves_numeric_order_with_literal_glob_filename(tmp_path):
    src = tmp_path / "clip [synthetic].mp4"
    run(
        "ffmpeg",
        "-v",
        "error",
        "-f",
        "lavfi",
        "-i",
        "testsrc2=size=96x64:rate=10:duration=12",
        str(src),
    )
    before = sha(src)
    parts = apply_tool("splitVideo", [src], tmp_path, segment_time=1)
    assert len(parts) == 12
    assert [p.stem.rsplit("-", 1)[1] for p in parts] == [str(n) for n in range(1, 13)]
    assert sha(src) == before


def test_unchanged_edit_or_invisible_annotation_is_not_saved(tmp_path):
    src = image(tmp_path / "fixture.png")
    for tool, opts in [
        ("editImage", {"brightness": 1.0000001}),
        ("annotateImage", {"text": "TEST", "xy": (95, 63)}),
    ]:
        with pytest.raises(ValueError, match="visible|pixels|change"):
            apply_tool(tool, [src], tmp_path / "out", **opts)
    assert not list((tmp_path / "out").rglob("*"))


def test_gui_pdf_identity_order_is_not_falsely_saved(tmp_path):
    src = pdf(tmp_path / "fixture.pdf")
    with pytest.raises(ValueError, match="change|unchanged"):
        apply_tool("organizePDF", [src], tmp_path / "out", spec={"reorder": [0, 1, 2]})
    assert not list((tmp_path / "out").rglob("*"))


def test_tiff_metadata_is_really_removed(tmp_path):
    src = tmp_path / "tagged.tiff"
    tags = Image.Exif()
    tags[315] = "Private artist"
    Image.new("RGB", (80, 48), "red").save(src, exif=tags)
    before = sha(src)
    out = apply_tool("removeMetadata", [src], tmp_path)
    with Image.open(out) as im:
        assert not im.getexif().get(315)
        assert im.getpixel((10, 10)) == (255, 0, 0)
    assert sha(src) == before


def test_flac_normalization_keeps_usable_sample_rate(tmp_path):
    src = media(tmp_path / "fixture.flac")
    before = sha(src)
    out = apply_tool("normalizeAudio", [src], tmp_path)
    info = probe(out)
    audio = next(s for s in info["streams"] if s["codec_type"] == "audio")
    original = next(s for s in probe(src)["streams"] if s["codec_type"] == "audio")
    assert audio["sample_rate"] == original["sample_rate"]
    assert float(info["format"]["duration"]) == pytest.approx(2, abs=0.1)
    assert sha(src) == before


@pytest.mark.parametrize(
    "tool",
    [
        "compress",
        "removeMetadata",
        "trimVideo",
        "cropVideo",
        "changeVideoSpeed",
        "joinVideos",
    ],
)
def test_gif_tools_preserve_animation_and_effect(tmp_path, tool):
    src = tmp_path / "animation.gif"
    frames = [Image.new("RGB", (96, 64), c) for c in ("red", "blue", "green")]
    frames[0].save(
        src,
        save_all=True,
        append_images=frames[1:],
        duration=400,
        loop=0,
        comment=b"Synthetic private comment",
    )
    before = sha(src)
    opts = {
        "compress": {"max_w": 48},
        "trimVideo": {"start": 0.4, "end": 1.2},
        "cropVideo": {"box": (0, 0, 48, 32)},
        "changeVideoSpeed": {"factor": 2},
    }.get(tool, {})
    out = apply_tool(
        tool, [src, src] if tool == "joinVideos" else [src], tmp_path, **opts
    )
    with Image.open(out) as result:
        assert result.n_frames >= 2
        expected = (48, 32) if tool in {"compress", "cropVideo"} else (96, 64)
        assert result.size == expected
        length = (
            sum(result.seek(n) or result.info["duration"] for n in range(result.n_frames))
            / 1000
        )
        wanted = {"trimVideo": 0.8, "changeVideoSpeed": 0.6, "joinVideos": 2.4}.get(
            tool, 1.2
        )
        assert length == pytest.approx(wanted, abs=0.1)
        if tool == "removeMetadata":
            assert not result.info.get("comment")
    assert sha(src) == before


def test_mute_gif_is_explicitly_unavailable_not_a_saved_noop(tmp_path):
    src = tmp_path / "animation.gif"
    Image.new("RGB", (96, 64), "red").save(src)
    before = sha(src)
    with pytest.raises(NotImplementedError, match="GIF.*audio"):
        apply_tool("muteVideo", [src, src], tmp_path)
    assert sha(src) == before


@pytest.mark.parametrize("tool", ["trimVideo", "trimAudio", "redactAudio"])
def test_time_ranges_cannot_extend_beyond_input(tmp_path, tool):
    src = media(tmp_path / ("fixture.mp4" if tool == "trimVideo" else "fixture.wav"))
    before = sha(src)
    with pytest.raises(ValueError, match="duration|outside"):
        apply_tool(tool, [src], tmp_path / "out", start=1, end=5)
    assert sha(src) == before
    assert not list((tmp_path / "out").rglob("*"))


def test_snapshot_cannot_return_a_nonexistent_saved_path(tmp_path):
    src = media(tmp_path / "fixture.mp4")
    with pytest.raises(ValueError, match="duration|outside"):
        apply_tool("videoSnapshots", [src], tmp_path / "out", at=10)
    assert not list((tmp_path / "out").rglob("*"))


def test_infinite_speed_is_rejected_before_building_atempo(tmp_path, monkeypatch):
    from kumquat import tools_media

    src = media(tmp_path / "fixture.mp4")
    monkeypatch.setattr(
        tools_media,
        "_atempo_chain",
        lambda _: pytest.fail("nonfinite speed reached encoder"),
    )
    with pytest.raises(ValueError, match="finite"):
        apply_tool("changeVideoSpeed", [src], tmp_path / "out", factor=float("inf"))
