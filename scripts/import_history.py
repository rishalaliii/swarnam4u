"""Backfill REAL historical rates into data/rates.json from a CSV.

CSV columns:  date,series,rate     e.g.  2026-04-21,gold22,12850
series ids:   gold22, gold24, silver999, silver925
Usage:        python scripts/import_history.py history.csv
Only use genuine recorded prices (e.g. from AKGSMA archives) - never estimates.
"""
import csv, json, sys
path = "data/rates.json"
data = json.load(open(path, encoding="utf-8"))
ser = data["series"]
n = 0
for row in csv.DictReader(open(sys.argv[1], encoding="utf-8")):
    sid, d, r = row["series"].strip(), row["date"].strip(), float(row["rate"])
    if sid not in ser or r <= 0:
        continue
    h = {x["date"]: x["rate"] for x in ser[sid]["history"]}
    h.setdefault(d, r)          # never overwrite an already-recorded day
    ser[sid]["history"] = [{"date": k, "rate": h[k]} for k in sorted(h)]
    n += 1
# keep legacy gold/silver history in sync with the basis series
for grp, sid in (("gold", "gold22"), ("silver", "silver925")):
    data["history"][grp] = ser[sid]["history"]
json.dump(data, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("imported", n, "rows")
