from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from config import STATIC_DIR, SUMMARY_COUNTER_FIELDS
from database import get_db, get_latest_summary, has_morning_gate, insert_event
from utils import get_event_date

router = APIRouter()


@router.get("/update", response_class=HTMLResponse)
async def update_form():
    form_html = (STATIC_DIR / "update.html").read_text()
    conn = await get_db()
    today_date = get_event_date()

    summary = await get_latest_summary(conn, today_date)
    if summary:
        for field in SUMMARY_COUNTER_FIELDS:
            val = summary.get(field)
            if val is not None:
                form_html = form_html.replace(
                    f'id="{field}"', f'id="{field}" value="{val}"'
                )

    return HTMLResponse(content=form_html)


@router.post("/update", response_class=HTMLResponse)
async def update_submit(
    request: Request,
    mood: Optional[int] = Form(None),
    energy: Optional[int] = Form(None),
    anxiety: Optional[int] = Form(None),
    coffee: Optional[int] = Form(None),
    intrusive: Optional[int] = Form(None),
    meals: Optional[int] = Form(None),
    snacks: Optional[int] = Form(None),
    exercise_minutes: Optional[int] = Form(None),
    sunlight_minutes: Optional[int] = Form(None),
    hours_worked: Optional[float] = Form(None),
):
    conn = await get_db()
    today_date = get_event_date()
    tomorrow_date = (date.fromisoformat(today_date) + timedelta(days=1)).isoformat()
    now = datetime.now().isoformat()

    # Lock check: reject if tomorrow has morning gate
    if await has_morning_gate(conn, tomorrow_date):
        return HTMLResponse(
            content="<p style='color:red'>Today's checkin is finalized. No further updates allowed.</p>",
            status_code=400,
        )

    # Counter validation
    current_summary = await get_latest_summary(conn, today_date)
    current = current_summary or {}
    submitted_counters = {
        "coffee": coffee,
        "intrusive": intrusive,
        "meals": meals,
        "snacks": snacks,
        "exercise_minutes": exercise_minutes,
        "sunlight_minutes": sunlight_minutes,
        "hours_worked": hours_worked,
    }

    # Layer 1: validate against latest daily_summary
    for field in SUMMARY_COUNTER_FIELDS:
        new_val = submitted_counters[field]
        if new_val is None:
            continue
        existing = current.get(field, 0)
        if new_val < existing:
            return HTMLResponse(
                content=f"<p style='color:red'>{field} cannot decrease (current: {existing}, submitted: {new_val}).</p>",
                status_code=400,
            )

    # Layer 2: validate against individual events (coffee and intrusive only)
    coffee_event_count_row = await conn.execute_fetchall(
        "SELECT COUNT(*) as c FROM events WHERE event_type = 'coffee' AND event_date = ?",
        (today_date,),
    )
    coffee_event_count = coffee_event_count_row[0]["c"] if coffee_event_count_row else 0
    if coffee is not None and coffee < coffee_event_count:
        return HTMLResponse(
            content=f"<p style='color:red'>Coffee count cannot be less than {coffee_event_count} individual logged events.</p>",
            status_code=400,
        )

    intrusive_event_count_row = await conn.execute_fetchall(
        "SELECT COUNT(*) as c FROM events WHERE event_type = 'intrusive' AND event_date = ?",
        (today_date,),
    )
    intrusive_event_count = (
        intrusive_event_count_row[0]["c"] if intrusive_event_count_row else 0
    )
    if intrusive is not None and intrusive < intrusive_event_count:
        return HTMLResponse(
            content=f"<p style='color:red'>Intrusive count cannot be less than {intrusive_event_count} individual logged events.</p>",
            status_code=400,
        )

    # Layer 2 (continued): validate hours_worked against sum of individual work events
    work_hours_row = await conn.execute_fetchall(
        "SELECT COALESCE(SUM(CAST(json_extract(data, '$.hours') AS REAL)), 0) as total "
        "FROM events WHERE event_type = 'work' AND event_date = ?",
        (today_date,),
    )
    work_hours_total = work_hours_row[0]["total"] if work_hours_row else 0
    if hours_worked is not None and hours_worked < work_hours_total:
        return HTMLResponse(
            content=f"<p style='color:red'>Hours worked cannot be less than {work_hours_total:.1f}h from individual work events.</p>",
            status_code=400,
        )

    # Insert snapshot events (if provided)
    if mood is not None:
        await insert_event(conn, "mood", today_date, now, {"value": mood}, "update")
    if energy is not None:
        await insert_event(conn, "energy", today_date, now, {"value": energy}, "update")
    if anxiety is not None:
        await insert_event(conn, "anxiety", today_date, now, {"value": anxiety}, "update")

    # Insert daily_summary only if any counter changed
    any_changed = False
    new_summary_data = {}
    for field in SUMMARY_COUNTER_FIELDS:
        submitted = submitted_counters[field]
        current_val = current.get(field, 0)
        if submitted is not None:
            if submitted != current_val:
                any_changed = True
            new_summary_data[field] = submitted
        else:
            new_summary_data[field] = current_val

    if any_changed:
        await insert_event(conn, "daily_summary", today_date, now, new_summary_data, "update")

    await conn.commit()

    return HTMLResponse(
        content=f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Update Saved</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
               max-width: 480px; margin: 40px auto; padding: 0 16px; text-align: center;
               background: #0d1117; color: #c9d1d9; }}
        .success {{ background: #0d2818; border: 1px solid #238636; border-radius: 8px;
                    padding: 24px; margin-top: 40px; }}
        h1 {{ color: #58a6ff; }}
        a {{ color: #58a6ff; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
    </style>
</head>
<body>
    <div class="success">
        <h1>Update Saved</h1>
        <p>Submitted for <strong>{today_date}</strong>.</p>
        <a href="/update">Submit another update</a> · <a href="/history">View history</a>
    </div>
</body>
</html>"""
    )
