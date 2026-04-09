import json
from datetime import date, datetime, timedelta


def calc_sleep_hours(fell_asleep: str | None, sleep_end: str | None) -> str:
    """Calculate sleep hours from fell_asleep and sleep_end HH:MM strings."""
    if not fell_asleep or not sleep_end:
        return "—"
    try:
        fa_h, fa_m = map(int, fell_asleep.split(":"))
        se_h, se_m = map(int, sleep_end.split(":"))
        fa_mins = fa_h * 60 + fa_m
        se_mins = se_h * 60 + se_m
        if se_mins <= fa_mins:
            diff = (1440 - fa_mins) + se_mins
        else:
            diff = se_mins - fa_mins
        hours = diff / 60
        return f"{hours:.1f}"
    except (ValueError, AttributeError):
        return "—"


def get_event_date() -> str:
    """Get event_date with 5am boundary. Returns yesterday's date if hour < 5."""
    now = datetime.now()
    if now.hour < 5:
        return (date.today() - timedelta(days=1)).isoformat()
    return date.today().isoformat()


def format_event_details(event_type: str, data_str: str | None) -> str:
    """Format event data for history display."""
    if not data_str:
        return "—"
    try:
        d = json.loads(data_str)
    except (json.JSONDecodeError, TypeError):
        return data_str or "—"

    if event_type == "sleep":
        sleep_h = calc_sleep_hours(d.get("fell_asleep"), d.get("sleep_end"))
        parts = []
        if d.get("no_sleep"):
            parts.append("No sleep")
        else:
            if d.get("sleep_end"):
                parts.append(f"Wake {d['sleep_end']}")
            if sleep_h != "—":
                parts.append(f"{sleep_h}h")
        if d.get("nightmares"):
            parts.append("Nightmares")
        if d.get("melatonin"):
            parts.append("Melatonin")
        if not d.get("no_shower") and d.get("shower_end"):
            parts.append(f"Shower {d['shower_end']}")
        elif d.get("no_shower"):
            parts.append("No shower")
        return " · ".join(parts) if parts else "—"

    elif event_type in ("mood", "energy", "anxiety"):
        return str(d.get("value", "—"))

    elif event_type == "daily_summary":
        parts = []
        mapping = [
            ("meals", "Meals"),
            ("snacks", "Snacks"),
            ("coffee", "Coffee"),
            ("exercise_minutes", "Ex"),
            ("sunlight_minutes", "Sun"),
            ("hours_worked", "Work"),
            ("intrusive", "Int"),
        ]
        for key, label in mapping:
            val = d.get(key)
            if val is not None:
                suffix = "m" if "minutes" in key else ("h" if key == "hours_worked" else "")
                parts.append(f"{label}:{val}{suffix}")
        return " ".join(parts) if parts else "—"

    elif event_type == "exercise":
        parts = []
        if d.get("type"):
            parts.append(d["type"])
        if d.get("duration_minutes"):
            parts.append(f"{d['duration_minutes']}m")
        return " ".join(parts) if parts else "—"

    elif event_type == "food":
        parts = [d.get("name", "(unnamed)")]
        if d.get("is_full_meal"):
            parts.append("meal")
        else:
            parts.append("snack")
        if d.get("is_dairy"):
            parts.append("dairy")
        return " · ".join(parts)

    elif event_type == "medicine":
        parts = []
        if d.get("name"):
            parts.append(d["name"])
        if d.get("reason"):
            parts.append(f"for {d['reason']}")
        return " ".join(parts) if parts else "—"

    elif event_type == "headache":
        sev = d.get("severity")
        return f"severity {sev}/10" if sev is not None else "—"

    elif event_type == "bowel":
        return d.get("type", "—")

    elif event_type == "work":
        hours = d.get("hours")
        return f"{hours}h" if hours is not None else "—"

    elif event_type == "relax":
        parts = []
        if d.get("hours") is not None:
            parts.append(f"{d['hours']}h")
        if d.get("video_game"):
            parts.append("gaming")
        return " · ".join(parts) if parts else "—"

    else:
        return data_str
