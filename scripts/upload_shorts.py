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
CHANNEL_URL = "https://www.youtube.com/@SWARANAM4U"
UPLOAD_MODES = {"private_test", "schedule"}
TITLE_HASHTAGS = " #KeralaGoldRate #Shorts"
PRIVATE_TEST_MARKER = " [PRIVATE TEST]"

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

def title_slot_identity(title: str) -> tuple[str, str, str, str] | None:
    """Normalize language/date/time so rate changes do not let a rerun duplicate its slot."""
    parts = title.split(" | ")
    if len(parts) < 3:
        return None

    prefix = parts[0].strip().casefold()
    if prefix.startswith("today's gold rate"):
        language = "en"
    elif prefix.startswith("innathe swarna vila") or prefix.startswith("ഇന്നത്തെ സ്വർണ്ണവില"):
        language = "ml"
    else:
        return None

    date_text = parts[1].strip()
    board_date = None
    for date_format in ("%d %b %Y", "%d %B %Y"):
        try:
            board_date = dt.datetime.strptime(date_text, date_format).date().isoformat()
            break
        except ValueError:
            pass
    if board_date is None:
        malayalam_months = {
            "ജനുവരി": 1, "ഫെബ്രുവരി": 2, "മാർച്ച്": 3, "ഏപ്രിൽ": 4,
            "മേയ്": 5, "ജൂൺ": 6, "ജൂലൈ": 7, "ഓഗസ്റ്റ്": 8,
            "സെപ്റ്റംബർ": 9, "ഒക്ടോബർ": 10, "നവംബർ": 11, "ഡിസംബർ": 12,
        }
        match = re.fullmatch(r"(\d{1,2})\s+(\S+)\s+(\d{4})", date_text)
        if match and match.group(2) in malayalam_months:
            try:
                board_date = dt.date(
                    int(match.group(3)), malayalam_months[match.group(2)], int(match.group(1))
                ).isoformat()
            except ValueError:
                return None
    if board_date is None:
        return None

    time_match = re.search(r"(?<![0-9])([0-9]{2}:[0-9]{2})(?![0-9])", parts[2])
    if not time_match:
        return None

    # A private test must not block the real scheduled upload for the same slot.
    mode = "private_test" if "[PRIVATE TEST]" in title else "production"
    return language, board_date, time_match.group(1), mode


def is_duplicate_slot(existing_titles: set[str], candidate_title: str) -> bool:
    """Reject an already-uploaded language/date/slot even if the rate movement or time wording changes."""
    if candidate_title in existing_titles:
        return True
    identity = title_slot_identity(candidate_title)
    if identity is None:
        return False
    return any(title_slot_identity(existing) == identity for existing in existing_titles)


def video_description(date: dt.date, lang: str = "en", private_test: bool = False) -> str:
    """Create localized YouTube metadata with source, website and subscription links."""
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
            f"പുതിയ നിരക്കുകൾക്കായി ചാനൽ Subscribe ചെയ്യുക: {CHANNEL_URL}\n"
            f"ഇപ്പോഴത്തെ നിരക്കുകൾ: https://{WEBSITE}\n"
            "നിരക്കുകൾ ഗ്രാമിന് നൽകിയതാണ്. ഒരു പവന്റെ തുക 8 ഗ്രാമിന്റെ നിരക്കിൽ നിന്ന് കണക്കാക്കിയതാണ്. "
            "വാങ്ങുന്നതിന് മുമ്പ് നിലവിലെ നിരക്ക് സ്ഥിരീകരിക്കുക."
        )
    else:
        description = (
            f"Kerala gold and silver board rates dated {english_date}.\n"
            "Source: AKGSMA Kerala — https://akgsma.com/\n"
            f"Subscribe for daily Kerala gold-rate updates: {CHANNEL_URL}\n"
            f"Check the latest rates: https://{WEBSITE}\n"
            "Rates are shown per gram. Pawan totals are calculated from the published per-gram rates. "
            "Confirm the current rate before purchase."
        )
    if private_test:
        prefix = (
            "[PRIVATE VALIDATION TEST — KEEP PRIVATE]\n"
            if lang == "en"
            else "സ്വകാര്യ പരിശോധനാ വീഡിയോ — Public ആക്കരുത്.\n"
        )
        description = prefix + description
    return description + "\n#Shorts #KeralaGoldRate #GoldRate #SilverRate #Swarnam4U"


def private_test_title(title: str) -> str:
    """Add a visible private-test marker without cutting a word or dropping hashtags."""
    if title.endswith(TITLE_HASHTAGS):
        core = title[:-len(TITLE_HASHTAGS)].rstrip()
        room = 100 - len(PRIVATE_TEST_MARKER) - len(TITLE_HASHTAGS)
        if len(core) > room:
            core = core[:room].rsplit(" ", 1)[0].rstrip()
        result = core + PRIVATE_TEST_MARKER + TITLE_HASHTAGS
    else:
        room = 100 - len(PRIVATE_TEST_MARKER)
        core = title[:room]
        if len(title) > room:
            core = core.rsplit(" ", 1)[0].rstrip()
        result = core + PRIVATE_TEST_MARKER
    if len(result) > 100:
        raise ValueError("Private-test title exceeds YouTube's 100-character limit.")
    return result


def video_resource(
    lang: str,
    date: dt.date,
    title: str,
    mode: str,
    publish_at: dt.datetime | None = None,
) -> dict:
    """Build a YouTube metadata body that fails closed on upload mode and visibility."""
    if mode not in UPLOAD_MODES:
        raise ValueError(f"Refusing unsupported YouTube upload mode: {mode}")
    if not title or len(title) > 100:
        raise ValueError(f"YouTube title must be 1–100 characters; got {len(title)}.")
    if lang not in ("en", "ml"):
        raise ValueError(f"Unsupported video language: {lang}")
    description = video_description(date, lang, private_test=(mode == "private_test"))
    if len(description) > 5000:
        raise ValueError(f"YouTube description exceeds 5,000 characters ({len(description)}).")

    status = {"privacyStatus": "private", "selfDeclaredMadeForKids": False}
    if mode == "schedule":
        if publish_at is None or publish_at.tzinfo is None:
            raise ValueError("Scheduled publication requires a timezone-aware target time.")
        status["publishAt"] = publish_at.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    elif publish_at is not None:
        raise ValueError("Private test uploads must not have a publishAt time.")

    return {
        "snippet": {
            "title": title,
            "description": description,
            "tags": ["Shorts", "Kerala Gold Rate", "Gold Rate", "Silver Rate", "Swarnam4U"],
            "categoryId": "22",
            "defaultLanguage": "en" if lang == "en" else "ml",
        },
        "status": status,
    }


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

def upload_one(
    youtube, path: pathlib.Path, lang: str, date: dt.date, mode: str,
    publish_at: dt.datetime | None, title: str,
) -> dict:
    body = video_resource(lang, date, title, mode, publish_at)
    media = MediaFileUpload(str(path), mimetype="video/mp4", resumable=True, chunksize=8 * 1024 * 1024)
    response = youtube.videos().insert(
        part="snippet,status", body=body, media_body=media
    ).execute(num_retries=5)
    video_id = response.get("id")
    if not video_id:
        raise RuntimeError(f"YouTube upload response did not include a video ID for {lang}.")
    return {
        "language": lang,
        "title": title,
        "video_id": video_id,
        "video_url": f"https://www.youtube.com/watch?v={video_id}",
        "mode": mode,
        "publish_at_ist": publish_at.astimezone(IST).isoformat(timespec="seconds") if publish_at else None,
        "status": "scheduled_private" if mode == "schedule" else "private_test",
    }


def main() -> int:
    slot = os.environ.get("SHORTS_SLOT", "").strip()
    mode = os.environ.get("SHORTS_UPLOAD_MODE", "build_only").strip().lower()
    if slot not in SLOT_TIMES:
        print("SHORTS_SLOT must be morning, midday, or evening.", file=sys.stderr)
        return 2
    if mode not in UPLOAD_MODES:
        print("Upload refused. Explicitly select private_test or schedule; build_only must not call this script.", file=sys.stderr)
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
    if publish_at:
        try:
            ensure_publish_window(publish_at)
        except (RuntimeError, ValueError) as exc:
            return block(str(exc))

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
    if set(videos) != {"en", "ml"} or any(not path.is_file() or path.stat().st_size < 20_000 for path in videos.values()):
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
            if is_duplicate_slot(existing_titles, title):
                report["results"].append({
                    "language": lang, "title": title, "mode": mode, "status": "skipped_duplicate"
                })
                save_report()
                continue

            # Recheck close to each scheduled upload, because a preceding upload/retry takes time.
            if publish_at:
                try:
                    ensure_publish_window(publish_at)
                except (RuntimeError, ValueError) as exc:
                    report["status"] = "blocked"
                    report["blocked_language"] = lang
                    report["reason"] = str(exc)
                    save_report()
                    print(json.dumps(report, ensure_ascii=False, indent=2), file=sys.stderr)
                    return 2

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
