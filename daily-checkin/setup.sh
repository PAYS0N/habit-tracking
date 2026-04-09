#!/bin/bash
# setup.sh — Install system files and reload services on the Pi.
# Run from the project directory on kuudra (pays0n).
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYSTEMD_DIR="/etc/systemd/system"
SUDOERS_DEST="/etc/sudoers.d/daily-checkin"

# ---------------------------------------------------------------------------
# 1. systemd units
# ---------------------------------------------------------------------------
echo "==> Installing systemd units..."
for unit in checkin.service daily-checkin-block.service daily-checkin-block.timer; do
    sudo cp "$REPO_DIR/$unit" "$SYSTEMD_DIR/$unit"
done

# ---------------------------------------------------------------------------
# 2. sudoers
# ---------------------------------------------------------------------------
echo "==> Installing sudoers..."
sudo visudo -c -f "$REPO_DIR/sudoers-daily-checkin"
sudo cp "$REPO_DIR/sudoers-daily-checkin" "$SUDOERS_DEST"
sudo chmod 0440 "$SUDOERS_DEST"

# ---------------------------------------------------------------------------
# 3. Shell scripts
# ---------------------------------------------------------------------------
echo "==> Marking shell scripts executable..."
chmod +x "$REPO_DIR/block.sh" "$REPO_DIR/reblock_akura.sh"

# ---------------------------------------------------------------------------
# 4. Reload and restart
# ---------------------------------------------------------------------------
echo "==> Reloading systemd daemon..."
sudo systemctl daemon-reload

echo "==> Restarting checkin.service..."
sudo systemctl restart checkin.service
sudo systemctl status checkin.service --no-pager -l

echo "==> Enabling and restarting block timer..."
sudo systemctl enable daily-checkin-block.timer
sudo systemctl restart daily-checkin-block.timer

echo ""
echo "Setup complete."
