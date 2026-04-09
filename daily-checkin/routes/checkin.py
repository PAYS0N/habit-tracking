from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from config import STATIC_DIR, SUMMARY_COUNTER_FIELDS
from database import get_db, get_latest_summary, has_morning_gate, insert_event
from firewall import unblock_all
from utils import get_event_date

router = APIRouter()


@router.get("/checkin", response_class=HTMLResponse)
async def checkin():
    conn = await get_db()
    today_date = get_event_date()
    yesterday_date = (date.fromisoformat(today_date) - timedelta(days=1)).isoformat()

    # Check if today's morning gate already completed
    if await has_morning_gate(conn, today_date):
        return RedirectResponse(url="/update", status_code=303)

    form_html = (STATIC_DIR / "form.html").read_text()

    # Autofill yesterday's counters from latest daily_summary
    summary = await get_latest_summary(conn, yesterday_date)
    if summary:
        # Autofill SUMMARY_COUNTER_FIELDS except coffee (not on form's yesterday section)
        yesterday_fields = [f for f in SUMMARY_COUNTER_FIELDS if f != "coffee"]
        for field in yesterday_fields:
            val = summary.get(field)
            if val is not None:
                form_html = form_html.replace(
                    f'id="yesterday_{field}"', f'id="yesterday_{field}" value="{val}"'
                )

    return HTMLResponse(content=form_html)


@router.post("/submit", response_class=HTMLResponse)
async def submit(
    request: Request,
    # Yesterday confirmation (required)
    yesterday_intrusive: int = Form(...),
    yesterday_meals: int = Form(...),
    yesterday_snacks: int = Form(...),
    yesterday_exercise_minutes: int = Form(...),
    yesterday_sunlight_minutes: int = Form(...),
    yesterday_hours_worked: float = Form(...),
    # Last night (sleep)
    shower_end: Optional[str] = Form(None),
    no_shower: Optional[int] = Form(None),
    fell_asleep: Optional[str] = Form(None),
    sleep_end: Optional[str] = Form(None),
    no_sleep: Optional[int] = Form(None),
    nightmares: int = Form(...),
    melatonin: int = Form(...),
    # Mental state (required)
    mood: int = Form(...),
    energy: int = Form(...),
    anxiety: int = Form(...),
    # Today so far (all optional)
    coffee: Optional[int] = Form(None),
    intrusive: Optional[int] = Form(None),
    meals: Optional[int] = Form(None),
    snacks: Optional[int] = Form(None),
    exercise_minutes: Optional[int] = Form(None),
    sunlight_minutes: Optional[int] = Form(None),
    hours_worked: Optional[float] = Form(None),
):
    # Server-side sleep validation
    if not shower_end and not no_shower:
        return HTMLResponse(
            content="<p style='color:red'>Either provide shower end time or check 'No shower'.</p>",
            status_code=400,
        )
    if (not fell_asleep or not sleep_end) and not no_sleep:
        return HTMLResponse(
            content="<p style='color:red'>Either provide both fell asleep and wake time, or check 'No sleep'.</p>",
            status_code=400,
        )

    conn = await get_db()
    today_date = get_event_date()
    yesterday_date = (date.fromisoformat(today_date) - timedelta(days=1)).isoformat()
    now = datetime.now().isoformat()

    # Counter validation for yesterday's confirmed values
    prev_yesterday_summary = await get_latest_summary(conn, yesterday_date)
    yesterday_confirmed = {
        "intrusive": yesterday_intrusive,
        "meals": yesterday_meals,
        "snacks": yesterday_snacks,
        "exercise_minutes": yesterday_exercise_minutes,
        "sunlight_minutes": yesterday_sunlight_minutes,
        "hours_worked": yesterday_hours_worked,
    }
    if prev_yesterday_summary:
        for field, new_val in yesterday_confirmed.items():
            existing = prev_yesterday_summary.get(field, 0)
            if existing is not None and new_val < existing:
                return HTMLResponse(
                    content=f"<p style='color:red'>Yesterday's {field} cannot decrease (current: {existing}, submitted: {new_val}).</p>",
                    status_code=400,
                )

    # Batch insert events
    # 1. sleep event for today
    sleep_data = {
        "shower_end": shower_end,
        "no_shower": bool(no_shower),
        "fell_asleep": fell_asleep,
        "sleep_end": sleep_end,
        "no_sleep": bool(no_sleep),
        "nightmares": bool(nightmares),
        "melatonin": bool(melatonin),
    }
    await insert_event(conn, "sleep", today_date, now, sleep_data, "morning_gate")

    # 2. mood, energy, anxiety events for today
    await insert_event(conn, "mood", today_date, now, {"value": mood}, "morning_gate")
    await insert_event(conn, "energy", today_date, now, {"value": energy}, "morning_gate")
    await insert_event(conn, "anxiety", today_date, now, {"value": anxiety}, "morning_gate")

    # 3. daily_summary for yesterday (required)
    # Carry forward coffee from previous summary (default 0)
    yesterday_coffee = (prev_yesterday_summary or {}).get("coffee", 0)
    yesterday_summary_data = {
        "meals": yesterday_meals,
        "snacks": yesterday_snacks,
        "coffee": yesterday_coffee,
        "intrusive": yesterday_intrusive,
        "exercise_minutes": yesterday_exercise_minutes,
        "sunlight_minutes": yesterday_sunlight_minutes,
        "hours_worked": yesterday_hours_worked,
    }
    await insert_event(conn, "daily_summary", yesterday_date, now, yesterday_summary_data, "morning_gate")

    # 4. daily_summary for today (optional, only if any counter is non-zero)
    today_counters = {
        "coffee": coffee,
        "intrusive": intrusive,
        "meals": meals,
        "snacks": snacks,
        "exercise_minutes": exercise_minutes,
        "sunlight_minutes": sunlight_minutes,
        "hours_worked": hours_worked,
    }
    if any(v is not None and v != 0 for v in today_counters.values()):
        today_summary_data = {
            k: (v if v is not None else 0) for k, v in today_counters.items()
        }
        await insert_event(conn, "daily_summary", today_date, now, today_summary_data, "morning_gate")

    await conn.commit()

    unblock_all()

    return HTMLResponse(
        content=f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Checkin Complete</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
               max-width: 480px; margin: 40px auto; padding: 0 16px; text-align: center;
               background: #0d1117; color: #c9d1d9; }}
        .success {{ background: #0d2818; border: 1px solid #238636; border-radius: 8px;
                    padding: 24px; margin-top: 40px; }}
        h1 {{ color: #58a6ff; }}
        a {{ color: #58a6ff; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
        .update-link {{ display: block; margin-top: 16px; font-size: 0.95rem; }}
    </style>
</head>
<body>
    <div class="success">
        <h1>Checkin Complete</h1>
        <p>Submitted for <strong>{today_date}</strong>.</p>
        <p>All devices are unblocked. Internet restored.</p>
        <a href="/update" class="update-link">Submit another update later today →</a>
    </div>
</body>
</html>"""
    )
