# Daily Checkin — Project Status

## Active Work

| Item | Status | Notes |
|------|--------|-------|
| MVP implementation | Code complete | All files created, needs deployment to Pi |

## Open Items

### Pre-deploy (on the Pi)

- Verify binary paths: `which ipset`, `which iptables` — update `main.py`, `block.sh`, and `sudoers-daily-checkin` if they're at `/sbin/` instead of `/usr/sbin/`
- Create venv and install deps
- Copy sudoers file and validate with `visudo -c`
- Copy systemd units and enable services
- Open port 8900 in iptables INPUT chain and persist
- Test full flow: block → form → submit → unblock

### Post-MVP

- `/history` read-only UI
- iptables persistence across reboot (currently documented as manual step)
- Per-device submission tracking
- HTTPS / trusted cert for captive portal
