import json
import logging
from typing import Optional

import aiosqlite

from config import DB_PATH, SCHEMA_PATH

log = logging.getLogger("daily-checkin")

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


async def close_db() -> None:
    global db
    if db:
        await db.close()
        db = None


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
            "coffee", "intrusive", "meals", "snacks",
            "exercise_minutes", "sunlight_minutes", "hours_worked",
        ]
        if any(row[f] is not None for f in counter_fields):
            summary_data = {f: (row[f] if row[f] is not None else 0) for f in counter_fields}
            await insert_event(conn, "daily_summary", event_date, logged_at, summary_data, source)

    await conn.commit()
    log.info("Migration complete: %d checkins rows converted", len(rows))

    await conn.execute("DROP TABLE checkins")
    await conn.commit()
    log.info("checkins table dropped")
