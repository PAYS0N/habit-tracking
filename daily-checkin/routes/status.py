import subprocess

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from config import DEVICES, IPSET_BIN
from database import get_db, has_morning_gate
from utils import get_event_date

router = APIRouter()


@router.get("/status", response_class=JSONResponse)
async def status():
    conn = await get_db()
    today_date = get_event_date()
    today_submitted = await has_morning_gate(conn, today_date)
    blocked = False
    for ip in DEVICES:
        result = subprocess.run(
            ["sudo", IPSET_BIN, "test", "allowed_internet", ip],
            check=False,
            capture_output=True,
        )
        if result.returncode != 0:
            blocked = True
            break
    return {"blocked": blocked, "today_submitted": today_submitted}
