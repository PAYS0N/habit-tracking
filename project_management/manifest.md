## Project Context

| File | Description |
|------|-------------|
| [CLAUDE.md](../CLAUDE.md) | Project rules and guidelines for Claude and file management |
| [project_management/status.md](status.md) | Active work, open items, and closed items tracking |
| [project_management/manifest.md](manifest.md) | This file — full project file listing with descriptions |
| [project_management/cdoc.md](cdoc.md) | Template instructions for generating context documents |
| [project_management/prompting.md](prompting.md) | Template instructions for generating task prompts |
| [project_management/cdocs/daily-checkin.md](cdocs/daily-checkin.md) | Background and design rationale for the daily checkin concept |
| [project_management/cdocs/daily-checkin-system.md](cdocs/daily-checkin-system.md) | Full system documentation for the deployed daily checkin service |
| [project_management/cdocs/pi-router.md](cdocs/pi-router.md) | Pi network architecture, ipset/iptables setup, existing sudoers |
| [project_management/cdocs/productivity-guard.md](cdocs/productivity-guard.md) | Existing FastAPI service on the Pi; pattern reference |

## Daily Checkin Service

| File | Description |
|------|-------------|
| [daily-checkin/main.py](../daily-checkin/main.py) | FastAPI app: routes, DB init, backfill logic, ipset/iptables subprocess calls |
| [daily-checkin/schema.sql](../daily-checkin/schema.sql) | SQLite DDL for the checkins table |
| [daily-checkin/static/form.html](../daily-checkin/static/form.html) | Mobile-friendly HTML/CSS checkin form |
| [daily-checkin/block.sh](../daily-checkin/block.sh) | Shell script to block devices and add captive portal DNAT rule |
| [daily-checkin/checkin.service](../daily-checkin/checkin.service) | systemd unit for the FastAPI backend (port 8900) |
| [daily-checkin/daily-checkin-block.service](../daily-checkin/daily-checkin-block.service) | systemd oneshot unit for the block script |
| [daily-checkin/daily-checkin-block.timer](../daily-checkin/daily-checkin-block.timer) | systemd timer firing at 05:00 daily |
| [daily-checkin/sudoers-daily-checkin](../daily-checkin/sudoers-daily-checkin) | Passwordless sudo rules for ipset/iptables commands |
| [daily-checkin/requirements.txt](../daily-checkin/requirements.txt) | Python dependencies: fastapi, uvicorn, aiosqlite, python-multipart |
