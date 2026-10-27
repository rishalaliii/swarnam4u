#!/usr/bin/env python3
"""Verify YouTube OAuth, channel identity, and permission to list recent uploads.

This diagnostic never uploads, edits, schedules, or deletes a video.
"""
from __future__ import annotations

import json
import sys

from upload_shorts import get_youtube, recent_uploaded_titles


def main() -> int:
    try:
        titles, handle = recent_uploaded_titles(get_youtube())
    except Exception as exc:
        print(f"YOUTUBE CONNECTION CHECK FAILED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({
        "status": "CONNECTION_VERIFIED",
        "channel_handle": handle,
        "recent_upload_titles_checked": len(titles),
        "upload_attempted": False,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
