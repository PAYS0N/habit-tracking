CREATE TABLE IF NOT EXISTS checkins (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    date              TEXT NOT NULL UNIQUE,   -- YYYY-MM-DD
    submitted_at      TEXT,                   -- ISO 8601 timestamp; NULL = backfilled
    device_ip         TEXT,                   -- submitting device IP; NULL = backfilled

    -- Sleep
    sleep_hours       REAL,                   -- e.g. 7.5
    sleep_start       TEXT,                   -- HH:MM (lights out)
    sleep_end         TEXT,                   -- HH:MM (wake time)
    nightmares        INTEGER,                -- 0/1 boolean

    -- Mood & mental state
    mood              INTEGER,                -- 1-10
    energy            INTEGER,                -- 1-10
    anxiety           INTEGER,                -- 1-10
    intrusive         INTEGER,                -- 0-5 (0=none, 5=severe/frequent)

    -- Substances
    coffee            INTEGER,                -- 0/1
    melatonin         INTEGER,                -- 0/1

    -- Yesterday's activity
    meals_yesterday   INTEGER,
    snacks_yesterday  INTEGER,
    exercise_minutes  INTEGER,                -- intentional activity only
    sunlight_minutes  INTEGER,                -- direct sun during daylight hours only
    hours_worked      REAL,                   -- yesterday's working hours

    UNIQUE(date)
);
