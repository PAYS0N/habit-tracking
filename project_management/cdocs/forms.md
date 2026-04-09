# Daily Checkin — Forms

## Morning Gate Form (`static/form.html` → POST /submit)

Four sections in order:

**1. Confirm Yesterday** (required)
Fields: `yesterday_intrusive`, `yesterday_meals`, `yesterday_snacks`, `yesterday_exercise_minutes`, `yesterday_sunlight_minutes`, `yesterday_hours_worked`. Pre-filled from yesterday's latest `daily_summary`. Each value must be >= corresponding field in previous summary (default 0 if none).

Note: `yesterday_coffee` is not on the form. Carried forward from previous summary (default 0) server-side.

**2. Last Night** (required)
Either `shower_end` (HH:MM) or `no_shower=1`. Either both `fell_asleep` + `sleep_end` (HH:MM) or `no_sleep=1`. Plus `nightmares` and `melatonin` (both required).

**3. Mental State** (required)
`mood`, `energy`, `anxiety` — integers 1–10, all required.

**4. Today So Far** (optional)
`coffee`, `intrusive`, `meals`, `snacks`, `exercise_minutes`, `sunlight_minutes`, `hours_worked`. All optional. A `daily_summary` event for today is only created if at least one field is non-zero.

## Update Form (`static/update.html` → POST /update)

**Mental State** (optional): `mood`, `energy`, `anxiety`. Left blank to skip. Each submitted value creates an event.

**Today So Far** (optional, pre-filled): `coffee`, `intrusive`, `meals`, `snacks`, `exercise_minutes`, `sunlight_minutes`, `hours_worked`. Pre-filled from today's latest `daily_summary`. A new `daily_summary` event is created only if any counter differs from the current summary.

Lock: rejected with 400 if tomorrow's morning gate has been submitted.

## Home Page (`static/home.html`)

**Quick Log**: 2×3 grid — Food, Coffee, Headache, Bowel, Work, Relax. Each button expands an inline form below the grid. Coffee submits immediately via `fetch` (no form). Work and Relax include optional `mood` field (server inserts a separate `mood` event). All Quick Log forms POST to `/event/{type}`.

## UI Theme

Dark GitHub theme across all pages: `#0d1117` background, `#c9d1d9` text, `#58a6ff` accent. Mobile-first, `max-width: 480px`. Form confirmation pages include a link back to `/update` or `/history`.
