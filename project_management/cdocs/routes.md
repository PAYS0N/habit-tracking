# Daily Checkin — API Routes

All routes use `APIRouter`, included in `main.py`. See [daily-checkin-forms.md](daily-checkin-forms.md) for form field details.

## GET /
Returns `static/home.html`. No DB queries. Two sections: Checkin buttons (→ `/checkin`, `/history`) and Quick Log (Food, Coffee, Headache, Bowel, Work, Relax inline forms). Quick Log forms POST to `/event/{type}` and show a brief "Logged!" banner on success.

## GET /checkin
Checks if today has a `sleep` event with `source='morning_gate'`. If yes, redirects to `/update` (303). Otherwise serves `static/form.html` with yesterday's `daily_summary` counter values injected into `yesterday_*` fields.

## POST /submit
Validates sleep fields (shower or no_shower; sleep times or no_sleep). Validates yesterday counters don't decrease from previous summary. Batch-inserts (all `source='morning_gate'`):
1. `sleep` event — today
2. `mood`, `energy`, `anxiety` events — today
3. `daily_summary` — yesterday (all 7 fields; coffee carried forward from previous summary, default 0)
4. `daily_summary` — today (only if any "Today So Far" field is non-zero)

Then calls `firewall.unblock_all()`. Returns HTML confirmation with link to `/update`.

## GET /update
Serves `static/update.html`. Pre-fills counter fields from today's latest `daily_summary`.

## POST /update
1. Lock check: if tomorrow has `sleep` event with `source='morning_gate'`, reject 400 (today finalized).
2. Counter validation (two layers):
   - Each submitted counter >= latest `daily_summary` value for today (default 0)
   - `coffee`/`intrusive` >= count of individual events for today; `hours_worked` >= sum of `work.hours`
3. Inserts `mood`/`energy`/`anxiety` events if values were provided.
4. Inserts `daily_summary` for today if any counter changed (pre-fills unchanged fields from current summary).

All `source='update'`. No firewall changes.

## GET /history
All events ordered `event_date DESC, logged_at DESC`. Table: Date | Time (HH:MM) | Source (gate/upd/man) | Type | Details. Details formatted by `utils.format_event_details()`. Dark theme; sleep rows blue-tinted, daily_summary rows green-tinted.

## GET /status
Returns `{"blocked": bool, "today_submitted": bool}`. Checks `allowed_internet` ipset membership for each device IP. `today_submitted` = has morning gate for today's event_date.

## POST /event/food
Fields: `name` (optional), `is_dairy` (0/1), `is_full_meal` (0/1, default 1). Inserts `food` event, `source='manual'`. Returns `{"ok": true}`.

## POST /event/coffee
No fields. Inserts `coffee` event with NULL data, `source='manual'`. Returns `{"ok": true}`.

## POST /event/headache
Fields: `severity` (required 1–10), `started_at` (HH:MM → `occurred_at`), `medicine_taken` (0/1), `medicine_name`, `medicine_time` (HH:MM → `occurred_at`). Inserts `headache` event; if `medicine_taken=1`, also inserts `medicine` event `{name, reason: "headache"}`. Returns `{"ok": true}`.

## POST /event/bowel
Field: `type` (required: `"diarrhea"` or `"constipation"`). Returns 400 if invalid. Returns `{"ok": true}`.

## POST /event/work
Fields: `hours` (required), `mood` (optional 1–10). Inserts `work` event; if mood provided, also inserts `mood` event. Returns `{"ok": true}`.

## POST /event/relax
Fields: `hours` (required), `video_game` (0/1, default false), `mood` (optional 1–10). Inserts `relax` event; if mood provided, also inserts `mood` event. Returns `{"ok": true}`.
