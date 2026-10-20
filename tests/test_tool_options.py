"""Pure options contracts; deliberately safe in a Python without gi."""

import importlib.util
import sys

import pytest


def validate(tool_id, raw):
    from kumquat.gui.tool_options import validate_options

    return validate_options(tool_id, raw)


@pytest.mark.parametrize(
    ("tool_id", "raw", "expected"),
    [
        (
            "cropVideo",
            {"x": 2, "y": 4, "width": 100, "height": 80},
            {"box": (2, 4, 102, 84)},
        ),
        ("trimVideo", {"start": "1.25", "end": "3"}, {"start": 1.25, "end": 3.0}),
        ("trimAudio", {"start": "0", "end": "2.5"}, {"start": 0.0, "end": 2.5}),
        ("redactAudio", {"start": 1, "end": 2}, {"start": 1.0, "end": 2.0}),
        ("changeVideoSpeed", {"factor": "0.5"}, {"factor": 0.5}),
        ("splitVideo", {"segment_time": "8.5"}, {"segment_time": 8.5}),
        ("videoSnapshots", {"at": "0.25"}, {"at": 0.25}),
        ("compress", {"quality": "80", "max_w": "1200"}, {"quality": 80, "max_w": 1200}),
        ("frameImage", {"mode": "blur"}, {"mode": "blur"}),
        ("createCollage", {"layout": "row"}, {"layout": "row"}),
        ("organizePDF", {"page_order": "3, 1, 2"}, {"spec": {"reorder": [2, 0, 1]}}),
    ],
)
def test_parameterised_tool_kwargs(tool_id, raw, expected):
    assert validate(tool_id, raw) == expected


@pytest.mark.parametrize(
    ("tool_id", "raw"),
    [
        ("cropVideo", {"x": -1, "y": 0, "width": 20, "height": 30}),
        ("cropVideo", {"width": 0, "height": 30}),
        ("cropImage", {"crop_mode": "box", "width": "2.5", "height": 30}),
        ("cropImage", {"aspect": "made-up"}),
        ("trimVideo", {}),
        ("trimAudio", {"start": 4, "end": 3}),
        ("redactAudio", {"start": 2, "end": 2}),
        ("trimVideo", {"start": "nan", "end": 4}),
        ("trimAudio", {"start": 0, "end": "inf"}),
        ("changeVideoSpeed", {"factor": 0}),
        ("changeVideoSpeed", {"factor": True}),
        ("splitVideo", {"segment_time": -1}),
        ("videoSnapshots", {"at": -1}),
        ("compress", {"quality": 101}),
        ("compress", {"quality": 0}),
        ("compress", {"max_w": -1}),
        ("frameImage", {"mode": "unknown"}),
        ("createCollage", {"layout": "unknown"}),
        ("organizePDF", {"page_order": "1,1"}),
        ("organizePDF", {"page_order": "0,1"}),
        ("organizePDF", {"page_order": "1,3"}),
        ("organizePDF", {"page_order": ""}),
        ("cropImage", {"unexpected": "1"}),
        ("not-a-tool", {}),
    ],
)
def test_reject_invalid_choices(tool_id, raw):
    with pytest.raises(ValueError):
        validate(tool_id, raw)


def test_integer_fields_do_not_silently_round_large_or_fractional_values():
    assert validate("compress", {"max_bytes": "9007199254740993"})["max_bytes"] == (
        9007199254740993
    )
    with pytest.raises(ValueError):
        validate("compress", {"quality": "75.00000000000000001"})


def test_compression_target_is_optional_positive_bytes():
    assert validate("compress", {"max_bytes": "2048"}) == {
        "quality": 75,
        "max_w": 0,
        "max_bytes": 2048,
    }
    assert "max_bytes" not in validate("compress", {"max_bytes": ""})
    for invalid in ("0", "-1", "2.5", "nan", True):
        with pytest.raises(ValueError):
            validate("compress", {"max_bytes": invalid})


def test_move_destination_is_explicit_and_pure():
    from kumquat.gui.tool_options import requires_options

    assert requires_options("move")
    assert validate("move", {"destination": "/some folder/وجهة"}) == {
        "destination": "/some folder/وجهة"
    }
    for destination in ("", "relative/path", " ", "/bad\x00path"):
        with pytest.raises(ValueError):
            validate("move", {"destination": destination})


def test_import_is_gi_free():
    assert "gi" not in sys.modules


def test_parameterless_tools_do_not_request_options():
    from kumquat.gui.tool_options import requires_options

    for tool_id in (
        "muteVideo",
        "removeMetadata",
        "normalizeAudio",
        "mergePDF",
        "splitPDF",
        "extractArchive",
        "createPDF",
        "joinVideos",
    ):
        assert not requires_options(tool_id)


@pytest.mark.parametrize(
    ("tool_id", "raw", "expected"),
    [
        (
            "annotateImage",
            {
                "text": "Hello صورة",
                "x": "3",
                "y": "4",
                "color": "#ff0000",
                "font_size": "24",
            },
            {"text": "Hello صورة", "xy": (3, 4), "color": "#ff0000", "font_size": 24},
        ),
        (
            "redactImage",
            {"x": 1, "y": 2, "width": 30, "height": 40},
            {"boxes": [(1, 2, 31, 42)]},
        ),
        (
            "redactVideo",
            {"x": 1, "y": 2, "width": 30, "height": 40},
            {"boxes": [(1, 2, 31, 42)]},
        ),
        (
            "editImage",
            {"brightness": "1.2", "contrast": "0.8", "saturation": "0", "rotate": "-90"},
            {"brightness": 1.2, "contrast": 0.8, "saturation": 0.0, "rotate": -90.0},
        ),
        ("audioToVideo", {"size": "640x360"}, {"size": "640x360"}),
        ("audioChannels", {}, {}),
    ],
)
def test_supported_editors_have_real_explicit_parameters(tool_id, raw, expected):
    from kumquat.gui.tool_options import requires_options

    assert requires_options(tool_id)
    assert validate(tool_id, raw) == expected


@pytest.mark.parametrize(
    ("tool_id", "raw"),
    [
        ("annotateImage", {"text": " "}),
        ("annotateImage", {"text": "Hello", "x": -1}),
        ("annotateImage", {"text": "Hello", "font_size": 1001}),
        ("annotateImage", {"text": "Hello", "color": "not-a-colour"}),
        ("redactImage", {}),
        ("redactVideo", {"width": 0, "height": 10}),
        ("editImage", {}),
        ("editImage", {"rotate": 360}),
        ("editImage", {"brightness": -1}),
        ("editImage", {"contrast": "nan"}),
        ("audioToVideo", {"size": "unsafe:value"}),
    ],
)
def test_editors_reject_empty_noop_and_invalid_regions(tool_id, raw):
    with pytest.raises(ValueError):
        validate(tool_id, raw)


def test_options_module_exists_and_crop_defaults_are_visible():
    assert importlib.util.find_spec("kumquat.gui.tool_options") is not None
    from kumquat.gui.tool_options import SCHEMAS, requires_options, validate_options

    assert requires_options("cropImage")
    assert SCHEMAS["cropImage"].fields[1].default == "1:1"
    assert validate_options("cropImage", {}) == {"aspect": "1:1"}
    assert validate_options(
        "cropImage",
        {
            "crop_mode": "box",
            "x": "10",
            "y": "20",
            "width": "30",
            "height": "40",
        },
    ) == {"box": (10, 20, 40, 60)}


# --- draw-on-image crop ------------------------------------------------------


def test_crop_offers_a_draw_mode_without_changing_the_old_defaults():
    from kumquat.gui.tool_options import SCHEMAS

    crop = SCHEMAS["cropImage"]
    mode = crop.fields[0]
    assert mode.name == "crop_mode" and mode.default == "aspect"
    assert mode.choices == ("aspect", "box", "draw")
    assert [f.name for f in crop.fields][-1] == "lock"
    assert crop.fields[-1].default == "free"
    assert set(crop.fields[-1].choices) == {
        "free", "1:1", "4:3", "3:2", "16:9", "9:16"}


def test_drawn_rectangle_becomes_a_backend_box():
    assert validate(
        "cropImage",
        {"crop_mode": "draw", "x": "10", "y": "20", "width": "100", "height": "50"},
    ) == {"box": (10, 20, 110, 70)}


def test_draw_mode_without_a_drawn_box_says_what_to_do():
    with pytest.raises(ValueError, match="Drag on the picture"):
        validate("cropImage", {"crop_mode": "draw"})


def test_lock_must_be_a_known_ratio():
    with pytest.raises(ValueError, match="keep ratio"):
        validate(
            "cropImage",
            {"crop_mode": "draw", "width": "5", "height": "5", "lock": "7:7"},
        )
