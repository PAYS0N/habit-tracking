# Daily Checkin — System Documentation

## Overview

A FastAPI service running on the Raspberry Pi router (kuudra) that serves a daily morning checkin form, enforces internet access blocks via ipset, and accumulates a longitudinal SQLite dataset for mood and lifestyle analysis. One submission per day unblocks all personal devices. A `must_checkin` ipset scopes the captive portal DNAT rule so only blocked devices are redirected; other devices on the network are unaffected.

**Status:** Deployed and operational on the Pi.
**Port:** 8900
**Deployment path:** `/home/pays0n/Documents/Projects/habit-tracking/daily-checkin/`

## Repository Layout

```
daily-checkin/
├── main.py                       # FastAPI app: routes, DB init, backfill, ipset/iptables calls
├── schema.sql                    # SQLite DDL (applied at startup if DB absent)
├── static/
│   └── form.html                 # Mobile-friendly checkin form (dark theme)
├── block.sh                      # Block script: removes IPs, adds DNAT rule
├── checkin.service               # systemd unit for FastAPI backend
├── daily-checkin-block.service   # systemd oneshot for block script
├── daily-checkin-block.timer     # systemd timer (05:00 daily)
├── sudoers-daily-checkin         # sudoers rules (copied to /etc/sudoers.d/)
├── requirements.txt              # fastapi, uvicorn[standard], aiosqlite, python-multipart
└── checkin.db                    # SQLite database (created at runtime)
```

## Database Schema

Single table `checkins`. One row per calendar date (Pi local time). Null rows are backfilled for any gaps on each submission.

```sql
CREATE TABLE IF NOT EXISTS checkins (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    date              TEXT NOT NULL UNIQUE,   -- YYYY-MM-DD
    submitted_at      TEXT,                   -- ISO 8601 timestamp; NULL = backfilled
    device_ip         TEXT,                   -- submitting device IP; NULL = backfilled

    -- Sleep
    sleep_hours       REAL,                   -- e.g. 7.5
    shower_end        TEXT,                   -- HH:MM (time shower ended)
    fell_asleep       TEXT,                   -- HH:MM (estimated time fell asleep)
    sleep_end         TEXT,                   -- HH:MM (wake time)
    nightmares        INTEGER,                -- 0/1 boolean

    -- Mood & mental state (current morning)
    mood              INTEGER,                -- 1-10
    energy            INTEGER,                -- 1-10
    anxiety           INTEGER,                -- 1-10

    -- Substances
    coffee            INTEGER,                -- 0/1
    melatonin         INTEGER,                -- 0/1

    -- Yesterday's activity & experience
    intrusive         INTEGER,                -- 0-5 (0=none, 5=severe/frequent)
    meals_yesterday   INTEGER,
    snacks_yesterday  INTEGER,
    exercise_minutes  INTEGER,                -- intentional activity only
    sunlight_minutes  INTEGER,                -- direct sun during daylight hours only
    hours_worked      REAL,                   -- yesterday's working hours

    UNIQUE(date)
);
```

**Field clarifications (embedded in form as inline hints):**
- **Shower ended:** Time you finished your shower / started winding down for bed.
- **Fell asleep:** Best estimate of when you actually fell asleep.
- **Exercise:** Intentional physical activity only (walking, gym, cycling, yoga). Not passive movement. Enter 0 if none.
- **Sunlight:** Direct sun on skin/eyes during daylight hours. Heavy overcast or nighttime doesn't count.
- **Intrusive thoughts/flashbacks:** 0 = none; 1 = one brief instance; 5 = severe or frequent throughout the day. Refers to yesterday.
- **Coffee:** Have you had coffee this morning before filling this out?
- **Melatonin:** Did you take melatonin last night before sleep?
- **Mood/energy/anxiety:** Current state as of this morning.
- **Meals/snacks/exercise/sunlight/hours worked/intrusive:** Yesterday's counts.

## API Endpoints

### `GET /`
Serves `static/form.html`. No authentication; device IP is captured server-side.

### `POST /submit`
Accepts form data. Steps in order:
1. Determine today's date (Pi local time).
2. **Backfill gaps:** Query most recent date in DB. Insert null rows for any missing dates between last entry and yesterday.
3. Insert today's row via `INSERT OR REPLACE`.
4. Re-add all device IPs to `allowed_internet` ipset.
5. Flush `must_checkin` ipset (stops DNAT matching immediately).
6. Remove captive portal DNAT rule.
7. Return HTML confirmation page with date and unblock confirmation.

### `GET /status`
Returns JSON `{"blocked": true/false, "today_submitted": true/false}`. Checks `allowed_internet` ipset membership via `ipset test`.

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

The DNAT rule is idempotent (checks with `-C` before adding with `-A`). Only devices in `must_checkin` are redirected; all other network devices are unaffected.

### Unblock on submit

On `POST /submit`, `main.py`:
1. Re-adds each device IP to `allowed_internet` via `sudo ipset add ... -exist`.
2. Flushes `must_checkin` ipset (DNAT rule immediately stops matching any device).
3. Deletes the DNAT rule from the nat PREROUTING chain.

All subprocess calls use `check=False, capture_output=True` and log stderr on failure without aborting the response.

### Captive Portal

DNAT rule matches only `must_checkin` source IPs on wlan0 port 80. HTTPS (443) is not redirected — most modern sites use HTTPS, so the captive portal has limited automatic redirect capability. The practical approach is a browser bookmark to `http://192.168.22.1:8900` on the phone.

## Sudoers Configuration

File: `/etc/sudoers.d/daily-checkin` (mode 0440). Source in repo as `sudoers-daily-checkin`.

```
pays0n ALL=(root) NOPASSWD: /usr/sbin/ipset add allowed_internet * -exist
pays0n ALL=(root) NOPASSWD: /usr/sbin/ipset del allowed_internet *
pays0n ALL=(root) NOPASSWD: /usr/sbin/ipset test allowed_internet *
pays0n ALL=(root) NOPASSWD: /usr/sbin/ipset flush must_checkin
pays0n ALL=(root) NOPASSWD: /usr/sbin/iptables -t nat -D PREROUTING -i wlan0 -m set --match-set must_checkin src -p tcp --dport 80 -j DNAT --to-destination 192.168.22.1\:8900
```

The iptables sudoers entry is locked to the exact DNAT rule — no wildcards. Binary paths are `/usr/sbin/` (verified on the Pi).

## Systemd Units

**FastAPI backend** (`checkin.service`): runs as `pays0n`, uvicorn on `0.0.0.0:8900`, auto-restart on failure.
**Block script** (`daily-checkin-block.service`): oneshot, runs as root.
**Block timer** (`daily-checkin-block.timer`): `OnCalendar=*-*-* 05:00:00`, `Persistent=true`.

Port 8900 is open in iptables INPUT chain (persisted via `netfilter-persistent`).

## Form UI

Plain HTML/CSS, dark theme, no JavaScript framework. Fields grouped into sections: Sleep, Mental State, Substances, Yesterday's Activity. Boolean fields use toggle-button radio groups. All fields required with HTML5 `min`/`max` validation. Mobile-optimized for the S25.

## Known Limitations

- **Captive portal HTTPS:** DNAT only redirects HTTP (port 80). HTTPS-first sites require manual navigation to the form URL.
- **iptables persistence:** The DNAT rule and `must_checkin` ipset do not persist across Pi reboots. The block timer recreates them at the next 05:00. If the Pi reboots mid-day before checkin, devices regain internet until the next 05:00 trigger.
- **No authentication:** Any device on the LAN can submit the form.

## Future Work

- `/history` read-only UI for viewing past checkins
- Per-device submission tracking
- iptables/ipset persistence across reboot
- HTTPS / trusted cert for captive portal
