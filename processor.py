"""
Core crochet pattern processing logic.

The central concept is "crochet space": a coordinate system where each unit is
one stitch and stitches have a physical aspect ratio (typically wider than tall).
Converting a photograph to crochet space means:

  1. Resampling the image to the target stitch dimensions (subsampling is the
     common case — original photos are almost always larger than the final
     stitch grid).
  2. Quantizing the reduced image to a limited yarn-colour palette.
  3. Rendering a human-readable pattern grid where every cell represents one
     stitch and the cell dimensions respect the physical stitch aspect ratio.
"""

from __future__ import annotations

from io import BytesIO
from typing import Any

from PIL import Image, ImageDraw

# ---------------------------------------------------------------------------
# Public resample name → PIL constant mapping
# ---------------------------------------------------------------------------

RESAMPLE_METHODS: dict[str, Image.Resampling] = {
    "nearest": Image.Resampling.NEAREST,
    "bilinear": Image.Resampling.BILINEAR,
    "bicubic": Image.Resampling.BICUBIC,
    "lanczos": Image.Resampling.LANCZOS,
}


# ---------------------------------------------------------------------------
# Image loading
# ---------------------------------------------------------------------------


def load_image(stream: Any) -> Image.Image:
    """
    Load an image from any Pillow-supported format.

    The image is always converted to 24-bit RGB so that all downstream steps
    work on a consistent pixel type regardless of the original format
    (JPEG, PNG, GIF, BMP, TIFF, WebP, …).
    """
    return Image.open(stream).convert("RGB")


# ---------------------------------------------------------------------------
# Crochet-space subsampling
# ---------------------------------------------------------------------------


def gauge_to_stitch_counts(
    stitches_per_unit: float,
    rows_per_unit: float,
    finished_width: float,
    finished_height: float,
) -> tuple[int, int]:
    """
    Calculate the stitch grid dimensions from a crochet gauge.

    Parameters
    ----------
    stitches_per_unit:
        Number of stitches that span *one* unit of width (cm, inch, etc.).
    rows_per_unit:
        Number of rows that span *one* unit of height.
    finished_width:
        Desired finished width of the piece (same unit).
    finished_height:
        Desired finished height of the piece (same unit).

    Returns
    -------
    (stitch_count, row_count)
        Integer grid dimensions, each at least 1.
    """
    stitch_count = max(1, round(stitches_per_unit * finished_width))
    row_count = max(1, round(rows_per_unit * finished_height))
    return stitch_count, row_count


def to_crochet_space(
    image: Image.Image,
    stitch_count: int,
    row_count: int,
    resample: str = "lanczos",
) -> Image.Image:
    """
    Resample *image* so that every output pixel represents one crochet stitch.

    Subsampling (stitch_count × row_count < original dimensions) is the
    dominant use case.  Oversampling is accepted but unusual.

    Parameters
    ----------
    image:
        Source image in RGB mode.
    stitch_count:
        Number of stitches in the horizontal direction (output width).
    row_count:
        Number of rows in the vertical direction (output height).
    resample:
        Resampling algorithm key from *RESAMPLE_METHODS*.  Defaults to
        ``"lanczos"`` which gives the sharpest result when downscaling.

    Returns
    -------
    RGB image with dimensions ``(stitch_count, row_count)``.
    """
    method = RESAMPLE_METHODS.get(resample.lower(), Image.Resampling.LANCZOS)
    w = max(1, stitch_count)
    h = max(1, row_count)
    return image.resize((w, h), resample=method)


# ---------------------------------------------------------------------------
# Colour quantization
# ---------------------------------------------------------------------------

PaletteEntry = dict[str, Any]  # {hex, rgb, count, pct}


def quantize_colors(
    image: Image.Image,
    n_colors: int,
) -> tuple[Image.Image, list[PaletteEntry]]:
    """
    Reduce *image* to at most *n_colors* unique colours.

    This maps a continuous-colour crochet-space image to a small yarn palette.
    Pillow's median-cut quantizer is used; dithering is disabled so that the
    output colour per stitch is unambiguous.

    Parameters
    ----------
    image:
        RGB image (typically the output of :func:`to_crochet_space`).
    n_colors:
        Target palette size.  Clamped to 1–256.

    Returns
    -------
    (rgb_image, palette)
        *rgb_image* is a standard RGB image with at most *n_colors* unique
        pixel values.  *palette* is an ordered list (most-used first) of
        ``{'hex', 'rgb', 'count', 'pct'}`` entries.
    """
    n_colors = max(1, min(256, n_colors))
    quantized = image.quantize(
        colors=n_colors,
        method=Image.Quantize.MEDIANCUT,
        dither=Image.Dither.NONE,
    )
    rgb = quantized.convert("RGB")

    raw_palette = quantized.getpalette()  # flat [R,G,B, R,G,B, …], always 256*3 entries
    color_counts: dict[int, int] = {idx: cnt for cnt, idx in quantized.getcolors()}

    total = rgb.width * rgb.height
    palette: list[PaletteEntry] = []
    for pal_idx, cnt in sorted(color_counts.items(), key=lambda x: -x[1]):
        r = raw_palette[pal_idx * 3]
        g = raw_palette[pal_idx * 3 + 1]
        b = raw_palette[pal_idx * 3 + 2]
        palette.append(
            {
                "hex": f"#{r:02x}{g:02x}{b:02x}",
                "rgb": [r, g, b],
                "count": cnt,
                "pct": round(100.0 * cnt / total, 1),
            }
        )

    return rgb, palette


# ---------------------------------------------------------------------------
# Pattern grid rendering
# ---------------------------------------------------------------------------

# Maximum dimension for the rendered pattern image (prevents absurdly large
# images when stitch counts are high or cell sizes are large).
_MAX_PATTERN_PX = 8_000


def _clamp_cell_dims(
    stitch_count: int,
    row_count: int,
    cell_w: int,
    cell_h: int,
) -> tuple[int, int]:
    """Scale *cell_w* / *cell_h* down if the canvas would exceed *_MAX_PATTERN_PX*."""
    # Leave room for the left/top margins (≈ 60 px each)
    canvas_w = 60 + stitch_count * cell_w
    canvas_h = 60 + row_count * cell_h
    scale = min(1.0, _MAX_PATTERN_PX / max(canvas_w, canvas_h, 1))
    return max(1, int(cell_w * scale)), max(1, int(cell_h * scale))


def render_pattern_grid(
    crochet_image: Image.Image,
    cell_w: int = 24,
    cell_h: int = 16,
    grid_color: tuple[int, int, int] = (180, 180, 180),
    guide_every: int = 5,
    guide_color: tuple[int, int, int] = (60, 60, 60),
) -> Image.Image:
    """
    Render a human-readable crochet pattern grid.

    Every pixel in *crochet_image* becomes a ``cell_w × cell_h`` coloured
    rectangle.  The default cell dimensions (24 × 16) give an aspect ratio of
    1.5, matching typical worsted-weight crochet stitches.

    Parameters
    ----------
    crochet_image:
        Output of :func:`to_crochet_space` (optionally colour-quantized).
        Width = stitch count, height = row count.
    cell_w:
        Width of each stitch cell in pixels.  Automatically reduced if the
        total canvas would exceed the maximum allowed dimension.
    cell_h:
        Height of each stitch cell in pixels.
    grid_color:
        RGB colour of the minor grid lines between stitches.
    guide_every:
        Draw a heavier guide line (and a number label) every this many stitches.
    guide_color:
        RGB colour of the major guide lines.

    Returns
    -------
    RGB pattern image suitable for display or saving.
    """
    cols = crochet_image.width
    rows = crochet_image.height

    cell_w, cell_h = _clamp_cell_dims(cols, rows, cell_w, cell_h)

    # Margins for row/column number labels.
    margin_left = max(12, cell_w * 2)
    margin_top = max(12, cell_h + 4)

    canvas_w = margin_left + cols * cell_w + 1
    canvas_h = margin_top + rows * cell_h + 1

    canvas = Image.new("RGB", (canvas_w, canvas_h), (255, 255, 255))
    draw = ImageDraw.Draw(canvas)

    pixels = crochet_image.load()

    # Draw stitch cells.
    for row in range(rows):
        for col in range(cols):
            r, g, b = pixels[col, row]
            x0 = margin_left + col * cell_w
            y0 = margin_top + row * cell_h
            draw.rectangle(
                [x0, y0, x0 + cell_w, y0 + cell_h],
                fill=(r, g, b),
            )

    # Minor grid lines (between every stitch).
    for col in range(cols + 1):
        x = margin_left + col * cell_w
        is_guide = col % guide_every == 0
        draw.line(
            [(x, margin_top), (x, margin_top + rows * cell_h)],
            fill=guide_color if is_guide else grid_color,
            width=1,
        )

    for row in range(rows + 1):
        y = margin_top + row * cell_h
        is_guide = row % guide_every == 0
        draw.line(
            [(margin_left, y), (margin_left + cols * cell_w, y)],
            fill=guide_color if is_guide else grid_color,
            width=1,
        )

    # Number labels at every guide position.
    label_step = max(1, guide_every)
    for col in range(0, cols, label_step):
        x = margin_left + col * cell_w + cell_w // 2
        draw.text((x, margin_top - cell_h + 2), str(col + 1), fill=(0, 0, 0))

    for row in range(0, rows, label_step):
        y = margin_top + row * cell_h + cell_h // 2
        draw.text((4, y), str(row + 1), fill=(0, 0, 0))

    return canvas


# ---------------------------------------------------------------------------
# Convenience: image → data URI
# ---------------------------------------------------------------------------


def image_to_data_uri(image: Image.Image) -> str:
    """Return a PNG data URI for embedding in HTML or JSON."""
    buf = BytesIO()
    image.save(buf, format="PNG")
    import base64

    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"
