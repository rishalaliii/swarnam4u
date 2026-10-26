#!/usr/bin/env python3
"""Safe live-rate preflight for the Swarnam4U Shorts project.

Never edits the rate snapshot and never uploads to YouTube. It ensures
AKGSMA's board date matches the current date in Kerala and requires the
board's 916, 750 and 999 values to be present before a production render.
"""
from __future__ import annotations
import datetime as dt
import json
import pathlib
import re
import sys
import urllib.request
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
RATES_PATH = ROOT / "data" / "rates.json"
OUT = ROOT / "output" / "shorts-preflight.json"
IST = ZoneInfo("Asia/Kolkata")
URL = "https://akgsma.com/"

def fetch_board() -> tuple[str, dict[str, float | None]]:
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0 Swarnam4U preflight"})
    with urllib.request.urlopen(req, timeout=25) as response:
        html = response.read().decode("utf-8", "replace")
    text = re.sub(r"<[^>]+>", " ", html)
    text = text.replace("&nbsp;", " ").replace("&#8377;", "₹").replace("&amp;", "&")
    text = re.sub(r"\s+", " ", text)
    date_match = re.search(r"Today'?s Rate\s*\((\d{1,2})/(\d{1,2})/(\d{4})\)", text, re.I)
    if not date_match:
        raise ValueError("Could not parse AKGSMA board date; source page may have changed.")
    board_date = dt.date(int(date_match[3]), int(date_match[2]), int(date_match[1])).isoformat()
    def rate(pattern: str) -> float | None:
        m = re.search(pattern, text, re.I)
        return float(m.group(1).replace(",", "")) if m else None
    rates = {
        "gold_22k_916": rate(r"22\s*K\s*916\s*\(\s*1\s*gm\s*\)\s*[-–:]?\s*(?:₹|Rs\.?)?\s*([\d,]+(?:\.\d+)?)"),
        "gold_18k_750": rate(r"18\s*K\s*750\s*\(\s*1\s*gm\s*\)\s*[-–:]?\s*(?:₹|Rs\.?)?\s*([\d,]+(?:\.\d+)?)"),
        "silver_999": rate(r"(?<!Marked\s)(?<!925\s)\bSilver\s*\(\s*1\s*gm\s*\)\s*[-–:]?\s*(?:₹|Rs\.?)?\s*([\d,]+(?:\.\d+)?)"),
        "silver_925_published": rate(r"925\s*Hall\s*Marked\s*Silver\s*\(\s*1\s*gm\s*\)\s*[-–:]?\s*(?:₹|Rs\.?)?\s*([\d,]+(?:\.\d+)?)"),
    }
    return board_date, rates

def main() -> int:
    now = dt.datetime.now(IST)
    report: dict = {
        "checked_at_ist": now.isoformat(timespec="seconds"),
        "source_url": URL,
        "current_date_ist": now.date().isoformat(),
        "status": "BLOCKED",
        "reason": None,
        "board_date": None,
        "rates": {},
        "note": "Preflight only. No video rendered and no YouTube upload attempted."
    }
    try:
        if not RATES_PATH.exists():
            raise ValueError("data/rates.json is missing.")
        saved = json.loads(RATES_PATH.read_text(encoding="utf-8"))
        board_date, rates = fetch_board()
        report["board_date"] = board_date
        report["rates"] = rates
        if board_date != now.date().isoformat():
            raise ValueError(f"AKGSMA board date is {board_date}; today in Kerala is {now.date().isoformat()}. Do not publish as today's rate.")
        for key in ("gold_22k_916", "gold_18k_750", "silver_999"):
            if rates.get(key) is None or rates[key] <= 0:
                raise ValueError(f"Required published rate missing: {key}")
        saved_date = saved.get("updated", "")[:10]
        if saved_date != board_date:
            raise ValueError(f"Stored data snapshot date is {saved_date or 'missing'}, but live board date is {board_date}. Refresh rates and verify before rendering.")
        report["status"] = "PREFLIGHT_PASSED"
        report["reason"] = "Current board date and required published rates verified. Render/upload remain disabled in this starter."
        print("PREFLIGHT PASSED — rates/date only; rendering and uploads are not enabled.")
        print(json.dumps(report, ensure_ascii=False, indent=2))
    except Exception as exc:
        report["reason"] = str(exc)
        print(f"PREFLIGHT BLOCKED: {exc}", file=sys.stderr)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if report["status"] == "PREFLIGHT_PASSED" else 1

if __name__ == "__main__":
    raise SystemExit(main())
