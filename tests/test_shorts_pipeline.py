import datetime as dt
import tempfile
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image, features
from scripts import build_shorts, shorts_preflight, upload_shorts


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
        self.assertEqual(build_shorts.inr(13085 * 8), "₹1,04,680")
        self.assertEqual(build_shorts.inr(10705 * 8), "₹85,640")

    def test_english_script_has_source_link_and_pawan_totals(self):
        text = build_shorts.script_text("en", self.date, self.values)
        self.assertIn("AKGSMA", text)
        self.assertIn("swarnam4u.onrender.com", text)
        self.assertIn("₹13,085", text)
        self.assertIn("₹1,04,680", text)
        self.assertIn("₹85,640", text)
        self.assertIn("One pawan, equal to eight grams", text)
        self.assertIn("27 October 2026", text)

    def test_malayalam_script_has_link_prices_and_pawan_totals(self):
        text = build_shorts.script_text("ml", self.date, self.values)
        self.assertIn("swarnam4u.onrender.com", text)
        self.assertIn("₹10,705", text)
        self.assertIn("₹220", text)
        self.assertIn("ഒരു പവൻ", text)
        self.assertIn("എട്ട് ഗ്രാം", text)
        self.assertIn("₹1,04,680", text)
        self.assertIn("₹85,640", text)

    def test_every_youtube_description_has_latest_rates_call_to_action(self):
        description = upload_shorts.video_description(self.date)
        self.assertIn("Check out the latest rates via https://swarnam4u.onrender.com", description)
        self.assertIn("Source: AKGSMA Kerala", description)
        self.assertIn("27 October 2026", description)
        self.assertIn("#Shorts", description)
        self.assertNotIn("Website: https://swarnam4u.onrender.com", description)

    def test_board_parser_reads_published_rates_and_refuses_na_925(self):
        text = (
            "Today's Rate (27/10/2026) "
            "22K916 (1gm) - ₹ 13085 "
            "18K750 (1gm) - ₹ 10705 "
            "Silver (1gm) - ₹ 220 "
            "925 Hall Marked Silver (1gm) - ₹ NA"
        )
        date, rates = shorts_preflight.parse_board_text(text)
        self.assertEqual(date, "2026-10-27")
        self.assertEqual(rates["gold_22k_916"], 13085)
        self.assertEqual(rates["gold_18k_750"], 10705)
        self.assertEqual(rates["silver_999"], 220)
        self.assertIsNone(rates["silver_925_published"])

    def test_parser_fails_if_board_date_is_missing(self):
        with self.assertRaisesRegex(ValueError, "board date"):
            shorts_preflight.parse_board_text("22K916 (1gm) - ₹ 13085")

    def test_malayalam_font_and_raqm_are_required(self):
        self.assertTrue(features.check_feature("raqm"), "CI Pillow must include RAQM for Malayalam shaping")
        malayalam = build_shorts.find_font("ml", True, 32)
        latin = build_shorts.find_font("en", True, 32)
        self.assertIn("malayalam", malayalam.getname()[0].lower())
        self.assertIn("dejavu sans", latin.getname()[0].lower())

    def test_renderer_avoids_bullet_glyph_that_created_square_boxes(self):
        source = Path(build_shorts.__file__).read_text(encoding="utf-8")
        self.assertNotIn("•", source)
        self.assertNotIn("□", source)

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
