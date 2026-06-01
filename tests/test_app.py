"""Integration tests for Flask routes."""

import io
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from app import app


def _png_bytes(width=60, height=40, color=(200, 100, 50)):
    img = Image.new("RGB", (width, height), color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


class AppTestCase(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        app.config["TESTING"] = True
        app.config["OUTPUT_BASE_DIR"] = Path(self.tempdir.name)
        self.client = app.test_client()

    def tearDown(self):
        self.tempdir.cleanup()

    # ---- UI route ----

    def test_index_returns_html(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Crochey", resp.data)

    # ---- Direct mode ----

    def test_direct_mode_subsamples_to_stitch_count(self):
        resp = self.client.post(
            "/api/process",
            data={
                "image": (_png_bytes(60, 40), "test.png"),
                "mode": "direct",
                "stitch_count": "30",
                "row_count": "20",
                "n_colors": "0",
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["after"]["stitch_count"], 30)
        self.assertEqual(data["after"]["row_count"], 20)
        self.assertEqual(data["before"]["width"], 60)
        self.assertEqual(data["before"]["height"], 40)

    def test_response_includes_pattern_grid(self):
        resp = self.client.post(
            "/api/process",
            data={"image": (_png_bytes(), "test.png"), "n_colors": "0"},
            content_type="multipart/form-data",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("pattern", data)
        self.assertTrue(data["pattern"]["preview"].startswith("data:image/png;base64,"))
        self.assertGreater(data["pattern"]["width"], 0)

    def test_colour_quantization_returns_palette(self):
        resp = self.client.post(
            "/api/process",
            data={
                "image": (_png_bytes(), "test.png"),
                "n_colors": "4",
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIsInstance(data["palette"], list)
        self.assertGreater(len(data["palette"]), 0)
        entry = data["palette"][0]
        self.assertIn("hex", entry)
        self.assertIn("count", entry)
        self.assertIn("pct", entry)

    def test_no_quantization_returns_empty_palette(self):
        resp = self.client.post(
            "/api/process",
            data={"image": (_png_bytes(), "test.png"), "n_colors": "0"},
            content_type="multipart/form-data",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["palette"], [])

    # ---- Gauge mode ----

    def test_gauge_mode_calculates_stitch_counts(self):
        # 14 sts/unit, 12 rows/unit, 10 × 10 units → 140 × 120
        resp = self.client.post(
            "/api/process",
            data={
                "image": (_png_bytes(200, 200), "test.png"),
                "mode": "gauge",
                "stitches_per_unit": "14",
                "rows_per_unit": "12",
                "finished_width": "10",
                "finished_height": "10",
                "n_colors": "0",
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["after"]["stitch_count"], 140)
        self.assertEqual(data["after"]["row_count"], 120)

    # ---- Output saving ----

    def test_save_output_creates_file(self):
        resp = self.client.post(
            "/api/process",
            data={
                "image": (_png_bytes(), "test.png"),
                "n_colors": "0",
                "save_output": "true",
                "output_name": "my-pattern.png",
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["saved_output"], "my-pattern.png")
        self.assertTrue((Path(self.tempdir.name) / "my-pattern.png").exists())

    def test_invalid_output_name_rejected(self):
        resp = self.client.post(
            "/api/process",
            data={
                "image": (_png_bytes(), "test.png"),
                "n_colors": "0",
                "save_output": "true",
                "output_name": "../escape.png",
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(resp.status_code, 400)

    # ---- Download endpoint ----

    def test_download_saved_file(self):
        # First save a file
        self.client.post(
            "/api/process",
            data={
                "image": (_png_bytes(), "test.png"),
                "n_colors": "0",
                "save_output": "true",
                "output_name": "dl-test.png",
            },
            content_type="multipart/form-data",
        )
        resp = self.client.get("/api/download/dl-test.png")
        self.assertEqual(resp.status_code, 200)

    def test_download_missing_file_returns_404(self):
        resp = self.client.get("/api/download/does-not-exist.png")
        self.assertEqual(resp.status_code, 404)

    def test_download_path_traversal_rejected(self):
        resp = self.client.get("/api/download/../app.py")
        self.assertEqual(resp.status_code, 404)

    # ---- Error cases ----

    def test_missing_image_returns_400(self):
        resp = self.client.post("/api/process", data={}, content_type="multipart/form-data")
        self.assertEqual(resp.status_code, 400)

    def test_corrupt_image_returns_400(self):
        resp = self.client.post(
            "/api/process",
            data={"image": (io.BytesIO(b"not an image"), "bad.png")},
            content_type="multipart/form-data",
        )
        self.assertEqual(resp.status_code, 400)


if __name__ == "__main__":
    unittest.main()
