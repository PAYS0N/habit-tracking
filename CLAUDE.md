# Habit Tracking — Daily Checkin System

A FastAPI service deployed on a Raspberry Pi router (kuudra) that enforces daily behavioral checkins via a captive portal (blocking internet access until submission), tracks longitudinal mood and lifestyle metrics (sleep, exercise, food, caffeine, work hours) in SQLite, and provides a history view for analysis. Supports multiple form submissions per day (morning gate + optional updates). Built with Python (FastAPI, uvicorn, aiosqlite), systemd timers for daily enforcement (05:00 block trigger), and Linux firewall rules (ipset/iptables DNAT) for captive portal redirection. **Status:** Deployed and operational on port 8900.

## Project Rules

- All non-code files should be markdown unless specifically mentioned otherwise.

- The source files in this project are the single source of truth. Always read them directly rather than relying on conversation memory.

- Read project_management/manifest.md for a list of all files and purposes.

- Remember: When asked to create or edit a context document, read project_management/cdoc.md.

- When asked to create project management files, create them in the project_management directory in root.

- When asked to create a prompt, read project_management/prompting.md. Do not rely on memory, re-read it every time.