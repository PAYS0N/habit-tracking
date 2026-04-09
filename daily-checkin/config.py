from pathlib import Path

PORT = 8900
DB_PATH = Path(__file__).parent / "checkin.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"
STATIC_DIR = Path(__file__).parent / "static"

DEVICES = ["192.168.22.75", "192.168.22.50", "192.168.22.52"]

# Binary paths — verify on the Pi; adjust if located at /usr/sbin/ instead
IPSET_BIN = "/usr/sbin/ipset"
IPTABLES_BIN = "/usr/sbin/iptables"

SUMMARY_COUNTER_FIELDS = [
    "coffee", "intrusive", "meals", "snacks",
    "exercise_minutes", "sunlight_minutes", "hours_worked",
]
