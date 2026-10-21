"""Backfill past daily Kerala gold rates (22K, 24K) from GoodReturns into data/rates.json.

GoodReturns' own date picker loads a past day with:
    GET /gold-rates/kerala.html?gr_db_dynamic_content=metal_past_price&date=YYYY-MM-DD
(headers X-Requested-With: XMLHttpRequest, X-OIGT-Header: GITPL). This script calls that same
request once per day, politely (delay between calls), and stores only prices actually returned.
Days with no price are skipped, never invented. Safe to re-run: recorded days are kept unless --force.

Usage:  python scripts/backfill_goodreturns.py 2021-10-21 2026-10-21 [--force]   (5 years; resumable)
"""
import json, re, sys, time
from datetime import date, timedelta
import requests

BASE = "https://www.goodreturns.in/gold-rates/kerala.html"
HEAD = {"User-Agent": "Mozilla/5.0", "X-Requested-With": "XMLHttpRequest", "X-OIGT-Header": "GITPL"}
DATA = "data/rates.json"

def num(v):
    if v is None:
        return None
    m = re.search(r"\d[\d,]*(?:\.\d+)?", str(v))
    if not m:
        return None
    x = float(m.group(0).replace(",", ""))
    return x if x > 0 else None

def parse_payload(text):
    """Return (k22, k24) from the endpoint's reply, or None. Accepts JSON or an HTML/text fragment."""
    try:
        j = json.loads(text)
        k22 = num(j.get("gold_price_22K") or j.get("current_price_22K"))
        k24 = num(j.get("gold_price_24K") or j.get("current_price_24K"))
        return (k22, k24) if k22 else None
    except (ValueError, AttributeError):
        pass
    m22 = re.search(r"22\s*K[^\d₹]{0,40}₹\s*([\d,]+)", text, re.I)
    m24 = re.search(r"24\s*K[^\d₹]{0,40}₹\s*([\d,]+)", text, re.I)
    k22 = num(m22.group(1)) if m22 else None
    return (k22, num(m24.group(1)) if m24 else None) if k22 else None

def put(data, iso, k22, k24, force):
    for sid, rate in (("gold22", k22), ("gold24", k24)):
        if rate is None:
            continue
        h = {r["date"]: r["rate"] for r in data["series"][sid]["history"]}
        if iso in h and not force:
            continue
        h[iso] = rate
        data["series"][sid]["history"] = [{"date": k, "rate": h[k]} for k in sorted(h)]

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    force = "--force" in sys.argv
    d0, d1 = date.fromisoformat(args[0]), date.fromisoformat(args[1])
    data = json.load(open(DATA, encoding="utf-8"))
    have = {r["date"] for r in data["series"]["gold22"]["history"]}
    s = requests.Session()
    ok = miss = 0
    d = d0
    while d <= d1:
        iso = d.isoformat()
        if force or iso not in have:
            got = None
            for attempt in range(3):                      # retry transient failures
                try:
                    r = s.get(BASE, params={"gr_db_dynamic_content": "metal_past_price", "date": iso}, headers=HEAD, timeout=30)
                    got = parse_payload(r.text) if r.status_code == 200 else None
                    if got is None and ok == 0 and miss < 3:
                        print(f"[sample reply for {iso}] HTTP {r.status_code}: {r.text[:300]!r}")
                    break
                except requests.RequestException:
                    time.sleep(2 * (attempt + 1))
            if got:
                put(data, iso, got[0], got[1], force); ok += 1
            else:
                miss += 1
            if (ok + miss) % 20 == 0:
                print(f"... {iso}: {ok} added, {miss} empty", flush=True)
                json.dump(data, open(DATA, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
            time.sleep(0.6)
        d += timedelta(days=1)
    data["history"]["gold"] = data["series"]["gold22"]["history"]
    json.dump(data, open(DATA, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"added {ok} days, {miss} days returned nothing")
    if ok == 0:
        sys.exit("No prices parsed - the endpoint reply format may differ; see the sample printed above.")

if __name__ == "__main__":
    main()
