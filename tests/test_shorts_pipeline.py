import datetime as dt
import tempfile
import unittest
from pathlib import Path

from PIL import Image
from scripts import build_shorts


class ShortsDesignTests(unittest.TestCase):
    def setUp(self):
        self.date = dt.date(2026, 10, 27)
        self.values = {
            "22K · 916": 13085,
            "18K · 750": 10705,
            "Silver · 999": 220,
        }

    def test_price_formatting(self):
        self.assertEqual(build_shorts.inr(13085), "₹13,085")

    def test_english_script_has_source_and_link(self):
        text = build_shorts.script_text("en", self.date, self.values)
        self.assertIn("AKGSMA", text)
        self.assertIn("swarnam4u.onrender.com", text)
        self.assertIn("₹13,085", text)
        self.assertIn("27 October 2026", text)

    def test_malayalam_script_has_link_and_prices(self):
        text = build_shorts.script_text("ml", self.date, self.values)
        self.assertIn("swarnam4u.onrender.com", text)
        self.assertIn("₹10,705", text)
        self.assertIn("₹220", text)

    def test_both_rate_cards_are_vertical_1080_by_1920(self):
        with tempfile.TemporaryDirectory() as temp:
            for language in ("en", "ml"):
                path = Path(temp) / f"{language}.png"
                build_shorts.draw_card(language, self.date, self.values, "morning", path)
                with Image.open(path) as im:
                    self.assertEqual(im.size, (1080, 1920))
                    self.assertEqual(im.mode, "RGB")


if __name__ == "__main__":
    unittest.main()
