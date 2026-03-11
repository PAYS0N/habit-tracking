# Daily Checkin — System Documentation

## Overview

A FastAPI service running on the Raspberry Pi router (kuudra) that serves a daily morning checkin form, enforces internet access blocks via ipset, and accumulates a longitudinal SQLite dataset for mood and lifestyle analysis. Uses an **event log architecture**: each observable fact (sleep, mood snapshot, daily counter summary) is a separate row in a single `events` table with typed JSON data. Supports multiple submissions per day: a morning gate form unblocks devices, and an update form allows further submissions throughout the day. A `must_checkin` ipset scopes the captive portal DNAT rule so only blocked devices are redirected; other devices on the network are unaffected.

**Status:** Deployed and operational on the Pi (event log architecture active).
**Port:** 8900
**Deployment path:** `/home/pays0n/Documents/Projects/habit-tracking/daily-checkin/`

## Repository Layout

```
daily-checkin/
├── main.py                       # FastAPI app: routes, event inserts, migration, counter validation, ipset/iptables calls
├── schema.sql                    # SQLite DDL for events table (applied at startup if DB absent)
├── static/
│   ├── form.html                 # Morning gate form (dark theme; unchanged field names)
│   ├── update.html               # Update form for later-in-day submissions (dark theme; unchanged field names)
│   └── home.html                 # Home page
├── block.sh                      # Block script: removes IPs, adds DNAT rule
├── checkin.service               # systemd unit for FastAPI backend
├── daily-checkin-block.service   # systemd oneshot for block script
├── daily-checkin-block.timer     # systemd timer (05:00 daily)
├── sudoers-daily-checkin         # sudoers rules (copied to /etc/sudoers.d/)
├── requirements.txt              # fastapi, uvicorn[standard], aiosqlite, python-multipart
└── checkin.db                    # SQLite database (created at runtime)
```

## Database Schema

Single table `events` with JSON `data` column. Each row represents one typed event (sleep, mood, anxiety, energy, daily_summary, coffee, intrusive, etc.). **Ground truth for daily totals is the `daily_summary` event** — the most recent per date. Individual events (coffee, intrusive) are sparse timing details that supplement the daily totals.

```sql
CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type  TEXT NOT NULL,       -- discriminator: 'sleep', 'mood', 'energy', 'anxiety', 'daily_summary', etc.
    event_date  TEXT NOT NULL,       -- YYYY-MM-DD (logical date; 5am boundary; see below)
    logged_at   TEXT NOT NULL,       -- ISO 8601 timestamp of insertion
    occurred_at TEXT,                -- ISO 8601 timestamp of when event happened (optional, for backdated events)
    ended_at    TEXT,                -- ISO 8601 timestamp of span end (for events like headache)
    data        TEXT,                -- JSON blob with type-specific fields; NULL if no data
    source      TEXT NOT NULL        -- 'morning_gate', 'update', 'manual'
);

CREATE INDEX idx_events_type_date ON events (event_type, event_date);
CREATE INDEX idx_events_date ON events (event_date);
```

### Event Types and Data Schemas

See [events.md](events.md) for the full event type catalog, field schemas, and design notes.

Summary of event types: `sleep`, `mood`, `energy`, `anxiety`, `daily_summary`, `coffee`, `food`, `headache`, `medicine`, `bowel`, `exercise`, `intrusive`, `sunlight`, `work`, `relax`.

**`sleep_hours`** is not stored — calculated at render time from `fell_asleep` and `sleep_end` (handling midnight crossover).

### 5am Day Boundary

The `event_date` field uses a **5am boundary**: if local time is before 05:00, events belong to yesterday's logical date. This aligns with the system block timer firing at 05:00 each morning. All date calculations in routes use `get_event_date()` helper to respect this boundary.

### Startup Migration

On first run with the new event log schema, if the old `checkins` table exists and `events` table is absent, the application automatically:
1. Creates the new `events` table and indexes
2. Reads all submitted rows from the old `checkins` table where `submitted_at IS NOT NULL`
3. Converts each row to one or more event records:
   - `sleep` event (if `submission_number=1`)
   - `mood`, `energy`, `anxiety` events (if non-NULL)
   - `daily_summary` event (if any counter field non-NULL; fills NULL fields with 0)
4. Sets `source = 'morning_gate'` for `submission_number=1` rows, `source = 'update'` for later submissions
5. Drops the old `checkins` table

This migration is **one-time, non-destructive** (reads only, then drops). All historical data is preserved as events.

## Form Data Model

### Morning Gate Form

Submitted to `POST /submit`, creates 5–6 events in a single batch transaction:

| Section | Fields | Event(s) Created | Validation |
|---|---|---|---|
| Confirm Yesterday | yesterday_intrusive, yesterday_meals, yesterday_snacks, yesterday_exercise_minutes, yesterday_sunlight_minutes, yesterday_hours_worked | `daily_summary` for yesterday | Each value >= corresponding field in yesterday's previous daily_summary (default 0 if none) |
| Last Night | shower_end, no_shower, fell_asleep, sleep_end, no_sleep, nightmares, melatonin | `sleep` for today | Either shower_end or no_shower=1; either both fell_asleep & sleep_end or no_sleep=1 |
| Mental State | mood, energy, anxiety (1–10) | `mood`, `energy`, `anxiety` events for today | All required |
| Today So Far | coffee, intrusive, meals, snacks, exercise_minutes, sunlight_minutes, hours_worked (all optional) | `daily_summary` for today (only if any field non-zero) | N/A (optional) |

**Note on yesterday's coffee**: The form does not collect `yesterday_coffee`. This field is carried forward from yesterday's previous `daily_summary` (defaults to 0) and inserted into yesterday's new daily_summary automatically.

### Update Form

Submitted to `POST /update`, creates 2–3 events:

| Section | Fields | Event(s) Created | Validation |
|---|---|---|---|
| Mental State | mood, energy, anxiety (all optional) | `mood`, `energy`, `anxiety` events if provided | None (optional) |
| Today So Far | coffee, intrusive, meals, snacks, exercise_minutes, sunlight_minutes, hours_worked (all optional, pre-filled) | `daily_summary` for today (only if any field differs from previous summary) | Each submitted value >= previous daily_summary value AND >= count/sum of individual events for that type (coffee: count, intrusive: count, hours_worked: sum of work event hours) |

**Lock check**: If tomorrow's `event_date` has a `sleep` event with `source='morning_gate'`, reject with 400 — today is finalized.

## API Endpoints

### `GET /`
Home page landing. Returns `static/home.html`. Dark theme, mobile-first. No database queries. Contains two sections:
- **Checkin**: "Submit Checkin" (→ `/checkin`) and "View History" (→ `/history`) buttons.
- **Quick Log**: 2×3 grid of compact buttons (Food, Coffee, Headache, Bowel, Work, Relax). Tapping a button expands an inline form below the grid; Coffee submits immediately via `fetch` with no form. Work and Relax forms include an optional mood snapshot (submitted as a separate `mood` event server-side). All forms submit via `POST /event/{type}` and return to home with a brief green "Logged!" banner that auto-fades after 3s.

### `GET /checkin`
Checks if today (per `get_event_date()` 5am boundary) already has a `sleep` event with `source='morning_gate'`. If yes, redirects to `GET /update` (status 303). Otherwise, serves `static/form.html`, queries yesterday's latest `daily_summary` event, and injects `value` attributes into the `yesterday_*` counter fields for autofill. All counter fields default to blank if no previous summary exists. No authentication.

### `POST /submit`
Morning gate form submission. Performs server-side sleep validation (shower/no_shower, sleep/no_sleep), then batch-inserts 5–6 events in a single transaction:
1. `sleep` event for today (with all sleep fields from form)
2. `mood` event for today
3. `energy` event for today
4. `anxiety` event for today
5. `daily_summary` event for yesterday (required; includes all 7 counter fields; coffee carried forward from yesterday's previous summary, default 0)
6. `daily_summary` event for today (optional, only if any "Today So Far" field is non-zero)

All events use `source='morning_gate'`.

Counter validation: confirmed yesterday values must each be >= corresponding field in yesterday's latest `daily_summary` (default 0 if none).

Then unblocks all devices (ipset add → flush must_checkin → remove DNAT rule).

### `GET /update`
Serves `static/update.html`. Queries today's latest `daily_summary` event and injects counter field values for pre-fill. Snapshot fields (mood/energy/anxiety) left blank. All fields optional.

### `POST /update`
1. **Lock check**: if tomorrow (per `get_event_date()`) has a `sleep` event with `source='morning_gate'`, reject with 400 ("Today's checkin is finalized").
2. **Counter validation** (two layers):
   - Each submitted counter >= corresponding field in today's latest `daily_summary` (default 0)
   - Coffee and intrusive submitted values >= count of individual `coffee`/`intrusive` events for today
3. Insert events based on what changed:
   - Insert `mood`, `energy`, `anxiety` events if provided (only if values are non-NULL)
   - Insert `daily_summary` event for today (only if any counter differs from previous summary; pre-fill missing submitted fields from current summary)

All new events use `source='update'`.

No firewall changes. Returns HTML confirmation.

### `GET /history`
All events from `events` table, ordered by `event_date DESC, logged_at DESC`. Table columns: Date | Time (HH:MM from logged_at) | Source (gate/upd/man) | Type (event_type) | Details (formatted data).

Details formatting per event type:
- `sleep`: "Wake HH:MM · 7.5h · Nightmares · Melatonin" (sleep_hours computed in Python)
- `mood`/`energy`/`anxiety`: just the value (e.g., "7")
- `daily_summary`: "Meals:3 Snacks:1 Coffee:2 Ex:45m Sun:30m Work:6h Int:0"
- `coffee`/`intrusive`: "—" (no data)
- `exercise`: "{type} {duration}m" if present
- `food`: "{name} · meal/snack · dairy?"

Dark theme with subtle row tinting (sleep rows slightly blue, daily_summary rows slightly green).

### `POST /event/food`
Logs a single food event. Fields: `name` (text, optional), `is_dairy` (0/1, optional), `is_full_meal` (0/1, optional, default 1). Creates a `food` event with `source='manual'`. Returns `{"ok": true}`.

### `POST /event/coffee`
Logs a single coffee event with no data fields. Creates a `coffee` event with `source='manual'`. Returns `{"ok": true}`.

### `POST /event/headache`
Logs a headache event and optionally a medicine event in a single transaction. Fields: `severity` (1–10, required), `started_at` (HH:MM time, optional — used as `occurred_at`), `medicine_taken` (0/1, optional), `medicine_name` (text), `medicine_time` (HH:MM time, optional — used as `occurred_at` for medicine). If `medicine_taken=1`, inserts a `medicine` event with `{name, reason: "headache"}` alongside the headache event. Both use `source='manual'`. Returns `{"ok": true}`.

### `POST /event/bowel`
Logs a bowel event. Field: `type` (required, `"diarrhea"` or `"constipation"`). Creates a `bowel` event with `source='manual'`. Returns `{"ok": true}` or 400 if type is invalid.

### `POST /event/work`
Logs a work session. Fields: `hours` (real, required), `mood` (1–10, optional). Creates a `work` event with `source='manual'`. If `mood` provided, also inserts a `mood` event (same timestamp, same source). Returns `{"ok": true}`.

### `POST /event/relax`
Logs a relax session. Fields: `hours` (real, required), `video_game` (0/1, optional, default false), `mood` (1–10, optional). Creates a `relax` event with `source='manual'`. If `mood` provided, also inserts a `mood` event. Returns `{"ok": true}`.

### `GET /status`
Returns JSON `{"blocked": true/false, "today_submitted": true/false}`. Checks `allowed_internet` ipset membership. `today_submitted` is true if a `sleep` event with `source='morning_gate'` exists for today's `event_date`.

## Form UI

Field names and form structure are **unchanged** from the checkins era. The POST handlers read the same form field names, but insert them into the new event log structure instead of flat checkins rows.

### Morning form (`static/form.html`)
Four sections in order:
1. **Confirm Yesterday** — required counter fields (`yesterday_intrusive`, `yesterday_meals`, `yesterday_snacks`, `yesterday_exercise_minutes`, `yesterday_sunlight_minutes`, `yesterday_hours_worked`), autofilled from yesterday's latest `daily_summary` event
2. **Last Night** — sleep fields with fallback checkboxes (`no_shower`, `no_sleep`), `nightmares`, `melatonin`
3. **Mental State** — `mood`, `energy`, `anxiety` (required, 1–10 scale)
4. **Today So Far** — all optional: `coffee`, `intrusive`, `meals`, `snacks`, `exercise_minutes`, `sunlight_minutes`, `hours_worked`

Confirmation page includes link to `/update`. Dark GitHub theme (`#0d1117` background, `#58a6ff` accent).

### Update form (`static/update.html`)
Two sections:
1. **Mental State** — `mood`, `energy`, `anxiety` (all optional, 1–10 scale)
2. **Today So Far** — `coffee`, `intrusive`, `meals`, `snacks`, `exercise_minutes`, `sunlight_minutes`, `hours_worked` (all optional; pre-filled from today's latest `daily_summary` event)

No sleep section. Submit button: "Save Update". Matches morning form dark theme. Includes "Back to home" link.

## Enforcement Mechanism

### Devices blocked

| Device | IP |
|---|---|
| payson_s25 | 192.168.22.75 |
| voidgloom | 192.168.22.50 |
| akura_malice | 192.168.22.52 |

To add a new device: add its IP to `DEVICES` in both `block.sh` and `main.py`.

### Daily block (systemd timer — 05:00 Pi local time)

`block.sh` runs as root via `daily-checkin-block.timer` at 05:00 daily:
1. Creates `must_checkin` ipset (hash:ip) if it doesn't exist.
2. For each device IP: removes from `allowed_internet`, adds to `must_checkin`.
3. Adds a single DNAT rule scoped to `must_checkin` set: redirects HTTP port 80 from matching source IPs to `192.168.22.1:8900`.

### Unblock on submit

On `POST /submit`, `main.py`:
1. Re-adds each device IP to `allowed_internet` via `sudo ipset add ... -exist`.
2. Flushes `must_checkin` ipset (DNAT rule immediately stops matching any device).
3. Deletes the DNAT rule from the nat PREROUTING chain.

All subprocess calls use `check=False, capture_output=True` and log stderr on failure without aborting the response.

### Captive Portal

DNAT rule matches only `must_checkin` source IPs on wlan0 port 80. HTTPS (443) is not redirected.

## Sudoers Configuration

File: `/etc/sudoers.d/daily-checkin` (mode 0440). Source in repo as `sudoers-daily-checkin`.

```
pays0n ALL=(root) NOPASSWD: /usr/sbin/ipset add allowed_internet * -exist
pays0n ALL=(root) NOPASSWD: /usr/sbin/ipset del allowed_internet *
pays0n ALL=(root) NOPASSWD: /usr/sbin/ipset test allowed_internet *
pays0n ALL=(root) NOPASSWD: /usr/sbin/ipset flush must_checkin
pays0n ALL=(root) NOPASSWD: /usr/sbin/iptables -t nat -D PREROUTING -i wlan0 -m set --match-set must_checkin src -p tcp --dport 80 -j DNAT --to-destination 192.168.22.1\:8900
```

## Systemd Units

**FastAPI backend** (`checkin.service`): runs as `pays0n`, uvicorn on `0.0.0.0:8900`, auto-restart on failure.
**Block script** (`daily-checkin-block.service`): oneshot, runs as root.
**Block timer** (`daily-checkin-block.timer`): `OnCalendar=*-*-* 05:00:00`, `Persistent=true`.

Port 8900 is open in iptables INPUT chain (persisted via `netfilter-persistent`).

## Known Limitations

- **Captive portal HTTPS:** DNAT only redirects HTTP (port 80). HTTPS-first sites require manual navigation to the form URL.
- **iptables persistence:** The DNAT rule and `must_checkin` ipset do not persist across Pi reboots. The block timer recreates them at the next 05:00.
- **No authentication:** Any device on the LAN can submit the form.
