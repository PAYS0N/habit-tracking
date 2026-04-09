# Daily Checkin — Database

## Schema

Single table `events`. All facts are typed event rows with JSON data.

```sql
CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type  TEXT NOT NULL,   -- discriminator: 'sleep', 'mood', 'daily_summary', etc.
    event_date  TEXT NOT NULL,   -- YYYY-MM-DD logical date (5am boundary)
    logged_at   TEXT NOT NULL,   -- ISO 8601 wall-clock insert time
    occurred_at TEXT,            -- ISO 8601; set when event happened earlier than it was logged
    ended_at    TEXT,            -- ISO 8601; span events only (headache); updated in place
    data        TEXT,            -- JSON blob; NULL if event type has no fields
    source      TEXT NOT NULL    -- 'morning_gate', 'update', 'manual'
);
CREATE INDEX idx_events_type_date ON events (event_type, event_date);
CREATE INDEX idx_events_date ON events (event_date);
```

**Ground truth for daily counts**: latest `daily_summary` event per `event_date`. Individual events (coffee, intrusive, food) are sparse timing details that supplement totals.

## 5am Day Boundary

`get_event_date()` in `utils.py`: if `datetime.now().hour < 5`, return yesterday's date. Aligns with the block timer firing at 05:00. All routes call this function for `event_date` assignment.

## Source Values

| Value | Set by |
|---|---|
| `morning_gate` | POST /submit |
| `update` | POST /update |
| `manual` | POST /event/* endpoints |

## Key DB Functions (`database.py`)

| Function | Purpose |
|---|---|
| `get_db()` | Returns singleton `aiosqlite.Connection`; applies schema DDL on first connect |
| `close_db()` | Closes and nulls the connection (called at shutdown) |
| `insert_event()` | Inserts one event row; handles JSON serialization of `data` |
| `get_latest_summary()` | Returns parsed dict of latest `daily_summary` for a date, or None |
| `has_morning_gate()` | Bool: sleep event with source='morning_gate' exists for date |
| `migrate_if_needed()` | Detects old `checkins` table; migrates to events if needed, then drops it |

## Startup Migration

`migrate_if_needed()` runs at every startup. If the old `checkins` table is present alongside a populated `events` table, it drops `checkins`. If `events` is empty, it converts all `checkins` rows to events and drops the table. This was a one-time migration; on current deployments `checkins` should not exist.
