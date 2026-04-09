## Project Context

| File | Description |
|------|-------------|
| [CLAUDE.md](../CLAUDE.md) | Project rules and guidelines for Claude and file management |
| [project_management/status.md](status.md) | Active work, open items, and closed items tracking |
| [project_management/manifest.md](manifest.md) | This file — full project file listing with descriptions |
| [project_management/cdoc.md](cdoc.md) | Template instructions for generating context documents |
| [project_management/prompting.md](prompting.md) | Template instructions for generating task prompts |
| [project_management/cdocs/overview.md](cdocs/overview.md) | System overview, repository layout, systemd units, known limitations |
| [project_management/cdocs/database.md](cdocs/database.md) | DB schema, 5am boundary, source values, key DB functions, migration |
| [project_management/cdocs/routes.md](cdocs/routes.md) | All API endpoints: behavior, validation, events created |
| [project_management/cdocs/forms.md](cdocs/forms.md) | Morning gate and update form fields, Quick Log, UI theme |
| [project_management/cdocs/enforcement.md](cdocs/enforcement.md) | Blocked devices, daily block mechanism, unblock flow, sudoers |
| [project_management/cdocs/events.md](cdocs/events.md) | Event type catalog, key field schemas, design decisions |
| [project_management/cdocs/queries.md](cdocs/queries.md) | Common SQL/Python query patterns for the events table |
| [project_management/cdocs/past_work/pi-router.md](cdocs/past_work/pi-router.md) | Pi network architecture, ipset/iptables setup, existing sudoers |
| [project_management/cdocs/past_work/productivity-guard.md](cdocs/past_work/productivity-guard.md) | Productivity Guard FastAPI service: DNS blocking, LLM gatekeeper, Firefox extension |
| [project_management/cdocs/past_work/home-assistant.md](cdocs/past_work/home-assistant.md) | Home Assistant deployment, Bermuda BLE room tracking, HA REST API |

## Daily Checkin Service

| File | Description |
|------|-------------|
| [daily-checkin/main.py](../daily-checkin/main.py) | FastAPI app entry point: startup/shutdown lifecycle, router registration, home route |
| [daily-checkin/config.py](../daily-checkin/config.py) | Constants: PORT, DB_PATH, SCHEMA_PATH, STATIC_DIR, DEVICES, IPSET_BIN, IPTABLES_BIN, SUMMARY_COUNTER_FIELDS |
| [daily-checkin/database.py](../daily-checkin/database.py) | DB layer: get_db, close_db, insert_event, get_latest_summary, has_morning_gate, migrate_if_needed |
| [daily-checkin/firewall.py](../daily-checkin/firewall.py) | Firewall helpers: unblock_all (ipset add/flush + iptables DNAT removal) |
| [daily-checkin/utils.py](../daily-checkin/utils.py) | Pure helpers: calc_sleep_hours, get_event_date, format_event_details |
| [daily-checkin/routes/__init__.py](../daily-checkin/routes/__init__.py) | Package marker for routes module |
| [daily-checkin/routes/checkin.py](../daily-checkin/routes/checkin.py) | Routes: GET /checkin, POST /submit (morning gate) |
| [daily-checkin/routes/update.py](../daily-checkin/routes/update.py) | Routes: GET /update, POST /update |
| [daily-checkin/routes/events.py](../daily-checkin/routes/events.py) | Routes: POST /event/food, /event/coffee, /event/headache, /event/bowel, /event/work, /event/relax |
| [daily-checkin/routes/history.py](../daily-checkin/routes/history.py) | Route: GET /history |
| [daily-checkin/routes/status.py](../daily-checkin/routes/status.py) | Route: GET /status |
| [daily-checkin/schema.sql](../daily-checkin/schema.sql) | SQLite DDL for the checkins table (multi-row per date) |
| [daily-checkin/static/form.html](../daily-checkin/static/form.html) | Morning gate form: confirm yesterday's counters, last night's sleep, mental state, today so far |
| [daily-checkin/static/update.html](../daily-checkin/static/update.html) | Update form: optional mental state snapshots and today's counter updates |
| [daily-checkin/static/home.html](../daily-checkin/static/home.html) | Home screen: Submit Checkin / View History buttons + Quick Log section (Food, Coffee, Headache, Bowel inline forms) |
| [daily-checkin/block.sh](../daily-checkin/block.sh) | Shell script to block devices and add captive portal DNAT rule |
| [daily-checkin/checkin.service](../daily-checkin/checkin.service) | systemd unit for the FastAPI backend (port 8900) |
| [daily-checkin/daily-checkin-block.service](../daily-checkin/daily-checkin-block.service) | systemd oneshot unit for the block script |
| [daily-checkin/daily-checkin-block.timer](../daily-checkin/daily-checkin-block.timer) | systemd timer firing at 05:00 daily |
| [daily-checkin/sudoers-daily-checkin](../daily-checkin/sudoers-daily-checkin) | Passwordless sudo rules for ipset/iptables commands |
| [daily-checkin/requirements.txt](../daily-checkin/requirements.txt) | Python dependencies: fastapi, uvicorn, aiosqlite, python-multipart |
