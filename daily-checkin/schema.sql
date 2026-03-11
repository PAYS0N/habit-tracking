CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type  TEXT NOT NULL,
    event_date  TEXT NOT NULL,
    logged_at   TEXT NOT NULL,
    occurred_at TEXT,
    ended_at    TEXT,
    data        TEXT,
    source      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_type_date ON events (event_type, event_date);
CREATE INDEX IF NOT EXISTS idx_events_date ON events (event_date);
