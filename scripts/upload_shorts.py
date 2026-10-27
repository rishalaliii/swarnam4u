#!/usr/bin/env python3
"""Optional YouTube uploader for scheduled-private or explicitly requested public uploads.

The workflow controls normal publishing; this script independently enforces the emergency stop.
Uses a refresh token and OAuth client JSON stored in GitHub Actions Secrets.
"""
from __future__ import annotations
import datetime as dt
import json
import os
import pathlib
import re
import sys
from zoneinfo import ZoneInfo

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
SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.readonly"]
SLOT_TIMES = {"morning": (10, 30), "midday": (13, 0), "evening": (17, 0)}
WEBSITE = "swarnam4u.onrender.com"
EXPECTED_CHANNEL_HANDLE = os.environ.get("YOUTUBE_EXPECTED_CHANNEL_HANDLE", "").strip() or "@SWARANAM4U"

def normalize_channel_handle(value: str | None) -> str:
    """Normalize @handle, bare handle, or a YouTube channel URL for safe comparison."""
    value = (value or "").strip()
    if not value:
        return ""
    if "youtube.com" in value.lower() or value.lower().startswith(("http://", "https://")):
        from urllib.parse import urlparse
        value = urlparse(value if "://" in value else "https://" + value).path.rstrip("/").split("/")[-1]
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
        # The API resolved expected_handle to this exact channel ID, so the ID match is authoritative.
        return "@" + expected
    if not normalize_channel_handle(actual):
        raise RuntimeError("The authorized YouTube channel did not expose a verifiable handle; upload refused. Verify the OAuth account and channel handle before retrying.")
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
    today = dt.datetime.now(IST).date()
    h, minute = SLOT_TIMES[slot]
    return dt.datetime.combine(today, dt.time(h, minute), tzinfo=IST)

def ensure_publish_window(
    publish_at: dt.datetime,
    now: dt.datetime | None = None,
    minimum_lead: dt.timedelta = dt.timedelta(minutes=5),
) -> None:
    """Refuse an upload if its scheduled publish time is too close or already passed."""
    current = now or dt.datetime.now(IST)
    if publish_at.tzinfo is None or current.tzinfo is None:
        raise ValueError("Publish time and current time must include timezone information.")
    remaining = publish_at.astimezone(IST) - current.astimezone(IST)
    if remaining < minimum_lead:
        raise RuntimeError(
            f"Target publishing time {publish_at.astimezone(IST).isoformat()} is less than "
            f"{minimum_lead.total_seconds() / 60:g} minutes away or has passed; upload refused."
        )


def recent_uploaded_titles(youtube) -> tuple[set[str], str]:
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
    playlist = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
    result = youtube.playlistItems().list(
        part="snippet,contentDetails", playlistId=playlist, maxResults=50
    ).execute()
    titles = {row.get("snippet", {}).get("title", "") for row in result.get("items", [])}
    return titles, channel_handle

def title_slot_identity(title: str) -> tuple[str, str, str] | None:
    """Extract stable language/date/slot identity, independent of rate-movement wording."""
    parts = title.split(" | ")
    if len(parts) < 3:
        return None
    match = re.search(r"(?<![0-9])([0-9]{2}:[0-9]{2})(?![0-9])", parts[2])
    if not match:
        return None
    return parts[0], parts[1], match.group(1)


def is_duplicate_slot(existing_titles: set[str], candidate_title: str) -> bool:
    """Prevent a rerun from duplicating the same language/date/time when rates change."""
    if candidate_title in existing_titles:
        return True
    candidate_identity = title_slot_identity(candidate_title)
    if candidate_identity is None:
        return False
    return any(title_slot_identity(existing) == candidate_identity for existing in existing_titles)


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

def upload_one(youtube, path: pathlib.Path, lang: str, date: dt.date, slot: str, publish_at: dt.datetime | None, title: str, publish_mode: str) -> dict:
    if not title or len(title) > 100:
        raise ValueError(f"YouTube title must be 1–100 characters; got {len(title)}.")
    description = video_description(date)
    if len(description) > 5000:
        raise ValueError(f"YouTube description exceeds 5,000 characters ({len(description)}).")
    if publish_mode == "scheduled_private" and (publish_at is None or publish_at.tzinfo is None):
        raise ValueError("Scheduled YouTube publish time must be timezone-aware.")
    status = {
        "privacyStatus": "public" if publish_mode == "public_now" else "private",
        "selfDeclaredMadeForKids": False,
    }
    if publish_mode == "scheduled_private":
        status["publishAt"] = publish_at.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    body = {
        "snippet": {
            "title": title,
            "description": description[:5000],
            "tags": ["Shorts", "Kerala Gold Rate", "Gold Rate", "Silver Rate", "Swarnam4U"],
            "categoryId": "22",
            "defaultLanguage": "en" if lang == "en" else "ml",
        },
        "status": status,
    }
    media = MediaFileUpload(str(path), mimetype="video/mp4", resumable=True, chunksize=8 * 1024 * 1024)
    response = youtube.videos().insert(part="snippet,status", body=body, media_body=media).execute(num_retries=5)
    video_id = response.get("id")
    if not video_id:
        raise RuntimeError("YouTube upload response did not include a video ID.")
    result = {"language": lang, "title": title, "video_id": video_id,
              "status": "published_public" if publish_mode == "public_now" else "scheduled_private"}
    if publish_at is not None:
        result["publish_at_ist"] = publish_at.astimezone(IST).isoformat(timespec="seconds")
    return result

def main() -> int:
    # Fail closed independently of workflow conditions: generation can still finish, but this
    # uploader must never send a request while the emergency stop is enabled.
    if os.environ.get("YOUTUBE_UPLOAD_KILL_SWITCH", "false").strip().lower() == "true":
        print("Emergency stop is ON; refusing every YouTube upload.", file=sys.stderr)
        return 2
    publish_mode = os.environ.get("SHORTS_PUBLISH_MODE", "scheduled_private").strip().lower()
    if publish_mode not in {"scheduled_private", "public_now"}:
        print("SHORTS_PUBLISH_MODE must be scheduled_private or public_now.", file=sys.stderr)
        return 2
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
    target = target_time(slot) if publish_mode == "scheduled_private" else None
    if target is not None:
        try:
            ensure_publish_window(target)
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
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
    comparisons = manifest.get("comparisons", {})
    primary_change = comparisons.get("22K · 916", {"direction": "unavailable", "change": None})
    youtube = get_youtube()
    existing_titles, channel_handle = recent_uploaded_titles(youtube)
    results = []
    for lang in ("en", "ml"):
        title = video_title(lang, today, slot, primary_change)
        if is_duplicate_slot(existing_titles, title):
            results.append({"language": lang, "title": title, "status": "skipped_duplicate"})
            continue
        # Scheduled uploads recheck the target immediately before each upload. Public-now
        # uploads intentionally bypass the schedule window because the user explicitly requested it.
        if target is not None:
            try:
                ensure_publish_window(target)
            except RuntimeError as exc:
                report = {"date": today.isoformat(), "slot": slot, "channel_handle": channel_handle, "results": results,
                          "blocked_language": lang, "reason": str(exc)}
                (out_dir / "upload-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
                print(json.dumps(report, ensure_ascii=False, indent=2), file=sys.stderr)
                return 2
        results.append(upload_one(youtube, videos[lang], lang, date=today, slot=slot,
                                  publish_at=target, title=title, publish_mode=publish_mode))
    report = {"date": today.isoformat(), "slot": slot, "publish_mode": publish_mode,
              "channel_handle": channel_handle, "results": results}
    (out_dir / "upload-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
