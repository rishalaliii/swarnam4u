"""Merge GoodReturns' 'last 10 days' Kerala table into data/rates.json (gold22 / gold24 series).

The page's full interactive graph is loaded by JavaScript from a data source that is not in the
static HTML, so this script only reads what the page itself publishes: the last-10-days table.
Run it every update (see .github/workflows/update.yml) and the history keeps growing.
Usage: python scripts/import_goodreturns.py
"""
import json, re, sys
from datetime import datetime
import requests
from bs4 import BeautifulSoup

URL = "https://www.goodreturns.in/gold-rates/kerala.html"
ROW = re.compile(r"([A-Z][a-z]{2} \d{1,2}, \d{4})\s*₹\s*([\d,]+)\s*\([^)]*\)\s*₹\s*([\d,]+)")

def parse(text):
    out = []
    for d, k24, k22 in ROW.findall(text):
        iso = datetime.strptime(d, "%b %d, %Y").strftime("%Y-%m-%d")
        out.append((iso, float(k24.replace(",", "")), float(k22.replace(",", ""))))
    return out

def merge(data, rows):
    ser = data["series"]
    for iso, k24, k22 in rows:
        for sid, rate in (("gold22", k22), ("gold24", k24)):
            h = {r["date"]: r["rate"] for r in ser[sid]["history"]}
            h[iso] = rate
            ser[sid]["history"] = [{"date": k, "rate": h[k]} for k in sorted(h)]
    data["history"]["gold"] = ser["gold22"]["history"]

if __name__ == "__main__":
    html = requests.get(URL, timeout=30, headers={"User-Agent": "Mozilla/5.0"}).text
    rows = parse(BeautifulSoup(html, "html.parser").get_text(" "))
    if len(rows) < 5:
        sys.exit("GoodReturns table not found - page layout may have changed")
    p = "data/rates.json"
    data = json.load(open(p, encoding="utf-8"))
    merge(data, rows)
    json.dump(data, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("merged", len(rows), "days")
