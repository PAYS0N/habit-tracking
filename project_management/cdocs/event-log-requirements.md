# Event Log Architecture — Requirements Notes

## Context

The current flat `checkins` schema has required full rewrites twice as requirements evolved. The goal is a stable data model that can absorb new event types and metrics without schema migrations or data loss.

## Core Constraints

- **Sparse data is valid.** Logging 1 food event does not imply only 1 meal occurred. The system must never assume completeness of optional event types.
- **Minimum required, maximum optional.** The morning gate enforces a small required set (sleep + mood at minimum). Everything else is voluntary and can be logged as little or as much as desired.
- **Easy processing.** Analysis will be done in Python scripts, not raw SQL. JSON fields are acceptable since `json.loads()` is trivial in Python.
- **No schema changes for new event types.** Adding a new thing to track should not require `ALTER TABLE` or new tables.

## Architectural Direction (Agreed)

- Single `events` table — everything is an event, including mood/energy/anxiety snapshots and sleep.
- No separate `daily_log` table. Aggregation is done at query time via Python or SQLite views.
- Morning gate form = batch insert of required events (sleep, mood) + ipset unlock. The "confirm yesterday's counters" section goes away — meals/exercise are individual events, not counters.
- Existing DB can be wiped. No data worth preserving.

## Event Types Discussed

### Sleep (morning, required, structured)
Complex multi-field event logged once per day at morning checkin. Fields:
- `shower_end` — HH:MM or `no_shower` flag
- `fell_asleep` — HH:MM or `no_sleep` flag (grouped with wake time)
- `sleep_end` — HH:MM (wake time)
- `nightmares` — boolean
- `melatonin` — boolean (taken last night)

Sleep hours derived from `fell_asleep` → `sleep_end`, not stored.

### Mood / Energy / Anxiety (snapshot, optional, repeatable)
1–10 scale. Can be logged multiple times per day — each is a discrete event recording state at that moment. Morning checkin logs the first of the day (required for gate).

### Food (optional, sparse)
Per-item/meal event. Fields: name, `is_dairy` (boolean), `is_full_meal` (boolean, vs snack). Dairy flag is for health correlation (inflammation, sleep quality). Logging is sparse by design — not every meal needs to be logged.

### Headache (optional, span event)
Has a start time and optional end time, which may be logged separately. Multiple logging modes:
- "Just started" — start = now, end unknown
- "Started at HH:MM" — backdated start, end unknown
- "Started at HH:MM, ended at HH:MM" — complete span entered retroactively
- Implies the ability to close an open headache later

Fields: severity, start time, end time (optional at log time), medicine taken (boolean), medicine time (optional).

### Others (mentioned, not yet specified)
- Exercise — type, duration
- Coffee — currently a daily counter; may become timestamped individual events
- Play / leisure session — not yet specified

## Open Questions

- **Headache end time:** Update existing event in place (simpler, loses audit trail) vs. log a linked "end" event with a parent reference (full audit trail, more complex queries)?
- **Medicine:** Property of the headache event, or a standalone event type? Standalone is more honest if medicines are taken for other reasons.
- **Coffee:** Stays as a morning boolean/count on the sleep event, or becomes individual timestamped events throughout the day?
- **Morning gate minimum:** Sleep + mood confirmed as the direction, but exact required fields not finalized.
- **Headache severity scale:** 1–5 or 1–10?

## What Goes Away

- The `submission_number` / counter model entirely.
- "Confirm yesterday's counters" morning form section.
- Counter validation logic (can-only-increase enforcement).
- The distinction between morning form and update form may simplify significantly — the home page just provides buttons to log events.
