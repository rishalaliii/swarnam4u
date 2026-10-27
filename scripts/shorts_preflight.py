#!/usr/bin/env python3
"""Safe live-rate preflight for the Swarnam4U Shorts project.

This check never changes data/rates.json and never uploads to YouTube.
It requires today's actual AKGSMA board values and verifies that the checked-in
snapshot values and each record's own date agree with the live board.
"""
from __future__ import annotations
import datetime as dt
import json
import pathlib
import re
import sys
import urllib.request
import urllib.error
import urllib.robotparser
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
RATES_PATH = ROOT / "data" / "rates.json"
OUT = ROOT / "output" / "shorts-preflight.json"
IST = ZoneInfo("Asia/Kolkata")
URL = "https://akgsma.com/"
UA = "Swarnam4U-rate-bot (+mailto:swarnam4u@gmail.com)"

def parse_board_text(text: str) -> tuple[str, dict[str, float | None]]:
    """Parse normalized visible text from AKGSMA's current board page."""
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

def robots_allows(robots_text: str, url: str = URL + "/") -> bool:
    parser = urllib.robotparser.RobotFileParser()
    parser.set_url(URL + "/robots.txt")
    parser.parse(robots_text.splitlines())
    return parser.can_fetch(UA, url)

def ensure_primary_source_allowed() -> None:
    req = urllib.request.Request(URL + "/robots.txt", headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            robots_text = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return  # No robots.txt means there is no published robots policy.
        raise ValueError(f"Could not verify AKGSMA robots.txt (HTTP {exc.code}); preflight will not fetch the board.") from exc
    except Exception as exc:
        raise ValueError(f"Could not verify AKGSMA robots.txt; preflight will not fetch the board: {exc}") from exc
    if not robots_allows(robots_text):
        raise ValueError("AKGSMA robots.txt disallows this user-agent; preflight will not fetch the board.")

def fetch_board() -> tuple[str, dict[str, float | None]]:
    ensure_primary_source_allowed()
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=25) as response:
        html = response.read().decode("utf-8", "replace")
    text = re.sub(r"<[^>]+>", " ", html)
    text = text.replace("&nbsp;", " ").replace("&#8377;", "₹").replace("&#39;", "'").replace("&amp;", "&")
    return parse_board_text(text)

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
        "note": "This step validates current board rates only. Rendering follows separately; YouTube uploading remains separately gated."
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
        required = ("gold_22k_916", "gold_18k_750", "silver_999")
        for key in required:
            if rates.get(key) is None or rates[key] <= 0:
                raise ValueError(f"Required published rate missing: {key}")
        checks = (
            ("gold", "22K · 916", "gold_22k_916"),
            ("gold", "18K · 750", "gold_18k_750"),
            ("silver", "Silver · 999", "silver_999"),
        )
        for group, label, key in checks:
            item = saved.get(group, {}).get(label, {})
            if item.get("date") != board_date:
                raise ValueError(f"Saved {label} record date is {item.get('date')}; board date is {board_date}.")
            try:
                stored_value = float(item.get("today"))
            except (TypeError, ValueError):
                raise ValueError(f"Saved rate missing or invalid for {label}.")
            if abs(stored_value - float(rates[key])) > 0.01:
                raise ValueError(f"Saved {label} value ({stored_value:g}) differs from live board value ({rates[key]:g}).")
        saved_date = saved.get("updated", "")[:10]
        if saved_date != board_date:
            raise ValueError(f"Stored snapshot timestamp date is {saved_date or 'missing'}, but live board date is {board_date}.")
        report["status"] = "PREFLIGHT_PASSED"
        report["reason"] = "Current board date and saved published rates match the live board."
        print("PREFLIGHT PASSED — live board date and saved published rates match.")
    except Exception as exc:
        report["reason"] = str(exc)
        print(f"PREFLIGHT BLOCKED: {exc}", file=sys.stderr)
    finally:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PREFLIGHT_PASSED" else 1

if __name__ == "__main__":
    raise SystemExit(main())
