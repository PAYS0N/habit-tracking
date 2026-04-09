# Event Types — Reference

Single `events` table. Each row has `event_type`, `event_date` (5am boundary), `logged_at`, `occurred_at` (optional), `ended_at` (span events), `data` (JSON or NULL), `source` (`morning_gate`/`update`/`manual`).

## Event Type Catalog

| Event Type | Source | Data Schema |
|---|---|---|
| `sleep` | morning_gate | `{shower_end, no_shower, fell_asleep, sleep_end, no_sleep, nightmares, melatonin}` |
| `mood` | any | `{value: 1–10}` |
| `energy` | any | `{value: 1–10}` |
| `anxiety` | any | `{value: 1–10}` |
| `daily_summary` | morning_gate / update | `{meals, snacks, coffee, intrusive, exercise_minutes, sunlight_minutes, hours_worked}` |
| `coffee` | manual | NULL |
| `food` | manual | `{name?, is_dairy?, is_full_meal?}` |
| `headache` | manual | `{severity: 1–10}` |
| `medicine` | manual | `{name, reason?}` |
| `bowel` | manual | `{type: "diarrhea"\|"constipation"}` |
| `exercise` | manual | `{type?, duration_minutes?}` |
| `intrusive` | manual | NULL |
| `sunlight` | manual | `{duration_minutes?}` |
| `work` | manual | `{hours}` |
| `relax` | manual | `{hours, video_game: bool}` |

## Key Field Schemas

**sleep** — `shower_end`/`no_shower` are conditional (one required). `fell_asleep`/`sleep_end`/`no_sleep` are conditional (either both times or no_sleep=true). Sleep hours are computed at render time from `fell_asleep`→`sleep_end` (midnight crossover handled); not stored.

**daily_summary** — All 7 fields (`meals`, `snacks`, `coffee`, `intrusive`, `exercise_minutes`, `sunlight_minutes`, `hours_worked`) must be present when written. Latest per `event_date` is ground truth for daily counts. Counter validation: each field must be >= the same field in the previous summary for that date.

**headache** — `occurred_at` = start time. `ended_at` = end time (NULL if active, updated in place when closed). No linked end event — single-row span.

**medicine** — Standalone, not tied to a headache row. Temporal proximity provides correlation. `reason` e.g. "headache", "anxiety".

**food** — `is_full_meal` defaults to true (meal vs snack). `is_dairy` for inflammation/sleep correlation.

## Design Notes

- **Individual events (coffee, intrusive, food) are sparse.** Not every occurrence is logged in real time. `daily_summary` totals are ground truth.
- **Medicine is standalone** so it can represent medicines taken for any reason without requiring a headache event to exist.
- **Headache end time is updated in place** (no join needed for duration; no audit trail requirement).
- **No schema changes for new event types** — just define the JSON keys and insert rows.
