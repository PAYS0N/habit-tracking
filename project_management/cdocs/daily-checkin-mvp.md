# Daily Checkin — MVP Specification

## Overview

A FastAPI service running on the Pi that serves a daily morning checkin form, enforces internet access blocks via ipset, and accumulates a longitudinal SQLite dataset for mood and lifestyle analysis. One submission per day unblocks all personal devices. Captive portal via iptables DNAT redirects blocked HTTP traffic to the form automatically.

## Repository Layout

```
daily-checkin/
├── main.py           # FastAPI app: routes, DB init, block/unblock logic
├── schema.sql        # SQLite DDL (also applied at startup if DB absent)
├── static/
│   └── form.html     # Checkin form (served as static file)
├── checkin.db        # SQLite database (created at runtime)
├── checkin.service   # systemd unit file
└── requirements.txt  # fastapi, uvicorn[standard], aiosqlite
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
    sleep_start       TEXT,                   -- HH:MM (lights out)
    sleep_end         TEXT,                   -- HH:MM (wake time)
    nightmares        INTEGER,                -- 0/1 boolean

    -- Mood & mental state (all refer to current morning / yesterday's experience)
    mood              INTEGER,                -- 1–10
    energy            INTEGER,               -- 1–10
    anxiety           INTEGER,               -- 1–10
    intrusive         INTEGER,               -- 0–5 (0=none, 5=severe/frequent)

    -- Substances
    coffee            INTEGER,               -- 0/1 (taken this morning before checkin)
    melatonin         INTEGER,               -- 0/1 (taken last night)

    -- Yesterday's activity
    meals_yesterday   INTEGER,
    snacks_yesterday  INTEGER,
    exercise_minutes  INTEGER,               -- intentional activity only (see notes)
    sunlight_minutes  INTEGER,               -- direct sun during daylight hours only
    hours_worked      REAL,                  -- yesterday's working hours

    UNIQUE(date)
);
```

**Field clarifications embedded in form UI:**
- **Exercise:** Any intentional physical activity (walking, running, gym, cycling, yoga). Does not include passive movement (commuting, standing). Enter 0 if none.
- **Sunlight:** Direct sunlight on skin/eyes during daylight hours. Outdoors at night or under heavy overcast does not count. Estimate conservatively.
- **Intrusive thoughts/flashbacks:** 0 = none; 1 = one brief instance; 5 = severe or frequent throughout the day.
- **Coffee:** Assumes checkin happens after morning coffee if taken.
- **Melatonin:** Did you take melatonin last night before sleep?
- **Mood/energy/anxiety:** Current state as of this morning.
- **Meals/snacks/exercise/sunlight/hours worked:** Yesterday's counts.

## API Endpoints

### `GET /`
Serves `static/form.html`. The form collects all fields above. On load, pre-fills the date (Pi local date). No authentication; device IP is captured server-side.

### `POST /submit`
Accepts form data. Steps in order:
1. Validate all fields are present and within range.
2. Determine today's date (Pi local time, `YYYY-MM-DD`).
3. **Backfill gaps:** Query `SELECT date FROM checkins ORDER BY date DESC LIMIT 1`. If the most recent date is older than yesterday, insert one null row per missing date (all metric columns NULL, `submitted_at` NULL, `device_ip` NULL).
4. Insert today's row (upsert via `INSERT OR REPLACE`).
5. Re-add all three personal device IPs to `allowed_internet` ipset via `sudo ipset add allowed_internet <ip> -exist` for each. Run as subprocess; log stderr on failure but do not abort the response.
6. Remove captive portal DNAT rule (see Captive Portal section).
7. Return a simple "Checkin complete. Internet restored." HTML confirmation page.

### `GET /status`
Returns JSON `{"blocked": true/false, "today_submitted": true/false}`. Checks whether today's date has a non-null row in the DB. Useful for debugging.

## Enforcement Mechanism

### Devices blocked

| Device | IP |
|---|---|
| payson_s25 | 192.168.22.75 |
| voidgloom | 192.168.22.50 |
| akura_malice | 192.168.22.52 |

### Daily block (cron/systemd timer — 05:00 Pi local time)

A systemd timer (preferred over cron for consistency with the service) runs a one-shot script at 05:00 daily:

```bash
#!/bin/bash
# /home/pays0n/daily-checkin/block.sh
DEVICES=(192.168.22.75 192.168.22.50 192.168.22.52)
for ip in "${DEVICES[@]}"; do
    ipset del allowed_internet "$ip" 2>/dev/null || true
done
# Add captive portal DNAT rule (idempotent)
iptables -t nat -C PREROUTING -i wlan0 -p tcp --dport 80 \
    -j DNAT --to-destination 192.168.22.1:PORT 2>/dev/null \
    || iptables -t nat -A PREROUTING -i wlan0 -p tcp --dport 80 \
    -j DNAT --to-destination 192.168.22.1:PORT
```

Replace `PORT` with the chosen service port.

**Systemd timer unit** (`/etc/systemd/system/daily-checkin-block.timer`):
```ini
[Unit]
Description=Daily checkin block timer

[Timer]
OnCalendar=*-*-* 05:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

**Systemd service unit for block script** (`/etc/systemd/system/daily-checkin-block.service`):
```ini
[Unit]
Description=Run daily checkin block

[Service]
Type=oneshot
ExecStart=/home/pays0n/daily-checkin/block.sh
User=root
```

### Unblock on submit

On `POST /submit`, the backend runs (for each device IP):
```python
subprocess.run(
    ["sudo", "ipset", "add", "allowed_internet", ip, "-exist"],
    check=False, capture_output=True
)
```

A single submission unblocks all three devices simultaneously.

### Captive Portal

DNAT rule (added by `block.sh` at 05:00, removed on submit):

```
iptables -t nat -A PREROUTING -i wlan0 -p tcp --dport 80 \
    -j DNAT --to-destination 192.168.22.1:<PORT>
```

On submit, the backend removes it:
```python
subprocess.run([
    "sudo", "iptables", "-t", "nat", "-D", "PREROUTING",
    "-i", "wlan0", "-p", "tcp", "--dport", "80",
    "-j", "DNAT", "--to-destination", f"192.168.22.1:{PORT}"
], check=False, capture_output=True)
```

HTTPS (443) is not redirected. Users on HTTPS-first sites will need to navigate manually to `http://192.168.22.1:<PORT>` or use a plain HTTP URL as a bookmark trigger.

## Sudoers Configuration

Create `/etc/sudoers.d/daily-checkin` (mode 0440):

```
pays0n ALL=(root) NOPASSWD: /sbin/ipset add allowed_internet * -exist
pays0n ALL=(root) NOPASSWD: /sbin/ipset del allowed_internet *
pays0n ALL=(root) NOPASSWD: /sbin/iptables -t nat -D PREROUTING *
pays0n ALL=(root) NOPASSWD: /sbin/iptables -t nat -A PREROUTING *
pays0n ALL=(root) NOPASSWD: /sbin/iptables -t nat -C PREROUTING *
```

Validate with `visudo -c` after writing.

## Systemd Service (FastAPI backend)

`/etc/systemd/system/daily-checkin.service`:

```ini
[Unit]
Description=Daily Checkin FastAPI Service
After=network.target

[Service]
Type=simple
User=pays0n
WorkingDirectory=/home/pays0n/daily-checkin
ExecStart=/home/pays0n/daily-checkin/venv/bin/uvicorn main:app --host 0.0.0.0 --port PORT
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable: `systemctl enable --now daily-checkin.service`

## Port Selection

Choose a port that does not conflict with:
- Productivity Guard: 8800
- Home Assistant: 8123
- Common Pi services: 80, 443, 22, 53

Suggested: **8900**. Must be opened in iptables INPUT chain:
```bash
iptables -A INPUT -i wlan0 -p tcp --dport 8900 -j ACCEPT
```
This rule must be made persistent (e.g., via `iptables-save` / `netfilter-persistent`).

## Form UI Requirements

Plain HTML/CSS, no JS framework. Single-page form. Fields grouped into logical sections (Sleep, Mental State, Substances, Yesterday's Activity). Each field must display its clarification text inline as a form hint. Submit button label: "Submit Checkin". On successful submit, replace page with confirmation message including the date submitted and a note that all devices are unblocked.

Form must be usable on mobile (the S25 is the likely submission device). Use `<input type="number">` with appropriate `min`/`max` attributes for range enforcement client-side. All fields required.

## Missed Days Backfill Logic (detail)

On `POST /submit`:
```python
today = date.today().isoformat()        # Pi local date
yesterday = (date.today() - timedelta(days=1)).isoformat()

row = await db.fetchone("SELECT date FROM checkins ORDER BY date DESC LIMIT 1")
if row:
    last_date = date.fromisoformat(row["date"])
    gap_start = last_date + timedelta(days=1)
    gap_end = date.fromisoformat(yesterday)
    d = gap_start
    while d <= gap_end:
        await db.execute(
            "INSERT OR IGNORE INTO checkins (date) VALUES (?)",
            (d.isoformat(),)
        )
        d += timedelta(days=1)
```

This is fire-and-forget — null rows are inserted with only the `date` column populated.

## Implementation Notes (deviations from original spec)

- **`must_checkin` ipset:** Instead of a blanket DNAT rule on all wlan0 HTTP traffic, the captive portal uses a `must_checkin` ipset (hash:ip). `block.sh` adds blocked device IPs to this set, and the DNAT rule uses `-m set --match-set must_checkin src` so only blocked devices are redirected. Other devices (coral, iPhone, notebook) are unaffected. On submit, `main.py` flushes this set and removes the DNAT rule.
- **Binary paths:** Default set to `/usr/sbin/ipset` and `/usr/sbin/iptables` (not `/sbin/`). Must be verified on the Pi before deployment; paths appear in `main.py`, `block.sh`, and `sudoers-daily-checkin`.
- **`ipset test` sudoers entry:** Added `ipset test allowed_internet *` to the sudoers file (not in original spec) so `GET /status` can check whether devices are blocked.
- **`ipset flush must_checkin` sudoers entry:** Added so `main.py` can clear the captive portal set on submit.
- **Sudoers file:** Shipped as `sudoers-daily-checkin` in the repo for version control; must be copied to `/etc/sudoers.d/daily-checkin` with mode 0440 on the Pi.
- **Form UI:** Dark theme with toggle buttons for boolean fields. No JavaScript framework; all client-side validation via HTML5 `required`/`min`/`max` attributes.

## Out of Scope (MVP)

- `/history` read-only UI
- Per-device submission requirement
- Persistent iptables rules across reboot (document manual step; handle in follow-up)
- Any authentication or user accounts
- HTTPS / trusted cert for captive portal
