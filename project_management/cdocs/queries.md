# Daily Checkin — Query Patterns

Common queries against the `events` table. Prefer Python `json.loads()` over SQLite JSON functions for analysis scripts — cleaner and easier to handle edge cases.

## Has morning gate been completed today?

```sql
SELECT 1 FROM events
WHERE event_type = 'sleep' AND event_date = :today AND source = 'morning_gate'
LIMIT 1;
```

## Latest daily summary for a date

```sql
SELECT data FROM events
WHERE event_type = 'daily_summary' AND event_date = :date
ORDER BY logged_at DESC LIMIT 1;
```

## Average sleep hours (last 30 days) — Python preferred

```python
rows = conn.execute(
    "SELECT data FROM events WHERE event_type = 'sleep'"
    " AND event_date >= date(?, '-30 days')", [today]
).fetchall()
hours = [float(calc_sleep_hours(d["fell_asleep"], d["sleep_end"]))
         for r in rows
         for d in [json.loads(r["data"])]
         if not d.get("no_sleep") and calc_sleep_hours(d.get("fell_asleep"), d.get("sleep_end")) != "—"]
```

## Individual event counts today (used for counter validation)

```sql
-- Coffee events logged today
SELECT COUNT(*) FROM events WHERE event_type = 'coffee' AND event_date = :today;

-- Sum of work session hours today
SELECT COALESCE(SUM(CAST(json_extract(data, '$.hours') AS REAL)), 0)
FROM events WHERE event_type = 'work' AND event_date = :today;
```

## Open headaches (started, not ended)

```sql
SELECT id, event_date, occurred_at, json_extract(data, '$.severity') AS severity
FROM events WHERE event_type = 'headache' AND ended_at IS NULL
ORDER BY logged_at DESC;
```

## Days where anxiety exceeded a threshold

```sql
SELECT DISTINCT event_date FROM events
WHERE event_type = 'anxiety' AND json_extract(data, '$.value') > 7
ORDER BY event_date DESC;
```

## Weekly summary rollup (Python)

```python
rows = conn.execute(
    "SELECT event_date, data FROM events WHERE event_type = 'daily_summary'"
    " AND event_date >= date(?, '-7 days') ORDER BY logged_at DESC", [today]
).fetchall()
# De-duplicate: keep only latest summary per date
seen = {}
for r in rows:
    if r["event_date"] not in seen:
        seen[r["event_date"]] = json.loads(r["data"])
```
