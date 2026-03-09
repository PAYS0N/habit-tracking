# Daily Checkin — Context Document

## Purpose and Architecture

A morning checkin system that gates internet access across all personal devices until a short daily form is submitted. The Pi serves the form and enforces the block by removing device IPs from the `allowed_internet` ipset at a scheduled time each morning. On form submission, the Pi re-adds the submitting device's IP. Goal: build a longitudinal dataset of mood and lifestyle variables for future analysis.

The service runs as a new standalone FastAPI backend on the Pi (not part of Productivity Guard), exposed on a distinct port. Data is stored in SQLite on the Pi.

## Checkin Form Fields

All fields are collected via an HTML form served from the Pi:

- **Mood** — numeric scale (TBD: 1–10?)
    - Should likely be multiple metrics, like 'happy' 'sad' 'depressed'
- **Hours of sleep** — numeric (e.g., 7.5)
- **Sleep window** — what time did you fall asleep / wake up (two time inputs)
- **Coffee today** — boolean (yes/no); assumes checkin happens in the morning after coffee if taken
- **Meals yesterday** — integer count
- **Non-meal snacks yesterday** — integer count

The form is a simple single-page HTML file served by the backend. No login; device IP is used to identify the submitter.

## Enforcement Mechanism

Blocked devices: `payson_s25` (`.75`), `voidgloom` (`.50`), `akura_malice` (`.52`). These are the three IPs currently in `allowed_internet` that belong to personal devices (`.76` iPhone and `.77` notebook excluded pending decision).

**Block trigger:** A cron job (or systemd timer) runs at a configurable morning time (e.g., 05:00) and removes the three device IPs from the `allowed_internet` ipset via `sudo ipset del`. This cuts off internet forwarding for those devices without affecting LAN access (they can still reach the Pi on `192.168.22.1`).

**Unblock on submit:** On `POST /submit`, the backend validates the form, writes to the DB, then re-adds the devices' IP (`request.client.host`) to `allowed_internet` via `sudo ipset add`. A single submission unblocks all devices.

**Captive portal (optional):** An iptables DNAT rule on the Pi could redirect all outbound HTTP (port 80) traffic from blocked IPs to the checkin form port, creating a captive portal effect. HTTPS (443) cannot be redirected without a trusted cert. Baseline approach: user navigates to `http://192.168.22.1:<port>` manually or via a browser bookmark. Captive portal is a stretch goal.

## Data Storage

SQLite database on the Pi at a path like `/home/pays0n/daily-checkin/checkin.db`. Single table `checkins`:

| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| date | TEXT | ISO 8601 date (YYYY-MM-DD) |
| submitted_at | TEXT | ISO 8601 timestamp |
| device_ip | TEXT | submitting device |
| mood | INTEGER | |
| sleep_hours | REAL | |
| sleep_start | TEXT | HH:MM |
| sleep_end | TEXT | HH:MM |
| coffee | INTEGER | 0/1 |
| meals_yesterday | INTEGER | |
| snacks_yesterday | INTEGER | |

One record per device per day (or one per day total — TBD). A `/history` endpoint or simple read-only HTML page can display past entries for future analysis.

## Pi Integration

The service needs passwordless sudo for two new commands (to be added to `/etc/sudoers.d/`):
- `ipset add allowed_internet <ip>`
- `ipset del allowed_internet <ip>`

The block/unblock logic mirrors the Productivity Guard pattern (subprocess call to a privileged command). The service runs as `pays0n` user via systemd, bound to `0.0.0.0:<port>` (port TBD, must not conflict with PG's 8800 or HA's 8123). iptables INPUT chain must permit the chosen port from `wlan0`.

## Schedule

The daily reset fires at a fixed time via cron/systemd timer. The checkin window stays open until submitted; there is no expiry within the day. At the next morning's reset time, all three IPs are removed again regardless of yesterday's submission status. Checkin date is the calendar date of submission (device local time or Pi time — TBD).

## Tech Stack

- **Backend:** Python 3, FastAPI, uvicorn, aiosqlite — consistent with Productivity Guard
- **Form UI:** Plain HTML/CSS served as a static file from FastAPI; no JS framework needed
- **Scheduler:** systemd timer or cron on the Pi
- **Database:** SQLite
- **Deployment:** systemd service under `pays0n` user, auto-start on boot

## Estimated Difficulty

**Low–Medium.** The Pi infrastructure, FastAPI pattern, and ipset manipulation are all proven by Productivity Guard. The new pieces are: the HTML form, the scheduled block trigger, and per-IP unblock on submit. No LLM, no external APIs, no mobile app. Main risk is sudoers/ipset permission wiring and ensuring the service survives reboots cleanly.

## Value Delivered

Passive longitudinal data collection with zero friction after setup. Enforced daily habit via a hard internet gate — the system can't be ignored or snoozed. Data enables future correlation analysis (e.g., does sleep duration predict mood? does coffee?). Extensible to more variables over time.

## Open Questions

- **Block time:** What time should the daily reset fire? (05:00 suggested; should be before the earliest typical wake time)
- **Per-device vs. shared checkin:** Does each device need its own submission to get unblocked, or does one submission unblock all three?
- **Captive portal:** Worth implementing for better UX, or is a manual URL sufficient?
- **History UI:** Read-only HTML page on the Pi, or just raw DB access for now?
- **Date boundary:** Is the checkin for "today" or "yesterday" (i.e., do meal/snack counts refer to the previous calendar day)? The current spec mixes both — meals/snacks are "yesterday", mood/sleep reflect the current morning.
- **Missed days:** Should missed checkins be recorded as nulls in the DB for continuity of the dataset?
