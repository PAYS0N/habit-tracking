import json
import logging
import subprocess
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import aiosqlite
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

PORT = 8900
DB_PATH = Path(__file__).parent / "checkin.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"
STATIC_DIR = Path(__file__).parent / "static"

DEVICES = ["192.168.22.75", "192.168.22.50", "192.168.22.52"]

# Binary paths — verify on the Pi; adjust if located at /usr/sbin/ instead
IPSET_BIN = "/usr/sbin/ipset"
IPTABLES_BIN = "/usr/sbin/iptables"

log = logging.getLogger("daily-checkin")
logging.basicConfig(level=logging.INFO)

app = FastAPI()
db: aiosqlite.Connection | None = None

SUMMARY_COUNTER_FIELDS = [
    "coffee", "intrusive", "meals", "snacks",
    "exercise_minutes", "sunlight_minutes", "hours_worked",
]


async def get_db() -> aiosqlite.Connection:
    global db
    if db is None:
        db = await aiosqlite.connect(str(DB_PATH))
        db.row_factory = aiosqlite.Row
        schema = SCHEMA_PATH.read_text()
        await db.executescript(schema)
        await db.commit()
    return db


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


async def insert_event(
    conn: aiosqlite.Connection,
    event_type: str,
    event_date: str,
    logged_at: str,
    data: Optional[dict],
    source: str,
    occurred_at: Optional[str] = None,
) -> None:
    """Insert an event row. Centralizes JSON serialization."""
    await conn.execute(
        "INSERT INTO events (event_type, event_date, logged_at, occurred_at, data, source) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            event_type,
            event_date,
            logged_at,
            occurred_at,
            json.dumps(data) if data is not None else None,
            source,
        ),
    )


async def get_latest_summary(conn: aiosqlite.Connection, event_date: str) -> dict | None:
    """Fetch latest daily_summary for a date, returns parsed dict or None."""
    rows = await conn.execute_fetchall(
        "SELECT data FROM events WHERE event_type = 'daily_summary' AND event_date = ? "
        "ORDER BY logged_at DESC LIMIT 1",
        (event_date,),
    )
    if rows and rows[0]["data"]:
        return json.loads(rows[0]["data"])
    return None


async def has_morning_gate(conn: aiosqlite.Connection, event_date: str) -> bool:
    """Check if sleep event with source='morning_gate' exists for date."""
    rows = await conn.execute_fetchall(
        "SELECT 1 FROM events WHERE event_type = 'sleep' AND event_date = ? "
        "AND source = 'morning_gate' LIMIT 1",
        (event_date,),
    )
    return bool(rows)


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

    else:
        return data_str


async def migrate_if_needed(conn: aiosqlite.Connection) -> None:
    """Auto-migrate from checkins table to events table if needed."""
    checkins_exists = bool(
        await conn.execute_fetchall(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='checkins'"
        )
    )
    if not checkins_exists:
        return  # nothing to migrate

    events_exists = bool(
        await conn.execute_fetchall(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='events'"
        )
    )

    if events_exists:
        # Check if events is empty (just created by get_db()) or populated (prior run)
        event_count_row = await conn.execute_fetchall("SELECT COUNT(*) as c FROM events")
        event_count = event_count_row[0]["c"] if event_count_row else 0
        if event_count > 0:
            # Migration was done but DROP failed, or schema was pre-created
            log.warning(
                "checkins exists alongside populated events table — dropping checkins"
            )
            await conn.execute("DROP TABLE checkins")
            await conn.commit()
            return
        # events is empty — fall through to run migration

    log.info("Starting migration from checkins to events table")

    rows = await conn.execute_fetchall(
        "SELECT * FROM checkins WHERE submitted_at IS NOT NULL "
        "ORDER BY date ASC, submission_number ASC"
    )

    for row in rows:
        event_date = row["date"]
        logged_at = row["submitted_at"]
        source = "morning_gate" if row["submission_number"] == 1 else "update"

        # sleep event (morning gate only)
        if row["submission_number"] == 1:
            sleep_data = {
                "shower_end": row["shower_end"],
                "no_shower": bool(row["no_shower"]),
                "fell_asleep": row["fell_asleep"],
                "sleep_end": row["sleep_end"],
                "no_sleep": bool(row["no_sleep"]),
                "nightmares": bool(row["nightmares"]),
                "melatonin": bool(row["melatonin"]),
            }
            await insert_event(conn, "sleep", event_date, logged_at, sleep_data, source)

        # mood / energy / anxiety
        for field in ("mood", "energy", "anxiety"):
            if row[field] is not None:
                await insert_event(conn, field, event_date, logged_at, {"value": row[field]}, source)

        # daily_summary
        counter_fields = [
            "coffee",
            "intrusive",
            "meals",
            "snacks",
            "exercise_minutes",
            "sunlight_minutes",
            "hours_worked",
        ]
        if any(row[f] is not None for f in counter_fields):
            summary_data = {f: (row[f] if row[f] is not None else 0) for f in counter_fields}
            await insert_event(conn, "daily_summary", event_date, logged_at, summary_data, source)

    await conn.commit()
    log.info("Migration complete: %d checkins rows converted", len(rows))

    await conn.execute("DROP TABLE checkins")
    await conn.commit()
    log.info("checkins table dropped")


@app.on_event("startup")
async def startup():
    conn = await get_db()
    await migrate_if_needed(conn)
    log.info("Daily checkin service started on port %d", PORT)


@app.on_event("shutdown")
async def shutdown():
    global db
    if db:
        await db.close()
        db = None


@app.get("/", response_class=HTMLResponse)
async def home():
    return HTMLResponse((STATIC_DIR / "home.html").read_text())


@app.get("/checkin", response_class=HTMLResponse)
async def checkin():
    conn = await get_db()
    today_date = get_event_date()
    yesterday_date = (date.fromisoformat(today_date) - timedelta(days=1)).isoformat()

    # Check if today's morning gate already completed
    if await has_morning_gate(conn, today_date):
        return RedirectResponse(url="/update", status_code=303)

    form_html = (STATIC_DIR / "form.html").read_text()

    # Autofill yesterday's counters from latest daily_summary
    summary = await get_latest_summary(conn, yesterday_date)
    if summary:
        # Autofill SUMMARY_COUNTER_FIELDS except coffee (not on form's yesterday section)
        yesterday_fields = [f for f in SUMMARY_COUNTER_FIELDS if f != "coffee"]
        for field in yesterday_fields:
            val = summary.get(field)
            if val is not None:
                form_html = form_html.replace(
                    f'id="yesterday_{field}"', f'id="yesterday_{field}" value="{val}"'
                )

    return HTMLResponse(content=form_html)


@app.post("/submit", response_class=HTMLResponse)
async def submit(
    request: Request,
    # Yesterday confirmation (required)
    yesterday_intrusive: int = Form(...),
    yesterday_meals: int = Form(...),
    yesterday_snacks: int = Form(...),
    yesterday_exercise_minutes: int = Form(...),
    yesterday_sunlight_minutes: int = Form(...),
    yesterday_hours_worked: float = Form(...),
    # Last night (sleep)
    shower_end: Optional[str] = Form(None),
    no_shower: Optional[int] = Form(None),
    fell_asleep: Optional[str] = Form(None),
    sleep_end: Optional[str] = Form(None),
    no_sleep: Optional[int] = Form(None),
    nightmares: int = Form(...),
    melatonin: int = Form(...),
    # Mental state (required)
    mood: int = Form(...),
    energy: int = Form(...),
    anxiety: int = Form(...),
    # Today so far (all optional)
    coffee: Optional[int] = Form(None),
    intrusive: Optional[int] = Form(None),
    meals: Optional[int] = Form(None),
    snacks: Optional[int] = Form(None),
    exercise_minutes: Optional[int] = Form(None),
    sunlight_minutes: Optional[int] = Form(None),
    hours_worked: Optional[float] = Form(None),
):
    # Server-side sleep validation
    if not shower_end and not no_shower:
        return HTMLResponse(
            content="<p style='color:red'>Either provide shower end time or check 'No shower'.</p>",
            status_code=400,
        )
    if (not fell_asleep or not sleep_end) and not no_sleep:
        return HTMLResponse(
            content="<p style='color:red'>Either provide both fell asleep and wake time, or check 'No sleep'.</p>",
            status_code=400,
        )

    conn = await get_db()
    today_date = get_event_date()
    yesterday_date = (date.fromisoformat(today_date) - timedelta(days=1)).isoformat()
    now = datetime.now().isoformat()
    device_ip = request.client.host if request.client else None

    # Counter validation for yesterday's confirmed values
    prev_yesterday_summary = await get_latest_summary(conn, yesterday_date)
    yesterday_confirmed = {
        "intrusive": yesterday_intrusive,
        "meals": yesterday_meals,
        "snacks": yesterday_snacks,
        "exercise_minutes": yesterday_exercise_minutes,
        "sunlight_minutes": yesterday_sunlight_minutes,
        "hours_worked": yesterday_hours_worked,
    }
    if prev_yesterday_summary:
        for field, new_val in yesterday_confirmed.items():
            existing = prev_yesterday_summary.get(field, 0)
            if existing is not None and new_val < existing:
                return HTMLResponse(
                    content=f"<p style='color:red'>Yesterday's {field} cannot decrease (current: {existing}, submitted: {new_val}).</p>",
                    status_code=400,
                )

    # Batch insert events
    # 1. sleep event for today
    sleep_data = {
        "shower_end": shower_end,
        "no_shower": bool(no_shower),
        "fell_asleep": fell_asleep,
        "sleep_end": sleep_end,
        "no_sleep": bool(no_sleep),
        "nightmares": bool(nightmares),
        "melatonin": bool(melatonin),
    }
    await insert_event(conn, "sleep", today_date, now, sleep_data, "morning_gate")

    # 2. mood, energy, anxiety events for today
    await insert_event(conn, "mood", today_date, now, {"value": mood}, "morning_gate")
    await insert_event(conn, "energy", today_date, now, {"value": energy}, "morning_gate")
    await insert_event(conn, "anxiety", today_date, now, {"value": anxiety}, "morning_gate")

    # 3. daily_summary for yesterday (required)
    # Carry forward coffee from previous summary (default 0)
    yesterday_coffee = (prev_yesterday_summary or {}).get("coffee", 0)
    yesterday_summary_data = {
        "meals": yesterday_meals,
        "snacks": yesterday_snacks,
        "coffee": yesterday_coffee,
        "intrusive": yesterday_intrusive,
        "exercise_minutes": yesterday_exercise_minutes,
        "sunlight_minutes": yesterday_sunlight_minutes,
        "hours_worked": yesterday_hours_worked,
    }
    await insert_event(conn, "daily_summary", yesterday_date, now, yesterday_summary_data, "morning_gate")

    # 4. daily_summary for today (optional, only if any counter is non-zero)
    today_counters = {
        "coffee": coffee,
        "intrusive": intrusive,
        "meals": meals,
        "snacks": snacks,
        "exercise_minutes": exercise_minutes,
        "sunlight_minutes": sunlight_minutes,
        "hours_worked": hours_worked,
    }
    if any(v is not None and v != 0 for v in today_counters.values()):
        today_summary_data = {
            k: (v if v is not None else 0) for k, v in today_counters.items()
        }
        await insert_event(conn, "daily_summary", today_date, now, today_summary_data, "morning_gate")

    await conn.commit()

    # Unblock all devices
    for ip in DEVICES:
        result = subprocess.run(
            ["sudo", IPSET_BIN, "add", "allowed_internet", ip, "-exist"],
            check=False,
            capture_output=True,
        )
        if result.returncode != 0:
            log.error("ipset add %s failed: %s", ip, result.stderr.decode())

    # Flush must_checkin ipset
    result = subprocess.run(
        ["sudo", IPSET_BIN, "flush", "must_checkin"],
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        log.error("ipset flush must_checkin failed: %s", result.stderr.decode())

    # Remove captive portal DNAT rule
    result = subprocess.run(
        [
            "sudo",
            IPTABLES_BIN,
            "-t",
            "nat",
            "-D",
            "PREROUTING",
            "-i",
            "wlan0",
            "-m",
            "set",
            "--match-set",
            "must_checkin",
            "src",
            "-p",
            "tcp",
            "--dport",
            "80",
            "-j",
            "DNAT",
            "--to-destination",
            f"192.168.22.1:{PORT}",
        ],
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        log.warning("iptables DNAT removal: %s", result.stderr.decode())

    return HTMLResponse(
        content=f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Checkin Complete</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
               max-width: 480px; margin: 40px auto; padding: 0 16px; text-align: center;
               background: #0d1117; color: #c9d1d9; }}
        .success {{ background: #0d2818; border: 1px solid #238636; border-radius: 8px;
                    padding: 24px; margin-top: 40px; }}
        h1 {{ color: #58a6ff; }}
        a {{ color: #58a6ff; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
        .update-link {{ display: block; margin-top: 16px; font-size: 0.95rem; }}
    </style>
</head>
<body>
    <div class="success">
        <h1>Checkin Complete</h1>
        <p>Submitted for <strong>{today_date}</strong>.</p>
        <p>All devices are unblocked. Internet restored.</p>
        <a href="/update" class="update-link">Submit another update later today →</a>
    </div>
</body>
</html>"""
    )


@app.get("/update", response_class=HTMLResponse)
async def update_form():
    form_html = (STATIC_DIR / "update.html").read_text()
    conn = await get_db()
    today_date = get_event_date()

    summary = await get_latest_summary(conn, today_date)
    if summary:
        for field in SUMMARY_COUNTER_FIELDS:
            val = summary.get(field)
            if val is not None:
                form_html = form_html.replace(
                    f'id="{field}"', f'id="{field}" value="{val}"'
                )

    return HTMLResponse(content=form_html)


@app.post("/update", response_class=HTMLResponse)
async def update_submit(
    request: Request,
    mood: Optional[int] = Form(None),
    energy: Optional[int] = Form(None),
    anxiety: Optional[int] = Form(None),
    coffee: Optional[int] = Form(None),
    intrusive: Optional[int] = Form(None),
    meals: Optional[int] = Form(None),
    snacks: Optional[int] = Form(None),
    exercise_minutes: Optional[int] = Form(None),
    sunlight_minutes: Optional[int] = Form(None),
    hours_worked: Optional[float] = Form(None),
):
    conn = await get_db()
    today_date = get_event_date()
    tomorrow_date = (date.fromisoformat(today_date) + timedelta(days=1)).isoformat()
    now = datetime.now().isoformat()

    # Lock check: reject if tomorrow has morning gate
    if await has_morning_gate(conn, tomorrow_date):
        return HTMLResponse(
            content="<p style='color:red'>Today's checkin is finalized. No further updates allowed.</p>",
            status_code=400,
        )

    # Counter validation
    current_summary = await get_latest_summary(conn, today_date)
    current = current_summary or {}
    submitted_counters = {
        "coffee": coffee,
        "intrusive": intrusive,
        "meals": meals,
        "snacks": snacks,
        "exercise_minutes": exercise_minutes,
        "sunlight_minutes": sunlight_minutes,
        "hours_worked": hours_worked,
    }

    # Layer 1: validate against latest daily_summary
    for field in SUMMARY_COUNTER_FIELDS:
        new_val = submitted_counters[field]
        if new_val is None:
            continue
        existing = current.get(field, 0)
        if new_val < existing:
            return HTMLResponse(
                content=f"<p style='color:red'>{field} cannot decrease (current: {existing}, submitted: {new_val}).</p>",
                status_code=400,
            )

    # Layer 2: validate against individual events (coffee and intrusive only)
    coffee_event_count_row = await conn.execute_fetchall(
        "SELECT COUNT(*) as c FROM events WHERE event_type = 'coffee' AND event_date = ?",
        (today_date,),
    )
    coffee_event_count = coffee_event_count_row[0]["c"] if coffee_event_count_row else 0
    if coffee is not None and coffee < coffee_event_count:
        return HTMLResponse(
            content=f"<p style='color:red'>Coffee count cannot be less than {coffee_event_count} individual logged events.</p>",
            status_code=400,
        )

    intrusive_event_count_row = await conn.execute_fetchall(
        "SELECT COUNT(*) as c FROM events WHERE event_type = 'intrusive' AND event_date = ?",
        (today_date,),
    )
    intrusive_event_count = (
        intrusive_event_count_row[0]["c"] if intrusive_event_count_row else 0
    )
    if intrusive is not None and intrusive < intrusive_event_count:
        return HTMLResponse(
            content=f"<p style='color:red'>Intrusive count cannot be less than {intrusive_event_count} individual logged events.</p>",
            status_code=400,
        )

    # Insert snapshot events (if provided)
    if mood is not None:
        await insert_event(conn, "mood", today_date, now, {"value": mood}, "update")
    if energy is not None:
        await insert_event(conn, "energy", today_date, now, {"value": energy}, "update")
    if anxiety is not None:
        await insert_event(conn, "anxiety", today_date, now, {"value": anxiety}, "update")

    # Insert daily_summary only if any counter changed
    any_changed = False
    new_summary_data = {}
    for field in SUMMARY_COUNTER_FIELDS:
        submitted = submitted_counters[field]
        current_val = current.get(field, 0)
        if submitted is not None:
            if submitted != current_val:
                any_changed = True
            new_summary_data[field] = submitted
        else:
            new_summary_data[field] = current_val

    if any_changed:
        await insert_event(conn, "daily_summary", today_date, now, new_summary_data, "update")

    await conn.commit()

    return HTMLResponse(
        content=f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Update Saved</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
               max-width: 480px; margin: 40px auto; padding: 0 16px; text-align: center;
               background: #0d1117; color: #c9d1d9; }}
        .success {{ background: #0d2818; border: 1px solid #238636; border-radius: 8px;
                    padding: 24px; margin-top: 40px; }}
        h1 {{ color: #58a6ff; }}
        a {{ color: #58a6ff; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
    </style>
</head>
<body>
    <div class="success">
        <h1>Update Saved</h1>
        <p>Submitted for <strong>{today_date}</strong>.</p>
        <a href="/update">Submit another update</a> · <a href="/history">View history</a>
    </div>
</body>
</html>"""
    )


@app.get("/history", response_class=HTMLResponse)
async def history():
    conn = await get_db()
    rows = await conn.execute_fetchall(
        "SELECT id, event_type, event_date, logged_at, occurred_at, data, source "
        "FROM events ORDER BY event_date DESC, logged_at DESC"
    )

    def fmt_time(logged_at: str) -> str:
        """Extract HH:MM from ISO 8601 timestamp."""
        if logged_at and len(logged_at) > 10:
            return logged_at[11:16]
        return logged_at or "—"

    def fmt_source(source: str) -> str:
        """Format source as short badge."""
        if source == "morning_gate":
            return "gate"
        elif source == "update":
            return "upd"
        elif source == "manual":
            return "man"
        return source or "—"

    table_rows = ""
    for row in rows:
        time_str = fmt_time(row["logged_at"])
        source_str = fmt_source(row["source"])
        details = format_event_details(row["event_type"], row["data"])
        table_rows += (
            f"<tr>"
            f'<td>{row["event_date"]}</td>'
            f'<td>{time_str}</td>'
            f"<td>{source_str}</td>"
            f'<td>{row["event_type"]}</td>'
            f"<td>{details}</td>"
            f"</tr>\n"
        )

    return HTMLResponse(
        content=f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Checkin History</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            padding: 16px;
            background: #0d1117; color: #c9d1d9;
        }}
        h1 {{ color: #58a6ff; margin-bottom: 20px; text-align: center; font-size: 1.5rem; }}
        .back-link {{ display: block; text-align: center; margin-bottom: 20px; color: #58a6ff;
                      text-decoration: none; font-size: 0.95rem; }}
        .back-link:hover {{ text-decoration: underline; }}
        .table-wrap {{ overflow-x: auto; border-radius: 8px; border: 1px solid #21262d; }}
        table {{ border-collapse: collapse; width: 100%; min-width: 600px; font-size: 0.85rem; }}
        thead tr {{ background: #161b22; }}
        th {{
            padding: 10px 12px; text-align: left; color: #8b949e;
            font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em;
            border-bottom: 1px solid #30363d; white-space: nowrap;
        }}
        td {{ padding: 9px 12px; border-bottom: 1px solid #21262d; }}
        tbody tr:last-child td {{ border-bottom: none; }}
        tbody tr:hover td {{ background: #161b22; }}
        tr.event-sleep td {{ background: #0d1d2d; }}
        tr.event-daily_summary td {{ background: #0d2d1d; }}
        .count {{ color: #8b949e; font-size: 0.85rem; text-align: center; margin-top: 12px; }}
    </style>
</head>
<body>
    <h1>Checkin History</h1>
    <a href="/" class="back-link">&larr; Back to home</a>
    <div class="table-wrap">
        <table>
            <thead>
                <tr>
                    <th>Date</th>
                    <th>Time</th>
                    <th>Source</th>
                    <th>Type</th>
                    <th>Details</th>
                </tr>
            </thead>
            <tbody>
{table_rows}            </tbody>
        </table>
    </div>
    <p class="count">{len(rows)} event{"s" if len(rows) != 1 else ""} total</p>
</body>
</html>"""
    )


@app.get("/status", response_class=JSONResponse)
async def status():
    conn = await get_db()
    today_date = get_event_date()
    today_submitted = await has_morning_gate(conn, today_date)
    blocked = False
    for ip in DEVICES:
        result = subprocess.run(
            ["sudo", IPSET_BIN, "test", "allowed_internet", ip],
            check=False,
            capture_output=True,
        )
        if result.returncode != 0:
            blocked = True
            break
    return {"blocked": blocked, "today_submitted": today_submitted}
