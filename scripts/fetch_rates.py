"""Fetch AKGSMA (Kerala) board rates and update data/rates.json.

Runs on a schedule in GitHub Actions (.github/workflows/update.yml).
Nothing is ever invented: if the page cannot be fetched or parsed, the existing
file is left untouched and the script exits non-zero so the failed run is visible.

    python scripts/fetch_rates.py           fetch and update data/rates.json
    python scripts/fetch_rates.py --check   fetch and print what was parsed; write nothing

NOTE: the patterns below must be checked once against the live akgsma.com page.
"""
import json, re, sys, datetime, pathlib, urllib.robotparser
import requests
from bs4 import BeautifulSoup

URL = "https://akgsma.com"   # primary source (also used for robots.txt check)
UA = "Swarnam4U-rate-bot (+mailto:swarnam4u@gmail.com)"
OUT = pathlib.Path(__file__).resolve().parent.parent / "data" / "rates.json"
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
CODES = {999, 925, 916, 950, 900, 850, 800, 750, 585}   # purity numbers, never a price
MAX_JUMP = 0.25                                          # reject >25% move vs stored value

# ---- Method copied from the Asian Jewellery project (rates_sync.py), which fetches reliably because it runs server-side ----
# 1. AKGSMA (primary): exact lines "Today's Rate (dd/mm/yyyy)", "22K916 (1gm) - ₹ N", "18K750 (1gm) - ₹ N", "Silver (1gm) - ₹ N".
# 2. LiveGold Kerala (backup, relays the same AKGSMA board rate): "22 Karat Gold ... ₹N", "18 Karat 750 ... ₹N", "Ag 999 ... ₹N/g".
# 3. 24K, 14K are CALCULATED from the AKGSMA 22K board rate (22K x 24/22, 22K x 585/916) exactly like Asian does, and tagged as such.
# 4. Platinum has no AKGSMA rate: fallback pages only (amber tag).
# 5. Validation: plausible ranges, 18K/22K ratio check, reject >15% jump vs the last saved rate.
GAP = r"\s*\(\s*1\s*gm\s*\)\s*[-–:]?\s*(?:₹|Rs\.?)?\s*([\d,]+(?:\.\d+)?)"
MON = {m: i for i, m in enumerate("January February March April May June July August September October November December".split(), 1)}
GOLD_MAX_JUMP = 0.15
SERIES = [("gold22", "gold", "22K · 916", "Gold 22K · 916", "AKGSMA board rate"),
          ("gold24", "gold", "24K · 999", "Gold 24K · 999", "Calculated from the 22K board rate (22K x 24/22); AKGSMA does not publish 24K"),
          ("silver999", "silver", "Silver · 999", "Silver 999", "AKGSMA board rate"),
          ("silver925", "silver", "Silver · 925", "Silver 925", "Calculated from the 999 rate (x 0.925) unless the board quotes it")]


def _num(t, p):
    m = re.search(p, t, re.I)
    return float(m.group(1).replace(",", "")) if m else None


def parse_akgsma(t):
    d = re.search(r"Today'?s Rate\s*\((\d{1,2})/(\d{1,2})/(\d{4})\)", t, re.I)
    if not d:
        raise ValueError("rate date not found (page layout changed?)")
    return dict(date=datetime.date(int(d[3]), int(d[2]), int(d[1])).isoformat(),
                g916=_num(t, r"22\s*K\s*916" + GAP), g750=_num(t, r"18\s*K\s*750" + GAP),
                s999=_num(t, r"(?<!Marked\s)(?<!925\s)\bSilver" + GAP),
                s925=_num(t, r"925\s*Hall\s*Marked\s*Silver" + GAP))


def parse_livegold(t):
    if "AKGSMA" not in t:
        raise ValueError("AKGSMA board label missing")
    d = re.search(r"\b\w+day,\s*(\d{1,2}) ([A-Z][a-z]+) (\d{4})", t)
    if not d or d[2] not in MON:
        raise ValueError("rate date not found")
    return dict(date=datetime.date(int(d[3]), MON[d[2]], int(d[1])).isoformat(),
                g916=_num(t, r"22 Karat Gold.{0,60}?₹\s*([\d,]+)"), g750=_num(t, r"18 Karat\s*750.{0,40}?₹\s*([\d,]+)"),
                s999=_num(t, r"Ag 999.{0,60}?₹\s*([\d,]+(?:\.\d+)?)\s*/\s*g"))


BOARD_SOURCES = [("AKGSMA Kerala", "https://akgsma.com/", parse_akgsma, r"Today'?s Rate"),
                 ("LiveGold Kerala (AKGSMA board rate)", "https://www.livegoldkerala.com/kozhikode", parse_livegold, r"AKGSMA"),
                 ("LiveGold Kerala (AKGSMA board rate)", "https://www.livegoldkerala.com/", parse_livegold, r"AKGSMA")]


def validate(d):
    g, g7, s = d.get("g916"), d.get("g750"), d.get("s999")
    if not g and not s:
        raise ValueError("no rates found")
    if g and not 3000 < g < 60000:
        raise ValueError("22K value %s outside plausible range" % g)
    if g and g7 and abs(g7 / (g * 750 / 916) - 1) > .04:
        raise ValueError("18K/22K ratio implausible")
    if s and not 20 < s < 5000:
        raise ValueError("silver value %s outside plausible range" % s)
    return d


# label -> (group, regex, range): platinum (and only what the board lacks) from fallback pages; amber-tagged, never AKGSMA
PATTERNS = {}
# Fallback pages for what the board does not publish (platinum) or when every board source is down (silver). Each stored value records its source.
FALLBACKS = [
    ("Goodreturns Kerala", "https://www.goodreturns.in/platinum-rate-in-kerala.html", {
        "Platinum · 950": ("platinum", r"\bplatinum\b", (500, 50000)),
    }),
    ("BankBazaar Kerala", "https://www.bankbazaar.com/platinum-price-kerala.html", {
        "Platinum · 950": ("platinum", r"\bplatinum\b", (500, 50000)),
    }),
    ("Goodreturns Kerala", "https://www.goodreturns.in/silver-rates/kerala.html", {
        "Silver · 999": ("silver", r"\bsilver\b", (10, 2000)),
    }),
]
SPOT_GOLD = "https://api.gold-api.com/price/XAU"          # USD per troy ounce (reference only, not a board rate)
SPOT_FX = "https://open.er-api.com/v6/latest/USD"          # USD -> INR
OZ = 31.1034768
STOP = re.compile(r"\b(?:\d{2}\s*(?:K|Carat|Karat)|gold|silver|platinum)\b", re.I)
HISTORY_LABEL = {"gold": "22K · 916", "silver": "Silver · 925", "platinum": "Platinum · 950"}


def allowed_by_robots():
    """Respect robots.txt. A missing robots.txt means no restriction."""
    try:
        r = requests.get(URL + "/robots.txt", timeout=15, headers={"User-Agent": UA})
    except requests.RequestException:
        # If permission cannot be checked, do not scrape the primary source; use the fallbacks.
        return False
    if r.status_code == 404:
        return True
    if r.status_code != 200:
        return False
    rp = urllib.robotparser.RobotFileParser()
    rp.parse(r.text.splitlines())
    return rp.can_fetch(UA, URL + "/")


def find_exact(text, rx, lo, hi):
    m = re.search(rx, text, re.I)
    if not m:
        return None
    v = float(m.group(1).replace(",", ""))
    return v if lo <= v <= hi else None


def find_value(text, label_rx, lo, hi):
    """Plausible price shortly after the label. Pass 1 accepts only rupee-prefixed numbers; pass 2 plain numbers (never a year)."""
    for rupee_only in (True, False):
        for m in re.finditer(label_rx, text, re.I):
            win = text[m.end():m.end() + 120]
            win = re.sub(r"^\s*(?:gold|silver|platinum)\b", "", win, flags=re.I)   # label's own metal word is not a boundary
            stop = STOP.search(win)              # never read past the next label (nav bars, other rows)
            if stop:
                win = win[:stop.start()]
            rx = r"(?:₹|Rs\.?|INR)\s*(\d[\d,]*(?:\.\d+)?)" if rupee_only else r"(\d[\d,]*(?:\.\d+)?)"
            for n in re.finditer(rx, win):
                try:
                    v = float(n.group(1).replace(",", ""))
                except ValueError:
                    continue
                if v in CODES or not (lo <= v <= hi) or (not rupee_only and 1990 <= v <= 2100):
                    continue
                return v
    return None


BROWSER_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"


def get_text(url, must=None):
    """Direct fetch first; many sites block data-centre IPs, so retry as a browser, then via the r.jina.ai text mirror."""
    last = None
    for attempt in (lambda: requests.get(url, timeout=30, headers={"User-Agent": UA}),
                    lambda: requests.get(url, timeout=30, headers={"User-Agent": BROWSER_UA, "Accept-Language": "en-IN,en;q=0.9"}),
                    lambda: requests.get("https://r.jina.ai/" + url, timeout=45, headers={"User-Agent": BROWSER_UA})):
        try:
            r = attempt(); r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            for t in soup(["script", "style", "noscript"]):
                t.decompose()
            text = soup.get_text(" ", strip=True)
            if len(text) > 150 and (must is None or re.search(must, text, re.I)):   # a block/captcha page falls through to the next route
                return text
            last = "page did not contain the expected rate text"
        except requests.RequestException as e:
            last = e
    raise RuntimeError("all fetch routes failed: %s" % last)


def spot_reference():
    """International spot gold in INR/gram. Reference only: excludes Indian duty/premium, so it is never mixed into board rates."""
    try:
        usd_oz = float(requests.get(SPOT_GOLD, timeout=20, headers={"User-Agent": UA}).json()["price"])
        inr = float(requests.get(SPOT_FX, timeout=20, headers={"User-Agent": UA}).json()["rates"]["INR"])
        return {"gold_24k_per_gram": round(usd_oz / OZ * inr, 2), "usd_per_oz": usd_oz, "usd_inr": inr}
    except Exception as e:
        print("  spot reference unavailable:", e)
        return None


def board_rates(got_log):
    """Try each board source in order; use the freshest-dated valid result (AKGSMA wins ties), as Asian does."""
    res = []
    akgsma_allowed = allowed_by_robots()
    if not akgsma_allowed:
        got_log.append("AKGSMA skipped because robots.txt disallows this user-agent")
    for name, url, parser, must in BOARD_SOURCES:
        if name == "AKGSMA Kerala" and not akgsma_allowed:
            continue
        try:
            d = validate(parser(get_text(url, must))); d["name"] = name; res.append(d); got_log.append("%s ok (%s)" % (name, d["date"]))
        except Exception as e:
            got_log.append("%s failed: %s" % (name, e))
    if not res:
        return None, None
    top = max(d["date"] for d in res)
    gold = next(d for d in res if d["date"] == top and d.get("g916")) if any(d["date"] == top and d.get("g916") for d in res) else None
    sil = next((d for d in res if d["date"] == top and d.get("s999")), None) or next((d for d in res if d.get("s999")), None)
    return gold, sil


def main():
    check = "--check" in sys.argv
    data = json.loads(OUT.read_text(encoding="utf-8"))
    # Compare rate/history metadata, not the volatile wall-clock timestamp. This prevents a
    # no-change 10-minute poll from creating a commit and triggering unnecessary redeploys.
    tracked_keys = ("gold", "silver", "platinum", "history", "series", "history_basis", "source", "source_url", "currency", "unit")
    tracked_before = json.dumps({key: data.get(key) for key in tracked_keys}, sort_keys=True, ensure_ascii=False)
    now = datetime.datetime.now(IST)
    today = now.date().isoformat()
    got = {}                                     # (group,label) -> (value, source, rate_date)
    log = []

    def ok_jump(grp, label, val):
        old = data[grp].get(label)
        threshold = GOLD_MAX_JUMP if grp == "gold" else MAX_JUMP
        if old and old.get("today") and abs(val - old["today"]) / old["today"] > threshold:
            print("  skip %s: %s is >%d%% from stored %s" % (label, val, threshold * 100, old["today"])); return False
        return True

    gold, sil = board_rates(log)
    for line in log:
        print(" ", line)
    if gold and ok_jump("gold", "22K · 916", gold["g916"]):
        src, dt, g = gold["name"], gold["date"], gold["g916"]
        got[("gold", "22K · 916")] = (round(g), src, dt)
        g18 = gold.get("g750")
        if g18:
            got[("gold", "18K · 750")] = (round(g18), src, dt)
        else:
            got[("gold", "18K · 750")] = (round(g * 750 / 916), src + " (calculated from 22K)", dt)
        got[("gold", "24K · 999")] = (round(g * 24 / 22), src + " (calculated from 22K)", dt)
        got[("gold", "14K · 585")] = (round(g * 585 / 916), src + " (calculated from 22K)", dt)
    if sil and ok_jump("silver", "Silver · 999", sil["s999"]):
        s9, src, dt = sil["s999"], sil["name"], sil["date"]
        got[("silver", "Silver · 999")] = (s9, src, dt)
        if sil.get("s925"):                      # hallmarked 925 quoted by the board
            got[("silver", "Silver · 925")] = (sil["s925"], src, dt)
        else:                                    # otherwise calculated, as Asian Jewellery does (999 x .925, 999 x .8)
            got[("silver", "Silver · 925")] = (round(s9 * .925, 2), src + " (calculated from 999)", dt)
        got[("silver", "Silver · 800")] = (round(s9 * .8, 2), src + " (calculated from 999)", dt)

    # fallbacks fill only what is still missing (platinum, or silver if every board source failed)
    for name, url, pats in FALLBACKS:
        if all((g, l) in got for l, (g, _, _) in pats.items()):
            continue
        try:
            text = get_text(url, r"₹|Rs\.?")
            for label, (grp, rx, (lo, hi)) in pats.items():
                if (grp, label) in got:
                    continue
                val = find_value(text, rx, lo, hi)
                if val is not None and ok_jump(grp, label, val):
                    got[(grp, label)] = (val, name, today)
            print(name, "ok")
        except Exception as e:
            print(name, "failed:", e)
    if not got:
        print("No rates parsed from any source; keeping existing data"); sys.exit(1)

    for (grp, label), (val, source, rdate) in got.items():
        old = data[grp].get(label)
        if not old:
            yesterday = None
            yesterday_date = None
        elif old.get("date") == rdate:
            yesterday = old.get("yesterday")
            yesterday_date = old.get("yesterday_date")
        else:
            yesterday = old["today"]
            yesterday_date = old.get("date")
        data[grp][label] = {
            "today": val,
            "yesterday": yesterday,
            "yesterday_date": yesterday_date,
            "date": rdate,
            "source": source,
        }
        print("  %-16s %-10s %s (%s)" % (label, val, source, rdate))
    if check:
        print("Check only: nothing written"); return

    # Spot reference is auxiliary and volatile; refresh hourly, not on every 10-minute rates poll.
    # Keep the actual observation timestamp separate from the daily board rate timestamp.
    last_spot_stamp = (data.get("spot") or {}).get("updated_at")
    refresh_spot = not last_spot_stamp
    if last_spot_stamp:
        try:
            last_spot = datetime.datetime.fromisoformat(last_spot_stamp)
            if last_spot.tzinfo is None:
                last_spot = last_spot.replace(tzinfo=IST)
            refresh_spot = now - last_spot >= datetime.timedelta(hours=1)
        except (TypeError, ValueError):
            refresh_spot = True
    if refresh_spot:
        spot = spot_reference()
        if spot:
            spot["updated_at"] = now.isoformat(timespec="seconds")
            data["spot"] = spot

    data["source"], data["source_url"], data["currency"], data["unit"] = "AKGSMA Kerala", URL, "INR", "gram"
    data["history_basis"] = HISTORY_LABEL
    for grp, label in HISTORY_LABEL.items():
        entry = data[grp].get(label)
        if entry and entry.get("date"):
            h = [r for r in data["history"].get(grp, []) if r["date"] != entry["date"]]
            h.append({"date": entry["date"], "rate": entry["today"]})
            data["history"][grp] = sorted(h, key=lambda r: r["date"])[-3000:]
    # one real snapshot per day for every supported trend series (never back-filled or invented)
    ser = data.setdefault("series", {})
    for sid, grp, label, name, note in SERIES:
        entry = data[grp].get(label)
        if not (entry and entry.get("date") and entry.get("today")):
            continue
        sr = ser.setdefault(sid, {"label": name, "metal": grp, "group_key": label, "note": note, "history": []})
        sr["history"] = sorted([r for r in sr["history"] if r["date"] != entry["date"]] + [{"date": entry["date"], "rate": entry["today"]}], key=lambda r: r["date"])[-3000:]
    tracked_after = json.dumps({key: data.get(key) for key in tracked_keys}, sort_keys=True, ensure_ascii=False)
    if tracked_after != tracked_before or not data.get("updated"):
        data["updated"] = now.isoformat(timespec="seconds")
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(OUT)
    print("Updated", len(got), "rates")


if __name__ == "__main__":
    main()
