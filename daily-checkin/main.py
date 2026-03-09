import logging
import subprocess
from datetime import date, datetime, timedelta
from pathlib import Path

import aiosqlite
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse

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


async def get_db() -> aiosqlite.Connection:
    global db
    if db is None:
        db = await aiosqlite.connect(str(DB_PATH))
        db.row_factory = aiosqlite.Row
        schema = SCHEMA_PATH.read_text()
        await db.executescript(schema)
        await db.commit()
    return db


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
    form_html = (STATIC_DIR / "form.html").read_text()
    return HTMLResponse(content=form_html)


@app.post("/submit", response_class=HTMLResponse)
async def submit(
    request: Request,
    sleep_hours: float = Form(...),
    shower_end: str = Form(...),
    fell_asleep: str = Form(...),
    sleep_end: str = Form(...),
    nightmares: int = Form(...),
    mood: int = Form(...),
    energy: int = Form(...),
    anxiety: int = Form(...),
    coffee: int = Form(...),
    melatonin: int = Form(...),
    intrusive: int = Form(...),
    meals_yesterday: int = Form(...),
    snacks_yesterday: int = Form(...),
    exercise_minutes: int = Form(...),
    sunlight_minutes: int = Form(...),
    hours_worked: float = Form(...),
):
    conn = await get_db()
    today = date.today().isoformat()
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
                "INSERT OR IGNORE INTO checkins (date) VALUES (?)",
                (d.isoformat(),),
            )
            d += timedelta(days=1)

    # Insert today's row
    await conn.execute(
        """INSERT OR REPLACE INTO checkins
        (date, submitted_at, device_ip,
         sleep_hours, shower_end, fell_asleep, sleep_end, nightmares,
         mood, energy, anxiety,
         coffee, melatonin,
         intrusive, meals_yesterday, snacks_yesterday, exercise_minutes, sunlight_minutes, hours_worked)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            today, now, device_ip,
            sleep_hours, shower_end, fell_asleep, sleep_end, nightmares,
            mood, energy, anxiety,
            coffee, melatonin,
            intrusive, meals_yesterday, snacks_yesterday, exercise_minutes, sunlight_minutes, hours_worked,
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

    # Flush must_checkin ipset (stops DNAT rule from matching any device)
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
    </style>
</head>
<body>
    <div class="success">
        <h1>Checkin Complete</h1>
        <p>Submitted for <strong>{today}</strong>.</p>
        <p>All devices are unblocked. Internet restored.</p>
    </div>
</body>
</html>""")


@app.get("/status", response_class=JSONResponse)
async def status():
    conn = await get_db()
    today = date.today().isoformat()
    row = await conn.execute_fetchall(
        "SELECT submitted_at FROM checkins WHERE date = ?", (today,)
    )
    today_submitted = bool(row and row[0]["submitted_at"] is not None)
    # Check if any device is missing from ipset (i.e. blocked)
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
