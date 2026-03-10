# Multiple Submissions — Design Specification

## Overview

Extends the daily checkin service to support multiple submissions per day. The morning gate form is unchanged in UX and firewall behavior. An additional update form allows filing further submissions throughout the day to add or increase counter fields and record fresh snapshot values. The morning form autofills counter fields from the previous day's last submission.

Existing DB can be wiped and recreated — no data worth preserving.

## Data Model

Drop the existing `checkins` table and recreate with multiple rows per date — one per submission. `submission_number` starts at 1 (morning gate form) and increments per submission within a day. Backfilled rows for missed dates remain as `submission_number=1` with all metric columns NULL.

```sql
CREATE TABLE IF NOT EXISTS checkins (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    date                TEXT NOT NULL,              -- YYYY-MM-DD (Pi local time)
    submission_number   INTEGER NOT NULL DEFAULT 1, -- 1 = morning gate; 2+ = updates
    submitted_at        TEXT,                       -- ISO 8601; NULL = backfilled
    device_ip           TEXT,                       -- NULL = backfilled

    -- Sleep (morning form only; NULL on update submissions)
    shower_end          TEXT,                       -- HH:MM or NULL
    no_shower           INTEGER,                    -- 0/1; required on morning form if shower_end NULL
    fell_asleep         TEXT,                       -- HH:MM or NULL
    sleep_end           TEXT,                       -- HH:MM (wake time) or NULL
    no_sleep            INTEGER,                    -- 0/1; required on morning form if fell_asleep/sleep_end NULL
    nightmares          INTEGER,                    -- 0/1; morning form only
    melatonin           INTEGER,                    -- 0/1; morning form only

    -- Snapshot fields (recorded fresh each submission; blank on next morning's form)
    mood                INTEGER,                    -- 1–10 or NULL
    energy              INTEGER,                    -- 1–10 or NULL
    anxiety             INTEGER,                    -- 1–10 or NULL

    -- Counter fields (can only increase per submission within a day;
    --                 autofilled on next morning's form from prev day's last submission;
    --                 locked after next morning's submission_number=1 is written)
    coffee              INTEGER,                    -- cumulative count (0, 1, 2…)
    intrusive           INTEGER,                    -- 0–5 cumulative (0=none, 5=severe/frequent)
    meals               INTEGER,
    snacks              INTEGER,
    exercise_minutes    INTEGER,                    -- intentional activity only
    sunlight_minutes    INTEGER,                    -- direct sun during daylight hours only
    hours_worked        REAL
);
```

**Removed field:** `sleep_hours` is no longer stored. It is calculated at query time as the difference between `fell_asleep` and `sleep_end` (handling midnight crossover).

**Renamed fields:** `meals_yesterday` → `meals`, `snacks_yesterday` → `snacks` (the "yesterday" framing is replaced by the counter model; the morning form's autofill provides the previous day's running total as the starting value).

## Field Categories

| Category | Fields | Morning Form | Update Form | Carry-forward |
|---|---|---|---|---|
| Morning-only | shower_end, no_shower, fell_asleep, sleep_end, no_sleep, nightmares, melatonin | Required (with fallback) | Absent | No |
| Snapshot | mood, energy, anxiety | Required | Optional | No (blank next morning) |
| Counter | coffee, intrusive, meals, snacks, exercise_minutes, sunlight_minutes, hours_worked | Required | Optional | Yes — autofilled from prev day's last submission |

## Submission Rules

### Morning form (submission_number = 1)
- Triggers internet unblock (unchanged).
- Counter fields pre-filled from previous day's last submission. User confirms or increases. Snapshot fields blank.
- Sleep section: `shower_end`, `fell_asleep`, `sleep_end` are optional inputs, but each group requires either a value or its fallback checkbox (`no_shower` / `no_sleep`).
- All snapshot fields required. All counter fields required.

### Update form (submission_number ≥ 2)
- No firewall changes.
- No fields are required — submit only what you want to record.
- **Counter validation:** Each submitted counter value must be ≥ the maximum of that field across all existing rows for today. Reject with HTTP 400 and a clear message if any counter would decrease.
- **Lock check:** If a `submission_number=1` row exists for tomorrow, today is finalized — reject with HTTP 400 ("Today's checkin is finalized. No further updates allowed.").
- Counter fields pre-filled from today's last submission. Snapshot fields blank.

### Backfill (unchanged)
On each `POST /submit` (morning form only), insert null rows for any gap between the most recent date in the DB and yesterday.

## New and Changed Endpoints

### `GET /update`
Serves `static/update.html`. Queries today's last submission to pre-populate counter fields. Snapshot fields blank.

### `POST /update`
Accepts update form data. Runs lock check → counter validation → inserts new row with `submission_number = MAX(today) + 1`. Returns HTML confirmation.

### Changes to `GET /`
Before serving the morning form, query yesterday's last submission and inject counter field values as HTML `value` attributes for autofill.

### Changes to `GET /history`
Each submission is its own table row (no collapsing). Columns include `sub#`. Backfilled rows dimmed as before. `sleep_hours` calculated from `fell_asleep`/`sleep_end` at render time.

## Form UI Changes

**Morning form:** Add `no_shower` and `no_sleep` fallback checkboxes alongside their respective time inputs. Make `shower_end`, `fell_asleep`, `sleep_end` non-required in HTML; validate server-side that either the value or its fallback is present. Counter fields show pre-filled values from yesterday.

**Update form (new — `static/update.html`):** Matches dark theme of morning form. Two sections: Mental State (mood, energy, anxiety — all optional), Today So Far (coffee, intrusive, meals, snacks, exercise_minutes, sunlight_minutes, hours_worked — pre-filled from today's last submission, all optional). No sleep section. Submit button: "Save Update".

**Morning form confirmation page:** Add a link to `/update` ("Submit another update later today").

## Open Questions (resolved)

- **Intrusive thoughts:** Counter (cumulative 0–5, can only increase within a day). ✓
- **Coffee:** Counter (cumulative cup count, can only increase). ✓
- **History:** Show each submission as a separate row. ✓
- **Finalization:** Locked when next morning's submission_number=1 row is written. ✓
- **Data loss:** DB can be wiped and recreated. ✓
