from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path

from flask import Flask, jsonify, render_template, request
from PIL import Image

app = Flask(__name__, template_folder="templates")
app.config.setdefault("OUTPUT_BASE_DIR", Path(__file__).resolve().parent / "outputs")

_RESAMPLE_MAP = {
    "nearest": Image.Resampling.NEAREST,
    "bilinear": Image.Resampling.BILINEAR,
    "bicubic": Image.Resampling.BICUBIC,
    "lanczos": Image.Resampling.LANCZOS,
}


def _image_to_data_uri(image: Image.Image) -> str:
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _resolve_output_path(output_name: str | None) -> Path:
    output_base = Path(app.config["OUTPUT_BASE_DIR"]).resolve()
    output_base.mkdir(parents=True, exist_ok=True)

    cleaned_name = (output_name or "processed.png").strip().lstrip("/")
    candidate = (output_base / cleaned_name).resolve()
    if output_base not in candidate.parents and candidate != output_base:
        raise ValueError("output path must stay inside configured output base directory")

    candidate.parent.mkdir(parents=True, exist_ok=True)
    return candidate


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/api/process")
def process_image():
    upload = request.files.get("image")
    if upload is None or upload.filename == "":
        return jsonify({"error": "image file is required"}), 400

    try:
        original = Image.open(upload.stream).convert("RGB")
    except Exception:
        return jsonify({"error": "unable to read image format"}), 400

    try:
        subsample = max(1, int(request.form.get("subsample", "4")))
    except ValueError:
        return jsonify({"error": "subsample must be an integer"}), 400

    method_name = request.form.get("resample", "nearest").lower()
    resample_method = _RESAMPLE_MAP.get(method_name, Image.Resampling.NEAREST)

    width = max(1, original.width // subsample)
    height = max(1, original.height // subsample)
    processed = original.resize((width, height), resample=resample_method)

    if request.form.get("allow_oversampling", "false").lower() == "true":
        try:
            target_width = int(request.form.get("target_width", width) or width)
            target_height = int(request.form.get("target_height", height) or height)
            if target_width > 0 and target_height > 0:
                processed = processed.resize((target_width, target_height), resample=resample_method)
        except ValueError:
            return jsonify({"error": "target dimensions must be integers"}), 400

    output_path = None
    output_requested = request.form.get("save_output", "false").lower() == "true"
    if output_requested:
        try:
            output_path = _resolve_output_path(request.form.get("output_name"))
            processed.save(output_path)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

    return jsonify(
        {
            "before": {
                "width": original.width,
                "height": original.height,
                "preview": _image_to_data_uri(original),
            },
            "after": {
                "width": processed.width,
                "height": processed.height,
                "preview": _image_to_data_uri(processed),
            },
            "saved_output": str(output_path) if output_path else None,
            "options": {
                "subsample": subsample,
                "resample": method_name,
                "allow_oversampling": request.form.get("allow_oversampling", "false").lower() == "true",
            },
        }
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)
