#!/usr/bin/env python3
"""Safe YouTube uploader for the Swarnam4U bilingual Shorts pipeline.

The workflow controls when this script is called. The script itself fails closed:
- every run verifies the intended @SWARANAM4U channel;
- private_test uploads remain private and have an unmistakable test marker;
- schedule uploads are private until YouTube's publishAt time;
- build_only is the default when the mode is not explicitly selected.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import sys
from zoneinfo import ZoneInfo
from urllib.parse import urlparse

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

try:
    from rate_change_utils import video_title
except ImportError:
    from scripts.rate_change_utils import video_title

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "output"
IST = ZoneInfo("Asia/Kolkata")
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]
SLOT_TIMES = {"morning": (10, 30), "midday": (13, 0), "evening": (17, 0)}
WEBSITE = "https://swarnam4u.onrender.com"
CHANNEL_URL = "https://www.youtube.com/@SWARANAM4U"
EXPECTED_CHANNEL_HANDLE = os.environ.get("YOUTUBE_EXPECTED_CHANNEL_HANDLE", "").strip() or "@SWARANAM4U"
UPLOAD_MODES = {"private_test", "schedule"}
TITLE_HASHTAGS = " #KeralaGoldRate #Shorts"
PRIVATE_TEST_MARKER = " [PRIVATE TEST]"


def normalize_channel_handle(value: str | None) -> str:
    """Normalize an @handle, bare handle, or YouTube channel URL for comparison."""
    value = (value or "").strip()
    if not value:
        return ""
    if "youtube.com" in value.lower() or value.lower().startswith(("http://", "https://")):
        parsed = urlparse(value if "://" in value else "https://" + value)
        value = parsed.path.rstrip("/").split("/")[-1]
    return value.strip().lstrip("@").casefold()


def verify_channel_identity(
    channel: dict,
    expected_handle: str = EXPECTED_CHANNEL_HANDLE,
    expected_channel_id: str | None = None,
) -> str:
    """Fail closed if OAuth credentials identify anything other than the expected handle/ID."""
    if not isinstance(channel, dict) or not channel.get("id"):
        raise RuntimeError("YouTube returned no valid channel identity.")
    snippet = channel.get("snippet") or {}
    actual = snippet.get("customUrl") or snippet.get("handle") or ""
    expected = normalize_channel_handle(expected_handle)
    if expected_channel_id:
        if channel["id"] != expected_channel_id:
            actual_label = "@" + normalize_channel_handle(actual) if normalize_channel_handle(actual) else channel["id"]
            raise RuntimeError(
                f"Authorized YouTube channel {actual_label} does not match {expected_handle}; upload refused."
            )
        return "@" + expected
    if not normalize_channel_handle(actual):
        raise RuntimeError(
            "The authorized YouTube channel did not expose a verifiable handle; upload refused. "
            "Verify the OAuth account and channel handle before retrying."
        )
    if normalize_channel_handle(actual) != expected:
        raise RuntimeError(
            f"Authorized YouTube channel handle is @{normalize_channel_handle(actual)}, "
            f"but this project is configured for {expected_handle}; upload refused."
        )
    return "@" + normalize_channel_handle(actual)


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
    if slot not in SLOT_TIMES:
        raise ValueError(f"Unknown publication slot: {slot}")
    today = dt.datetime.now(IST).date()
    hour, minute = SLOT_TIMES[slot]
    return dt.datetime.combine(today, dt.time(hour, minute), tzinfo=IST)


def recent_uploaded_titles(youtube) -> tuple[set[str], str]:
    """Verify the OAuth identity against the configured handle and inspect recent upload titles."""
    expected_handle = "@" + normalize_channel_handle(EXPECTED_CHANNEL_HANDLE)
    expected_response = youtube.channels().list(
        part="id,snippet", forHandle=expected_handle, maxResults=1
    ).execute()
    expected_items = expected_response.get("items", [])
    if not expected_items:
        raise RuntimeError(f"YouTube could not resolve the configured channel handle {expected_handle}; upload refused.")
    expected_channel_id = expected_items[0].get("id")
    channels = youtube.channels().list(part="snippet,contentDetails", mine=True, maxResults=1).execute()
    items = channels.get("items", [])
    if not items:
        raise RuntimeError("No YouTube channel is available for the authorized account.")
    channel_handle = verify_channel_identity(items[0], expected_handle, expected_channel_id)
    playlist = (items[0].get("contentDetails") or {}).get("relatedPlaylists", {}).get("uploads")
    if not playlist:
        raise RuntimeError("YouTube did not return the channel's uploads playlist; upload refused.")
    result = youtube.playlistItems().list(
        part="snippet,contentDetails", playlistId=playlist, maxResults=50
    ).execute()
    titles = {row.get("snippet", {}).get("title", "") for row in result.get("items", [])}
    return titles, channel_handle


def video_description(date: dt.date, lang: str = "en", private_test: bool = False) -> str:
    """Build a language-appropriate description with source, website, and channel subscribe links."""
    english_date = date.strftime("%d %B %Y")
    malayalam_months = {
        1: "ജനുവരി", 2: "ഫെബ്രുവരി", 3: "മാർച്ച്", 4: "ഏപ്രിൽ",
        5: "മേയ്", 6: "ജൂൺ", 7: "ജൂലൈ", 8: "ഓഗസ്റ്റ്",
        9: "സെപ്റ്റംബർ", 10: "ഒക്ടോബർ", 11: "നവംബർ", 12: "ഡിസംബർ",
    }
    malayalam_date = f"{date.day} {malayalam_months[date.month]} {date.year}"
    if lang == "ml":
        description = (
            f"{malayalam_date}-ലെ കേരളത്തിലെ സ്വർണ്ണ, വെള്ളി ബോർഡ് നിരക്കുകൾ.\n"
            "ഉറവിടം: AKGSMA Kerala — https://akgsma.com/\n"
            f"പുതിയ നിരക്കുകൾക്കായി ചാനൽ സന്ദർശിച്ച് Subscribe ചെയ്യുക: {CHANNEL_URL}\n"
            f"ഇപ്പോഴത്തെ നിരക്കുകൾ: {WEBSITE}\n"
            "നിരക്കുകൾ ഗ്രാമിന് നൽകിയതാണ്. ഒരു പവന്റെ തുക 8 ഗ്രാമിന്റെ നിരക്കിൽ നിന്ന് കണക്കാക്കിയതാണ്. "
            "വാങ്ങുന്നതിന് മുമ്പ് നിലവിലെ നിരക്ക് സ്ഥിരീകരിക്കുക."
        )
    else:
        description = (
            f"Kerala gold and silver board rates dated {english_date}.\n"
            "Source: AKGSMA Kerala — https://akgsma.com/\n"
            f"Subscribe for daily Kerala gold-rate updates: {CHANNEL_URL}\n"
            f"Check the latest rates: {WEBSITE}\n"
            "Rates are shown per gram. Pawan totals are calculated from the published per-gram rates. "
            "Confirm the current rate before purchase."
        )
    if private_test:
        prefix = "[PRIVATE VALIDATION TEST — KEEP PRIVATE]\n" if lang == "en" else "സ്വകാര്യ പരിശോധനാ വീഡിയോ — Public ആക്കരുത്.\n"
        description = prefix + description
    return (description + "\n#Shorts #KeralaGoldRate #GoldRate #SilverRate #Swarnam4U")[:5000]


def private_test_title(title: str) -> str:
    """Add a conspicuous private-test marker while preserving hashtags and YouTube's 100-char limit."""
    if title.endswith(TITLE_HASHTAGS):
        core = title[:-len(TITLE_HASHTAGS)].rstrip()
        room = 100 - len(PRIVATE_TEST_MARKER) - len(TITLE_HASHTAGS)
        return core[:room].rstrip() + PRIVATE_TEST_MARKER + TITLE_HASHTAGS
    return title[:100 - len(PRIVATE_TEST_MARKER)].rstrip() + PRIVATE_TEST_MARKER


def video_resource(
    lang: str,
    date: dt.date,
    title: str,
    mode: str,
    publish_at: dt.datetime | None = None,
) -> dict:
    """Create a safe YouTube resource for either a private test or a scheduled publication."""
    if mode not in UPLOAD_MODES:
        raise ValueError(f"Refusing unsupported YouTube upload mode: {mode}")
    status = {"privacyStatus": "private", "selfDeclaredMadeForKids": False}
    if mode == "schedule":
        if publish_at is None:
            raise ValueError("Scheduled publication requires a target time.")
        status["publishAt"] = publish_at.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    elif publish_at is not None:
        raise ValueError("Private test uploads must not have a publishAt time.")
    return {
        "snippet": {
            "title": title,
            "description": video_description(date, lang, private_test=(mode == "private_test")),
            "tags": ["Shorts", "Kerala Gold Rate", "Gold Rate", "Silver Rate", "Swarnam4U"],
            "categoryId": "22",
            "defaultLanguage": "en" if lang == "en" else "ml",
        },
        "status": status,
    }


def upload_one(
    youtube, path: pathlib.Path, lang: str, date: dt.date, mode: str,
    publish_at: dt.datetime | None, title: str,
) -> dict:
    body = video_resource(lang, date, title, mode, publish_at)
    media = MediaFileUpload(str(path), mimetype="video/mp4", resumable=True, chunksize=8 * 1024 * 1024)
    response = youtube.videos().insert(part="snippet,status", body=body, media_body=media).execute()
    video_id = response.get("id")
    if not video_id:
        raise RuntimeError(f"YouTube returned no video ID for the {lang} upload.")
    return {
        "language": lang,
        "title": title,
        "video_id": video_id,
        "video_url": f"https://www.youtube.com/watch?v={video_id}",
        "mode": mode,
        "publish_at_ist": publish_at.isoformat(timespec="seconds") if publish_at else None,
        "status": "scheduled_private" if mode == "schedule" else "private_test",
    }


def main() -> int:
    slot = os.environ.get("SHORTS_SLOT", "").strip()
    mode = os.environ.get("SHORTS_UPLOAD_MODE", "build_only").strip().lower()
    if slot not in SLOT_TIMES:
        print("SHORTS_SLOT must be morning, midday, or evening.", file=sys.stderr)
        return 2
    if mode not in UPLOAD_MODES:
        print("Upload refused. Set SHORTS_UPLOAD_MODE explicitly to private_test or schedule.", file=sys.stderr)
        return 2

    today = dt.datetime.now(IST).date()
    out_dir = OUT / f"{today.isoformat()}-{slot}"
    report_path = out_dir / "upload-report.json"
    report: dict = {
        "date": today.isoformat(),
        "slot": slot,
        "mode": mode,
        "channel_handle": None,
        "status": "started",
        "results": [],
    }

    def save_report() -> None:
        out_dir.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    def block(reason: str) -> int:
        report["status"] = "blocked"
        report["reason"] = reason
        save_report()
        print(f"UPLOAD BLOCKED: {reason}", file=sys.stderr)
        return 2

    preflight_path = OUT / "shorts-preflight.json"
    if not preflight_path.exists():
        return block("Preflight report missing; upload refused.")
    try:
        preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return block(f"Preflight report could not be read: {exc}")
    if preflight.get("status") != "PREFLIGHT_PASSED" or preflight.get("current_date_ist") != today.isoformat():
        return block("Preflight has not passed for today's Kerala board rates; upload refused.")

    publish_at = target_time(slot) if mode == "schedule" else None
    if publish_at and publish_at - dt.datetime.now(IST) < dt.timedelta(minutes=5):
        return block(
            f"Target publishing time {publish_at.isoformat()} is less than five minutes away or has passed. "
            "The video was not uploaded late; choose build_only or private_test."
        )

    manifest_path = out_dir / "manifest.json"
    if not manifest_path.exists():
        return block(f"Expected manifest is missing: {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return block(f"Manifest could not be read: {exc}")
    if manifest.get("publish_enabled") is not True or manifest.get("date") != today.isoformat() or manifest.get("slot") != slot:
        return block("Manifest/date/slot mismatch or publishing was not enabled for this manual/scheduled run.")

    videos = {row.get("language"): out_dir / row.get("video", "") for row in manifest.get("videos", [])}
    if set(videos) != {"en", "ml"} or any(not p.is_file() or p.stat().st_size < 20_000 for p in videos.values()):
        return block("Both valid English and Malayalam MP4s are required.")

    comparisons = manifest.get("comparisons", {})
    primary_change = comparisons.get("22K · 916", {"direction": "unavailable", "change": None})
    save_report()
    try:
        youtube = get_youtube()
        existing_titles, channel_handle = recent_uploaded_titles(youtube)
        report["channel_handle"] = channel_handle
        save_report()
        for lang in ("en", "ml"):
            title = video_title(lang, today, slot, primary_change)
            if mode == "private_test":
                title = private_test_title(title)
            if title in existing_titles:
                report["results"].append({"language": lang, "title": title, "mode": mode, "status": "skipped_duplicate"})
                save_report()
                continue
            result = upload_one(youtube, videos[lang], lang, today, mode, publish_at, title)
            report["results"].append(result)
            existing_titles.add(title)
            save_report()
        report["status"] = "completed"
        save_report()
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = f"{type(exc).__name__}: {exc}"
        save_report()
        print(f"YouTube upload failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        print(json.dumps(report, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
