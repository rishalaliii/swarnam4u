import datetime as dt
import tempfile
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image, features
from scripts import build_shorts, shorts_preflight, upload_shorts, rate_change_utils


class ShortsDesignTests(unittest.TestCase):
    def setUp(self):
        self.date = dt.date(2026, 10, 27)
        self.values = {
            "22K · 916": 13135,
            "18K · 750": 10750,
            "Silver · 999": 220,
        }
        self.comparisons = {
            "22K · 916": rate_change_utils.compare_rate(13135, 13085),
            "18K · 750": rate_change_utils.compare_rate(10750, 10705),
            "Silver · 999": rate_change_utils.compare_rate(220, 220),
        }

    def test_price_formatting(self):
        self.assertEqual(build_shorts.inr(13135), "₹13,135")
        self.assertEqual(build_shorts.inr(13135 * 8), "₹1,05,080")
        self.assertEqual(build_shorts.inr(10750 * 8), "₹86,000")

    def test_english_script_has_source_link_and_pawan_totals(self):
        text = build_shorts.script_text("en", self.date, self.values, self.comparisons)
        self.assertIn("AKGSMA", text)
        self.assertIn("swarnam4u.onrender.com", text)
        self.assertIn("₹13,135", text)
        self.assertIn("₹1,05,080", text)
        self.assertIn("₹86,000", text)
        self.assertIn("One pawan, equal to eight grams", text)
        self.assertIn("Up ₹50 per gram versus yesterday.", text)
        self.assertIn("27 October 2026", text)

    def test_malayalam_script_has_link_prices_and_pawan_totals(self):
        text = build_shorts.script_text("ml", self.date, self.values, self.comparisons)
        self.assertIn("swarnam4u.onrender.com", text)
        self.assertIn("₹10,750", text)
        self.assertIn("₹220", text)
        self.assertIn("ഒരു പവൻ", text)
        self.assertIn("എട്ട് ഗ്രാം", text)
        self.assertIn("₹1,05,080", text)
        self.assertIn("₹86,000", text)
        self.assertIn("ഇന്നലെയേക്കാൾ ഗ്രാമിന് ₹50 വർധിച്ചു.", text)

    def test_every_youtube_description_has_latest_rates_call_to_action(self):
        description = upload_shorts.video_description(self.date)
        self.assertIn("Check out the latest rates via https://swarnam4u.onrender.com", description)
        self.assertIn("Source: AKGSMA Kerala", description)
        self.assertIn("27 October 2026", description)
        self.assertIn("#Shorts", description)
        self.assertNotIn("Website: https://swarnam4u.onrender.com", description)

    def test_day_over_day_comparison_up_down_same_and_unavailable(self):
        self.assertEqual(rate_change_utils.compare_rate(13135, 13085)["direction"], "up")
        self.assertEqual(rate_change_utils.compare_rate(13135, 13085)["change"], 50)
        self.assertEqual(rate_change_utils.compare_rate(10700, 10750)["direction"], "down")
        self.assertEqual(rate_change_utils.compare_rate(220, 220)["direction"], "no_change")
        self.assertEqual(rate_change_utils.compare_rate(220, None)["direction"], "unavailable")

    def test_localized_titles_include_relevant_hashtags_and_daily_price_movement(self):
        change = rate_change_utils.compare_rate(13135, 13085)
        english = rate_change_utils.video_title("en", self.date, "morning", change)
        malayalam = rate_change_utils.video_title("ml", self.date, "morning", change)
        self.assertEqual(english, "Today's Gold Rate | 27 Oct 2026 | 10:30 IST | UP ₹50/g vs Yesterday #KeralaGoldRate #Shorts")
        self.assertEqual(malayalam, "ഇന്നത്തെ സ്വർണ്ണവില | 27 Oct 2026 | 10:30 IST | ഇന്നലെയേക്കാൾ ₹50/g വർധന #KeralaGoldRate #Shorts")
        for title in (english, malayalam):
            self.assertIn("#KeralaGoldRate", title)
            self.assertIn("#Shorts", title)
            self.assertLessEqual(len(title), 100)
        self.assertIn("13:00 IST", rate_change_utils.video_title("en", self.date, "midday", change))
        self.assertIn("17:00 IST", rate_change_utils.video_title("ml", self.date, "evening", change))

    def test_all_movement_title_variants_keep_hashtags_and_fit_limit(self):
        comparisons = [
            rate_change_utils.compare_rate(13135, 13085),
            rate_change_utils.compare_rate(10700, 10750),
            rate_change_utils.compare_rate(220, 220),
            rate_change_utils.compare_rate(220, None),
            rate_change_utils.compare_rate(13135, 11135),
        ]
        for comparison in comparisons:
            for lang in ("en", "ml"):
                title = rate_change_utils.video_title(lang, self.date, "morning", comparison)
                self.assertLessEqual(len(title), 100, title)
                self.assertTrue(title.endswith("#KeralaGoldRate #Shorts"), title)

    def test_no_change_and_unavailable_titles_do_not_invent_deltas(self):
        same = rate_change_utils.compare_rate(220, 220)
        missing = rate_change_utils.compare_rate(220, None)
        self.assertIn("No Change vs Yesterday", rate_change_utils.video_title("en", self.date, "morning", same))
        self.assertIn("ഇന്നലെയേക്കാൾ മാറ്റമില്ല", rate_change_utils.video_title("ml", self.date, "morning", same))
        self.assertIn("Change Unavailable", rate_change_utils.video_title("en", self.date, "morning", missing))
        self.assertIn("മുൻദിവസത്തെ നിരക്ക് ലഭ്യമല്ല", rate_change_utils.video_title("ml", self.date, "morning", missing))

    def test_titles_and_filenames_are_language_specific_and_time_specific(self):
        change = rate_change_utils.compare_rate(13135, 13085)
        self.assertTrue(rate_change_utils.video_stem("en", self.date, "morning", change).startswith("todays-gold-rate-"))
        self.assertTrue(rate_change_utils.video_stem("ml", self.date, "morning", change).startswith("innathe-swarna-vila-"))
        self.assertNotEqual(
            rate_change_utils.video_stem("en", self.date, "morning", change),
            rate_change_utils.video_stem("en", self.date, "midday", change),
        )

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
                build_shorts.draw_card(language, self.date, self.values, self.comparisons, "morning", path)
                with Image.open(path) as im:
                    self.assertEqual(im.size, (1080, 1920))
                    self.assertEqual(im.mode, "RGB")


if __name__ == "__main__":
    unittest.main()
