from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from database import get_db
from utils import format_event_details

router = APIRouter()


@router.get("/history", response_class=HTMLResponse)
async def history():
    conn = await get_db()
    rows = await conn.execute_fetchall(
        "SELECT id, event_type, event_date, logged_at, occurred_at, data, source "
        "FROM events ORDER BY event_date DESC, logged_at DESC"
    )

    def fmt_time(logged_at: str) -> str:
        """Extract HH:MM from ISO 8601 timestamp."""
        if logged_at and len(logged_at) > 10:
            return logged_at[11:16]
        return logged_at or "—"

    def fmt_source(source: str) -> str:
        """Format source as short badge."""
        if source == "morning_gate":
            return "gate"
        elif source == "update":
            return "upd"
        elif source == "manual":
            return "man"
        return source or "—"

    table_rows = ""
    for row in rows:
        time_str = fmt_time(row["logged_at"])
        source_str = fmt_source(row["source"])
        details = format_event_details(row["event_type"], row["data"])
        table_rows += (
            f"<tr>"
            f'<td>{row["event_date"]}</td>'
            f'<td>{time_str}</td>'
            f"<td>{source_str}</td>"
            f'<td>{row["event_type"]}</td>'
            f"<td>{details}</td>"
            f"</tr>\n"
        )

    return HTMLResponse(
        content=f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Checkin History</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            padding: 16px;
            background: #0d1117; color: #c9d1d9;
        }}
        h1 {{ color: #58a6ff; margin-bottom: 20px; text-align: center; font-size: 1.5rem; }}
        .back-link {{ display: block; text-align: center; margin-bottom: 20px; color: #58a6ff;
                      text-decoration: none; font-size: 0.95rem; }}
        .back-link:hover {{ text-decoration: underline; }}
        .table-wrap {{ overflow-x: auto; border-radius: 8px; border: 1px solid #21262d; }}
        table {{ border-collapse: collapse; width: 100%; min-width: 600px; font-size: 0.85rem; }}
        thead tr {{ background: #161b22; }}
        th {{
            padding: 10px 12px; text-align: left; color: #8b949e;
            font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em;
            border-bottom: 1px solid #30363d; white-space: nowrap;
        }}
        td {{ padding: 9px 12px; border-bottom: 1px solid #21262d; }}
        tbody tr:last-child td {{ border-bottom: none; }}
        tbody tr:hover td {{ background: #161b22; }}
        tr.event-sleep td {{ background: #0d1d2d; }}
        tr.event-daily_summary td {{ background: #0d2d1d; }}
        .count {{ color: #8b949e; font-size: 0.85rem; text-align: center; margin-top: 12px; }}
    </style>
</head>
<body>
    <h1>Checkin History</h1>
    <a href="/" class="back-link">&larr; Back to home</a>
    <div class="table-wrap">
        <table>
            <thead>
                <tr>
                    <th>Date</th>
                    <th>Time</th>
                    <th>Source</th>
                    <th>Type</th>
                    <th>Details</th>
                </tr>
            </thead>
            <tbody>
{table_rows}            </tbody>
        </table>
    </div>
    <p class="count">{len(rows)} event{"s" if len(rows) != 1 else ""} total</p>
</body>
</html>"""
    )
