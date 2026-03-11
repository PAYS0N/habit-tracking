# Event Log Database Schema Plan

## Proposed Schema

```sql
CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type  TEXT NOT NULL,       -- see event type catalog below
    event_date  TEXT NOT NULL,       -- YYYY-MM-DD, logical date (5am boundary)
    logged_at   TEXT NOT NULL,       -- ISO 8601 timestamp of when this row was inserted
    occurred_at TEXT,                -- ISO 8601 timestamp of when event actually happened (for backdated events)
    ended_at    TEXT,                -- ISO 8601 timestamp; used by span events (headache)
    data        TEXT,                -- JSON blob with type-specific fields; NULL if event type has no fields
    source      TEXT NOT NULL        -- 'morning_gate', 'update', 'manual'
);

CREATE INDEX idx_events_type_date ON events (event_type, event_date);
CREATE INDEX idx_events_date ON events (event_date);
```

### Column semantics

| Column | Purpose |
|---|---|
| `event_type` | Discriminator. Determines which keys are expected in `data`. |
| `event_date` | Logical day this event belongs to. If local time < 05:00, this is yesterday's date. All daily queries group on this column. |
| `logged_at` | Wall-clock time the row was written. Always set by the server. |
| `occurred_at` | Optional. Set when the event happened at a different time than it was logged — e.g., "headache started at 14:00" entered at 16:00. NULL means `logged_at` is the occurrence time. |
| `ended_at` | Optional. For span events only. Updated in place when the span is closed (e.g., headache ended). |
| `data` | JSON string. Schema-per-event-type; see catalog below. NULL for event types with no fields (e.g., a bare `coffee` event). |
| `source` | How this event was created. `morning_gate` = morning form submission, `update` = update form submission, `manual` = individual event logged outside a form. |

### Design decisions

**Headache end time — update in place.** When closing an open headache, the application UPDATEs the existing row to set `ended_at`. No linked end event. Rationale: simpler queries, no joins needed to determine headache duration. There is no audit trail requirement.

**Medicine — standalone event type.** Medicine can be taken for headaches, anxiety, sleep, or other reasons. Storing it as a property of headache would force a headache to exist. Temporal proximity provides correlation when needed.

**Coffee — individual timestamped events.** Each coffee is a separate event with a timestamp. Daily count derived from individual events or overridden by the daily summary total (summary is ground truth). Timing data enables sleep-quality correlation analysis.

**Intrusive thoughts — individual timestamped events.** Same model as coffee. Each episode is logged when it happens. Time-of-day patterns are relevant for PTSD tracking. Daily summary total is ground truth for count.

**Headache severity — 1–10 scale.** Consistent with mood, energy, and anxiety scales.

**Daily summary as ground truth for counts.** Individual events (coffee, food, etc.) are sparse by design — not every occurrence is logged in real time. The `daily_summary` event stores reconciled totals and is the authoritative count. Individual events provide optional timing detail.

**Single table, JSON data column.** Adding a new event type means defining its JSON keys and inserting rows — no ALTER TABLE, no new tables. Analysis in Python uses `json.loads()` on the `data` column.

## Event Type Catalog

### sleep (morning gate, required, one per day)

Logged once per day at morning checkin. Complex multi-field event.

| JSON key | Type | Required | Description |
|---|---|---|---|
| `shower_end` | string (HH:MM) or null | conditional | Time shower ended; null if `no_shower` is true |
| `no_shower` | boolean | conditional | True if no shower taken; required if `shower_end` is null |
| `fell_asleep` | string (HH:MM) or null | conditional | Time fell asleep; null if `no_sleep` is true |
| `sleep_end` | string (HH:MM) or null | conditional | Wake time; null if `no_sleep` is true |
| `no_sleep` | boolean | conditional | True if didn't sleep; required if `fell_asleep`/`sleep_end` are null |
| `nightmares` | boolean | yes | Whether nightmares occurred |
| `melatonin` | boolean | yes | Whether melatonin was taken last night |

Sleep hours derived at query time: `sleep_end - fell_asleep` (handling midnight crossover). Not stored.

### mood (morning gate required, update optional, repeatable)

Point-in-time snapshot. Can appear multiple times per day.

| JSON key | Type | Required | Description |
|---|---|---|---|
| `value` | integer 1–10 | yes | Current mood level |

### energy (morning gate required, update optional, repeatable)

| JSON key | Type | Required | Description |
|---|---|---|---|
| `value` | integer 1–10 | yes | Current energy level |

### anxiety (morning gate required, update optional, repeatable)

| JSON key | Type | Required | Description |
|---|---|---|---|
| `value` | integer 1–10 | yes | Current anxiety level |

### daily_summary (morning gate + update form, repeatable)

Reconciled totals for a day. Multiple summaries per day are valid (one per form submission). The latest summary for a given `event_date` is the authoritative count. Counter validation: each field must be >= the same field in the previous summary for that date.

Created at morning gate for both yesterday (required) and today (optional). Created at update form for today (optional).

| JSON key | Type | Required | Description |
|---|---|---|---|
| `meals` | integer | yes | Total meals for the day |
| `snacks` | integer | yes | Total snacks for the day |
| `coffee` | integer | yes | Total coffees for the day |
| `intrusive` | integer | yes | Total intrusive thought episodes |
| `exercise_minutes` | integer | yes | Total exercise minutes |
| `sunlight_minutes` | integer | yes | Total sunlight minutes |
| `hours_worked` | real | yes | Total hours worked |

"Required" means all fields must be present when the event is written. On the morning gate, yesterday's summary has all fields required (form enforces it). On update forms, the summary is only written if the user changes any counter value — but if written, all fields are included (pre-filled from previous values).

### food (optional, sparse)

Individual meal or snack event. Logged manually throughout the day. Does not need to account for every meal — the daily summary total is ground truth.

| JSON key | Type | Required | Description |
|---|---|---|---|
| `name` | string | no | What was eaten |
| `is_dairy` | boolean | no | Contains dairy (inflammation/sleep correlation) |
| `is_full_meal` | boolean | no | True = meal, false = snack |

### headache (optional, span event)

Has a start and optional end. `ended_at` column updated in place when the headache ends.

| JSON key | Type | Required | Description |
|---|---|---|---|
| `severity` | integer 1–10 | yes | Pain level at onset |

`occurred_at` = headache start time (may differ from `logged_at` if backdated). `ended_at` = headache end time (NULL if still active, updated in place when closed).

### medicine (optional, standalone)

| JSON key | Type | Required | Description |
|---|---|---|---|
| `name` | string | yes | Medicine name (e.g., "ibuprofen", "melatonin") |
| `reason` | string | no | Why it was taken (e.g., "headache", "anxiety") |

### coffee (optional, individual)

No data fields. The event's existence is the data point. `logged_at` or `occurred_at` captures timing.

`data`: NULL

### exercise (optional, individual)

| JSON key | Type | Required | Description |
|---|---|---|---|
| `type` | string | no | Exercise type (e.g., "walk", "gym", "bike") |
| `duration_minutes` | integer | no | Duration in minutes |

### intrusive (optional, individual)

Individual intrusive thought episode. No data fields needed — existence and timestamp are the data.

`data`: NULL

### sunlight (optional, individual)

| JSON key | Type | Required | Description |
|---|---|---|---|
| `duration_minutes` | integer | no | Minutes of sunlight exposure |

### work (optional, individual)

| JSON key | Type | Required | Description |
|---|---|---|---|
| `hours` | real | no | Duration of work session |

## Morning Gate Interaction

### Events created on morning submission

A single morning gate submission inserts the following events, all with `source = 'morning_gate'`:

1. **sleep** event — `event_date` = today. Data from the "Last Night" form section.
2. **mood** event — `event_date` = today. Required.
3. **energy** event — `event_date` = today. Required.
4. **anxiety** event — `event_date` = today. Required.
5. **daily_summary** event — `event_date` = yesterday. Required, all counter fields filled. This is the "Confirm Yesterday" section.
6. **daily_summary** event — `event_date` = today. Optional, only written if any counter field is non-zero. This is the "Today So Far" section.

After all inserts, the application unblocks devices (ipset add → flush must_checkin → remove DNAT rule).

### Autofill for yesterday's counters

Query: latest `daily_summary` event for yesterday's `event_date`, ordered by `logged_at DESC`, limit 1. Extract each JSON field and pre-fill the form. If no summary exists for yesterday (missed day or no updates), all fields default to 0.

```sql
SELECT data FROM events
WHERE event_type = 'daily_summary' AND event_date = :yesterday
ORDER BY logged_at DESC LIMIT 1;
```

### Has today's gate been completed?

Replaces the old `submission_number = 1` check:

```sql
SELECT 1 FROM events
WHERE event_type = 'sleep' AND event_date = :today AND source = 'morning_gate'
LIMIT 1;
```

If a row exists, redirect to the update form.

### 5am day boundary

The application determines `event_date` using Pi local time:

```python
from datetime import datetime, timedelta, date

def get_event_date() -> str:
    now = datetime.now()
    if now.hour < 5:
        return (date.today() - timedelta(days=1)).isoformat()
    return date.today().isoformat()
```

This means:
- A morning gate submission at 06:00 on March 12 → `event_date = 2026-03-12` for today's events, `2026-03-11` for yesterday's summary.
- A coffee logged at 02:00 on March 12 → `event_date = 2026-03-11`.
- The 05:00 block trigger and the day boundary are aligned — the block fires at 05:00, which is the start of the new logical day.

### Update form interaction

`GET /update` pre-fills counters from the latest `daily_summary` for today. Snapshot fields (mood/energy/anxiety) are blank.

`POST /update` inserts:
- **mood**, **energy**, **anxiety** events — only if values were provided.
- **daily_summary** event for today — only if any counter field changed. Counter validation: each field >= corresponding field in today's latest summary.

Lock check: if tomorrow's morning gate has been completed (a `sleep` event with `source = 'morning_gate'` exists for tomorrow's `event_date`), reject the update — today is finalized.

## Migration Path

The existing `checkins` table data can be dropped. Migration is a clean cutover:

1. Stop the FastAPI service: `sudo systemctl stop checkin.service`
2. Back up the existing DB (optional, for reference): `cp checkin.db checkin.db.bak`
3. Delete or rename the existing DB: `rm checkin.db`
4. Deploy the new `schema.sql` containing the `CREATE TABLE events` and index statements.
5. The application creates the DB on startup (same pattern as today — apply DDL if DB absent).
6. Restart the service: `sudo systemctl start checkin.service`
7. On first morning gate after restart, yesterday's summary will have all-zero autofill (no prior data). This is expected and correct.

No data migration scripts needed. The old `checkins` table schema and all counter validation logic are removed from `main.py`.

## Query Examples

### What was my last mood today?

```sql
SELECT json_extract(data, '$.value') AS mood, logged_at
FROM events
WHERE event_type = 'mood' AND event_date = :today
ORDER BY logged_at DESC
LIMIT 1;
```

### How many meals did I log on 2026-03-10?

Ground truth from the daily summary (accounts for unlogged meals):

```sql
SELECT json_extract(data, '$.meals') AS meals
FROM events
WHERE event_type = 'daily_summary' AND event_date = '2026-03-10'
ORDER BY logged_at DESC
LIMIT 1;
```

### Average sleep hours for the last 30 days

```sql
SELECT AVG(
    CASE
        WHEN json_extract(data, '$.no_sleep') = 1 THEN 0
        ELSE (
            (CAST(substr(json_extract(data, '$.sleep_end'), 1, 2) AS REAL) * 60
             + CAST(substr(json_extract(data, '$.sleep_end'), 4, 2) AS REAL)
             + CASE WHEN json_extract(data, '$.sleep_end') < json_extract(data, '$.fell_asleep')
                    THEN 1440 ELSE 0 END)
            -
            (CAST(substr(json_extract(data, '$.fell_asleep'), 1, 2) AS REAL) * 60
             + CAST(substr(json_extract(data, '$.fell_asleep'), 4, 2) AS REAL))
        ) / 60.0
    END
) AS avg_sleep_hours
FROM events
WHERE event_type = 'sleep'
  AND event_date >= date(:today, '-30 days')
  AND json_extract(data, '$.fell_asleep') IS NOT NULL;
```

Note: this is complex in raw SQL. In practice, analysis scripts will compute this in Python after `json.loads()` on each row's data, which is cleaner:

```python
rows = db.execute("SELECT data FROM events WHERE event_type = 'sleep' AND event_date >= date(?, '-30 days')", [today])
hours = [calc_sleep_hours(json.loads(row["data"])) for row in rows]
avg = sum(hours) / len(hours)
```

### All open headaches (started but not ended)

```sql
SELECT id, event_date, occurred_at, logged_at, json_extract(data, '$.severity') AS severity
FROM events
WHERE event_type = 'headache' AND ended_at IS NULL
ORDER BY logged_at DESC;
```

### Days where anxiety was above 7

```sql
SELECT DISTINCT event_date
FROM events
WHERE event_type = 'anxiety' AND json_extract(data, '$.value') > 7
ORDER BY event_date DESC;
```
