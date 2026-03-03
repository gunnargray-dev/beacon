# Beacon Session Log

A running log of what Beacon has built. Each session corresponds to a PR.

---

## Session 1 -- 2026-03-03

**PR**: [#1 Session 1: Foundation + CLI skeleton](https://github.com/gunnargray-dev/beacon/pull/1)

**Completed**:
- Created core data models in `src/models.py`
- Implemented connector plugin base in `src/connectors/base.py`
- Added config loader for `beacon.toml` in `src/config.py`
- Built CLI routing in `src/cli.py` (commands: status, sync, sources)
- Added test harness + fixtures in `tests/`

---

## Session 2 -- 2026-03-03

**PR**: [#2 Session 2: GitHub connector + status view](https://github.com/gunnargray-dev/beacon/pull/2)

**Completed**:
- GitHub connector: notifications, PR reviews requested, issues assigned, recent commits
- Enhanced `beacon status` with source list, last sync time, pending action items
- Added GitHub connector tests

---

## Session 3 -- 2026-03-03

**PR**: [#3 Session 3: Calendar connector + conflicts](https://github.com/gunnargray-dev/beacon/pull/3)

**Completed**:
- Calendar connector: today's meetings, upcoming conflicts, free/busy blocks
- Conflict detector: flag overlaps in calendar events
- Added calendar connector tests

---

## Session 4 -- 2026-03-03

**PR**: [#4 Session 4: Email connector + action extraction](https://github.com/gunnargray-dev/beacon/pull/4)

**Completed**:
- Email connector: unread count, flagged messages, sender frequency analysis
- Action item extractor: surface todos and deadlines from events
- Added email connector tests

---

## Session 5 -- 2026-03-03

**PR**: [#5 Session 5: Weather, News, HN connectors + sync](https://github.com/gunnargray-dev/beacon/pull/5)

**Completed**:
- Weather connector: current conditions + forecast for configured location
- News/RSS connector: RSS feed support + keyword filtering
- Hacker News connector: top stories, trending topics
- `beacon sync` command: run all connectors, write `~/.cache/beacon/last_sync.json`
- `beacon sources` enhancements: add/remove/test connectors

---

## Session 6 -- 2026-03-03

>**PR**: [#10 Session 6: Web dashboard reads from SQLite store (fallback to sync cache)](https://github.com/gunnargray-dev/beacon/pull/10)

**Completed**:
- `src/web/data.py` -- centralize dashboard data loading: prefer SQLite store if `~/.cache/beacon/beacon.db` exists (or `BEACON_DB` env var), else fall back to sync cache
- `src/web/routes.py` -- updated web + API routes to use store-backed loader while preserving backwards-compatible `_CACHE_FILE`/`_load_cache` patch points for tests
- `tests/test_web_dashboard_store_fallback.py` -- tests for store vs cache selection

**Stats**: 540+ tests passing, PRs merged: 10, Sessions: 6

---

## Session 7 -- 2026-03-03

>**PR**: [#11 Session 7: Store-backed API endpoints for events + action items](https://github.com/gunnargray-dev/beacon/pull/11)

**Completed**:
- `src/web/store_api.py` -- Store-backed JSON endpoints mounted at `/api/store/*`:
  - `GET /api/store/meta` — db_path + whether the DB exists
  - `GET /api/store/events` — filters: source_type, source_id, since, until, limit
  - `GET /api/store/action-items` — filters: source_type, source_id, priority, completed, due_before, limit
- `src/web/server.py` -- Mount store API router
- `tests/test_web_store_api.py` -- FastAPI tests for validation + missing DB behavior

**Stats**: 540+ tests passing, PRs merged: 11, Sessions: 7

---

## Session 8 -- 2026-03-03

**PR**: [#13 Session 8: Ops stats endpoint + beacon db](https://github.com/gunnargray-dev/beacon/pull/13)

**Completed**:
- `src/ops.py` -- stdlib-only store stats helper: counts for events/action items, completed vs pending, by source_type
- `src/web/store_api.py` -- added `GET /api/store/stats` returning the above counts
- `src/db_cli.py` + `src/cli.py` -- added `beacon db` command to print db_path + counts
- `src/web/routes.py` + sources page -- adds a "backend" summary card (store vs sync cache) and shows active db_path when store-backed
- `tests/test_ops.py`, `tests/test_db_cli.py`, `tests/test_web_store_stats_api.py` -- new tests for ops & observability

**Stats**: 540+ tests passing, PRs merged: 12, Sessions: 8

---

## Session 9 -- 2026-03-03

**PR**: [#15 Session 9: Store queries pagination + stable sorting](https://github.com/gunnargray-dev/beacon/pull/15)

**Completed**:
- `src/store.py` -- cursor + sort support for store-backed queries:
  - `query_events(..., cursor, sort)` with stable ordering and tie-breakers
  - `query_action_items(..., cursor, sort)` with stable ordering and tie-breakers
- `src/web/store_api.py` -- API upgrades:
  - `GET /api/store/events` accepts `cursor` + `sort` and returns `next_cursor`
  - `GET /api/store/action-items` accepts `cursor` + `sort` and returns `next_cursor`
- `src/store_pagination.py` -- stdlib cursor helpers (encode/decode) + limit clamping
- `tests/test_store_pagination.py`, `tests/test_store_query_pagination.py` -- new tests for cursor helpers and store pagination

**Stats**: 540+ tests passing, PRs merged: 13, Sessions: 9

---

## Session 10 -- 2026-03-03

>**PR**: [#17 Session 10: Store-backed exports (no sync cache required)](https://github.com/gunnargray-dev/beacon/pull/17)

**Completed**:
- `src/store_export/` -- new stdlib module bridging SQLite store queries to the existing `src.advanced.export.export_report` formats (JSON/HTML/PDF)
- `tests/test_store_export.py` -- unit tests covering payload shaping + export file writing

**Stats**: 540+ tests passing, PRs merged: 14, Sessions: 10

---
