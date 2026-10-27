#!/usr/bin/env python3
"""Create a YouTube OAuth refresh token locally after verifying @SWARANAM4U.

This helper only prints a refresh token after it confirms that the authorized Google
account controls the expected channel. It does not write tokens to disk.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
from urllib.parse import urlparse

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]
DEFAULT_HANDLE = "@SWARANAM4U"


def normalize_handle(value: str | None) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    if "youtube.com" in value.lower() or value.lower().startswith(("http://", "https://")):
        parsed = urlparse(value if "://" in value else "https://" + value)
        value = parsed.path.rstrip("/").split("/")[-1]
    return value.strip().lstrip("@").casefold()


def create_token(client_secrets_path: pathlib.Path, expected_handle: str) -> tuple[str, str]:
    if not client_secrets_path.is_file():
        raise FileNotFoundError(f"OAuth client JSON not found: {client_secrets_path}")
    try:
        config = json.loads(client_secrets_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"OAuth client JSON could not be parsed: {exc}") from exc
    if not isinstance(config, dict) or not isinstance(config.get("installed"), dict):
        raise ValueError(
            "Use a Google OAuth client of type Desktop app and its downloaded JSON "
            "(the file must contain an 'installed' object). Do not use a Web application client."
        )

    flow = InstalledAppFlow.from_client_secrets_file(str(client_secrets_path), scopes=SCOPES)
    credentials = flow.run_local_server(
        host="localhost",
        port=0,
        open_browser=True,
        timeout_seconds=300,
        access_type="offline",
        prompt="consent",
        authorization_prompt_message="Opening Google authorization in your browser. If it does not open, visit: {url}",
        success_message="Swarnam4U YouTube authorization finished. You may close this tab.",
    )
    if not credentials.refresh_token:
        raise RuntimeError(
            "Google returned no refresh token. Revoke this app's old grant in your Google Account, "
            "then run this helper again and approve offline access."
        )

    granted = set(credentials.granted_scopes or [])
    if granted and not set(SCOPES).issubset(granted):
        missing = sorted(set(SCOPES) - granted)
        raise RuntimeError("The OAuth grant is missing required YouTube scopes: " + ", ".join(missing))

    youtube = build("youtube", "v3", credentials=credentials, cache_discovery=False)
    expected = "@" + normalize_handle(expected_handle)
    expected_result = youtube.channels().list(
        part="id,snippet", forHandle=expected, maxResults=1
    ).execute(num_retries=3)
    expected_items = expected_result.get("items", [])
    if not expected_items or not expected_items[0].get("id"):
        raise RuntimeError(f"YouTube could not resolve expected channel {expected}; no token was printed.")
    expected_id = expected_items[0]["id"]

    mine_result = youtube.channels().list(part="id,snippet", mine=True, maxResults=1).execute(num_retries=3)
    mine_items = mine_result.get("items", [])
    if not mine_items or mine_items[0].get("id") != expected_id:
        actual = (mine_items[0].get("snippet") or {}).get("customUrl") if mine_items else None
        raise RuntimeError(
            f"Authorized Google account is linked to a different YouTube channel "
            f"({actual or 'channel identity unavailable'}), not {expected}; no token was printed."
        )

    actual_snippet = mine_items[0].get("snippet") or {}
    actual_handle = actual_snippet.get("customUrl") or actual_snippet.get("handle") or expected
    if normalize_handle(actual_handle) != normalize_handle(expected):
        raise RuntimeError(
            f"Channel ID matched but the returned handle ({actual_handle}) is not {expected}; no token was printed."
        )
    return credentials.refresh_token, "@" + normalize_handle(actual_handle)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--client-secrets",
        required=True,
        help="Path to the downloaded Google OAuth Desktop-app JSON file",
    )
    parser.add_argument(
        "--expected-handle",
        default=os.environ.get("YOUTUBE_EXPECTED_CHANNEL_HANDLE", DEFAULT_HANDLE),
        help="Expected channel handle or URL (default: @SWARANAM4U)",
    )
    args = parser.parse_args()
    try:
        token, handle = create_token(pathlib.Path(args.client_secrets).expanduser(), args.expected_handle)
    except Exception as exc:
        print(f"YOUTUBE OAUTH SETUP FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print(f"Verified YouTube channel: {handle}")
    print("Authorization scopes: youtube.upload and youtube.readonly")
    print()
    print("Copy the next line into GitHub Actions secret YOUTUBE_REFRESH_TOKEN:")
    print(token)
    print()
    print("Also create GitHub Actions secret YOUTUBE_CLIENT_SECRET_JSON using the full downloaded OAuth JSON file contents.")
    print("For unattended publishing, review Google OAuth publishing status; grants for external test users can expire after seven days.")
    print("Never commit the client JSON or refresh token, and never paste the refresh token into issues or chat.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
