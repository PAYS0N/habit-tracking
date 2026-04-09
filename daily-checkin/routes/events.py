from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Form
from fastapi.responses import JSONResponse

from database import get_db, get_video_game_hours_by_day, insert_event
from firewall import schedule_akura_reblock, unblock_akura
from utils import get_event_date

_VIDEO_GAME_TIER_CAPS = [4, 2, 2, 1, 1, 1, 1]

router = APIRouter()


@router.post("/event/food")
async def event_food(
    name: Optional[str] = Form(None),
    is_dairy: Optional[int] = Form(None),
    is_full_meal: Optional[int] = Form(None),
):
    conn = await get_db()
    event_date = get_event_date()
    now = datetime.now().isoformat()
    data = {
        "name": name or None,
        "is_dairy": bool(is_dairy) if is_dairy is not None else None,
        "is_full_meal": bool(is_full_meal) if is_full_meal is not None else True,
    }
    await insert_event(conn, "food", event_date, now, data, "manual")
    await conn.commit()
    return JSONResponse({"ok": True})


@router.post("/event/coffee")
async def event_coffee():
    conn = await get_db()
    event_date = get_event_date()
    now = datetime.now().isoformat()
    await insert_event(conn, "coffee", event_date, now, None, "manual")
    await conn.commit()
    return JSONResponse({"ok": True})


@router.post("/event/headache")
async def event_headache(
    severity: int = Form(...),
    started_at: Optional[str] = Form(None),
    medicine_taken: Optional[int] = Form(None),
    medicine_name: Optional[str] = Form(None),
    medicine_time: Optional[str] = Form(None),
):
    conn = await get_db()
    event_date = get_event_date()
    now = datetime.now().isoformat()

    occurred_at = None
    if started_at:
        occurred_at = f"{event_date}T{started_at}:00"

    await insert_event(
        conn, "headache", event_date, now, {"severity": severity}, "manual",
        occurred_at=occurred_at,
    )

    if medicine_taken:
        med_occurred_at = None
        if medicine_time:
            med_occurred_at = f"{event_date}T{medicine_time}:00"
        await insert_event(
            conn, "medicine", event_date, now,
            {"name": medicine_name or None, "reason": "headache"},
            "manual",
            occurred_at=med_occurred_at,
        )

    await conn.commit()
    return JSONResponse({"ok": True})


@router.post("/event/bowel")
async def event_bowel(type: str = Form(...)):
    if type not in ("diarrhea", "constipation"):
        return JSONResponse({"ok": False, "error": "Invalid type"}, status_code=400)
    conn = await get_db()
    event_date = get_event_date()
    now = datetime.now().isoformat()
    await insert_event(conn, "bowel", event_date, now, {"type": type}, "manual")
    await conn.commit()
    return JSONResponse({"ok": True})


@router.post("/event/work")
async def event_work(
    hours: float = Form(...),
    mood: Optional[int] = Form(None),
):
    conn = await get_db()
    event_date = get_event_date()
    now = datetime.now().isoformat()
    await insert_event(conn, "work", event_date, now, {"hours": hours}, "manual")
    if mood is not None:
        await insert_event(conn, "mood", event_date, now, {"value": mood}, "manual")
    await conn.commit()
    return JSONResponse({"ok": True})


@router.post("/event/relax")
async def event_relax(
    hours: float = Form(...),
    video_game: Optional[int] = Form(None),
    mood: Optional[int] = Form(None),
):
    conn = await get_db()
    event_date = get_event_date()
    now = datetime.now().isoformat()
    is_video_game = bool(video_game) if video_game is not None else False

    if is_video_game:
        hours_by_day = await get_video_game_hours_by_day(conn)
        today_existing = hours_by_day.get(event_date, 0.0)
        today_proposed = today_existing + hours

        # Build the full 7-day picture with today's proposed total
        daily_totals = {d: h for d, h in hours_by_day.items() if d != event_date}
        daily_totals[event_date] = today_proposed

        sorted_totals = sorted(daily_totals.values(), reverse=True)
        for i, total in enumerate(sorted_totals):
            if total > _VIDEO_GAME_TIER_CAPS[i]:
                return JSONResponse(
                    {"ok": False, "error": "Weekly video game budget exceeded"},
                    status_code=400,
                )

    data = {"hours": hours, "video_game": is_video_game}
    await insert_event(conn, "relax", event_date, now, data, "manual")
    if mood is not None:
        await insert_event(conn, "mood", event_date, now, {"value": mood}, "manual")
    await conn.commit()

    if is_video_game:
        unblock_akura()
        schedule_akura_reblock(hours)

    return JSONResponse({"ok": True})
