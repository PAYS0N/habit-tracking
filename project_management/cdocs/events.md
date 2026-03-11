# Event Types — Reference

Single-table event log. Each row in `events` has `event_type`, `event_date` (5am boundary), `logged_at`, `occurred_at` (optional backdated time), `ended_at` (span events only), `data` (JSON or NULL), and `source` (`morning_gate`, `update`, `manual`).

## Event Type Catalog

| Event Type | Source | Repeatable | Data Schema | Notes |
|---|---|---|---|---|
| `sleep` | morning_gate | No (1/day) | `{shower_end, no_shower, fell_asleep, sleep_end, no_sleep, nightmares, melatonin}` | Required at morning gate. Sleep hours computed from fell_asleep/sleep_end at render time. |
| `mood` | morning_gate / update / manual | Yes (snapshot) | `{value: 1–10}` | Point-in-time snapshot. |
| `energy` | morning_gate / update / manual | Yes (snapshot) | `{value: 1–10}` | Point-in-time snapshot. |
| `anxiety` | morning_gate / update / manual | Yes (snapshot) | `{value: 1–10}` | Point-in-time snapshot. |
| `daily_summary` | morning_gate / update | Yes (per submission) | `{meals, snacks, coffee, intrusive, exercise_minutes, sunlight_minutes, hours_worked}` | Latest per event_date is authoritative count for all counter fields. |
| `coffee` | manual | Yes | NULL | Individual timestamped coffee event. Timing detail. |
| `food` | manual | Yes | `{name?: str, is_dairy?: bool, is_full_meal?: bool}` | Individual meal or snack. is_full_meal defaults to true. |
| `headache` | manual | Yes | `{severity: 1–10}` | Span event. occurred_at = start time. ended_at updated in place when closed. |
| `medicine` | manual | Yes | `{name: str, reason?: str}` | Standalone; not tied to headache row. Temporal proximity provides correlation. |
| `bowel` | manual | Yes | `{type: "diarrhea"\|"constipation"}` | Individual episode. |
| `exercise` | manual | Yes | `{type?: str, duration_minutes?: int}` | Individual session. |
| `intrusive` | manual | Yes | NULL | Individual intrusive thought episode. Timing detail. |
| `sunlight` | manual | Yes | `{duration_minutes?: int}` | Individual sunlight exposure. |
| `work` | manual | Yes | `{hours: real}` | Individual work session. Sum of work.hours must not exceed daily_summary.hours_worked on update. Optional mood snapshot inserted as a separate event. |
| `relax` | manual | Yes | `{hours: real, video_game: bool}` | Individual relaxation session. Optional mood snapshot inserted as a separate event. |

## Field Schemas (verbose)

### sleep
| Key | Type | Notes |
|---|---|---|
| `shower_end` | HH:MM or null | Null if no_shower=true |
| `no_shower` | bool | True if skipped shower |
| `fell_asleep` | HH:MM or null | Null if no_sleep=true |
| `sleep_end` | HH:MM or null | Wake time; null if no_sleep=true |
| `no_sleep` | bool | True if didn't sleep |
| `nightmares` | bool | |
| `melatonin` | bool | Taken the prior night |

### daily_summary
All fields required when written. Latest per event_date is ground truth for daily counts.

| Key | Type |
|---|---|
| `meals` | integer |
| `snacks` | integer |
| `coffee` | integer |
| `intrusive` | integer |
| `exercise_minutes` | integer |
| `sunlight_minutes` | integer |
| `hours_worked` | real |

### food
| Key | Type | Required |
|---|---|---|
| `name` | string | no |
| `is_dairy` | bool | no |
| `is_full_meal` | bool | no (default true) |

### headache
| Key | Type | Required | Notes |
|---|---|---|---|
| `severity` | integer 1–10 | yes | |

`occurred_at` = headache start. `ended_at` = headache end (NULL if active, updated in place).

### medicine
| Key | Type | Required |
|---|---|---|
| `name` | string | yes |
| `reason` | string | no (e.g. "headache", "anxiety") |

### bowel
| Key | Type | Values |
|---|---|---|
| `type` | string | `"diarrhea"` or `"constipation"` |

### work
| Key | Type | Required |
|---|---|---|
| `hours` | real | yes |

### relax
| Key | Type | Required | Notes |
|---|---|---|---|
| `hours` | real | yes | |
| `video_game` | bool | no (default false) | |

## Design Notes

- **Daily summary as ground truth**: individual events (coffee, food, intrusive) are sparse by design. The `daily_summary` event stores reconciled totals and is the authoritative count. Individual events provide optional timing detail.
- **Headache end time — update in place**: closing a headache UPDATEs `ended_at` on the existing row. No linked end event. No joins needed for duration.
- **Medicine — standalone**: medicine can be taken for headaches, anxiety, sleep, or other reasons. Storing as a headache property would force a headache to exist.
- **Coffee / intrusive as individual events**: each is a separate row with timestamp. Daily count derived from individual events or overridden by daily_summary total.
- **Headache severity — 1–10 scale**: consistent with mood, energy, anxiety.
