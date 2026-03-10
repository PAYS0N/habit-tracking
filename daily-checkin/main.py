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

COUNTER_FIELDS = [
    "coffee", "intrusive", "meals", "snacks",
    "exercise_minutes", "sunlight_minutes", "hours_worked",
]

# Counter fields that appear on the "Confirm Yesterday" section of the morning form
YESTERDAY_COUNTER_FIELDS = [
    "intrusive", "meals", "snacks",
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


@app.on_event("startup")
async def startup():
    await get_db()
    log.info("Daily checkin service started on port %d", PORT)


@app.on_event("shutdown")
async def shutdown():
    global db
    if db:
        await db.close()
        db = None


@app.get("/", response_class=HTMLResponse)
async def index():
    conn = await get_db()
    today = date.today().isoformat()

    # Check if today already has submission_number=1 with submitted_at IS NOT NULL
    today_submitted = await conn.execute_fetchall(
        "SELECT id FROM checkins WHERE date = ? AND submission_number = 1 AND submitted_at IS NOT NULL",
        (today,),
    )
    if today_submitted:
        return RedirectResponse(url="/update", status_code=303)

    form_html = (STATIC_DIR / "form.html").read_text()
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    rows = await conn.execute_fetchall(
        "SELECT * FROM checkins WHERE date = ? ORDER BY submission_number DESC LIMIT 1",
        (yesterday,),
    )
    if rows:
        row = rows[0]
        # Autofill only the "Confirm Yesterday" fields (yesterday_ prefixed ids)
        for field in YESTERDAY_COUNTER_FIELDS:
            val = row[field]
            if val is not None:
                form_html = form_html.replace(
                    f'id="yesterday_{field}"',
                    f'id="yesterday_{field}" value="{val}"',
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
    today = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    now = datetime.now().isoformat()
    device_ip = request.client.host if request.client else None

    # Backfill gaps
    row = await conn.execute_fetchall(
        "SELECT date FROM checkins ORDER BY date DESC LIMIT 1"
    )
    if row:
        last_date = date.fromisoformat(row[0]["date"])
        gap_start = last_date + timedelta(days=1)
        gap_end = date.today() - timedelta(days=1)
        d = gap_start
        while d <= gap_end:
            await conn.execute(
                "INSERT INTO checkins (date, submission_number) VALUES (?, 1)",
                (d.isoformat(),),
            )
            d += timedelta(days=1)

    # Counter validation for yesterday's confirmed values
    yesterday_confirmed = {
        "intrusive": yesterday_intrusive, "meals": yesterday_meals,
        "snacks": yesterday_snacks, "exercise_minutes": yesterday_exercise_minutes,
        "sunlight_minutes": yesterday_sunlight_minutes, "hours_worked": yesterday_hours_worked,
    }
    yesterday_rows = await conn.execute_fetchall(
        "SELECT * FROM checkins WHERE date = ? ORDER BY submission_number DESC",
        (yesterday,),
    )
    if yesterday_rows:
        for field, new_val in yesterday_confirmed.items():
            max_val = max(
                (r[field] for r in yesterday_rows if r[field] is not None),
                default=None,
            )
            if max_val is not None and new_val < max_val:
                return HTMLResponse(
                    content=f"<p style='color:red'>Yesterday's {field} cannot decrease (current: {max_val}, submitted: {new_val}).</p>",
                    status_code=400,
                )

    # Insert yesterday's retroactive row (sub#N+1)
    yesterday_max_sub = await conn.execute_fetchall(
        "SELECT MAX(submission_number) as max_sub FROM checkins WHERE date = ?",
        (yesterday,),
    )
    yesterday_next_sub = (yesterday_max_sub[0]["max_sub"] or 0) + 1

    await conn.execute(
        """INSERT INTO checkins
        (date, submission_number, submitted_at, device_ip,
         intrusive, meals, snacks, exercise_minutes, sunlight_minutes, hours_worked)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            yesterday, yesterday_next_sub, now, device_ip,
            yesterday_intrusive, yesterday_meals, yesterday_snacks,
            yesterday_exercise_minutes, yesterday_sunlight_minutes, yesterday_hours_worked,
        ),
    )

    # Insert today's submission_number=1 row
    await conn.execute(
        """INSERT INTO checkins
        (date, submission_number, submitted_at, device_ip,
         shower_end, no_shower, fell_asleep, sleep_end, no_sleep, nightmares, melatonin,
         mood, energy, anxiety,
         coffee, intrusive, meals, snacks, exercise_minutes, sunlight_minutes, hours_worked)
        VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            today, now, device_ip,
            shower_end or None, 1 if no_shower else 0,
            fell_asleep or None, sleep_end or None, 1 if no_sleep else 0,
            nightmares, melatonin,
            mood, energy, anxiety,
            coffee, intrusive, meals, snacks, exercise_minutes, sunlight_minutes, hours_worked,
        ),
    )
    await conn.commit()

    # Unblock all devices
    for ip in DEVICES:
        result = subprocess.run(
            ["sudo", IPSET_BIN, "add", "allowed_internet", ip, "-exist"],
            check=False, capture_output=True,
        )
        if result.returncode != 0:
            log.error("ipset add %s failed: %s", ip, result.stderr.decode())

    # Flush must_checkin ipset
    result = subprocess.run(
        ["sudo", IPSET_BIN, "flush", "must_checkin"],
        check=False, capture_output=True,
    )
    if result.returncode != 0:
        log.error("ipset flush must_checkin failed: %s", result.stderr.decode())

    # Remove captive portal DNAT rule
    result = subprocess.run(
        [
            "sudo", IPTABLES_BIN, "-t", "nat", "-D", "PREROUTING",
            "-i", "wlan0", "-m", "set", "--match-set", "must_checkin", "src",
            "-p", "tcp", "--dport", "80",
            "-j", "DNAT", "--to-destination", f"192.168.22.1:{PORT}",
        ],
        check=False, capture_output=True,
    )
    if result.returncode != 0:
        log.warning("iptables DNAT removal: %s", result.stderr.decode())

    return HTMLResponse(content=f"""<!DOCTYPE html>
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
        <p>Submitted for <strong>{today}</strong>.</p>
        <p>All devices are unblocked. Internet restored.</p>
        <a href="/update" class="update-link">Submit another update later today →</a>
    </div>
</body>
</html>""")


@app.get("/update", response_class=HTMLResponse)
async def update_form():
    form_html = (STATIC_DIR / "update.html").read_text()
    conn = await get_db()
    today = date.today().isoformat()
    rows = await conn.execute_fetchall(
        "SELECT * FROM checkins WHERE date = ? ORDER BY submission_number DESC LIMIT 1",
        (today,),
    )
    if rows:
        row = rows[0]
        for field in COUNTER_FIELDS:
            val = row[field]
            if val is not None:
                form_html = form_html.replace(
                    f'id="{field}"',
                    f'id="{field}" value="{val}"',
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
    today = date.today().isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    now = datetime.now().isoformat()
    device_ip = request.client.host if request.client else None

    # Lock check: reject if tomorrow has a submission_number=1 row
    lock_row = await conn.execute_fetchall(
        "SELECT id FROM checkins WHERE date = ? AND submission_number = 1 AND submitted_at IS NOT NULL",
        (tomorrow,),
    )
    if lock_row:
        return HTMLResponse(
            content="<p style='color:red'>Today's checkin is finalized. No further updates allowed.</p>",
            status_code=400,
        )

    # Counter validation: each submitted counter must be >= current day's max
    today_rows = await conn.execute_fetchall(
        "SELECT * FROM checkins WHERE date = ? ORDER BY submission_number DESC",
        (today,),
    )
    submitted_counters = {
        "coffee": coffee, "intrusive": intrusive, "meals": meals,
        "snacks": snacks, "exercise_minutes": exercise_minutes,
        "sunlight_minutes": sunlight_minutes, "hours_worked": hours_worked,
    }
    if today_rows:
        for field in COUNTER_FIELDS:
            new_val = submitted_counters[field]
            if new_val is None:
                continue
            max_val = max(
                (r[field] for r in today_rows if r[field] is not None),
                default=None,
            )
            if max_val is not None and new_val < max_val:
                return HTMLResponse(
                    content=f"<p style='color:red'>{field} cannot decrease (current: {max_val}, submitted: {new_val}).</p>",
                    status_code=400,
                )

    # Determine next submission number
    max_sub_row = await conn.execute_fetchall(
        "SELECT MAX(submission_number) as max_sub FROM checkins WHERE date = ?",
        (today,),
    )
    next_sub = (max_sub_row[0]["max_sub"] or 0) + 1

    await conn.execute(
        """INSERT INTO checkins
        (date, submission_number, submitted_at, device_ip,
         mood, energy, anxiety,
         coffee, intrusive, meals, snacks, exercise_minutes, sunlight_minutes, hours_worked)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            today, next_sub, now, device_ip,
            mood, energy, anxiety,
            coffee, intrusive, meals, snacks, exercise_minutes, sunlight_minutes, hours_worked,
        ),
    )
    await conn.commit()

    return HTMLResponse(content=f"""<!DOCTYPE html>
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
        <p>Submission #{next_sub} for <strong>{today}</strong>.</p>
        <a href="/update">Submit another update</a> · <a href="/history">View history</a>
    </div>
</body>
</html>""")


@app.get("/history", response_class=HTMLResponse)
async def history():
    conn = await get_db()
    rows = await conn.execute_fetchall(
        "SELECT * FROM checkins ORDER BY date DESC, submission_number DESC"
    )

    def fmt(val):
        return "—" if val is None else str(val)

    def fmt_bool(val):
        if val is None:
            return "—"
        return "Yes" if val == 1 else "No"

    def fmt_submitted(val):
        if val is None:
            return "—"
        return val[11:16] if len(val) > 10 else val

    table_rows = ""
    for row in rows:
        backfilled = row["submitted_at"] is None
        row_class = ' class="backfilled"' if backfilled else ""
        sleep_h = calc_sleep_hours(row["fell_asleep"], row["sleep_end"])
        table_rows += (
            f'<tr{row_class}>'
            f'<td>{row["date"]}</td>'
            f'<td>{row["submission_number"]}</td>'
            f'<td>{fmt_submitted(row["submitted_at"])}</td>'
            f'<td>{fmt(row["mood"])}</td>'
            f'<td>{fmt(row["energy"])}</td>'
            f'<td>{fmt(row["anxiety"])}</td>'
            f'<td>{sleep_h}</td>'
            f'<td>{fmt(row["sleep_end"])}</td>'
            f'<td>{fmt_bool(row["nightmares"])}</td>'
            f'<td>{fmt(row["coffee"])}</td>'
            f'<td>{fmt_bool(row["melatonin"])}</td>'
            f'<td>{fmt(row["intrusive"])}</td>'
            f'<td>{fmt(row["exercise_minutes"])}</td>'
            f'<td>{fmt(row["sunlight_minutes"])}</td>'
            f'<td>{fmt(row["hours_worked"])}</td>'
            f'<td>{fmt(row["meals"])}</td>'
            f'<td>{fmt(row["snacks"])}</td>'
            f'</tr>\n'
        )

    return HTMLResponse(content=f"""<!DOCTYPE html>
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
        table {{ border-collapse: collapse; width: 100%; min-width: 950px; font-size: 0.85rem; }}
        thead tr {{ background: #161b22; }}
        th {{
            padding: 10px 12px; text-align: left; color: #8b949e;
            font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em;
            border-bottom: 1px solid #30363d; white-space: nowrap;
        }}
        td {{ padding: 9px 12px; border-bottom: 1px solid #21262d; white-space: nowrap; }}
        tbody tr:last-child td {{ border-bottom: none; }}
        tbody tr:hover td {{ background: #161b22; }}
        tr.backfilled td {{ color: #484f58; }}
        .count {{ color: #8b949e; font-size: 0.85rem; text-align: center; margin-top: 12px; }}
    </style>
</head>
<body>
    <h1>Checkin History</h1>
    <a href="/" class="back-link">&larr; Back to checkin form</a>
    <div class="table-wrap">
        <table>
            <thead>
                <tr>
                    <th>Date</th>
                    <th>Sub#</th>
                    <th>Time</th>
                    <th>Mood</th>
                    <th>Energy</th>
                    <th>Anxiety</th>
                    <th>Sleep h</th>
                    <th>Wake</th>
                    <th>Nightmares</th>
                    <th>Coffee</th>
                    <th>Melatonin</th>
                    <th>Intrusive</th>
                    <th>Exercise min</th>
                    <th>Sunlight min</th>
                    <th>Hrs worked</th>
                    <th>Meals</th>
                    <th>Snacks</th>
                </tr>
            </thead>
            <tbody>
{table_rows}            </tbody>
        </table>
    </div>
    <p class="count">{len(rows)} record{"s" if len(rows) != 1 else ""} total &mdash; dimmed rows are backfilled (no submission)</p>
</body>
</html>""")


@app.get("/status", response_class=JSONResponse)
async def status():
    conn = await get_db()
    today = date.today().isoformat()
    row = await conn.execute_fetchall(
        "SELECT submitted_at FROM checkins WHERE date = ? AND submission_number = 1",
        (today,),
    )
    today_submitted = bool(row and row[0]["submitted_at"] is not None)
    blocked = False
    for ip in DEVICES:
        result = subprocess.run(
            ["sudo", IPSET_BIN, "test", "allowed_internet", ip],
            check=False, capture_output=True,
        )
        if result.returncode != 0:
            blocked = True
            break
    return {"blocked": blocked, "today_submitted": today_submitted}
