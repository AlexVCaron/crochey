import io
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from app import app


class AppTestCase(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        app.config["TESTING"] = True
        app.config["OUTPUT_BASE_DIR"] = Path(self.tempdir.name)
        self.client = app.test_client()

    def tearDown(self):
        self.tempdir.cleanup()

    @staticmethod
    def _png_bytes(width=20, height=10):
        image = Image.new("RGB", (width, height), (255, 0, 0))
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        buffer.seek(0)
        return buffer

    def test_process_subsamples_image(self):
        response = self.client.post(
            "/api/process",
            data={
                "image": (self._png_bytes(), "sample.png"),
                "subsample": "2",
                "resample": "nearest",
            },
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["before"]["width"], 20)
        self.assertEqual(payload["before"]["height"], 10)
        self.assertEqual(payload["after"]["width"], 10)
        self.assertEqual(payload["after"]["height"], 5)
        self.assertTrue(payload["before"]["preview"].startswith("data:image/png;base64,"))
        self.assertTrue(payload["after"]["preview"].startswith("data:image/png;base64,"))

    def test_process_can_save_output(self):
        response = self.client.post(
            "/api/process",
            data={
                "image": (self._png_bytes(), "sample.png"),
                "subsample": "4",
                "save_output": "true",
                "output_name": "patterns/piece-1.png",
            },
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        output = Path(payload["saved_output"])
        self.assertTrue(output.exists())
        self.assertTrue(str(output).startswith(self.tempdir.name))


if __name__ == "__main__":
    unittest.main()
