# Daily Checkin — Enforcement Mechanism

## Blocked Devices

| Device | IP |
|---|---|
| payson_s25 | 192.168.22.75 |
| voidgloom | 192.168.22.50 |
| akura_malice | 192.168.22.52 |

To add a device: add its IP to `DEVICES` in both `config.py` and `block.sh`.

## Daily Block (05:00 Timer)

`block.sh` runs as root via `daily-checkin-block.timer` at 05:00 daily:
1. Creates `must_checkin` ipset (hash:ip) if it doesn't exist.
2. For each device IP: removes from `allowed_internet`, adds to `must_checkin`.
3. Adds DNAT rule: HTTP port 80 from `must_checkin` sources on `wlan0` → `192.168.22.1:8900`.

## Unblock on Submit

`POST /submit` calls `firewall.unblock_all()` after successful DB inserts:
1. Re-adds each device IP to `allowed_internet` via `sudo ipset add ... -exist`.
2. Flushes `must_checkin` (DNAT rule stops matching immediately).
3. Deletes the DNAT rule from nat PREROUTING chain.

All subprocess calls use `check=False, capture_output=True`. Failures are logged but do not abort the response.

## Captive Portal Scope

DNAT rule matches only `must_checkin` source IPs on `wlan0` port 80. HTTPS (443) is not redirected — HTTPS-first sites require manual navigation. Other LAN devices (not in `must_checkin`) are unaffected.

## Sudoers

Installed at `/etc/sudoers.d/daily-checkin` (mode 0440), sourced from `sudoers-daily-checkin`:

```
pays0n ALL=(root) NOPASSWD: /usr/sbin/ipset add allowed_internet * -exist
pays0n ALL=(root) NOPASSWD: /usr/sbin/ipset del allowed_internet *
pays0n ALL=(root) NOPASSWD: /usr/sbin/ipset test allowed_internet *
pays0n ALL=(root) NOPASSWD: /usr/sbin/ipset flush must_checkin
pays0n ALL=(root) NOPASSWD: /usr/sbin/iptables -t nat -D PREROUTING -i wlan0 -m set --match-set must_checkin src -p tcp --dport 80 -j DNAT --to-destination 192.168.22.1\:8900
```
