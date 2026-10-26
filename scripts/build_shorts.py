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
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont
import edge_tts

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "rates.json"
OUT = ROOT / "output"
IST = ZoneInfo("Asia/Kolkata")
WIDTH, HEIGHT = 1080, 1920
WEBSITE = "swarnam4u.onrender.com"
VOICES = {"en": "en-IN-PrabhatNeural", "ml": "ml-IN-SobhanaNeural"}

def checked_run(args: list[str]) -> str:
    p = subprocess.run(args, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return p.stdout.strip()

def find_font(language: str, bold: bool = False, size: int = 48) -> ImageFont.FreeTypeFont:
    family = "Noto Sans Malayalam" if language == "ml" else ("DejaVu Sans:style=Bold" if bold else "DejaVu Sans")
    path = checked_run(["fc-match", "-f", "%{file}", family])
    if not path or not pathlib.Path(path).exists():
        fallback = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        path = fallback
    return ImageFont.truetype(path, size=size)

def inr(value: float) -> str:
    return "₹" + f"{value:,.0f}"

def board_values() -> tuple[dt.date, dict[str, float]]:
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
        values[label] = value
    # Confirm board date and the published-rate values in the latest preflight report.
    report_path = OUT / "shorts-preflight.json"
    if not report_path.exists():
        raise ValueError("Preflight report missing. Run scripts/shorts_preflight.py first.")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("status") != "PREFLIGHT_PASSED" or report.get("board_date") != date_text:
        raise ValueError("Preflight did not pass for this board date.")
    return board_date, values

def script_text(lang: str, date: dt.date, values: dict[str, float]) -> str:
    date_en = date.strftime("%d %B %Y")
    v22, v18, silver = (inr(values["22K · 916"]), inr(values["18K · 750"]), inr(values["Silver · 999"]))
    if lang == "en":
        return (
            f"Here is the Kerala gold and silver rate update for {date_en}. "
            f"Twenty-two carat gold, nine-one-six purity, is {v22} per gram. "
            f"Eighteen carat gold is {v18} per gram. "
            f"Silver, nine-nine-nine purity, is {silver} per gram. "
            f"These are the published AKGSMA board rates dated {date_en}. "
            f"For updates, visit {WEBSITE}."
        )
    return (
        f"ഇന്നത്തെ കേരളത്തിലെ സ്വർണ്ണ, വെള്ളി നിരക്കുകൾ. തീയതി {date.day} {date.strftime('%B')} {date.year}. "
        f"22 കാരറ്റ്, 916 പരിശുദ്ധിയുള്ള സ്വർണ്ണം ഒരു ഗ്രാമിന് {v22}. "
        f"18 കാരറ്റ് സ്വർണ്ണം ഒരു ഗ്രാമിന് {v18}. "
        f"999 പരിശുദ്ധിയുള്ള വെള്ളി ഒരു ഗ്രാമിന് {silver}. "
        f"ഇവ {date_en} തീയതിയിലെ എ കെ ജി എസ് എം എ ബോർഡ് പ്രസിദ്ധീകരിച്ച നിരക്കുകളാണ്. "
        f"കൂടുതൽ വിവരങ്ങൾക്ക് {WEBSITE} സന്ദർശിക്കുക."
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

def draw_card(lang: str, date: dt.date, values: dict[str, float], slot: str, png: pathlib.Path) -> None:
    im = Image.new("RGB", (WIDTH, HEIGHT), "#101722")
    d = ImageDraw.Draw(im)
    # Restrained dark navy, warm ivory, and antique-gold palette.
    d.rectangle((0, 0, WIDTH, 18), fill="#C7A66A")
    d.ellipse((720, -240, 1300, 340), fill="#1A2634")
    d.ellipse((-240, 1290, 300, 1830), fill="#172330")
    title = find_font(lang, True, 76)
    sub = find_font(lang, False, 34)
    label_font = find_font(lang, True, 37)
    value_font = find_font(lang, True, 56)
    small = find_font(lang, False, 31)
    footer_font = find_font(lang, True, 33)
    d.text((70, 95), "Swarnam4U", font=title, fill="#F3E7CF")
    if lang == "ml":
        headline = "ഇന്നത്തെ നിരക്കുകൾ"
        intro = "കേരളം • സ്വർണ്ണവും വെള്ളിയും"
        labels = [("22 കാരറ്റ്  •  916", "22K · 916"), ("18 കാരറ്റ്  •  750", "18K · 750"), ("വെള്ളി  •  999", "Silver · 999")]
        source_text = "ഉറവിടം: AKGSMA Kerala"
        disclaimer = "ബോർഡ് പ്രസിദ്ധീകരിച്ച നിരക്കുകൾ"
    else:
        headline = "GOLD & SILVER RATES"
        intro = "KERALA • PUBLISHED BOARD RATES"
        labels = [("Gold 22K  •  916", "22K · 916"), ("Gold 18K  •  750", "18K · 750"), ("Silver  •  999", "Silver · 999")]
        source_text = "Source: AKGSMA Kerala"
        disclaimer = "Published board rates • Per gram"
    d.text((74, 215), headline, font=find_font(lang, True, 47), fill="#D8BC83")
    d.text((76, 290), intro, font=sub, fill="#C6D0DB")
    d.rounded_rectangle((66, 365, 1014, 500), radius=28, fill="#1D2937", outline="#657184", width=2)
    date_label = date.strftime("%d %B %Y")
    d.text((100, 407), date_label, font=find_font(lang, True, 42), fill="#F6EEDD")
    y = 550
    for label, key in labels:
        d.rounded_rectangle((65, y, 1015, y + 260), radius=28, fill="#182330", outline="#354455", width=2)
        d.rounded_rectangle((65, y, 82, y + 260), radius=8, fill="#C7A66A")
        d.text((112, y + 42), label, font=label_font, fill="#E4D4B5")
        d.text((112, y + 112), inr(values[key]), font=value_font, fill="#FFFFFF")
        d.text((115, y + 192), "PER GRAM" if lang == "en" else "ഒരു ഗ്രാം", font=small, fill="#ACB9C7")
        y += 292
    d.rounded_rectangle((65, 1460, 1015, 1630), radius=26, fill="#202E3B", outline="#5D6873", width=2)
    d.text((100, 1500), source_text, font=find_font(lang, True, 35), fill="#E9D5AA")
    d.text((100, 1560), disclaimer, font=small, fill="#C6D0DB")
    d.text((70, 1698), WEBSITE, font=footer_font, fill="#EACF95")
    d.text((72, 1765), "Verify rates before purchase", font=small, fill="#AEB9C6") if lang == "en" else d.text((72, 1765), "വാങ്ങുന്നതിന് മുമ്പ് നിരക്ക് ഉറപ്പാക്കുക", font=small, fill="#AEB9C6")
    d.rectangle((0, HEIGHT - 18, WIDTH, HEIGHT), fill="#C7A66A")
    im.save(png, "PNG", optimize=True)

async def make_voice(text: str, voice: str, target: pathlib.Path) -> None:
    communicate = edge_tts.Communicate(text=text, voice=voice, rate="-4%", volume="+0%")
    await communicate.save(str(target))

def probe_duration(path: pathlib.Path) -> float:
    raw = checked_run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                       "-of", "default=noprint_wrappers=1:nokey=1", str(path)])
    return float(raw)

def render_video(image_path: pathlib.Path, audio_path: pathlib.Path, video_path: pathlib.Path, duration: float) -> None:
    total = min(59.0, max(8.0, duration + 0.25))
    vf = "zoompan=z='min(zoom+0.00015,1.045)':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps=30,format=yuv420p"
    checked_run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-loop", "1", "-framerate", "30", "-i", str(image_path),
        "-i", str(audio_path),
        "-vf", vf, "-t", f"{total:.2f}", "-shortest",
        "-c:v", "libx264", "-preset", "veryfast", "-tune", "stillimage",
        "-pix_fmt", "yuv420p", "-r", "30",
        "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
        "-movflags", "+faststart", str(video_path)
    ])
    verify = checked_run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                          "-show_entries", "stream=width,height,codec_name",
                          "-of", "json", str(video_path)])
    info = json.loads(verify)["streams"][0]
    if info.get("width") != WIDTH or info.get("height") != HEIGHT:
        raise RuntimeError(f"Unexpected video dimensions in {video_path.name}: {info}")
    if video_path.stat().st_size < 20_000:
        raise RuntimeError(f"Video output is suspiciously small: {video_path.name}")

async def main_async(slot: str) -> int:
    date, values = board_values()
    out_dir = OUT / f"{date.isoformat()}-{slot}"
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = {"date": date.isoformat(), "slot": slot, "website": WEBSITE, "videos": [], "publish_enabled": os.environ.get("YOUTUBE_AUTO_PUBLISH", "").lower() == "true"}
    for lang in ("en", "ml"):
        stem = f"swarnam4u-{date.isoformat()}-{slot}-{lang}"
        png, mp3, mp4 = out_dir / f"{stem}.png", out_dir / f"{stem}.mp3", out_dir / f"{stem}.mp4"
        text = script_text(lang, date, values)
        draw_card(lang, date, values, slot, png)
        await make_voice(text, VOICES[lang], mp3)
        duration = probe_duration(mp3)
        if duration > 58:
            raise RuntimeError(f"{lang} narration is {duration:.1f}s; shorten the script before rendering.")
        render_video(png, mp3, mp4, duration)
        manifest["videos"].append({
            "language": lang, "voice": VOICES[lang], "script": text,
            "image": png.name, "audio": mp3.name, "video": mp4.name,
            "duration_seconds": round(probe_duration(mp4), 2), "bytes": mp4.stat().st_size
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
