import logging
import subprocess
from pathlib import Path

from config import AKURA_IP, DEVICES, IPSET_BIN, IPTABLES_BIN, PORT

log = logging.getLogger("daily-checkin")


def unblock_all() -> None:
    """Unblock all devices: add to allowed_internet, flush must_checkin, remove DNAT rule."""
    for ip in DEVICES:
        result = subprocess.run(
            ["sudo", IPSET_BIN, "add", "allowed_internet", ip, "-exist"],
            check=False,
            capture_output=True,
        )
        if result.returncode != 0:
            log.error("ipset add %s failed: %s", ip, result.stderr.decode())

    result = subprocess.run(
        ["sudo", IPSET_BIN, "flush", "must_checkin"],
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        log.error("ipset flush must_checkin failed: %s", result.stderr.decode())

    result = subprocess.run(
        [
            "sudo",
            IPTABLES_BIN,
            "-t", "nat",
            "-D", "PREROUTING",
            "-i", "wlan0",
            "-m", "set",
            "--match-set", "must_checkin", "src",
            "-p", "tcp",
            "--dport", "80",
            "-j", "DNAT",
            "--to-destination", f"192.168.22.1:{PORT}",
        ],
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        log.warning("iptables DNAT removal: %s", result.stderr.decode())


def unblock_akura() -> None:
    """Add akura_malice to allowed_internet."""
    result = subprocess.run(
        ["sudo", IPSET_BIN, "add", "allowed_internet", AKURA_IP, "-exist"],
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        log.error("ipset add akura failed: %s", result.stderr.decode())


def reblock_akura() -> None:
    """Remove akura_malice from allowed_internet."""
    result = subprocess.run(
        ["sudo", IPSET_BIN, "del", "allowed_internet", AKURA_IP],
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        log.error("ipset del akura failed: %s", result.stderr.decode())


def schedule_akura_reblock(hours: float) -> None:
    """Schedule a transient systemd timer to reblock akura after the session ends."""
    seconds = int(hours * 3600)
    script_path = Path(__file__).parent / "reblock_akura.sh"

    # Cancel any existing timer so sessions don't stack
    subprocess.run(
        ["sudo", "systemctl", "stop", "akura-reblock.timer"],
        check=False,
        capture_output=True,
    )

    result = subprocess.run(
        [
            "sudo", "systemd-run",
            f"--on-active={seconds}s",
            "--unit=akura-reblock",
            "/bin/bash", str(script_path),
        ],
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        log.error("systemd-run akura reblock failed: %s", result.stderr.decode())
