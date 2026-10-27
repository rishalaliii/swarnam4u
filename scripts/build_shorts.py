#!/usr/bin/env python3
"""Build two Shorts (English + Malayalam) from a verified rates.json snapshot."""
from __future__ import annotations
import argparse
import asyncio
import datetime as dt
import json
import os
import pathlib
import shutil
import subprocess
import sys
import textwrap
from fractions import Fraction
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont, features
import edge_tts

try:
    from rate_change_utils import (
        SLOT_TIMES, card_change_label, compare_rate, spoken_change_text,
        video_stem, video_title, malayalam_date_text,
    )
except ImportError:
    from scripts.rate_change_utils import (
        SLOT_TIMES, card_change_label, compare_rate, spoken_change_text,
        video_stem, video_title, malayalam_date_text,
    )

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "rates.json"
OUT = ROOT / "output"
IST = ZoneInfo("Asia/Kolkata")
WIDTH, HEIGHT = 1080, 1920
WEBSITE = "swarnam4u.onrender.com"
VOICES = {"en": "en-IN-PrabhatNeural", "ml": "ml-IN-SobhanaNeural"}

def checked_run(args: list[str]) -> str:
    """Run a subprocess and surface useful diagnostics instead of hiding stderr."""
    p = subprocess.run(args, check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.returncode:
        detail = (p.stderr or p.stdout or "").strip()
        if len(detail) > 3000:
            detail = detail[-3000:]
        command = " ".join(args)
        raise RuntimeError(f"Command failed with exit code {p.returncode}: {command}\n{detail}")
    return p.stdout.strip()

def find_font(language: str, bold: bool = False, size: int = 48) -> ImageFont.FreeTypeFont:
    """Load a verified script-specific font; never silently substitute a font without Malayalam glyphs."""
    if language == "ml":
        if not features.check_feature("raqm"):
            raise RuntimeError(
                "Pillow was built without RAQM text shaping. Install libraqm/harfbuzz/fribidi and rebuild Pillow."
            )
        style = "SemiBold" if bold else "Regular"
        query = f"Noto Sans Malayalam:style={style}"
        match = checked_run(["fc-match", "-f", "%{file}|%{family}", query])
        parts = match.split("|", 1)
        if len(parts) != 2:
            raise RuntimeError("Could not resolve a Malayalam font through fontconfig.")
        path, matched_family = parts[0].strip(), parts[1].strip()
        if "malayalam" not in matched_family.lower():
            raise RuntimeError(
                f"Malayalam font was not installed correctly (fontconfig matched {matched_family!r})."
            )
        if not pathlib.Path(path).is_file():
            raise RuntimeError(f"Resolved Malayalam font file does not exist: {path}")
        return ImageFont.truetype(path, size=size, layout_engine=ImageFont.Layout.RAQM)

    query = "DejaVu Sans:style=Bold" if bold else "DejaVu Sans:style=Book"
    match = checked_run(["fc-match", "-f", "%{file}|%{family}", query])
    parts = match.split("|", 1)
    if len(parts) != 2 or "dejavu sans" not in parts[1].lower():
        raise RuntimeError("DejaVu Sans Latin font is missing; refusing to render brand/domain text with a fallback.")
    path = parts[0].strip()
    if not pathlib.Path(path).is_file():
        raise RuntimeError(f"Resolved Latin font file does not exist: {path}")
    return ImageFont.truetype(path, size=size, layout_engine=ImageFont.Layout.BASIC)

def inr(value: float) -> str:
    """Format INR using Indian digit grouping (for example ₹1,05,080)."""
    digits = str(int(round(value)))
    if len(digits) <= 3:
        return "₹" + digits
    last_three = digits[-3:]
    prefix = digits[:-3]
    groups: list[str] = []
    while prefix:
        groups.append(prefix[-2:])
        prefix = prefix[:-2]
    return "₹" + ",".join(reversed(groups)) + "," + last_three

def board_values() -> tuple[dt.date, dict[str, float], dict[str, dict]]:
    obj = json.loads(DATA.read_text(encoding="utf-8"))
    today = dt.datetime.now(IST).date()
    date_text = obj.get("gold", {}).get("22K · 916", {}).get("date")
    if not date_text:
        raise ValueError("Missing 22K board date.")
    board_date = dt.date.fromisoformat(date_text)
    if board_date != today:
        raise ValueError(f"Rate snapshot is dated {board_date}; today in Kerala is {today}.")
    keys = {
        "22K · 916": ("gold", "22K · 916"),
        "18K · 750": ("gold", "18K · 750"),
        "Silver · 999": ("silver", "Silver · 999"),
    }
    values: dict[str, float] = {}
    comparisons: dict[str, dict] = {}
    expected_previous_date = (board_date - dt.timedelta(days=1)).isoformat()
    for label, (group, key) in keys.items():
        entry = obj.get(group, {}).get(key, {})
        if entry.get("date") != date_text:
            raise ValueError(f"{label} rate date does not match {date_text}.")
        try:
            value = float(entry["today"])
        except (TypeError, ValueError, KeyError):
            raise ValueError(f"Missing valid rate for {label}.")
        if value <= 0:
            raise ValueError(f"Invalid rate for {label}.")
        previous = entry.get("yesterday")
        previous_date = entry.get("yesterday_date")
        # A dated previous value is usable only when it is from the prior calendar day.
        # Legacy snapshots without yesterday_date use the existing yesterday field.
        if previous_date and previous_date != expected_previous_date:
            previous = None
        values[label] = value
        comparisons[label] = compare_rate(value, previous)
        comparisons[label]["previous_date"] = previous_date or (expected_previous_date if previous is not None else None)
    report_path = OUT / "shorts-preflight.json"
    if not report_path.exists():
        raise ValueError("Preflight report missing. Run scripts/shorts_preflight.py first.")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("status") != "PREFLIGHT_PASSED" or report.get("board_date") != date_text:
        raise ValueError("Preflight did not pass for this board date.")
    return board_date, values, comparisons

def script_text(lang: str, date: dt.date, values: dict[str, float], comparisons: dict[str, dict]) -> str:
    """Narrate rates, pawan totals, and the available 22K day-over-day move."""
    date_en = date.strftime("%d %B %Y")
    v22 = inr(values["22K · 916"])
    v18 = inr(values["18K · 750"])
    silver = inr(values["Silver · 999"])
    v22_pawan = inr(values["22K · 916"] * 8)
    v18_pawan = inr(values["18K · 750"] * 8)
    gold_change = spoken_change_text(comparisons["22K · 916"], lang)
    if lang == "en":
        return (
            f"India gold and silver rate update for {date_en}, using published board rates. "
            f"Twenty-two carat 916 gold: {v22} per gram. "
            f"One pawan, equal to eight grams, is {v22_pawan}. "
            f"{gold_change} "
            f"Eighteen carat 750 gold: {v18} per gram; one pawan is {v18_pawan}. "
            f"999 silver: {silver} per gram. "
            f"Pawan amounts are calculated from per-gram rates. "
            f"Visit {WEBSITE}."
        )
    return (
        f"{malayalam_date_text(date)} തീയതിയിലെ കേരളത്തിലെ സ്വർണ്ണ, വെള്ളി നിരക്കുകൾ. "
        f"22 കാരറ്റ് 916 സ്വർണ്ണം ഒരു ഗ്രാമിന് {v22}. "
        f"എട്ട് ഗ്രാം, ഒരു പവൻ {v22_pawan}. "
        f"{gold_change} "
        f"18 കാരറ്റ് 750 സ്വർണ്ണം ഒരു ഗ്രാമിന് {v18}; ഒരു പവൻ {v18_pawan}. "
        f"999 വെള്ളി ഒരു ഗ്രാമിന് {silver}. "
        f"പവൻ തുക ഗ്രാമിന്റെ നിരക്കിൽ നിന്ന് കണക്കാക്കിയതാണ്. "
        f"{WEBSITE} സന്ദർശിക്കുക."
    )

def wrap_to_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    line = ""
    for word in words:
        candidate = word if not line else line + " " + word
        if draw.textbbox((0, 0), candidate, font=font)[2] <= max_width:
            line = candidate
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines

def draw_card(lang: str, date: dt.date, values: dict[str, float], comparisons: dict[str, dict], slot: str, png: pathlib.Path, display_time: str | None = None) -> None:
    im = Image.new("RGB", (WIDTH, HEIGHT), "#101722")
    d = ImageDraw.Draw(im)
    # Restrained dark navy, warm ivory, and antique-gold palette.
    d.rectangle((0, 0, WIDTH, 18), fill="#C7A66A")
    d.ellipse((720, -240, 1300, 340), fill="#1A2634")
    d.ellipse((-240, 1290, 300, 1830), fill="#172330")
    title = find_font("en", True, 76)
    sub = find_font(lang, False, 34)
    label_font = find_font(lang, True, 34)
    value_font = find_font(lang, True, 56)
    small = find_font(lang, False, 31)
    footer_font = find_font("en", True, 33)
    d.text((70, 95), "Swarnam4U", font=title, fill="#F3E7CF")
    if lang == "ml":
        headline = "ഇന്നത്തെ നിരക്കുകൾ"
        # Avoid decorative bullet glyphs: the selected Malayalam font renders the bullet as a square.
        intro = "കേരളത്തിലെ സ്വർണ്ണം, വെള്ളി നിരക്കുകൾ"
        labels = [("22 കാരറ്റ് (916)", "22K · 916"), ("18 കാരറ്റ് (750)", "18K · 750"), ("വെള്ളി (999)", "Silver · 999")]
        source_text = "ഉറവിടം:"
        disclaimer = "ബോർഡ് പ്രസിദ്ധീകരിച്ച നിരക്കുകൾ"
        gram_text = "ഒരു ഗ്രാം"
        pawan_text = "ഒരു പവൻ (8 ഗ്രാം)"
        pawan_note = "പവൻ തുക ഗ്രാമിന്റെ നിരക്കിൽ നിന്ന് കണക്കാക്കിയതാണ്"
        silver_note = "ഒരു ഗ്രാമിന്റെ നിരക്ക് മാത്രം"
    else:
        headline = "GOLD & SILVER RATES"
        intro = "INDIA | GOLD & SILVER RATE UPDATE"
        labels = [("Gold 22K (916)", "22K · 916"), ("Gold 18K (750)", "18K · 750"), ("Silver (999)", "Silver · 999")]
        source_text = "Source:"
        disclaimer = "Published board rates | Per gram"
        gram_text = "PER GRAM"
        pawan_text = "1 PAWAN (8 GRAMS)"
        pawan_note = "Pawan total calculated from per-gram rate"
        silver_note = "Per-gram rate only"
    d.text((74, 215), headline, font=find_font(lang, True, 47), fill="#D8BC83")
    d.text((76, 290), intro, font=sub, fill="#C6D0DB")
    d.rounded_rectangle((66, 365, 1014, 500), radius=28, fill="#1D2937", outline="#657184", width=2)
    date_label = date.strftime("%d %B %Y") if lang == "en" else malayalam_date_text(date)
    d.text((100, 407), date_label, font=find_font(lang, True, 42), fill="#F6EEDD")
    # Manual public-now runs stamp the actual Kerala time into the video; scheduled
    # runs retain the configured slot time.
    slot_clock = f"{display_time or SLOT_TIMES[slot]} IST"
    clock_font = find_font("en", True, 38)
    clock_width = d.textbbox((0, 0), slot_clock, font=clock_font)[2]
    d.text((980 - clock_width, 410), slot_clock, font=clock_font, fill="#D8BC83")

    y = 540
    card_height = 275
    pawan_label_font = find_font(lang, True, 23)
    pawan_value_font = find_font("en", True, 46)
    gram_font = find_font("en", False, 24) if lang == "en" else find_font("ml", False, 24)
    rate_font = find_font("en", True, 62)
    change_font = find_font(lang, True, 17 if lang == "ml" else 18)
    change_amount_font = find_font("en", True, 18)
    for label, key in labels:
        d.rounded_rectangle((65, y, 1015, y + card_height), radius=28, fill="#182330", outline="#354455", width=2)
        d.rounded_rectangle((65, y, 82, y + card_height), radius=8, fill="#C7A66A")
        d.text((112, y + 16), label, font=label_font, fill="#E4D4B5")
        d.text((112, y + 56), inr(values[key]), font=rate_font, fill="#FFFFFF", stroke_width=1, stroke_fill="#FFFFFF")
        d.text((115, y + 128), gram_text, font=gram_font, fill="#D4DEE8")
        d.line((112, y + 160, 968, y + 160), fill="#718094", width=2)
        if key != "Silver · 999":
            d.text((112, y + 166), pawan_text, font=pawan_label_font, fill="#E7C879")
            d.text((112, y + 194), inr(values[key] * 8), font=pawan_value_font, fill="#FFFFFF", stroke_width=1, stroke_fill="#FFFFFF")
        else:
            d.text((112, y + 182), silver_note, font=gram_font, fill="#E7C879")
        label_text, change_amount = card_change_label(comparisons[key], lang)
        d.text((112, y + 242), label_text, font=change_font, fill="#E7C879")
        if change_amount:
            change_value = f"{change_amount}/g"
            amount_width = d.textbbox((0, 0), change_value, font=change_amount_font)[2]
            d.text((970 - amount_width, y + 241), change_value, font=change_amount_font, fill="#FFFFFF")
        y += 290

    d.rounded_rectangle((65, 1460, 1015, 1630), radius=26, fill="#202E3B", outline="#5D6873", width=2)
    if lang == "ml":
        source_ml = "ഉറവിടം:"
        source_ml_font = find_font("ml", True, 35)
        d.text((100, 1500), source_ml, font=source_ml_font, fill="#E9D5AA")
        source_x = 100 + d.textbbox((0, 0), source_ml, font=source_ml_font)[2] + 16
        d.text((source_x, 1500), "AKGSMA Kerala", font=find_font("en", True, 35), fill="#E9D5AA")
    else:
        d.text((100, 1500), source_text, font=find_font("en", True, 35), fill="#E9D5AA")
    d.text((100, 1550), disclaimer, font=small, fill="#C6D0DB")
    note_font = find_font(lang, False, 22)
    d.text((100, 1590), pawan_note, font=note_font, fill="#ADB9C5")
    d.text((70, 1698), WEBSITE, font=footer_font, fill="#EACF95")
    if lang == "en":
        d.text((72, 1765), "Verify rates before purchase", font=find_font("en", False, 27), fill="#AEB9C6")
    else:
        d.text((72, 1765), "വാങ്ങുന്നതിന് മുമ്പ് നിരക്ക് ഉറപ്പാക്കുക", font=find_font("ml", False, 27), fill="#AEB9C6")
    d.rectangle((0, HEIGHT - 18, WIDTH, HEIGHT), fill="#C7A66A")
    im.save(png, "PNG", optimize=True)

async def make_voice(text: str, voice: str, target: pathlib.Path) -> None:
    communicate = edge_tts.Communicate(text=text, voice=voice, rate="+2%", volume="+0%")
    await communicate.save(str(target))

def probe_duration(path: pathlib.Path) -> float:
    raw = checked_run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                       "-of", "default=noprint_wrappers=1:nokey=1", str(path)])
    return float(raw)

def validate_video_metadata(info: dict, label: str = "video") -> float:
    """Fail closed unless ffprobe confirms the expected Short video and audio streams."""
    streams = info.get("streams") or []
    videos = [stream for stream in streams if stream.get("codec_type") == "video"]
    audios = [stream for stream in streams if stream.get("codec_type") == "audio"]
    if len(videos) != 1:
        raise RuntimeError(f"{label} must contain exactly one video stream; found {len(videos)}.")
    if len(audios) != 1:
        raise RuntimeError(f"{label} must contain exactly one audio stream; found {len(audios)}.")
    video, audio = videos[0], audios[0]
    if video.get("codec_name") != "h264":
        raise RuntimeError(f"{label} video codec must be H.264; got {video.get('codec_name')!r}.")
    try:
        dimensions = (int(video.get("width", 0)), int(video.get("height", 0)))
    except (TypeError, ValueError):
        dimensions = (0, 0)
    if dimensions != (WIDTH, HEIGHT):
        raise RuntimeError(f"{label} dimensions must be {WIDTH}x{HEIGHT}; got {dimensions}.")
    if video.get("pix_fmt") != "yuv420p":
        raise RuntimeError(f"{label} pixel format must be yuv420p; got {video.get('pix_fmt')!r}.")
    try:
        fps_text = video.get("avg_frame_rate") or video.get("r_frame_rate") or "0/1"
        fps = float(Fraction(fps_text))
    except (TypeError, ValueError, ZeroDivisionError):
        fps = 0.0
    if abs(fps - 30.0) > 0.1:
        raise RuntimeError(f"{label} frame rate must be 30 fps; got {fps_text!r}.")
    if audio.get("codec_name") != "aac":
        raise RuntimeError(f"{label} audio codec must be AAC; got {audio.get('codec_name')!r}.")
    try:
        sample_rate = int(audio.get("sample_rate", 0))
    except (TypeError, ValueError):
        sample_rate = 0
    if sample_rate != 48000:
        raise RuntimeError(f"{label} audio sample rate must be 48000 Hz; got {sample_rate}.")
    try:
        duration = float((info.get("format") or {}).get("duration"))
    except (TypeError, ValueError):
        duration = 0.0
    if not 5.0 <= duration <= 60.0:
        raise RuntimeError(f"{label} duration must be between 5 and 60 seconds; got {duration:g}s.")
    return duration


def render_video(image_path: pathlib.Path, audio_path: pathlib.Path, video_path: pathlib.Path, duration: float) -> None:
    total = min(59.0, max(8.0, duration + 0.25))
    vf = "zoompan=z='min(zoom+0.00015,1.045)':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps=30,format=yuv420p"
    checked_run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-loop", "1", "-framerate", "30", "-i", str(image_path),
        "-i", str(audio_path),
        "-vf", vf, "-t", f"{total:.2f}", "-shortest",
        "-c:v", "libx264", "-preset", "veryslow", "-tune", "stillimage", "-crf", "10", "-profile:v", "high",
        "-pix_fmt", "yuv420p", "-r", "30", "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
        "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-c:a", "aac", "-b:a", "256k", "-ar", "48000",
        "-movflags", "+faststart", str(video_path)
    ])
    verify = checked_run([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration:stream=codec_name,codec_type,width,height,pix_fmt,r_frame_rate,avg_frame_rate,sample_rate",
        "-of", "json", str(video_path)
    ])
    validate_video_metadata(json.loads(verify), video_path.name)
    if video_path.stat().st_size < 20_000:
        raise RuntimeError(f"Video output is suspiciously small: {video_path.name}")

async def main_async(slot: str) -> int:
    date, values, comparisons = board_values()
    out_dir = OUT / f"{date.isoformat()}-{slot}"
    out_dir.mkdir(parents=True, exist_ok=True)
    publish_mode = os.environ.get("SHORTS_PUBLISH_MODE", "scheduled_private").strip().lower()
    if publish_mode not in {"scheduled_private", "public_now"}:
        raise ValueError("SHORTS_PUBLISH_MODE must be scheduled_private or public_now.")
    use_current_time = os.environ.get("SHORTS_USE_CURRENT_TIME", "").strip().lower() == "true"
    display_time = dt.datetime.now(IST).strftime("%H:%M") if use_current_time else SLOT_TIMES[slot]
    primary_change = comparisons["22K · 916"]
    manifest = {
        "date": date.isoformat(),
        "slot": slot,
        "publish_time_ist": display_time,
        "publish_mode": publish_mode,
        "website": WEBSITE,
        "comparisons": comparisons,
        "videos": [],
        "publish_enabled": os.environ.get("YOUTUBE_AUTO_PUBLISH", "").lower() == "true",
    }
    for lang in ("en", "ml"):
        stem = video_stem(lang, date, slot, primary_change)
        png, mp3, mp4 = out_dir / f"{stem}.png", out_dir / f"{stem}.mp3", out_dir / f"{stem}.mp4"
        narration = script_text(lang, date, values, comparisons)
        draw_card(lang, date, values, comparisons, slot, png, display_time=display_time)
        await make_voice(narration, VOICES[lang], mp3)
        duration = probe_duration(mp3)
        if duration > 55:
            raise RuntimeError(f"{lang} narration is {duration:.1f}s; limit is 55 seconds. Shorten the script before rendering.")
        render_video(png, mp3, mp4, duration)
        manifest["videos"].append({
            "language": lang,
            "voice": VOICES[lang],
            "script": narration,
            "youtube_title": video_title(lang, date, slot, primary_change),
            "primary_gold_change": primary_change,
            "image": png.name,
            "audio": mp3.name,
            "video": mp4.name,
            "duration_seconds": round(probe_duration(mp4), 2),
            "bytes": mp4.stat().st_size,
        })
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--slot", choices=("morning", "midday", "evening"), required=True)
    args = parser.parse_args()
    for binary in ("ffmpeg", "ffprobe", "fc-match"):
        if not shutil.which(binary):
            print(f"Missing dependency: {binary}", file=sys.stderr)
            return 2
    try:
        return asyncio.run(main_async(args.slot))
    except Exception as exc:
        print(f"SHORTS BUILD FAILED: {exc}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
