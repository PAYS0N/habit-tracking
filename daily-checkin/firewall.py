import logging
import subprocess

from config import DEVICES, IPSET_BIN, IPTABLES_BIN, PORT

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
