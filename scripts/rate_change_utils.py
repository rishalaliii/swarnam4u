"""Utilities for date-aware day-over-day rate changes and Shorts titles."""
from __future__ import annotations

import datetime as dt
import math

SLOT_TIMES = {
    "morning": "10:45",
    "midday": "13:15",
    "evening": "17:15",
}

MALAYALAM_MONTHS = {
    1: "ജനുവരി", 2: "ഫെബ്രുവരി", 3: "മാർച്ച്", 4: "ഏപ്രിൽ",
    5: "മേയ്", 6: "ജൂൺ", 7: "ജൂലൈ", 8: "ഓഗസ്റ്റ്",
    9: "സെപ്റ്റംബർ", 10: "ഒക്ടോബർ", 11: "നവംബർ", 12: "ഡിസംബർ",
}


def malayalam_date_text(date: dt.date) -> str:
    """Format a date entirely in Malayalam script except for Western digits."""
    return f"{date.day} {MALAYALAM_MONTHS[date.month]} {date.year}"


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


def title_change_text(comparison: dict, lang: str, compact: bool = False) -> str:
    direction = comparison.get("direction", "unavailable")
    amount = rate_change_amount(comparison)
    if lang == "ml":
        if direction == "up":
            return f"{amount}/ഗ്രാം വർധന" if compact else f"ഇന്നലെയേക്കാൾ {amount}/ഗ്രാം വർധന"
        if direction == "down":
            return f"{amount}/ഗ്രാം കുറവ്" if compact else f"ഇന്നലെയേക്കാൾ {amount}/ഗ്രാം കുറവ്"
        if direction == "no_change":
            return "മാറ്റമില്ല" if compact else "ഇന്നലെയേക്കാൾ മാറ്റമില്ല"
        return "മാറ്റം ലഭ്യമല്ല" if compact else "മുൻദിവസത്തെ നിരക്ക് ലഭ്യമല്ല"
    if direction == "up":
        return f"UP {amount}/g" if compact else f"UP {amount}/g vs Yesterday"
    if direction == "down":
        return f"DOWN {amount}/g" if compact else f"DOWN {amount}/g vs Yesterday"
    if direction == "no_change":
        return "No change" if compact else "No Change vs Yesterday"
    return "Change N/A" if compact else "Change Unavailable"


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


def video_title(
    lang: str,
    date: dt.date,
    slot: str,
    comparison: dict,
    display_time: str | None = None,
) -> str:
    """Localized title; optionally use the actual upload time instead of the scheduled slot."""
    if display_time is not None:
        try:
            parsed_time = dt.datetime.strptime(display_time, "%H:%M").time()
        except ValueError as exc:
            raise ValueError("display_time must use 24-hour HH:MM format.") from exc
        display_time = parsed_time.strftime("%H:%M")
    effective_time = display_time or SLOT_TIMES[slot]
    if slot not in SLOT_TIMES:
        raise ValueError(f"Unknown publish slot: {slot}")
    if lang not in ("en", "ml"):
        raise ValueError(f"Unsupported language: {lang}")
    hashtags = "#IndiaGoldRate #Shorts" if lang == "en" else "#KeralaGoldRate #Shorts"

    # Keep English titles exactly as before; localize the human-readable parts only for Malayalam.
    if lang == "en":
        time_text = f"{effective_time} IST"
        date_text = date.strftime("%d %b %Y")
        movement = title_change_text(comparison, "en")
        title = f"Today's Gold Rate | {date_text} | {time_text} | {movement} {hashtags}"
        if len(title) > 100:
            movement = title_change_text(comparison, "en", compact=True)
            title = f"Today's Gold Rate | {date_text} | {time_text} | {movement} {hashtags}"
        if len(title) > 100:
            raise ValueError(f"Generated English title exceeds YouTube's 100-character limit ({len(title)} characters).")
        return title

    date_text = malayalam_date_text(date)
    local_times = {
        "morning": f"രാവിലെ {effective_time}",
        "midday": f"ഉച്ചയ്ക്ക് {effective_time}",
        "evening": f"വൈകിട്ട് {effective_time}",
    }
    time_options = [local_times[slot], effective_time]
    movement_options = [
        title_change_text(comparison, "ml"),
        title_change_text(comparison, "ml", compact=True),
    ]
    prefix = "ഇന്നത്തെ സ്വർണ്ണവില"
    # Use native Malayalam script for YouTube metadata; retain Manglish only in filenames.
    # Shorten the time and movement phrase only when needed for YouTube's 100-character limit.
    for movement in movement_options:
        for time_text in time_options:
            title = f"{prefix} | {date_text} | {time_text} | {movement} {hashtags}"
            if len(title) <= 100:
                return title
    raise ValueError("Generated Malayalam title exceeds YouTube's 100-character limit.");



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
