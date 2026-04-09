# Daily Checkin — Enforcement Mechanism

## Blocked Devices

| Device | IP |
|---|---|
| payson_s25 | 192.168.22.75 |
| voidgloom | 192.168.22.50 |
| akura_malice | 192.168.22.52 |

To add a morning-gate device: add its IP to `DEVICES` in both `config.py` and `block.sh`.

akura_malice is **not** in `DEVICES` — it is never touched by `unblock_all()` and is not subject to the morning gate flow. It has its own separate enforcement subsystem (see below).

## Daily Block (05:00 Timer)

`block.sh` runs as root via `daily-checkin-block.timer` at 05:00 daily:
1. Creates `must_checkin` ipset (hash:ip) if it doesn't exist.
2. For each device IP in `DEVICES`: removes from `allowed_internet`, adds to `must_checkin`.
3. Adds DNAT rule: HTTP port 80 from `must_checkin` sources on `wlan0` → `192.168.22.1:8900`.

akura_malice is not added to `must_checkin` by `block.sh`.

## Unblock on Submit

`POST /submit` calls `firewall.unblock_all()` after successful DB inserts:
1. Re-adds each device IP in `DEVICES` to `allowed_internet` via `sudo ipset add ... -exist`.
2. Flushes `must_checkin` (DNAT rule stops matching immediately).
3. Deletes the DNAT rule from nat PREROUTING chain.

All subprocess calls use `check=False, capture_output=True`. Failures are logged but do not abort the response.

## Captive Portal Scope

DNAT rule matches only `must_checkin` source IPs on `wlan0` port 80. HTTPS (443) is not redirected — HTTPS-first sites require manual navigation. Other LAN devices (not in `must_checkin`) are unaffected.

## akura_malice Subsystem

akura_malice (192.168.22.52, `AKURA_IP` in `config.py`) is a gaming device blocked by default at all times. It is **not** in `DEVICES` and is never added to `must_checkin`. The only way to unblock it is to submit a `relax` event with `video_game: true`.

### Unblock Flow

On a valid `POST /event/relax` with `video_game=true`:
1. Budget validation runs (see below). If it fails, the event is not logged and the device stays blocked.
2. The relax event is inserted in the DB.
3. `unblock_akura()` calls `sudo ipset add allowed_internet 192.168.22.52 -exist`.
4. `schedule_akura_reblock(hours)` schedules automatic re-block.

### Reblock Mechanism

`schedule_akura_reblock(hours)` in `firewall.py`:
1. Calls `sudo systemctl stop akura-reblock.timer` (ignores errors) to cancel any existing pending timer — prevents stacked sessions from double-scheduling.
2. Converts `hours` to seconds and calls `sudo systemd-run --on-active=<seconds>s --unit=akura-reblock /bin/bash /path/reblock_akura.sh`.

`reblock_akura.sh` (deployed alongside the service) runs `/usr/sbin/ipset del allowed_internet 192.168.22.52` directly as root (no sudo needed since it runs under the system service manager).

If a second session is submitted before the first timer fires, `schedule_akura_reblock` cancels the old timer first, so the device stays unblocked for the full new session duration from the moment of the second submission.

### Rolling 7-Day Budget

`get_video_game_hours_by_day()` in `database.py` queries `relax` events where `json_extract(data, '$.video_game') = 1` within a rolling 7-day window (today's event_date and 6 prior days, using the 5am boundary). Returns `{event_date: total_hours}`.

Budget validation in `POST /event/relax`:
1. Fetch hours by day.
2. Compute `today_proposed = existing_today_hours + submitted_hours`.
3. Build a map of all days (today's proposed + other days' existing); sort totals descending.
4. Validate against tier caps `[4, 2, 2, 1, 1, 1, 1]` — position 0 gets 4h cap, positions 1–2 get 2h, positions 3–6 get 1h.
5. If any day's total exceeds its tier cap, return `{"ok": false, "error": "Weekly video game budget exceeded"}` (HTTP 400). Do not insert the event or unblock.

Days with no video game events are absent from the dict and treated as 0 — they do not occupy a tier slot unless they have hours > 0.

## Sudoers

Installed at `/etc/sudoers.d/daily-checkin` (mode 0440), sourced from `sudoers-daily-checkin`:

```
pays0n ALL=(root) NOPASSWD: /usr/sbin/ipset add allowed_internet * -exist
pays0n ALL=(root) NOPASSWD: /usr/sbin/ipset del allowed_internet *
pays0n ALL=(root) NOPASSWD: /usr/sbin/ipset test allowed_internet *
pays0n ALL=(root) NOPASSWD: /usr/sbin/ipset flush must_checkin
pays0n ALL=(root) NOPASSWD: /usr/sbin/iptables -t nat -D PREROUTING -i wlan0 -m set --match-set must_checkin src -p tcp --dport 80 -j DNAT --to-destination 192.168.22.1\:8900
pays0n ALL=(root) NOPASSWD: /usr/bin/systemd-run --on-active=* --unit=akura-reblock /bin/bash /home/pays0n/Documents/Projects/habit-tracking/daily-checkin/reblock_akura.sh
pays0n ALL=(root) NOPASSWD: /usr/bin/systemctl stop akura-reblock.timer
```

Note: `ipset add allowed_internet * -exist` and `ipset del allowed_internet *` cover both the morning-gate devices and akura_malice with a single wildcard rule each.
