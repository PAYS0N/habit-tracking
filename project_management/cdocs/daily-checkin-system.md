# Daily Checkin — System Documentation

## Overview

A FastAPI service running on the Raspberry Pi router (kuudra) that serves a daily morning checkin form, enforces internet access blocks via ipset, and accumulates a longitudinal SQLite dataset for mood and lifestyle analysis. Supports multiple submissions per day: a morning gate form (submission_number=1) unblocks devices, and an update form allows further submissions throughout the day. A `must_checkin` ipset scopes the captive portal DNAT rule so only blocked devices are redirected; other devices on the network are unaffected.

**Status:** Deployed and operational on the Pi.
**Port:** 8900
**Deployment path:** `/home/pays0n/Documents/Projects/habit-tracking/daily-checkin/`

## Repository Layout

```
daily-checkin/
├── main.py                       # FastAPI app: routes, DB init, backfill, counter validation, ipset/iptables calls
├── schema.sql                    # SQLite DDL (applied at startup if DB absent)
├── static/
│   ├── form.html                 # Morning gate form (dark theme)
│   └── update.html               # Update form for later-in-day submissions (dark theme)
├── block.sh                      # Block script: removes IPs, adds DNAT rule
├── checkin.service               # systemd unit for FastAPI backend
├── daily-checkin-block.service   # systemd oneshot for block script
├── daily-checkin-block.timer     # systemd timer (05:00 daily)
├── sudoers-daily-checkin         # sudoers rules (copied to /etc/sudoers.d/)
├── requirements.txt              # fastapi, uvicorn[standard], aiosqlite, python-multipart
└── checkin.db                    # SQLite database (created at runtime)
```

## Database Schema

Single table `checkins`. Multiple rows per calendar date — one per submission. `submission_number` starts at 1 (morning gate) and increments. Backfilled rows for missed dates have `submission_number=1` with all metric columns NULL.

```sql
CREATE TABLE IF NOT EXISTS checkins (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    date                TEXT NOT NULL,              -- YYYY-MM-DD (Pi local time)
    submission_number   INTEGER NOT NULL DEFAULT 1, -- 1 = morning gate; 2+ = updates
    submitted_at        TEXT,                       -- ISO 8601; NULL = backfilled
    device_ip           TEXT,                       -- NULL = backfilled

    -- Sleep (morning form only; NULL on update submissions)
    shower_end          TEXT,                       -- HH:MM or NULL
    no_shower           INTEGER,                    -- 0/1; fallback if shower_end NULL
    fell_asleep         TEXT,                       -- HH:MM or NULL
    sleep_end           TEXT,                       -- HH:MM (wake time) or NULL
    no_sleep            INTEGER,                    -- 0/1; fallback if fell_asleep/sleep_end NULL
    nightmares          INTEGER,                    -- 0/1; morning form only
    melatonin           INTEGER,                    -- 0/1; morning form only

    -- Snapshot fields (recorded fresh each submission; blank on next morning's form)
    mood                INTEGER,                    -- 1–10 or NULL
    energy              INTEGER,                    -- 1–10 or NULL
    anxiety             INTEGER,                    -- 1–10 or NULL

    -- Counter fields (can only increase within a day; autofilled from prev day on morning form)
    coffee              INTEGER,                    -- cumulative count (0, 1, 2…)
    intrusive           INTEGER,                    -- 0–5 cumulative
    meals               INTEGER,
    snacks              INTEGER,
    exercise_minutes    INTEGER,
    sunlight_minutes    INTEGER,
    hours_worked        REAL
);
```

**`sleep_hours`** is not stored — calculated at query time from `fell_asleep` and `sleep_end` (handling midnight crossover).

## Field Categories

| Category | Fields | Morning Form | Update Form | Carry-forward |
|---|---|---|---|---|
| Morning-only | shower_end, no_shower, fell_asleep, sleep_end, no_sleep, nightmares, melatonin | Required (with fallback) | Absent | No |
| Snapshot | mood, energy, anxiety | Required | Optional | No |
| Counter | coffee, intrusive, meals, snacks, exercise_minutes, sunlight_minutes, hours_worked | See below | Optional | Yes (yesterday → morning form) |

Counter fields on the morning form appear in two sections:
- **Confirm Yesterday** (required): `yesterday_intrusive`, `yesterday_meals`, `yesterday_snacks`, `yesterday_exercise_minutes`, `yesterday_sunlight_minutes`, `yesterday_hours_worked` — autofilled from yesterday's last submission, written as a retroactive row to yesterday's date.
- **Today So Far** (all optional): `coffee`, `intrusive`, `meals`, `snacks`, `exercise_minutes`, `sunlight_minutes`, `hours_worked` — written to today's sub#1 row.

## API Endpoints

### `GET /`
Serves `static/form.html`. Queries yesterday's last submission and injects `value` attributes into the `yesterday_*` counter fields for autofill. No authentication.

### `POST /submit`
Morning gate form submission. Two DB inserts in order:
1. **Yesterday retroactive row** (`submission_number = MAX(yesterday) + 1`): writes confirmed counter values (intrusive, meals, snacks, exercise_minutes, sunlight_minutes, hours_worked) to yesterday's date. Counter validation: each must be >= yesterday's current max.
2. **Today sub#1 row**: sleep fields, snapshot (mood/energy/anxiety), melatonin, plus any optional today-counter values.

Then unblocks all devices (ipset add → flush must_checkin → remove DNAT rule).

Sleep validation: `shower_end` requires either a value or `no_shower=1`; `fell_asleep`/`sleep_end` require either both values or `no_sleep=1`.

### `GET /update`
Serves `static/update.html`. Queries today's last submission and injects counter field values for pre-fill. Snapshot fields left blank.

### `POST /update`
1. **Lock check**: if tomorrow has a `submission_number=1` row with `submitted_at IS NOT NULL`, reject with 400 ("Today's checkin is finalized").
2. **Counter validation**: each submitted counter >= today's current max for that field; reject with 400 if any decrease.
3. Insert new row with `submission_number = MAX(today) + 1`.

No firewall changes. Returns HTML confirmation.

### `GET /history`
All rows from `checkins`, ordered by date DESC then submission_number DESC. Each submission is its own table row with a Sub# column. `sleep_hours` calculated at render time. Backfilled rows dimmed. Dark theme matching forms.

### `GET /status`
Returns JSON `{"blocked": true/false, "today_submitted": true/false}`. Checks `allowed_internet` ipset membership.

## Form UI

### Morning form (`static/form.html`)
Four sections in order:
1. **Confirm Yesterday** — required counter fields (`yesterday_` prefixed names), autofilled from yesterday's last submission
2. **Last Night** — sleep fields with fallback checkboxes (no_shower, no_sleep), nightmares, melatonin
3. **Mental State** — mood, energy, anxiety (required)
4. **Today So Far** — all optional: coffee, intrusive, meals, snacks, exercise, sunlight, hours_worked

Confirmation page includes link to `/update`.

### Update form (`static/update.html`)
Two sections:
1. **Mental State** — mood, energy, anxiety (optional)
2. **Today So Far** — coffee, intrusive, meals, snacks, exercise, sunlight, hours_worked (optional, pre-filled from today's last submission)

No sleep section. Submit button: "Save Update". Matches morning form dark theme.

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
