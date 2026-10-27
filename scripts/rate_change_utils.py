"""Utilities for date-aware day-over-day rate changes and Shorts titles."""
from __future__ import annotations

import datetime as dt
import math

SLOT_TIMES = {
    "morning": "10:30",
    "midday": "13:00",
    "evening": "17:00",
}


def compare_rate(current: float | int | None, previous: float | int | None) -> dict:
    """Compare the current published per-gram rate with the saved previous-day value."""
    result = {"current": None, "previous": None, "change": None, "direction": "unavailable"}
    try:
        cur = float(current)
    except (TypeError, ValueError):
        return result
    if not math.isfinite(cur) or cur <= 0:
        return result
    result["current"] = cur
    try:
        prev = float(previous)
    except (TypeError, ValueError):
        return result
    if not math.isfinite(prev) or prev <= 0:
        return result
    delta = round(cur - prev, 2)
    result.update({
        "previous": prev,
        "change": delta,
        "direction": "up" if delta > 0 else ("down" if delta < 0 else "no_change"),
    })
    return result


def rate_change_amount(comparison: dict) -> str | None:
    """Return a formatted absolute rupee change (without direction), or None."""
    delta = comparison.get("change")
    if delta is None:
        return None
    amount = abs(float(delta))
    if amount.is_integer():
        digits = str(int(amount))
        if len(digits) > 3:
            groups = []
            prefix = digits[:-3]
            while prefix:
                groups.append(prefix[-2:])
                prefix = prefix[:-2]
            digits = ",".join(reversed(groups)) + "," + digits[-3:]
        return "₹" + digits
    return "₹" + f"{amount:,.2f}"


def card_change_label(comparison: dict, lang: str) -> tuple[str, str | None]:
    """Return a short localized status label and a change amount only for up/down moves."""
    direction = comparison.get("direction", "unavailable")
    amount = rate_change_amount(comparison) if direction in ("up", "down") else None
    if lang == "ml":
        labels = {
            "up": "ഇന്നലെയേക്കാൾ വർധന",
            "down": "ഇന്നലെയേക്കാൾ കുറവ്",
            "no_change": "ഇന്നലെയേക്കാൾ മാറ്റമില്ല",
            "unavailable": "മുൻദിവസത്തെ നിരക്ക് ലഭ്യമല്ല",
        }
    else:
        labels = {
            "up": "UP vs YESTERDAY",
            "down": "DOWN vs YESTERDAY",
            "no_change": "NO CHANGE VS YESTERDAY",
            "unavailable": "CHANGE UNAVAILABLE",
        }
    return labels.get(direction, labels["unavailable"]), amount


def title_change_text(comparison: dict, lang: str) -> str:
    direction = comparison.get("direction", "unavailable")
    amount = rate_change_amount(comparison)
    if lang == "ml":
        if direction == "up":
            return f"ഇന്നലെയേക്കാൾ {amount}/g വർധിച്ചു"
        if direction == "down":
            return f"ഇന്നലെയേക്കാൾ {amount}/g കുറഞ്ഞു"
        if direction == "no_change":
            return "ഇന്നലെയേക്കാൾ മാറ്റമില്ല"
        return "മുൻദിവസത്തെ നിരക്ക് ലഭ്യമല്ല"
    if direction == "up":
        return f"UP {amount}/g vs Yesterday"
    if direction == "down":
        return f"DOWN {amount}/g vs Yesterday"
    if direction == "no_change":
        return "No Change vs Yesterday"
    return "Change Unavailable"


def spoken_change_text(comparison: dict, lang: str) -> str:
    """Short sentence fragment for narration; only states a change when a prior value exists."""
    direction = comparison.get("direction", "unavailable")
    amount = rate_change_amount(comparison)
    if lang == "ml":
        if direction == "up":
            return f"ഇന്നലെയേക്കാൾ ഗ്രാമിന് {amount} വർധിച്ചു."
        if direction == "down":
            return f"ഇന്നലെയേക്കാൾ ഗ്രാമിന് {amount} കുറഞ്ഞു."
        if direction == "no_change":
            return "ഇന്നലെയുമായി നിരക്കിൽ മാറ്റമില്ല."
        return "മുൻദിവസത്തെ നിരക്ക് ലഭ്യമല്ലാത്തതിനാൽ മാറ്റം കണക്കാക്കിയിട്ടില്ല."
    if direction == "up":
        return f"Up {amount} per gram versus yesterday."
    if direction == "down":
        return f"Down {amount} per gram versus yesterday."
    if direction == "no_change":
        return "No change versus yesterday."
    return "The previous-day comparison is unavailable."


def video_title(lang: str, date: dt.date, slot: str, comparison: dict) -> str:
    """Localized YouTube title using the planned publish time and 22K day-over-day move."""
    if slot not in SLOT_TIMES:
        raise ValueError(f"Unknown publish slot: {slot}")
    time_text = f"{SLOT_TIMES[slot]} IST"
    date_text = date.strftime("%d %b %Y")
    movement = title_change_text(comparison, lang)
    if lang == "ml":
        title = f"ഇന്നത്തെ സ്വർണ്ണവില | {date_text} | {time_text} | {movement} #Shorts"
    else:
        title = f"Today's Gold Rate | {date_text} | {time_text} | {movement} #Shorts"
    return title[:100]


def video_stem(lang: str, date: dt.date, slot: str, comparison: dict) -> str:
    """Readable, filesystem-safe filename reflecting language, slot and daily gold movement."""
    if slot not in SLOT_TIMES:
        raise ValueError(f"Unknown publish slot: {slot}")
    direction = comparison.get("direction", "unavailable")
    amount = rate_change_amount(comparison)
    amount_slug = ""
    if amount:
        amount_slug = "-" + amount.replace("₹", "").replace(",", "").replace(".", "p")
    prefix = "innathe-swarna-vila" if lang == "ml" else "todays-gold-rate"
    time_slug = SLOT_TIMES[slot].replace(":", "")
    return f"{prefix}-{date.isoformat()}-{time_slug}ist-{direction}{amount_slug}-{lang}"
