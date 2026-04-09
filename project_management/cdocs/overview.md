# Daily Checkin — Overview

## What It Is

A FastAPI service on the Raspberry Pi router (kuudra) that enforces daily behavioral checkins via a captive portal and accumulates longitudinal mood/lifestyle data in SQLite. Uses an event log architecture: every observable fact is a typed row in a single `events` table with JSON data.

**Status:** Deployed and operational.
**Port:** 8900
**Deployment path:** `/home/pays0n/Documents/Projects/habit-tracking/daily-checkin/`

## Repository Layout

```
daily-checkin/
├── main.py           # App entry point: startup/shutdown lifecycle, router includes, GET /
├── config.py         # Constants: PORT, DB_PATH, STATIC_DIR, DEVICES, IPSET_BIN, IPTABLES_BIN, SUMMARY_COUNTER_FIELDS
├── database.py       # DB layer: get_db, close_db, insert_event, get_latest_summary, has_morning_gate, migrate_if_needed
├── firewall.py       # unblock_all(): ipset add/flush + iptables DNAT removal
├── utils.py          # Helpers: calc_sleep_hours, get_event_date, format_event_details
├── routes/
│   ├── checkin.py    # GET /checkin, POST /submit
│   ├── update.py     # GET /update, POST /update
│   ├── events.py     # POST /event/{food,coffee,headache,bowel,work,relax}
│   ├── history.py    # GET /history
│   └── status.py     # GET /status
├── schema.sql        # SQLite DDL (applied at startup if DB absent)
├── static/           # form.html, update.html, home.html
├── block.sh          # Block script (run by systemd timer at 05:00)
├── checkin.service   # systemd unit for FastAPI backend
├── daily-checkin-block.service  # systemd oneshot for block script
├── daily-checkin-block.timer    # systemd timer (05:00 daily)
└── sudoers-daily-checkin        # passwordless sudo rules
```

## Systemd Units

- `checkin.service` — uvicorn on `0.0.0.0:8900`, user `pays0n`, auto-restart on failure
- `daily-checkin-block.service` — oneshot, runs as root
- `daily-checkin-block.timer` — `OnCalendar=*-*-* 05:00:00`, `Persistent=true`

Port 8900 is permitted in iptables INPUT chain (persisted via `netfilter-persistent`).

## Known Limitations

- DNAT only redirects HTTP port 80. HTTPS-first sites require manual navigation to `http://192.168.22.1:8900/checkin`.
- The DNAT rule and `must_checkin` ipset do not persist across Pi reboots; the block timer recreates them at the next 05:00.
- No authentication: any LAN device can submit the form.
