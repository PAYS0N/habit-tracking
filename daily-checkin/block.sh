#!/bin/bash
# /home/pays0n/daily-checkin/block.sh
# Removes device IPs from allowed_internet and adds captive portal DNAT rule.
# Run daily at 05:00 via daily-checkin-block.timer.
#
# NOTE: iptables rules do not persist across reboot. After reboot, manually run:
#   sudo netfilter-persistent save
# or re-enable the block timer. A persistent solution should be added post-MVP.

# Verify binary paths on the Pi — adjust if located at /sbin/ instead
IPSET="/usr/sbin/ipset"
IPTABLES="/usr/sbin/iptables"

PORT=8900
DEVICES=(192.168.22.75 192.168.22.50)

# Create must_checkin ipset if it doesn't exist
"$IPSET" create must_checkin hash:ip 2>/dev/null || true

# Remove devices from allowed_internet and add to must_checkin
for ip in "${DEVICES[@]}"; do
    "$IPSET" del allowed_internet "$ip" 2>/dev/null || true
    "$IPSET" add must_checkin "$ip" -exist
done

# Add captive portal DNAT rule scoped to must_checkin set (idempotent)
"$IPTABLES" -t nat -C PREROUTING -i wlan0 -m set --match-set must_checkin src -p tcp --dport 80 \
    -j DNAT --to-destination 192.168.22.1:$PORT 2>/dev/null \
    || "$IPTABLES" -t nat -A PREROUTING -i wlan0 -m set --match-set must_checkin src -p tcp --dport 80 \
    -j DNAT --to-destination 192.168.22.1:$PORT
