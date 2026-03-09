# Productivity Guard — Context Document

## Purpose and Architecture

Productivity Guard is a self-hosted, LLM-gated web access control system. It blocks distracting domains at the DNS level by default and allows temporary, scope-limited unblocking through negotiation with a Claude-backed gatekeeper. The system is hybrid: DNS provides hard network-level blocking that bypasses the browser entirely; a Firefox extension provides per-URL-path scope enforcement and the user-facing request UI. Neither component alone is sufficient — DNS can only act on full domains, and the extension can be disabled, but disabling it makes access stricter (DNS still blocks).

The system lives at `/home/pays0n/Documents/Projects/productivity-guard/`. The backend runs as a systemd service (`productivity-guard.service`) under the `pays0n` user, managed by uvicorn at `0.0.0.0:8800`.

## Backend (FastAPI)

**Stack:** Python 3, FastAPI, uvicorn, anthropic SDK (sync client), httpx, aiosqlite, PyYAML, Pydantic v2.

**Startup sequence:** Connects to SQLite DB, connects to HA REST API (failure is non-fatal), writes the full blocklist to `/etc/productivity-guard/blocked_hosts` via `sudo tee`, sends SIGHUP to dnsmasq. On shutdown, re-blocks all domains.

**Config:** `backend/config.yaml` (gitignored). Secrets (Anthropic API key, HA token) go here or in environment variables `ANTHROPIC_API_KEY` and `HA_TOKEN`. Config path overridable via `PG_CONFIG` env var. The example config is `config.example.yaml`.

**Endpoints:**
- `POST /request-access` — receives `{url, reason, device_ip?}` from the extension, runs the full evaluation pipeline, returns `{approved, scope, duration_minutes, message, domain}`.
- `GET /status` — returns active unblocks and force-blocked device IPs.
- `POST /revoke/{domain}` — immediately re-blocks a domain.
- `POST /revoke-all` — re-blocks everything, cancels all timers.
- `GET /history` — today's request log from SQLite.
- `POST /force-block` / `POST /force-unblock` — called by HA automations; force-blocked devices are auto-denied all requests without LLM evaluation, and any active unblocks for that device are immediately revoked.
- `GET /health` — liveness check.
- `POST /debug/prompt` — returns the system prompt and built user message without calling the LLM. Note: this endpoint has a Python name collision with the `/request-access` handler (`async def request_access` is defined twice); both routes are registered correctly because FastAPI captures the function object at decoration time, but the duplicate name is a latent bug.

**Request pipeline:** Checks force-block set → validates domain against conditional list → fetches device info and room from HA → queries DB for today's count and last 5 requests → calls LLM → if approved, calls `blocklist.unblock_domain()` → logs to DB → returns response.

**Known bug:** The always-blocked domain check uses `domain.lstrip("www.")` which strips individual characters from the set `{'w', '.'}` rather than the literal prefix `"www."`. This produces incorrect results for domains containing those characters in unexpected positions (e.g., `"www.woot.com"` strips too many characters). For `www.twitter.com` specifically, it happens to work correctly. Fix: replace with `domain.removeprefix("www.")` or a conditional string slice.

## Blocklist Manager

`blocklist.py` manages `/etc/productivity-guard/blocked_hosts`. It tracks `active_unblocks` as a dict of `domain → ActiveUnblock`. When a domain is unblocked, its www/non-www variant (if present in the config) is also unblocked under the same `ActiveUnblock` object. The hosts file is rewritten by piping content to `sudo tee <path>` (subprocess), then dnsmasq is signaled with `sudo pkill -HUP dnsmasq`. An asyncio task is scheduled to re-block after `duration_minutes * 60` seconds. Re-blocking cancels the timer and rewrites the file. `get_active_unblocks()` deduplicates by `unblock.domain` so www/bare variants appear as one entry.

## LLM Gatekeeper

`llm_gatekeeper.py` uses the synchronous `anthropic.Anthropic` client (not `AsyncAnthropic`), meaning each LLM call blocks the asyncio event loop during the HTTP request. The system prompt is loaded from `system_prompt.txt` at startup; a fallback is used if the file is missing.

The user message injected at request time contains: the URL, the stated reason, current day/time, device name and type, current room, whether a relax window is active, room eligibility (only shown during relax windows), the request number today, and the last 5 requests with their outcomes. Schedule window times (start/end) are not passed to the LLM — it only sees a YES/NO flag.

The system prompt encodes: default DENY posture; JSON-only response format `{approved, scope, duration_minutes, message}`; minimum-scope and minimum-duration principles (specific URL paths only, no wildcards unless whole domain needed; article/thread = 2 min, video = stated length + 1 min, max 60 min); video requests must state length or are denied; relax window logic with room eligibility; re-request handling (continuation of prior denial if timing and content match); anti-manipulation instructions; URL coherence checks.

Response parsing strips markdown code fences before JSON parsing. Parse failure defaults to DENY. Temperature is `0.2` (configurable).

## Extension (Firefox)

**Type:** WebExtension Manifest V2 (required for synchronous `webRequest.onBeforeRequest` blocking; MV3's `declarativeNetRequest` is insufficiently flexible). Works on Firefox Desktop and Firefox for Android (113+).

**Interception:** `background.js` registers a blocking listener on `onBeforeRequest` for `main_frame` requests matching the conditional domain patterns. If the URL's domain+path matches an active approved scope, the request is allowed. Otherwise, the request is cancelled and redirected to `blocked.html?url=...&domain=...`.

**Scope storage:** In-memory `Map` of `domain → {pathPrefix, expires, originalUrl, scope}`. Scopes are not persisted across browser restarts. Path matching: if `scopePrefix` is `"/*"` or `"/"`, all paths are allowed; otherwise, the URL path must start with the prefix (trailing `*` stripped). Both bare and www variants are stored simultaneously.

**Access request flow:** `blocked.html` prompts the user for a reason. On submit, `blocked.js` sends a `REQUEST_ACCESS` message to `background.js`, which POSTs `{url, reason}` to `http://192.168.22.1:8800/request-access` (device IP is detected server-side from `request.client.host`). If approved, the scope is stored, a cleanup timeout is set, and after 2.5 seconds (DNS propagation buffer) the tab is navigated to the original URL.

**Settings:** Backend URL is configurable in the options page, stored in `browser.storage.local`. Default is `http://192.168.22.1:8800`.

## Database

SQLite at `/home/pays0n/productivity-guard/requests.db`. Single table `requests` with columns: id, timestamp (ISO 8601), device_ip, device_name, url, domain, reason, room, approved (0/1), scope, duration_minutes, llm_message, request_number_today. Used by the LLM gatekeeper for history context and by the `/history` endpoint.

## Domain Config

Conditional domains (blockable via negotiation): `reddit.com`, `www.reddit.com`, `youtube.com`, `www.youtube.com`, `inv.nadeko.net`, `yewtu.be`, `invidious.nerdvpn.de`. Always-blocked domains: empty by default (configurable). Domains not in either list are rejected at the API level without LLM evaluation.

## Schedule / Relax Windows

Weekday relax window: 20:00–23:00. Weekend: 15:00–23:00. Eligible rooms for relax: `living_room`. During a relax window, vague reasons like "relaxing, N minutes" are approvable if the device is in an eligible room (or room is unknown). Outside a relax window, all relaxation-based requests are denied.

## Tests

Test suite in `backend/tests/` using pytest-asyncio (`asyncio_mode = "auto"`). `conftest.py` writes a temp config file and sets `PG_CONFIG` before any test imports `main.py` (required because `main.py` opens the config file at module level). `helpers/fake_config.py` provides the canonical test config dict. Tests cover `blocklist.py`, `database.py`, `ha_client.py`, `llm_gatekeeper.py`, and `main.py` (via `starlette.testclient.TestClient` with all I/O mocked). Dev dependencies in `requirements-dev.txt`: pytest, pytest-asyncio, pytest-mock, freezegun, pytest-cov.
