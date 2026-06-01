"""Unit tests for the crochet processor module."""

import io
import unittest

from PIL import Image

import processor as proc


def _rgb_image(width=60, height=40, color=(255, 0, 0)):
    return Image.new("RGB", (width, height), color)


def _png_stream(width=60, height=40, color=(255, 0, 0)):
    img = _rgb_image(width, height, color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


class TestLoadImage(unittest.TestCase):
    def test_loads_png(self):
        img = proc.load_image(_png_stream())
        self.assertEqual(img.mode, "RGB")
        self.assertEqual(img.size, (60, 40))

    def test_converts_to_rgb(self):
        # Create a RGBA image as bytes and load it
        buf = io.BytesIO()
        Image.new("RGBA", (10, 10), (0, 255, 0, 128)).save(buf, format="PNG")
        buf.seek(0)
        img = proc.load_image(buf)
        self.assertEqual(img.mode, "RGB")


class TestGaugeCounts(unittest.TestCase):
    def test_basic_gauge(self):
        # 14 sts/10 cm, 12 rows/10 cm, 20 cm × 15 cm
        sc, rc = proc.gauge_to_stitch_counts(1.4, 1.2, 20, 15)
        self.assertEqual(sc, 28)
        self.assertEqual(rc, 18)

    def test_minimum_one(self):
        sc, rc = proc.gauge_to_stitch_counts(0.001, 0.001, 0.1, 0.1)
        self.assertEqual(sc, 1)
        self.assertEqual(rc, 1)


class TestToCrochetSpace(unittest.TestCase):
    def test_subsamples_to_target_dimensions(self):
        img = _rgb_image(120, 80)
        result = proc.to_crochet_space(img, 40, 30)
        self.assertEqual(result.size, (40, 30))

    def test_respects_resample_choice(self):
        # All resample methods should produce a valid image of the right size
        img = _rgb_image(100, 100)
        for method in proc.RESAMPLE_METHODS:
            out = proc.to_crochet_space(img, 10, 10, resample=method)
            self.assertEqual(out.size, (10, 10))

    def test_clamps_to_minimum_one(self):
        img = _rgb_image(4, 4)
        out = proc.to_crochet_space(img, 0, 0)
        self.assertEqual(out.size, (1, 1))

    def test_unknown_resample_falls_back(self):
        img = _rgb_image(20, 20)
        out = proc.to_crochet_space(img, 5, 5, resample="notamethod")
        self.assertEqual(out.size, (5, 5))


class TestQuantizeColors(unittest.TestCase):
    def test_reduces_color_count(self):
        # Create an image with many unique colours
        img = _rgb_image(50, 50)
        # Paint four distinct colour quadrants
        import PIL.ImageDraw as ID
        draw = ID.Draw(img)
        draw.rectangle([0, 0, 24, 24], fill=(255, 0, 0))
        draw.rectangle([25, 0, 49, 24], fill=(0, 255, 0))
        draw.rectangle([0, 25, 24, 49], fill=(0, 0, 255))
        draw.rectangle([25, 25, 49, 49], fill=(255, 255, 0))

        quantized, palette = proc.quantize_colors(img, 4)

        self.assertEqual(quantized.mode, "RGB")
        self.assertLessEqual(len(palette), 4)

    def test_palette_entries_have_required_keys(self):
        img = _rgb_image(10, 10)
        _, palette = proc.quantize_colors(img, 2)
        for entry in palette:
            self.assertIn("hex", entry)
            self.assertIn("rgb", entry)
            self.assertIn("count", entry)
            self.assertIn("pct", entry)

    def test_palette_percentages_sum_to_100(self):
        img = _rgb_image(20, 20)
        _, palette = proc.quantize_colors(img, 4)
        total_pct = sum(e["pct"] for e in palette)
        self.assertAlmostEqual(total_pct, 100.0, delta=1.0)

    def test_palette_counts_sum_to_pixels(self):
        img = _rgb_image(12, 8)
        _, palette = proc.quantize_colors(img, 3)
        self.assertEqual(sum(e["count"] for e in palette), 12 * 8)

    def test_clamps_n_colors_to_valid_range(self):
        img = _rgb_image(10, 10)
        _, pal_min = proc.quantize_colors(img, 0)
        self.assertGreater(len(pal_min), 0)
        _, pal_max = proc.quantize_colors(img, 300)
        self.assertLessEqual(len(pal_max), 256)


class TestRenderPatternGrid(unittest.TestCase):
    def test_returns_rgb_image(self):
        img = _rgb_image(10, 8)
        grid = proc.render_pattern_grid(img)
        self.assertEqual(grid.mode, "RGB")

    def test_output_larger_than_input(self):
        img = _rgb_image(10, 8)
        grid = proc.render_pattern_grid(img, cell_w=24, cell_h=16)
        self.assertGreater(grid.width, img.width)
        self.assertGreater(grid.height, img.height)

    def test_custom_cell_dimensions(self):
        img = _rgb_image(5, 5)
        g1 = proc.render_pattern_grid(img, cell_w=10, cell_h=10)
        g2 = proc.render_pattern_grid(img, cell_w=20, cell_h=20)
        self.assertLess(g1.width, g2.width)

    def test_auto_clamp_for_huge_stitch_count(self):
        # 1000-stitch wide image with large cells — must stay under _MAX_PATTERN_PX
        img = _rgb_image(500, 100)
        grid = proc.render_pattern_grid(img, cell_w=40, cell_h=30)
        self.assertLessEqual(grid.width, proc._MAX_PATTERN_PX + 200)


class TestImageToDataUri(unittest.TestCase):
    def test_produces_png_data_uri(self):
        img = _rgb_image(4, 4)
        uri = proc.image_to_data_uri(img)
        self.assertTrue(uri.startswith("data:image/png;base64,"))
        self.assertGreater(len(uri), 50)


if __name__ == "__main__":
    unittest.main()
