# Daily Checkin — Project Status

## Active Work

| Item | Status | Notes |
|------|--------|-------|
| — | — | No active work items |

## Completed

- MVP implementation (all source files)
- Deployment to Pi (systemd services, sudoers, iptables INPUT rule, venv)
- Full flow tested: block → form → submit → unblock
- Schema revision: `sleep_start` → `shower_end` + `fell_asleep`; intrusive moved to yesterday section

## Open Items

- `/history` read-only UI for viewing past checkins
- Per-device submission tracking
- iptables/ipset persistence across reboot (DNAT rule and `must_checkin` set lost on reboot; block timer recreates at next 05:00)
- HTTPS / trusted cert for captive portal
- Captive portal auto-redirect limited to HTTP-only sites; phone bookmark is the practical workaround
