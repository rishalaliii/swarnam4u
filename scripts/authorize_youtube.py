#!/usr/bin/env python3
"""Create a local refresh token for Swarnam4U YouTube Shorts automation.

This interactive helper never uploads videos and refuses to write tokens inside
the repository. Keep the downloaded OAuth client JSON outside the repository too.
"""
from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from pathlib import Path

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]
REPO_ROOT = Path(__file__).resolve().parents[1]


def default_token_path() -> Path:
    """Store the refresh token in the user's profile, not in the repo."""
    if os.name == "nt":
        appdata = Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming")))
        return appdata / "Swarnam4U" / "youtube-refresh-token.txt"
    config_home = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    return config_home / "swarnam4u" / "youtube-refresh-token.txt"


def is_inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Authorize the YouTube account and save a refresh token locally; no videos are uploaded."
    )
    parser.add_argument(
        "client_json",
        type=Path,
        help="Path to the Google OAuth client JSON downloaded for a Desktop app",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional token-file path outside this repository (defaults to your user profile)",
    )
    args = parser.parse_args()

    client_path = args.client_json.expanduser().resolve()
    if not client_path.is_file():
        parser.error(f"OAuth client JSON does not exist: {client_path}")
    if is_inside(client_path, REPO_ROOT):
        parser.error("Keep the OAuth client JSON outside the repository, for example in Downloads.")

    try:
        client_config = json.loads(client_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        parser.error(f"Could not read valid JSON from the OAuth client file: {exc}")
    if not isinstance(client_config, dict) or not isinstance(client_config.get("installed"), dict):
        parser.error("Use the JSON for a Google OAuth client of type Desktop app (it must contain an 'installed' section).")

    token_path = (args.output or default_token_path()).expanduser().resolve()
    if is_inside(token_path, REPO_ROOT):
        parser.error("For safety, the refresh token must be saved outside the repository.")
    if token_path == client_path:
        parser.error("The token output path must not overwrite the OAuth client JSON.")

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print(
            "Missing dependency. Run: python -m pip install -r requirements-youtube-auth.txt",
            file=sys.stderr,
        )
        return 2

    try:
        flow = InstalledAppFlow.from_client_secrets_file(str(client_path), scopes=SCOPES)
        credentials = flow.run_local_server(
            host="localhost",
            port=0,
            open_browser=True,
            authorization_prompt_message="Open this URL in your browser to authorize Swarnam4U:\n{url}",
            success_message="Authorization complete. You may close this browser tab.",
            access_type="offline",
            prompt="consent",
        )
    except Exception as exc:
        print(f"YouTube OAuth authorization failed: {exc}", file=sys.stderr)
        return 1

    refresh_token = getattr(credentials, "refresh_token", None)
    if not refresh_token:
        print(
            "Google did not return a refresh token. Revoke this app's access in your Google Account, "
            "then rerun this helper and consent again.",
            file=sys.stderr,
        )
        return 1

    try:
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(refresh_token + "\n", encoding="utf-8")
        try:
            os.chmod(token_path, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            # Windows file permissions are governed by the user's profile ACL.
            pass
    except OSError as exc:
        print(f"Could not securely write the local token file: {exc}", file=sys.stderr)
        return 1

    print(json.dumps({
        "status": "OAUTH_AUTHORIZED",
        "saved_refresh_token_to": str(token_path),
        "requested_scopes": SCOPES,
        "upload_attempted": False,
    }, ensure_ascii=False, indent=2))
    print("Next: add this file's contents as the GitHub Actions secret YOUTUBE_REFRESH_TOKEN.")
    print("Do not commit or share the refresh token or OAuth client JSON.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
