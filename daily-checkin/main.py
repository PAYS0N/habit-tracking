import logging

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from config import PORT, STATIC_DIR
from database import close_db, get_db, migrate_if_needed
from routes.checkin import router as checkin_router
from routes.events import router as events_router
from routes.history import router as history_router
from routes.status import router as status_router
from routes.update import router as update_router

log = logging.getLogger("daily-checkin")
logging.basicConfig(level=logging.INFO)

app = FastAPI()

app.include_router(checkin_router)
app.include_router(update_router)
app.include_router(events_router)
app.include_router(history_router)
app.include_router(status_router)


@app.on_event("startup")
async def startup():
    conn = await get_db()
    await migrate_if_needed(conn)
    log.info("Daily checkin service started on port %d", PORT)


@app.on_event("shutdown")
async def shutdown():
    await close_db()


@app.get("/", response_class=HTMLResponse)
async def home():
    return HTMLResponse((STATIC_DIR / "home.html").read_text())
