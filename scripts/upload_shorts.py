#!/usr/bin/env python3
"""Optional YouTube uploader. It is only called when YOUTUBE_AUTO_PUBLISH=true.

The workflow is deliberately disabled unless the repository variable is opted in.
Uses a refresh token and OAuth client JSON stored in GitHub Actions Secrets.
"""
from __future__ import annotations
import datetime as dt
import json
import os
import pathlib
import sys
from zoneinfo import ZoneInfo

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "output"
IST = ZoneInfo("Asia/Kolkata")
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
SLOT_TIMES = {"morning": (10, 30), "midday": (13, 0), "evening": (17, 0)}
WEBSITE = "swarnam4u.onrender.com"

def get_youtube():
    raw = os.environ.get("YOUTUBE_CLIENT_SECRET_JSON", "")
    refresh_token = os.environ.get("YOUTUBE_REFRESH_TOKEN", "")
    if not raw or not refresh_token:
        raise RuntimeError("Missing YOUTUBE_CLIENT_SECRET_JSON or YOUTUBE_REFRESH_TOKEN GitHub Actions Secret.")
    cfg_all = json.loads(raw)
    cfg = cfg_all.get("installed") or cfg_all.get("web")
    if not cfg or not cfg.get("client_id") or not cfg.get("client_secret"):
        raise RuntimeError("OAuth client secret JSON must contain installed or web client_id/client_secret fields.")
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri=cfg.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=cfg["client_id"],
        client_secret=cfg["client_secret"],
        scopes=SCOPES,
    )
    creds.refresh(Request())
    return build("youtube", "v3", credentials=creds, cache_discovery=False)

def target_time(slot: str) -> dt.datetime:
    today = dt.datetime.now(IST).date()
    h, minute = SLOT_TIMES[slot]
    return dt.datetime.combine(today, dt.time(h, minute), tzinfo=IST)

def recent_uploaded_titles(youtube) -> set[str]:
    channels = youtube.channels().list(part="contentDetails", mine=True, maxResults=1).execute()
    items = channels.get("items", [])
    if not items:
        raise RuntimeError("No YouTube channel is available for the authorized account.")
    playlist = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
    result = youtube.playlistItems().list(
        part="snippet,contentDetails", playlistId=playlist, maxResults=50
    ).execute()
    return {row.get("snippet", {}).get("title", "") for row in result.get("items", [])}

def video_description(date: dt.date) -> str:
    """Return the common description used for every English and Malayalam Short."""
    return (
        f"Kerala gold and silver board rates dated {date:%d %B %Y}.\n"
        f"Source: AKGSMA Kerala — https://akgsma.com/\n"
        f"Check out the latest rates via https://{WEBSITE}\n"
        "Rates are shown per gram. Pawan totals are calculated from the published per-gram rates. "
        "Published values only; calculated or unavailable rates are not represented as board quotes.\n"
        "#Shorts #KeralaGoldRate #GoldRate #SilverRate #Swarnam4U"
    )

def upload_one(youtube, path: pathlib.Path, lang: str, date: dt.date, slot: str, publish_at: dt.datetime) -> dict:
    language_title = "English" if lang == "en" else "Malayalam"
    slot_title = {"morning": "Morning", "midday": "Midday", "evening": "Evening"}[slot]
    title = f"Kerala Gold & Silver Rates | {date:%d %b %Y} | {slot_title} | {language_title} #Shorts"
    description = video_description(date)
    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": ["Shorts", "Kerala Gold Rate", "Gold Rate", "Silver Rate", "Swarnam4U"],
            "categoryId": "22",
            "defaultLanguage": "en" if lang == "en" else "ml",
        },
        "status": {
            "privacyStatus": "private",
            "publishAt": publish_at.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "selfDeclaredMadeForKids": False,
        },
    }
    media = MediaFileUpload(str(path), mimetype="video/mp4", resumable=True, chunksize=8 * 1024 * 1024)
    response = youtube.videos().insert(part="snippet,status", body=body, media_body=media).execute()
    return {"language": lang, "title": title, "video_id": response.get("id"),
            "publish_at_ist": publish_at.isoformat(timespec="seconds"), "status": "scheduled_private"}

def main() -> int:
    slot = os.environ.get("SHORTS_SLOT", "")
    if slot not in SLOT_TIMES:
        print("SHORTS_SLOT must be morning, midday, or evening.", file=sys.stderr)
        return 2
    today = dt.datetime.now(IST).date()
    out_dir = OUT / f"{today.isoformat()}-{slot}"
    report_path = OUT / "shorts-preflight.json"
    if not report_path.exists():
        print("Preflight report missing; upload refused.", file=sys.stderr)
        return 2
    preflight = json.loads(report_path.read_text(encoding="utf-8"))
    if preflight.get("status") != "PREFLIGHT_PASSED" or preflight.get("current_date_ist") != today.isoformat():
        print("Preflight has not passed for today; upload refused.", file=sys.stderr)
        return 2
    target = target_time(slot)
    now = dt.datetime.now(IST)
    if target - now < dt.timedelta(minutes=5):
        print(f"Target publishing time {target.isoformat()} is less than five minutes away or has passed; upload refused.", file=sys.stderr)
        return 2
    manifest_path = out_dir / "manifest.json"
    if not manifest_path.exists():
        print(f"Expected manifest is missing: {manifest_path}", file=sys.stderr)
        return 2
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("publish_enabled") is not True or manifest.get("date") != today.isoformat() or manifest.get("slot") != slot:
        print("Manifest/date/slot mismatch; upload refused.", file=sys.stderr)
        return 2
    videos = {row.get("language"): out_dir / row.get("video", "") for row in manifest.get("videos", [])}
    if set(videos) != {"en", "ml"} or any(not p.is_file() or p.stat().st_size < 20_000 for p in videos.values()):
        print("Both valid English and Malayalam MP4s are required.", file=sys.stderr)
        return 2
    youtube = get_youtube()
    existing_titles = recent_uploaded_titles(youtube)
    results = []
    for lang in ("en", "ml"):
        language_title = "English" if lang == "en" else "Malayalam"
        slot_title = {"morning": "Morning", "midday": "Midday", "evening": "Evening"}[slot]
        title = f"Kerala Gold & Silver Rates | {today:%d %b %Y} | {slot_title} | {language_title} #Shorts"
        if title in existing_titles:
            results.append({"language": lang, "title": title, "status": "skipped_duplicate"})
            continue
        results.append(upload_one(youtube, videos[lang], lang, today, slot, target))
    report = {"date": today.isoformat(), "slot": slot, "results": results}
    (out_dir / "upload-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
