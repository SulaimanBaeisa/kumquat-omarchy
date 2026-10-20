"""Declarative tool options, pure validation, and a lazy GTK4 page factory.

Importing this module never imports gi or a processing backend. Widget callbacks
only validate choices and hand kwargs to the caller; the caller owns its Job.
Coordinates use top-left pixel origins; backend boxes use exclusive right/bottom.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path

from .crop_geometry import RATIOS


@dataclass(frozen=True)
class Field:
    name: str
    label: str
    default: str = ""
    choices: tuple[str, ...] = ()
    hint: str = ""


@dataclass(frozen=True)
class ToolSchema:
    title: str
    description: str
    fields: tuple[Field, ...]
    unavailable: bool = False


_RECTANGLE = (
    Field("x", "Left (px)", "0"),
    Field("y", "Top (px)", "0"),
    Field("width", "Width (px)"),
    Field("height", "Height (px)"),
)
_TIME_RANGE = (Field("start", "Start (seconds)", "0"), Field("end", "End (seconds)"))
SCHEMAS = {
    "move": ToolSchema(
        "Move files",
        "Move the ORIGINAL selected files into this folder. "
        "The folder will be created if needed. Existing files will not be overwritten.",
        (
            Field(
                "destination",
                "Destination directory",
                hint="Full path, e.g. /home/user/Archive",
            ),
        ),
    ),
    "cropVideo": ToolSchema(
        "Crop video",
        "Enter the rectangle in pixels. Source bounds are checked when run.",
        _RECTANGLE,
    ),
    "trimVideo": ToolSchema(
        "Trim video", "Keep only the chosen time range.", _TIME_RANGE
    ),
    "trimAudio": ToolSchema(
        "Trim audio", "Keep only the chosen time range.", _TIME_RANGE
    ),
    "redactAudio": ToolSchema(
        "Bleep audio",
        "Replace one time span with a tone; all times are in seconds.",
        _TIME_RANGE,
    ),
    "changeVideoSpeed": ToolSchema(
        "Change video speed",
        "0.5 = half speed; 2 = double speed. Audio changes too.",
        (Field("factor", "Speed factor", "2"),),
    ),
    "splitVideo": ToolSchema(
        "Split video",
        "Create clips of this duration; the last clip may be shorter.",
        (Field("segment_time", "Clip duration (seconds)", "60"),),
    ),
    "videoSnapshots": ToolSchema(
        "Video snapshot",
        "Save ONE PNG frame at the chosen time (not an interval).",
        (Field("at", "Time (seconds)", "0"),),
    ),
    "compress": ToolSchema(
        "Compress",
        "Quality applies to lossy images and media; PDF uses lossless "
        "optimization. Width applies only to images (0 keeps the original). "
        "Optional maximum bytes is a hard limit: an unmet target reports an error, "
        "not a successful oversized output. A smaller size is not guaranteed.",
        (
            Field("quality", "Quality (1–100)", "75"),
            Field("max_w", "Maximum image width (px)", "0"),
            Field(
                "max_bytes",
                "Maximum output size (bytes)",
                hint="Optional; leave blank for no limit",
            ),
        ),
    ),
    "frameImage": ToolSchema(
        "Image background",
        "Add a 40 px white or blurred background around the image.",
        (Field("mode", "Background", "solid", ("solid", "blur")),),
    ),
    "createCollage": ToolSchema(
        "Create collage",
        "Use the selection order in a grid, row, or column.",
        (Field("layout", "Layout", "grid", ("grid", "row", "column")),),
    ),
    "organizePDF": ToolSchema(
        "Organize PDF",
        "Enter EVERY page once, in the desired order. "
        "Page numbers start at 1; for example: 3, 1, 2. "
        "The source page count is checked when run.",
        (Field("page_order", "Page order", hint="For a 3-page PDF: 3, 1, 2"),),
    ),
    "annotateImage": ToolSchema(
        "Annotate image",
        "Draw text at this top-left pixel position. This is text "
        "annotation, not a freehand editor; the image bounds are checked when run.",
        (
            Field("text", "Annotation text"),
            *_RECTANGLE[:2],
            Field("font_size", "Font size (px, 1–1000)", "20"),
            Field(
                "color",
                "Text colour",
                "#000000",
                ("#000000", "#ffffff", "#ff0000", "#ffff00", "#0088ff"),
            ),
        ),
    ),
    "redactImage": ToolSchema(
        "Redact image",
        "Permanently black out ONE pixel rectangle in the output. "
        "The original is unchanged. Source bounds are checked when run.",
        _RECTANGLE,
    ),
    "redactVideo": ToolSchema(
        "Redact video",
        "Black out ONE pixel rectangle throughout the ENTIRE video. "
        "This does NOT redact audio; use Bleep for audio. The original is unchanged.",
        _RECTANGLE,
    ),
    "editImage": ToolSchema(
        "Edit image",
        "Enhancement factors: 1 = unchanged, 0 = minimum. "
        "Rotation is counter-clockwise in degrees. Choose at least one change.",
        (
            Field("brightness", "Brightness factor", "1"),
            Field("contrast", "Contrast factor", "1"),
            Field("saturation", "Saturation factor", "1"),
            Field("rotate", "Rotation (degrees)", "0"),
        ),
    ),
    "audioToVideo": ToolSchema(
        "Audio visualizer",
        "Render an MP4 waveform video with the original audio.",
        (Field("size", "Video size", "320x240", ("320x240", "640x360", "1280x720")),),
    ),
    "audioChannels": ToolSchema(
        "Convert audio to mono",
        "Downmix to ONE audio channel. Stereo and other "
        "channel layouts are not available in this build. The original is unchanged.",
        (),
    ),
    "cropImage": ToolSchema(
        "Crop image",
        "Drag on the picture to choose the part to keep, or use a centred ratio "
        "or exact pixels.",
        (
            Field("crop_mode", "Crop method", "aspect", ("aspect", "box", "draw")),
            Field("aspect", "Aspect ratio", "1:1", ("1:1", "4:3", "3:2", "16:9", "9:16")),
            *_RECTANGLE,
            Field("lock", "Keep ratio", "free", RATIOS),
        ),
    ),
}


def requires_options(tool_id: str) -> bool:
    """Whether the wheel should show a choice/instruction page before running."""
    return tool_id in SCHEMAS


def _number(
    raw: dict,
    name: str,
    *,
    minimum: int | float | None = 0,
    positive=False,
    integer=False,
):
    value = raw.get(name, "")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(
            f"{name.replace('_', ' ').capitalize()} must be a number."
        ) from None
    if isinstance(value, bool) or not number.is_finite():
        raise ValueError(f"{name.capitalize()} must be a finite number.")
    if (minimum is not None and number < minimum) or (positive and number <= 0):
        relation = "greater than 0" if positive else f"at least {minimum}"
        raise ValueError(f"{name.capitalize()} must be {relation}.")
    if integer:
        if number != number.to_integral_value():
            raise ValueError(f"{name.capitalize()} must be a whole number.")
        return int(number)
    result = float(number)
    if not math.isfinite(result) or (positive and result == 0):
        raise ValueError(f"{name.capitalize()} is outside the supported numeric range.")
    return result


def _rectangle(raw: dict) -> tuple[int, int, int, int]:
    x = _number(raw, "x", integer=True)
    y = _number(raw, "y", integer=True)
    width = _number(raw, "width", integer=True, positive=True)
    height = _number(raw, "height", integer=True, positive=True)
    return int(x), int(y), int(x + width), int(y + height)


def validate_options(tool_id: str, raw: dict) -> dict:
    """Translate human controls into validated backend kwargs, without any I/O.

    Raises ValueError for missing/invalid choices. Source bounds and durations
    remain backend checks: this function does not open files or spawn ffprobe.
    """
    if tool_id not in SCHEMAS:
        raise ValueError(f"No options schema for {tool_id!r}.")
    schema = SCHEMAS[tool_id]
    if schema.unavailable:
        raise ValueError(schema.description)
    values = {field.name: field.default for field in schema.fields}
    unknown = set(raw) - set(values)
    if unknown:
        raise ValueError(f"Unknown options: {', '.join(sorted(unknown))}.")
    values.update(raw)
    for field in schema.fields:
        if field.choices and values[field.name] not in field.choices:
            raise ValueError(f"Choose a valid {field.label.lower()}.")
    if tool_id == "annotateImage":
        text = values["text"]
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Enter nonblank annotation text.")
        font_size = _number(values, "font_size", integer=True, minimum=1)
        if font_size > 1000:
            raise ValueError("Font size must be between 1 and 1000 pixels.")
        return {
            "text": text,
            "xy": (
                _number(values, "x", integer=True),
                _number(values, "y", integer=True),
            ),
            "font_size": font_size,
            "color": values["color"],
        }
    if tool_id in ("redactImage", "redactVideo"):
        return {"boxes": [_rectangle(values)]}
    if tool_id == "editImage":
        settings = {
            key: _number(values, key) for key in ("brightness", "contrast", "saturation")
        }
        settings["rotate"] = _number(values, "rotate", minimum=None)
        if (
            settings["brightness"],
            settings["contrast"],
            settings["saturation"],
            settings["rotate"] % 360,
        ) == (1, 1, 1, 0):
            raise ValueError("Choose a change; all edit settings are unchanged.")
        return settings
    if tool_id == "move":
        destination = values["destination"]
        if (
            not isinstance(destination, str)
            or not destination.strip()
            or "\x00" in destination
        ):
            raise ValueError("Enter a destination directory.")
        if not Path(destination).is_absolute():
            raise ValueError(
                "Destination must be a full absolute path (starting with /)."
            )
        return {"destination": destination}
    if tool_id in ("cropImage", "cropVideo"):
        if tool_id == "cropImage" and values["crop_mode"] == "aspect":
            return {"aspect": values["aspect"]}
        drawing = tool_id == "cropImage" and values["crop_mode"] == "draw"
        if drawing and not (
            str(values["width"]).strip() and str(values["height"]).strip()
        ):
            raise ValueError("Drag on the picture to choose the area to keep.")
        return {"box": _rectangle(values)}
    if tool_id in ("trimVideo", "trimAudio", "redactAudio"):
        start, end = _number(values, "start"), _number(values, "end")
        if end <= start:
            raise ValueError("End must be greater than start (seconds).")
        return {"start": start, "end": end}
    if tool_id in ("changeVideoSpeed", "splitVideo", "videoSnapshots"):
        key = {
            "changeVideoSpeed": "factor",
            "splitVideo": "segment_time",
            "videoSnapshots": "at",
        }[tool_id]
        return {key: _number(values, key, positive=key != "at")}
    if tool_id == "compress":
        quality = _number(values, "quality", integer=True, minimum=1)
        if quality > 100:
            raise ValueError("Quality must be between 1 and 100.")
        kwargs = {"quality": quality, "max_w": _number(values, "max_w", integer=True)}
        if values["max_bytes"] != "":
            kwargs["max_bytes"] = _number(
                values, "max_bytes", integer=True, positive=True
            )
        return kwargs
    if tool_id == "organizePDF":
        try:
            pages = [int(part.strip()) for part in str(values["page_order"]).split(",")]
        except ValueError:
            raise ValueError(
                "Enter page numbers separated by commas, e.g. 3, 1, 2."
            ) from None
        if sorted(pages) != list(range(1, len(pages) + 1)):
            raise ValueError("Include every page exactly once, starting at page 1.")
        return {"spec": {"reorder": [page - 1 for page in pages]}}
    return dict(values)


@lru_cache(maxsize=1)
def _widget_type():
    """Define the real GTK subtype once, only when the GUI is actually opened."""
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Gdk", "4.0")
    from gi.repository import Gdk, GLib, Gtk, Pango

    choice_labels = {
        "aspect": "Centred aspect ratio",
        "box": "Pixel rectangle",
        "draw": "Draw on image",
        "free": "Free",
        "solid": "White (solid)",
        "blur": "Blurred image",
        "grid": "Grid",
        "row": "Horizontal row",
        "column": "Vertical column",
        "#000000": "Black",
        "#ffffff": "White",
        "#ff0000": "Red",
        "#ffff00": "Yellow",
        "#0088ff": "Blue",
    }

    class ToolOptions(Gtk.Box):
        def __init__(self, tool_id, files, on_apply, on_cancel):
            super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
            self.tool_id = tool_id
            self.schema = SCHEMAS[tool_id]
            self.on_apply = on_apply
            self.on_cancel = on_cancel
            self.controls = {}
            self.rows = {}
            self.pdf_pages = 0
            self.pdf_cells = []
            self.canvas = None
            self.canvas_box = None
            self.preview_note = ""
            self._syncing = False
            self.add_css_class("kumquat-tool-options")
            for side in ("top", "bottom", "start", "end"):
                getattr(self, f"set_margin_{side}")(12)

            title = Gtk.Label(label=self.schema.title, xalign=0)
            title.add_css_class("title-2")
            self.append(title)
            names = [Path(path).name for path in files]
            summary = ", ".join(names[:2])
            if len(names) > 2:
                summary += f" (+{len(names) - 2} more)"
            selected = Gtk.Label(label=summary, xalign=0)
            selected.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
            selected.set_tooltip_text("\n".join(names))
            selected.add_css_class("dim-label")
            self.append(selected)

            form = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
            description = Gtk.Label(label=self.schema.description, xalign=0, wrap=True)
            description.set_max_width_chars(45)
            form.append(description)
            for field in self.schema.fields:
                row = Gtk.Grid(row_spacing=4, column_spacing=8)
                row.add_css_class("kumquat-option-row")
                label = Gtk.Label(label=field.label, xalign=0)
                row.attach(label, 0, 0, 1, 1)
                if field.choices:
                    labels = [
                        choice_labels.get(choice, choice) for choice in field.choices
                    ]
                    control = Gtk.DropDown.new_from_strings(labels)
                    control.set_selected(field.choices.index(field.default))
                    control.connect("notify::selected", self._changed)
                else:
                    control = Gtk.Entry()
                    control.set_text(field.default)
                    control.set_placeholder_text(field.hint or "Required")
                    control.connect("changed", self._changed)
                    control.connect("activate", lambda _entry: self.submit())
                control.set_hexpand(True)
                control.update_property([Gtk.AccessibleProperty.LABEL], [field.label])
                label.set_mnemonic_widget(control)
                row.attach(control, 0, 1, 1, 1)
                self.controls[field.name] = control
                self.rows[field.name] = row
                form.append(row)

            self.scroller = Gtk.ScrolledWindow()
            self.scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            self.scroller.set_vexpand(True)
            self.scroller.set_child(form)
            self.scroller.set_propagate_natural_height(True)
            self.append(self.scroller)
            if tool_id == "cropImage":
                self._build_crop_canvas(files, selected)
            if tool_id == "organizePDF":
                self._build_pdf_strip(files, selected)
            self.error_label = Gtk.Label(xalign=0, wrap=True)
            self.error_label.add_css_class("kumquat-option-error")
            self.error_label.set_visible(False)
            self.append(self.error_label)

            buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            self.back_button = Gtk.Button(label="Back")
            self.back_button.connect("clicked", lambda _button: self.on_cancel())
            buttons.append(self.back_button)
            self.apply_button = Gtk.Button(label="Apply")
            self.apply_button.add_css_class("kumquat-apply")
            self.apply_button.add_css_class("suggested-action")
            self.apply_button.set_hexpand(True)
            self.apply_button.set_sensitive(not self.schema.unavailable)
            self.apply_button.connect("clicked", lambda _button: self.submit())
            buttons.append(self.apply_button)
            self.append(buttons)
            self._refresh_visibility()

        def _build_pdf_strip(self, files, after):
            """A small strip of page thumbnails that follows the typed page order."""
            from ..pdf_preview import THUMB_LIMIT, default_order, load_thumbnails

            self.pdf_note = Gtk.Label(xalign=0, wrap=True)
            self.pdf_note.add_css_class("dim-label")
            self.pdf_note.set_visible(False)
            self.insert_child_after(self.pdf_note, after)
            if len(files) != 1:
                self.pdf_note.set_text("Page preview needs exactly one PDF.")
                self.pdf_note.set_visible(True)
                return
            try:
                total, thumbs = load_thumbnails(files[0])
            except Exception as exc:  # noqa: BLE001 - any unreadable PDF falls back
                self.pdf_note.set_text(f"Page preview unavailable ({exc}).")
                self.pdf_note.set_visible(True)
                return
            self.pdf_pages = total
            self.pdf_textures = [self._texture(image) for image in thumbs]
            self.pdf_strip = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            self.pdf_strip.add_css_class("kumquat-pdf-strip")
            scroller = Gtk.ScrolledWindow()
            scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
            scroller.set_propagate_natural_height(True)
            scroller.set_child(self.pdf_strip)
            self.pdf_scroller = scroller
            self.insert_child_after(scroller, after)
            if total > THUMB_LIMIT:
                self.pdf_note.set_text(f"Preview shows the first {THUMB_LIMIT} pages.")
                self.pdf_note.set_visible(True)
            self.controls["page_order"].set_text(default_order(total))
            self._refresh_pdf_strip()

        @staticmethod
        def _texture(image):
            data = GLib.Bytes.new(image.tobytes())
            return Gdk.MemoryTexture.new(
                image.width, image.height, Gdk.MemoryFormat.R8G8B8, data, image.width * 3
            )

        def _refresh_pdf_strip(self):
            """Show the pages in the typed order (the current order while incomplete)."""
            from ..pdf_preview import order_from_text

            if self.tool_id != "organizePDF" or not self.pdf_pages:
                return
            typed = self.controls["page_order"].get_text()
            order = order_from_text(typed, self.pdf_pages)
            self.pdf_cells = order or list(range(1, self.pdf_pages + 1))
            while (child := self.pdf_strip.get_first_child()) is not None:
                self.pdf_strip.remove(child)
            for number in self.pdf_cells:
                if number - 1 >= len(self.pdf_textures):
                    continue
                cell = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
                picture = Gtk.Picture.new_for_paintable(self.pdf_textures[number - 1])
                picture.set_can_shrink(False)
                picture.add_css_class("kumquat-pdf-page")
                picture.update_property(
                    [Gtk.AccessibleProperty.LABEL], [f"Page {number}"]
                )
                label = Gtk.Label(label=str(number))
                label.add_css_class("dim-label")
                cell.append(picture)
                cell.append(label)
                self.pdf_strip.append(cell)
            incomplete = order is None and bool(typed.strip())
            truncated = self.pdf_pages > len(self.pdf_textures)
            if incomplete:
                self.pdf_note.set_text(
                    "Order not complete yet: list every page once. "
                    "Showing the current order."
                )
            elif truncated:
                self.pdf_note.set_text(
                    f"Preview shows the first {len(self.pdf_textures)} pages."
                )
            self.pdf_note.set_visible(incomplete or truncated)

        def _build_crop_canvas(self, files, after):
            """Show the picture with a draggable box when one image is selected."""
            from ..preview import load_preview
            from .crop_canvas import create_crop_canvas

            self.draw_note = Gtk.Label(xalign=0, wrap=True)
            self.draw_note.add_css_class("dim-label")
            self.draw_note.set_visible(False)
            self.rows["draw_note"] = self.draw_note
            self.insert_child_after(self.draw_note, after)
            if len(files) != 1:
                self.preview_note = "Drawing needs exactly one image; pick a ratio."
                return
            try:
                preview, full_size = load_preview(files[0])
            except Exception as exc:  # noqa: BLE001 - any unreadable image falls back
                self.preview_note = f"Preview unavailable ({exc}). Use a ratio or pixels."
                return
            self.full_size = full_size
            self.canvas = create_crop_canvas(preview, full_size, self._on_box_changed)
            self.readout = Gtk.Label(xalign=0)
            self.readout.add_css_class("dim-label")
            self.canvas_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            self.canvas_box.set_vexpand(True)
            self.canvas_box.append(self.canvas)
            self.canvas_box.append(self.readout)
            self.insert_child_after(self.canvas_box, after)
            self._on_box_changed(self.canvas.selection)
            self._was_drawing = True  # fields and box already agree
            self.set_value("crop_mode", "draw")

        def _on_box_changed(self, rect):
            """Mirror the dragged box into the pixel fields and the readout."""
            left, top, right, bottom = rect.to_box()
            self._syncing = True
            try:
                for name, value in (
                    ("x", left),
                    ("y", top),
                    ("width", right - left),
                    ("height", bottom - top),
                ):
                    self.controls[name].set_text(str(value))
            finally:
                self._syncing = False
            full_w, full_h = self.full_size
            self.readout.set_text(
                f"Keeping {right - left} × {bottom - top} px of {full_w} × {full_h} "
                f"(left {left}, top {top})"
            )
            if hasattr(self, "error_label"):
                self.error_label.set_visible(False)

        def _sync_canvas_from_fields(self):
            """Carry typed pixel values into the box when switching to Draw."""
            from .crop_geometry import Rect

            try:
                x, y, w, h = (
                    int(self.controls[name].get_text())
                    for name in ("x", "y", "width", "height")
                )
            except ValueError:
                return
            if w > 0 and h > 0:
                self.canvas.set_selection(Rect(x, y, w, h))

        def _raw(self):
            values = {}
            for field in self.schema.fields:
                control = self.controls[field.name]
                if field.choices:
                    index = control.get_selected()
                    values[field.name] = (
                        field.choices[index] if index < len(field.choices) else ""
                    )
                else:
                    values[field.name] = control.get_text()
            return values

        def _refresh_visibility(self):
            if self.tool_id != "cropImage":
                return
            mode = self._raw()["crop_mode"]
            drawing = mode == "draw"
            self.rows["aspect"].set_visible(mode == "aspect")
            for name in ("x", "y", "width", "height"):
                self.rows[name].set_visible(mode == "box")
            self.rows["lock"].set_visible(drawing and self.canvas is not None)
            if self.canvas_box is not None:
                self.canvas_box.set_visible(drawing)
            self.draw_note.set_text(self.preview_note)
            self.draw_note.set_visible(drawing and self.canvas is None)
            # The picture takes the spare height; the form keeps only what it needs.
            self.scroller.set_vexpand(not (drawing and self.canvas is not None))

        def _changed(self, *_args):
            # A changed signal can arrive during construction before the footer.
            if self._syncing:
                return
            if hasattr(self, "error_label"):
                self.error_label.set_text("")
                self.error_label.set_visible(False)
                self._refresh_visibility()
                self._follow_crop_controls()
                self._refresh_pdf_strip()

        def _follow_crop_controls(self):
            """Keep the canvas consistent with the mode and ratio controls."""
            if self.tool_id != "cropImage" or self.canvas is None:
                return
            from .crop_geometry import parse_ratio

            raw = self._raw()
            if raw["crop_mode"] != "draw":
                self._was_drawing = False
                return
            if not getattr(self, "_was_drawing", False):
                self._was_drawing = True
                self._sync_canvas_from_fields()
            ratio = parse_ratio(raw["lock"])
            if ratio != self.canvas.ratio:
                self.canvas.set_ratio(ratio)

        def set_value(self, name, value):
            """Set a control, retaining invalid numeric text for validation."""
            field = next(
                (field for field in self.schema.fields if field.name == name), None
            )
            if field is None:
                raise KeyError(name)
            if field.choices:
                if value not in field.choices:
                    raise ValueError(f"Choose one of {field.choices} for {name}.")
                self.controls[name].set_selected(field.choices.index(value))
            else:
                self.controls[name].set_text("" if value is None else str(value))

        def get_values(self) -> dict:
            """Return validated backend kwargs or raise ValueError. Never read files."""
            return validate_options(self.tool_id, self._raw())

        def submit(self) -> bool:
            """Validate and call the scheduling callback; never process a file."""
            try:
                kwargs = self.get_values()
            except ValueError as exc:
                self.error_label.set_text(str(exc))
                self.error_label.set_visible(True)
                return False
            self.error_label.set_text("")
            self.error_label.set_visible(False)
            try:
                self.on_apply(kwargs)
            except Exception as exc:
                self.error_label.set_text(f"Could not start: {exc}")
                self.error_label.set_visible(True)
                return False
            return True

    return ToolOptions


def create_tool_options(tool_id, files, on_apply, on_cancel):
    """Return a Gtk.Box options page (GTK is imported lazily).

    ``on_apply(kwargs)`` must only enqueue a Job, not process files synchronously.
    The root exports submit(), set_value(name, value), get_values(), error_label,
    apply_button and back_button. ``files`` is used for names, not opened/probed.
    """
    if tool_id not in SCHEMAS:
        raise ValueError(f"No options schema for {tool_id!r}.")
    return _widget_type()(tool_id, files, on_apply, on_cancel)
