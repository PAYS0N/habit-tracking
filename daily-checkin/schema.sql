CREATE TABLE IF NOT EXISTS checkins (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    date                TEXT NOT NULL,              -- YYYY-MM-DD (Pi local time)
    submission_number   INTEGER NOT NULL DEFAULT 1, -- 1 = morning gate; 2+ = updates
    submitted_at        TEXT,                       -- ISO 8601; NULL = backfilled
    device_ip           TEXT,                       -- NULL = backfilled

    -- Sleep (morning form only; NULL on update submissions)
    shower_end          TEXT,                       -- HH:MM or NULL
    no_shower           INTEGER,                    -- 0/1; required on morning form if shower_end NULL
    fell_asleep         TEXT,                       -- HH:MM or NULL
    sleep_end           TEXT,                       -- HH:MM (wake time) or NULL
    no_sleep            INTEGER,                    -- 0/1; required on morning form if fell_asleep/sleep_end NULL
    nightmares          INTEGER,                    -- 0/1; morning form only
    melatonin           INTEGER,                    -- 0/1; morning form only

    -- Snapshot fields (recorded fresh each submission; blank on next morning's form)
    mood                INTEGER,                    -- 1–10 or NULL
    energy              INTEGER,                    -- 1–10 or NULL
    anxiety             INTEGER,                    -- 1–10 or NULL

    -- Counter fields (can only increase per submission within a day;
    --                 autofilled on next morning's form from prev day's last submission;
    --                 locked after next morning's submission_number=1 is written)
    coffee              INTEGER,                    -- cumulative count (0, 1, 2…)
    intrusive           INTEGER,                    -- 0–5 cumulative (0=none, 5=severe/frequent)
    meals               INTEGER,
    snacks              INTEGER,
    exercise_minutes    INTEGER,                    -- intentional activity only
    sunlight_minutes    INTEGER,                    -- direct sun during daylight hours only
    hours_worked        REAL
);
