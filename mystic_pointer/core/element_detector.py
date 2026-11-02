"""Image-only detector for smart hover highlighting.

The detector is intentionally dependency-free (Pillow only).  It looks for
visually rich rectangular regions -- photographs, illustrations, screenshots
and charts -- and rejects text blocks, buttons and flat UI surfaces.

Candidates are found on a 16 px grid using local contrast (range and edge
energy), so grayscale photos and flat illustrations are found as reliably as
colourful ones.  Each candidate is then re-segmented against the colour of the
surface around it: the largest connected "ink" blob is the picture itself.  A
caption or a card border is a separate blob, so it does not extend the hover
area.  Text produces only tiny glyph blobs, which are rejected by size and by
palette statistics, without relying on saturation (which used to throw away
monochrome images).  Regions touching a screen edge are ignored so wallpaper
peeking around windows is not mistaken for a content image.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

from PIL import Image, ImageChops, ImageFilter, ImageStat
from PySide6.QtCore import QPoint, QRect


def _binary_lookup(minimum: float) -> Callable[[float], int]:
    """Build a threshold lookup table usable with ``Image.point``.

    An explicit callable type keeps type checkers on the numeric ``point``
    overload instead of the vector-transform one.
    """
    return cast(
        "Callable[[float], int]",
        lambda value: 255 if value >= minimum else 0,
    )


@dataclass
class _CellComponent:
    """Bounding box of a connected group of detailed grid cells."""

    left: int
    top: int
    right: int
    bottom: int

    def touches(self, other: "_CellComponent", gap: int = 1) -> bool:
        return not (
            self.right + gap < other.left
            or other.right + gap < self.left
            or self.bottom + gap < other.top
            or other.bottom + gap < self.top
        )


@dataclass
class _Blob:
    """Connected non-background region found inside one candidate area."""

    left: int
    top: int
    right: int
    bottom: int
    area: int


class ElementDetector:
    """Find content images in a screenshot for smart hover selection."""

    _ANALYSIS_MAX_SIZE = 1024
    _CELL_SIZE = 16

    # Candidate cells: high-pass texture, local range, or edge energy inside a
    # 16x16 cell.  Text also qualifies here; region validation is what rejects
    # it.
    _TEXTURE_RADIUS = 2.2
    _CELL_TEXTURE = 10
    _RANGE_KERNEL = 5
    _CELL_RANGE = 40
    _CELL_EDGE_FRACTION = 0.20
    _CELL_EDGE_MIN = 80
    _MAX_COMPONENTS = 80

    # Ink segmentation around a candidate.
    _SEARCH_CELLS = 4
    _BACKGROUND_BAND = 8
    _INK_THRESHOLD = 12
    _BLOB_DOWNSCALE = 4
    _MIN_BLOB_PIXELS = 3
    # A candidate must sit on a surface with a recognisable background colour.
    # Fragments of wallpaper or of one large photo fail this test.
    _MIN_RING_DOMINANT = 0.30

    # Region validation.
    _VALIDATION_MAX_SIZE = 200
    _MIN_MEANINGFUL_COLORS = 7
    _MEANINGFUL_SHARE = 0.003
    _MAX_BACKGROUND_SHARE = 0.94
    # A mostly uniform surface is text/UI unless substantial ink spans both
    # directions (chart axes, screenshot headers) or covers much of the box.
    _SPARSE_BACKGROUND_SHARE = 0.50
    _SPARSE_INK_SHARE = 0.30
    _MIN_RUN_SHARE = 0.25
    # Share of ink sitting in small, wide, word-shaped components.  Text on a
    # flat panel is almost entirely words; pictures -- including screenshots
    # with text embedded in coloured rows -- are not.
    _TEXT_ANALYSIS_WIDTH = 140
    _MAX_WORD_SHARE = 0.50
    _MAX_TEXT_BLOB_SHARE = 0.55
    _WORD_HEIGHT = 0.10
    _WORD_ASPECT = 1.2

    # Hover targets are content images, not icons, buttons or toolbars.  A
    # 96x64 logical minimum keeps small mutable UI out, and the aspect window
    # leaves portraits, 16:9 and 21:9 pictures while rejecting the wide bands
    # and narrow rails that window chrome produces.
    _MIN_LOGICAL_WIDTH = 96
    _MIN_LOGICAL_HEIGHT = 64
    _MIN_LOGICAL_ASPECT = 0.42
    _MAX_LOGICAL_WIDTH_RATIO = 0.90
    _MAX_LOGICAL_HEIGHT_RATIO = 0.90
    _MAX_LOGICAL_ASPECT = 2.6
    _EDGE_MARGIN_LOGICAL = 24

    def __init__(self, image: Image.Image, screen_geometry: QRect):
        self.image = image
        self.screen_geometry = screen_geometry
        self.detected_boxes: list[QRect] = []
        self._analyze_elements()

    def _analyze_elements(self) -> None:
        try:
            original_w, original_h = self.image.size
            screen_w = max(1, self.screen_geometry.width())
            screen_h = max(1, self.screen_geometry.height())
            if original_w == 0 or original_h == 0:
                return

            # Device pixels per logical pixel, and analysis pixels per device
            # pixel.
            ratio_x = original_w / screen_w
            ratio_y = original_h / screen_h
            scale = min(1.0, self._ANALYSIS_MAX_SIZE / max(original_w, original_h))
            small_w = max(1, int(original_w * scale))
            small_h = max(1, int(original_h * scale))

            rgb = self.image.convert("RGB")
            small = rgb.resize((small_w, small_h), Image.Resampling.BILINEAR)
            gray = small.convert("L")

            cell = self._CELL_SIZE
            cols = small_w // cell
            rows = small_h // cell
            if cols < 2 or rows < 2:
                return

            grid = self._detail_grid(gray, cols, rows, cell)
            components = self._connected_components(grid, cols, rows)
            components = self._merge_components(components)

            for component in components[: self._MAX_COMPONENTS]:
                primary, union, extras = self._candidate_boxes(
                    component, small, small_w, small_h, cell
                )
                accepted = (
                    self._validated_rect(
                        primary,
                        scale,
                        ratio_x,
                        ratio_y,
                        screen_w,
                        screen_h,
                        small,
                        small_w,
                        small_h,
                    )
                    if primary is not None
                    else None
                )
                if accepted is None and union is not None:
                    # The main blob can be only a fragment (the white body of a
                    # screenshot splits it from its header), so the column union
                    # is the fallback.
                    accepted = self._validated_rect(
                        union,
                        scale,
                        ratio_x,
                        ratio_y,
                        screen_w,
                        screen_h,
                        small,
                        small_w,
                        small_h,
                    )
                if accepted is not None:
                    self.detected_boxes.append(accepted)
                # One detail component can hold several pictures (two cards
                # side by side merge through their borders); the pictures that
                # do not share the main blob's column are kept too.
                for extra in extras:
                    accepted = self._validated_rect(
                        extra,
                        scale,
                        ratio_x,
                        ratio_y,
                        screen_w,
                        screen_h,
                        small,
                        small_w,
                        small_h,
                    )
                    if accepted is not None:
                        self.detected_boxes.append(accepted)

            self._deduplicate_boxes()
        except Exception as exc:
            print(f"[ElementDetector] Analysis fallback: {exc}")

    def _validated_rect(
        self,
        box: tuple[int, int, int, int],
        scale: float,
        ratio_x: float,
        ratio_y: float,
        screen_w: int,
        screen_h: int,
        small: Image.Image,
        small_w: int,
        small_h: int,
    ) -> QRect | None:
        left, top, right, bottom = box
        logical_width = (right - left) / scale / ratio_x
        logical_height = (bottom - top) / scale / ratio_y
        if not self._valid_size(logical_width, logical_height, screen_w, screen_h):
            return None

        margin_x = max(2, int(round(self._EDGE_MARGIN_LOGICAL * ratio_x * scale)))
        margin_y = max(2, int(round(self._EDGE_MARGIN_LOGICAL * ratio_y * scale)))
        if (
            left <= margin_x
            or top <= margin_y
            or right >= small_w - margin_x
            or bottom >= small_h - margin_y
        ):
            # Wallpaper and full-bleed window backgrounds are not content
            # images; they also produce huge highlights.
            return None

        candidate = small.crop((left, top, right, bottom))
        if not self._region_looks_like_image(candidate):
            return None

        logical_left = self.screen_geometry.x() + int(round(left / scale / ratio_x))
        logical_top = self.screen_geometry.y() + int(round(top / scale / ratio_y))
        return QRect(
            logical_left,
            logical_top,
            max(1, int(round(logical_width))),
            max(1, int(round(logical_height))),
        )

    # --- Candidate grid -----------------------------------------------------

    def _detail_grid(
        self,
        gray: Image.Image,
        cols: int,
        rows: int,
        cell: int,
    ) -> list[list[bool]]:
        """Mark cells that contain local contrast at the analysis scale.

        Local contrast is measured as the difference between the image and a
        blurred copy of itself.  That is a high-pass filter: it responds to
        photographic texture and to glyph strokes, while flat UI surfaces and
        smooth gradients stay dark.  A Gaussian blur is used instead of the
        old min/max rank filter because rank filters take several hundred
        milliseconds on a full-screen frame; this keeps detection interactive.
        """
        del cell  # the grid is already in cell units
        texture = ImageChops.difference(
            gray,
            gray.filter(ImageFilter.GaussianBlur(self._TEXTURE_RADIUS)),
        )
        # Local intensity range also picks up flat illustrations, where the
        # interior has no texture but the outlines do.  The rank filter runs on
        # a half-resolution copy: running it on the full analysis image costs
        # 350 ms, on the half-size copy about 50 ms for the same effective
        # neighbourhood.
        half = gray.resize(
            (max(1, gray.width // 2), max(1, gray.height // 2)),
            Image.Resampling.BOX,
        )
        local_range = ImageChops.difference(
            half.filter(ImageFilter.MaxFilter(self._RANGE_KERNEL)),
            half.filter(ImageFilter.MinFilter(self._RANGE_KERNEL)),
        )
        edges = gray.filter(ImageFilter.FIND_EDGES)

        texture_cells = texture.resize((cols, rows), Image.Resampling.BOX).tobytes()
        range_cells = local_range.resize((cols, rows), Image.Resampling.BOX).tobytes()
        edge_strength = edges.point(_binary_lookup(self._CELL_EDGE_MIN))
        edge_cells = edge_strength.resize((cols, rows), Image.Resampling.BOX).tobytes()
        edge_minimum = int(255 * self._CELL_EDGE_FRACTION)

        grid: list[list[bool]] = []
        for row in range(rows):
            offset = row * cols
            grid.append(
                [
                    texture_cells[offset + col] >= self._CELL_TEXTURE
                    or range_cells[offset + col] >= self._CELL_RANGE
                    or edge_cells[offset + col] >= edge_minimum
                    for col in range(cols)
                ]
            )
        return grid

    def _connected_components(
        self,
        grid: list[list[bool]],
        cols: int,
        rows: int,
    ) -> list[_CellComponent]:
        visited = [[False] * cols for _ in range(rows)]
        components: list[_CellComponent] = []

        for row in range(rows):
            for col in range(cols):
                if not grid[row][col] or visited[row][col]:
                    continue

                min_row = max_row = row
                min_col = max_col = col
                stack = [(row, col)]
                visited[row][col] = True

                while stack:
                    current_row, current_col = stack.pop()
                    min_row = min(min_row, current_row)
                    max_row = max(max_row, current_row)
                    min_col = min(min_col, current_col)
                    max_col = max(max_col, current_col)

                    for delta_row in (-1, 0, 1):
                        for delta_col in (-1, 0, 1):
                            next_row = current_row + delta_row
                            next_col = current_col + delta_col
                            if (
                                0 <= next_row < rows
                                and 0 <= next_col < cols
                                and grid[next_row][next_col]
                                and not visited[next_row][next_col]
                            ):
                                visited[next_row][next_col] = True
                                stack.append((next_row, next_col))

                components.append(_CellComponent(min_col, min_row, max_col, max_row))

        return components

    def _merge_components(
        self,
        components: list[_CellComponent],
    ) -> list[_CellComponent]:
        """Join fragments of one image split by smooth or flat areas."""
        merged = True
        current = components
        while merged:
            merged = False
            result: list[_CellComponent] = []
            for component in current:
                for existing in result:
                    if existing.touches(component):
                        existing.left = min(existing.left, component.left)
                        existing.top = min(existing.top, component.top)
                        existing.right = max(existing.right, component.right)
                        existing.bottom = max(existing.bottom, component.bottom)
                        merged = True
                        break
                else:
                    result.append(component)
            current = result
        return current

    # --- Ink segmentation ---------------------------------------------------

    def _candidate_boxes(
        self,
        component: _CellComponent,
        small: Image.Image,
        small_w: int,
        small_h: int,
        cell: int,
    ) -> tuple[
        tuple[int, int, int, int] | None,
        tuple[int, int, int, int] | None,
        list[tuple[int, int, int, int]],
    ]:
        """Turn a detail component into candidate image bounds.

        Returns the main blob, an optional union of its column fragments, and
        the substantial blobs that sit in other columns (other pictures).
        """
        left = component.left * cell
        top = component.top * cell
        right = min(small_w, (component.right + 1) * cell)
        bottom = min(small_h, (component.bottom + 1) * cell)
        if right - left < 8 or bottom - top < 8:
            return None, None, []
        # Long, thin strips are toolbars, text lines and separators.
        if (right - left) / max(1, bottom - top) > 12:
            return None, None, []

        # The background is sampled from a narrow ring around the detail
        # cells, not around the (larger) search area: that ring is usually the
        # card or page behind the picture.  Sampling the search border would
        # pick up neighbouring photos and text.
        background, dominant = self._ring_background(
            small, (left, top, right, bottom), small_w, small_h
        )
        # An image sits on a recognisable surface: a card, a page, a window.
        # When the ring is a noisy mix of colours there is no surface to segment
        # against -- the candidate is a fragment of a wallpaper or of one large
        # photo, and highlighting it would be arbitrary.
        if dominant < self._MIN_RING_DOMINANT:
            return None, None, []

        grow = cell * self._SEARCH_CELLS
        sx0 = max(0, left - grow)
        sy0 = max(0, top - grow)
        sx1 = min(small_w, right + grow)
        sy1 = min(small_h, bottom + grow)
        search = small.crop((sx0, sy0, sx1, sy1))
        difference = ImageChops.difference(search, Image.new("RGB", search.size, background))
        red, green, blue = difference.split()
        largest = ImageChops.lighter(ImageChops.lighter(red, green), blue)
        mask = largest.point(_binary_lookup(self._INK_THRESHOLD))

        factor = self._BLOB_DOWNSCALE
        mask_w = max(1, mask.width // factor)
        mask_h = max(1, mask.height // factor)
        small_mask = mask.resize((mask_w, mask_h), Image.Resampling.BOX).point(_binary_lookup(1))

        blobs = self._mask_blobs(small_mask)
        if not blobs:
            return None, None, []

        def to_analysis(blob: _Blob) -> tuple[int, int, int, int]:
            return (
                max(0, sx0 + blob.left * factor),
                max(0, sy0 + blob.top * factor),
                min(small_w, sx0 + (blob.right + 1) * factor),
                min(small_h, sy0 + (blob.bottom + 1) * factor),
            )

        # A blob can run past the component when the colours beyond the window
        # frame differ from the sampled background: at the bottom of a window
        # the desktop behind it would then be glued onto the picture.  The
        # detail cells already cover the picture, so a candidate is clamped to
        # the component plus one cell of margin.
        keep = cell
        allowed_left = max(0, left - keep)
        allowed_top = max(0, top - keep)
        allowed_right = min(small_w, right + keep)
        allowed_bottom = min(small_h, bottom + keep)

        def clamp(box: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
            return (
                max(allowed_left, box[0]),
                max(allowed_top, box[1]),
                min(allowed_right, box[2]),
                min(allowed_bottom, box[3]),
            )

        def intersects_component(box: tuple[int, int, int, int]) -> bool:
            return not (
                box[2] <= allowed_left
                or box[0] >= allowed_right
                or box[3] <= allowed_top
                or box[1] >= allowed_bottom
            )

        # Ignore specks, and fragments that are negligible next to the main
        # blob (single letters of a caption far from the picture).  Only blobs
        # that belong to this component take part: the biggest blob in the
        # search area can be an unrelated one beyond the window frame.
        nearby = [
            (blob, to_analysis(blob))
            for blob in blobs
            if blob.area >= self._MIN_BLOB_PIXELS and intersects_component(to_analysis(blob))
        ]
        if not nearby:
            return None, None, []
        main_blob = max((blob for blob, _box in nearby), key=lambda blob: blob.area)
        minimum_area = max(self._MIN_BLOB_PIXELS, int(main_blob.area * 0.02))
        parts = [(blob, clamp(box)) for blob, box in nearby if blob.area >= minimum_area]

        primary = clamp(to_analysis(main_blob))
        if not any(box == primary for _blob, box in parts):
            parts.append((main_blob, primary))

        # Fragments of the main picture share its column (a screenshot header
        # above its white body, the bars and axes of a chart).  They are united
        # only when the main blob alone is not a plausible picture.
        column = [box for _blob, box in parts if self._shares_column(primary, box)]
        union: tuple[int, int, int, int] | None = None
        if len(column) > 1:
            union = (
                min(box[0] for box in column),
                min(box[1] for box in column),
                max(box[2] for box in column),
                max(box[3] for box in column),
            )
            if union == primary:
                union = None

        # A second picture in the same component sits beside the main one and
        # must be substantial on its own; stray glyphs are not.
        extras = [
            box
            for blob, box in parts
            if not self._shares_column(primary, box)
            and blob.area >= max(self._MIN_BLOB_PIXELS, int(main_blob.area * 0.10))
        ]

        return primary, union, extras

    @staticmethod
    def _shares_column(
        first: tuple[int, int, int, int],
        second: tuple[int, int, int, int],
    ) -> bool:
        """Whether two boxes overlap horizontally enough to be one picture."""
        overlap = min(first[2], second[2]) - max(first[0], second[0])
        narrower = min(first[2] - first[0], second[2] - second[0])
        return narrower > 0 and overlap >= narrower * 0.5

    @staticmethod
    def _ring_background(
        image: Image.Image,
        box: tuple[int, int, int, int],
        width: int,
        height: int,
    ) -> tuple[tuple[int, int, int], float]:
        """Describe the band just outside ``box``.

        Returns the median colour (used for segmentation) and the share of the
        most common colour in the band.  A candidate that sits on a page, card
        or window has a dominant surrounding colour; a fragment of wallpaper or
        of one large photo does not.
        """
        left, top, right, bottom = box
        band = ElementDetector._BACKGROUND_BAND
        x0 = max(0, left - band)
        y0 = max(0, top - band)
        x1 = min(width, right + band)
        y1 = min(height, bottom + band)
        outer = image.crop((x0, y0, x1, y1))
        outer_w, outer_h = outer.size
        if outer_w <= 0 or outer_h <= 0:
            return (255, 255, 255), 0.0
        strip = max(1, min(band, outer_w // 2, outer_h // 2))
        parts = [
            outer.crop((0, 0, outer_w, strip)),
            outer.crop((0, outer_h - strip, outer_w, outer_h)),
            outer.crop((0, strip, strip, outer_h - strip)),
            outer.crop((outer_w - strip, strip, outer_w, outer_h - strip)),
        ]
        total = sum(part.width for part in parts)
        ring = Image.new("RGB", (max(1, total), max(1, strip)))
        offset = 0
        for part in parts:
            ring.paste(part, (offset, 0))
            offset += part.width

        stats = ImageStat.Stat(ring)
        median = stats.median
        quantized = ring.quantize(colors=8, method=Image.Quantize.MEDIANCUT).convert("RGB")
        colors = quantized.getcolors(maxcolors=8 * 8) or []
        area = max(1, ring.width * ring.height)
        dominant = max((count for count, _color in colors), default=0) / area
        return (
            (int(median[0]), int(median[1]), int(median[2])),
            dominant,
        )

    def _mask_blobs(self, mask: Image.Image) -> list[_Blob]:
        """Connected components of a binary mask, using an explicit stack."""
        width, height = mask.size
        if width <= 0 or height <= 0:
            return []
        data = mask.tobytes()
        visited = bytearray(width * height)
        blobs: list[_Blob] = []

        for start in range(width * height):
            if not data[start] or visited[start]:
                continue
            visited[start] = 1
            stack = [start]
            area = 0
            min_x = max_x = start % width
            min_y = max_y = start // width

            while stack:
                index = stack.pop()
                area += 1
                y, x = divmod(index, width)
                if x < min_x:
                    min_x = x
                elif x > max_x:
                    max_x = x
                if y < min_y:
                    min_y = y
                elif y > max_y:
                    max_y = y

                for next_y in (y - 1, y, y + 1):
                    if next_y < 0 or next_y >= height:
                        continue
                    row = next_y * width
                    for next_x in (x - 1, x, x + 1):
                        if next_x < 0 or next_x >= width:
                            continue
                        neighbour = row + next_x
                        if data[neighbour] and not visited[neighbour]:
                            visited[neighbour] = 1
                            stack.append(neighbour)

            blobs.append(_Blob(min_x, min_y, max_x, max_y, area))

        return blobs

    # --- Validation ---------------------------------------------------------

    def _valid_size(
        self,
        width: float,
        height: float,
        screen_w: int,
        screen_h: int,
    ) -> bool:
        if width < self._MIN_LOGICAL_WIDTH or height < self._MIN_LOGICAL_HEIGHT:
            return False
        if width > screen_w * self._MAX_LOGICAL_WIDTH_RATIO:
            return False
        if height > screen_h * self._MAX_LOGICAL_HEIGHT_RATIO:
            return False
        return self._MIN_LOGICAL_ASPECT <= width / max(1.0, height) <= self._MAX_LOGICAL_ASPECT

    def _region_looks_like_image(self, crop: Image.Image) -> bool:
        """Reject text blocks and flat UI surfaces inside a candidate box."""
        # Palette statistics do not need full resolution; shrinking keeps the
        # (relatively slow) quantizer cheap on large photos.
        if max(crop.size) > self._VALIDATION_MAX_SIZE:
            ratio = self._VALIDATION_MAX_SIZE / max(crop.size)
            crop = crop.resize(
                (
                    max(1, int(crop.width * ratio)),
                    max(1, int(crop.height * ratio)),
                ),
                Image.Resampling.BOX,
            )
        area = crop.width * crop.height
        if area <= 0:
            return False

        quantized = crop.quantize(
            colors=64,
            method=Image.Quantize.MEDIANCUT,
        ).convert("RGB")
        colors = quantized.getcolors(maxcolors=64 * 64) or []
        if not colors:
            return False

        minimum = max(3, int(area * self._MEANINGFUL_SHARE))
        meaningful = [count for count, _color in colors if count >= minimum]
        if len(meaningful) < self._MIN_MEANINGFUL_COLORS:
            return False

        top_count, top_color = max(colors, key=lambda item: item[0])
        if not isinstance(top_color, tuple) or len(top_color) < 3:
            return False
        background = (int(top_color[0]), int(top_color[1]), int(top_color[2]))
        background_share = top_count / area
        if background_share > self._MAX_BACKGROUND_SHARE:
            return False

        if self._looks_like_text(crop, background):
            return False

        if background_share > self._SPARSE_BACKGROUND_SHARE:
            mask = self._ink_mask(crop, background)
            horizontal, vertical = self._longest_runs(mask)
            mask_area = max(1, mask.width * mask.height)
            ink_share = mask.histogram()[255] / mask_area
            if ink_share < self._SPARSE_INK_SHARE:
                # Text has short glyph strokes, so it has no long run in both
                # directions.  Charts and screenshots do.
                if min(horizontal, vertical) < self._MIN_RUN_SHARE:
                    return False

        return True

    def _looks_like_text(
        self,
        crop: Image.Image,
        background: tuple[int, int, int],
    ) -> bool:
        """Whether a candidate is text on a flat panel rather than a picture.

        Text breaks into many small, wide, word-shaped components; a picture
        has one or two large blobs.  A text-heavy screenshot keeps its large
        header/body blobs and is therefore still accepted.
        """
        ratio = self._TEXT_ANALYSIS_WIDTH / max(1, crop.width)
        if ratio < 1.0:
            crop = crop.resize(
                (
                    max(1, int(crop.width * ratio)),
                    max(1, int(crop.height * ratio)),
                ),
                Image.Resampling.BOX,
            )
        mask = self._ink_mask(crop, background)
        blobs = self._mask_blobs(mask)
        ink = sum(blob.area for blob in blobs)
        if ink <= 0:
            return False
        height_limit = max(3, int(mask.height * self._WORD_HEIGHT))
        words = 0
        largest = 0
        for blob in blobs:
            largest = max(largest, blob.area)
            height = blob.bottom - blob.top + 1
            width = blob.right - blob.left + 1
            if blob.area >= 4 and height <= height_limit and width >= height * self._WORD_ASPECT:
                words += blob.area
        return words / ink >= self._MAX_WORD_SHARE and largest / ink < self._MAX_TEXT_BLOB_SHARE

    @staticmethod
    def _ink_mask(crop: Image.Image, background: tuple[int, int, int]) -> Image.Image:
        """Binary mask of pixels that differ from the dominant colour."""
        flat = Image.new("RGB", crop.size, background)
        difference = ImageChops.difference(crop.convert("RGB"), flat)
        red, green, blue = difference.split()
        largest = ImageChops.lighter(ImageChops.lighter(red, green), blue)
        # Downscale before the (pure-Python) run scan; the threshold stays low
        # so one-pixel chart lines survive the reduction.
        if largest.width > 360:
            ratio = 360 / largest.width
            largest = largest.resize(
                (360, max(1, int(largest.height * ratio))),
                Image.Resampling.BOX,
            )
        return largest.point(_binary_lookup(15))

    @staticmethod
    def _longest_runs(mask: Image.Image) -> tuple[float, float]:
        """Longest horizontal and vertical ink runs, normalised by size."""
        width, height = mask.size
        if width == 0 or height == 0:
            return 0.0, 0.0
        data = mask.tobytes()
        longest_row = 0
        longest_col = 0

        for row in range(height):
            run = 0
            for value in data[row * width : (row + 1) * width]:
                if value:
                    run += 1
                    if run > longest_row:
                        longest_row = run
                else:
                    run = 0

        for col in range(width):
            run = 0
            for row in range(height):
                if data[row * width + col]:
                    run += 1
                    if run > longest_col:
                        longest_col = run
                else:
                    run = 0

        return longest_row / width, longest_col / height

    def _deduplicate_boxes(self) -> None:
        unique: list[QRect] = []
        for box in sorted(
            self.detected_boxes,
            key=lambda item: item.width() * item.height(),
            reverse=True,
        ):
            duplicate = False
            for existing in unique:
                intersection = existing.intersected(box)
                if intersection.isEmpty():
                    continue
                intersection_area = intersection.width() * intersection.height()
                box_area = max(1, box.width() * box.height())
                existing_area = max(1, existing.width() * existing.height())
                if (
                    intersection_area / box_area >= 0.80
                    or intersection_area / existing_area >= 0.80
                ):
                    duplicate = True
                    break
            if not duplicate:
                unique.append(box)
        self.detected_boxes = unique

    def find_element_at(self, pos: QPoint) -> QRect | None:
        """Find the most specific detected image under ``pos``."""
        candidates = [box for box in self.detected_boxes if box.contains(pos)]
        if not candidates:
            return None
        return min(candidates, key=lambda box: box.width() * box.height())
