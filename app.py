"""
Crochey – web server.

Routes
------
GET  /                   Serve the single-page UI.
POST /api/process        Process an uploaded image and return JSON results.
GET  /api/download/<name> Download a previously saved output file.
"""

from __future__ import annotations

import re
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request, send_file
from PIL import Image

import processor as proc

app = Flask(__name__, template_folder="templates")
app.config.setdefault("OUTPUT_BASE_DIR", Path(__file__).resolve().parent / "outputs")

_ALLOWED_OUTPUT_NAME = re.compile(r"^[A-Za-z0-9._-]+$")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_output_path(name: str | None) -> Path:
    """
    Return an absolute path inside OUTPUT_BASE_DIR for *name*.

    Raises ValueError if *name* contains disallowed characters.
    """
    output_base: Path = Path(app.config["OUTPUT_BASE_DIR"]).resolve()
    output_base.mkdir(parents=True, exist_ok=True)

    clean = (name or "pattern.png").strip()
    # Validate the full supplied name — no path separators or sequences like '..'
    if not _ALLOWED_OUTPUT_NAME.fullmatch(clean):
        raise ValueError("output name must contain only letters, digits, dots, underscores, or dashes")

    return output_base / clean


def _int_form(key: str, default: int, *, min_val: int | None = None) -> int:
    raw = request.form.get(key, "").strip()
    value = int(raw) if raw else default
    if min_val is not None:
        value = max(min_val, value)
    return value


def _bool_form(key: str) -> bool:
    return request.form.get(key, "false").lower() == "true"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/")
def index() -> str:
    return render_template("index.html")


@app.post("/api/process")
def process_image() -> tuple[Response, int] | Response:
    # --- 1. Load image ---
    upload = request.files.get("image")
    if upload is None or upload.filename == "":
        return jsonify({"error": "image file is required"}), 400

    try:
        original = proc.load_image(upload.stream)
    except Exception:
        return jsonify({"error": "unable to read image – unsupported format"}), 400

    # --- 2. Determine target stitch / row counts ---
    mode = request.form.get("mode", "direct").lower()
    try:
        if mode == "gauge":
            spu = float(request.form.get("stitches_per_unit", "14") or "14")
            rpu = float(request.form.get("rows_per_unit", "12") or "12")
            fw = float(request.form.get("finished_width", "20") or "20")
            fh = float(request.form.get("finished_height", "15") or "15")
            stitch_count, row_count = proc.gauge_to_stitch_counts(spu, rpu, fw, fh)
        else:
            stitch_count = _int_form("stitch_count", max(1, original.width // 4), min_val=1)
            row_count = _int_form("row_count", max(1, original.height // 4), min_val=1)
    except (ValueError, ZeroDivisionError):
        return jsonify({"error": "invalid sizing parameters"}), 400

    # --- 3. Resample to crochet space ---
    resample = request.form.get("resample", "lanczos").lower()
    crochet = proc.to_crochet_space(original, stitch_count, row_count, resample=resample)

    # --- 4. Optional colour quantization ---
    palette: list[proc.PaletteEntry] = []
    n_colors_raw = request.form.get("n_colors", "8").strip()
    try:
        n_colors = int(n_colors_raw) if n_colors_raw else 0
    except ValueError:
        return jsonify({"error": "n_colors must be an integer"}), 400

    if n_colors > 0:
        crochet, palette = proc.quantize_colors(crochet, n_colors)

    # --- 5. Render pattern grid ---
    try:
        cell_w = _int_form("cell_w", 24, min_val=4)
        cell_h = _int_form("cell_h", 16, min_val=4)
        guide_every = _int_form("guide_every", 5, min_val=1)
    except ValueError:
        return jsonify({"error": "cell dimensions must be positive integers"}), 400

    pattern_img = proc.render_pattern_grid(
        crochet,
        cell_w=cell_w,
        cell_h=cell_h,
        guide_every=guide_every,
    )

    # --- 6. Optional save ---
    saved_output: str | None = None
    if _bool_form("save_output"):
        try:
            out_path = _resolve_output_path(request.form.get("output_name"))
            pattern_img.save(out_path)
            saved_output = out_path.name  # return only the file name, not the full server path
        except ValueError:
            return jsonify({"error": "invalid output name"}), 400

    return jsonify(
        {
            "before": {
                "width": original.width,
                "height": original.height,
                "preview": proc.image_to_data_uri(original),
            },
            "after": {
                "stitch_count": crochet.width,
                "row_count": crochet.height,
                "preview": proc.image_to_data_uri(crochet),
            },
            "pattern": {
                "width": pattern_img.width,
                "height": pattern_img.height,
                "preview": proc.image_to_data_uri(pattern_img),
            },
            "palette": palette,
            "saved_output": saved_output,
            "options": {
                "mode": mode,
                "stitch_count": stitch_count,
                "row_count": row_count,
                "resample": resample,
                "n_colors": n_colors,
                "cell_w": cell_w,
                "cell_h": cell_h,
            },
        }
    )


@app.get("/api/download/<output_name>")
def download_output(output_name: str) -> Response | tuple[Response, int]:
    """Serve a previously saved pattern file for download."""
    if not _ALLOWED_OUTPUT_NAME.fullmatch(output_name):
        return jsonify({"error": "invalid file name"}), 400

    output_base: Path = Path(app.config["OUTPUT_BASE_DIR"]).resolve()
    target = (output_base / output_name).resolve()

    # Ensure the resolved path is still inside the output base directory.
    if output_base not in target.parents:
        return jsonify({"error": "invalid file name"}), 400

    if not target.exists():
        return jsonify({"error": "file not found"}), 404

    return send_file(target, as_attachment=True)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)
