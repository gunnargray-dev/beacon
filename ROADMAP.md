# Beacon Roadmap

> A self-hosted personal ops agent that aggregates email, calendar, GitHub, and connected services into a single command center with daily briefings, action items, and smart notifications.

## Phase 1 -- Foundation (Sessions 1-4)

- [x] Core data models: User, Source, Event, ActionItem, Briefing
- [x] Plugin architecture: base connector class with register/discover/load pattern
- [x] Configuration system: beacon.toml with per-source credentials and preferences
- [x] CLI framework: `beacon` command with subcommand routing
- [x] `beacon status` -- show connected sources, last sync time, pending action items
- [x] Test framework: pytest with fixtures, >90% coverage target
- [x] CI pipeline: GitHub Actions on Python 3.11/3.12

## Phase 2 -- Connectors (Sessions 5-10)

- [x] GitHub connector: notifications, PR reviews requested, issues assigned, recent commits
- [x] Calendar connector: today's meetings, upcoming conflicts, free/busy blocks
- [x] Email connector: unread count, flagged messages, sender frequency analysis
- [x] Weather connector: current conditions + forecast for configured location
- [x] News/RSS connector: headlines from configured feeds, keyword filtering
- [x] Hacker News connector: top stories, trending topics
- [x] `beacon sync` -- pull latest data from all connected sources
- [x] `beacon sources` -- list/add/remove/test connectors

## Phase 3 -- Intelligence Engine (Sessions 11-16)

- [x] Daily briefing generator: structured morning summary across all sources
- [x] Action item extractor: surface todos, review requests, deadlines from all sources
- [x] Priority scorer: rank items by urgency, sender importance, deadline proximity
- [x] Conflict detector: flag calendar overlaps, double-booked slots
- [x] Pattern analyzer: identify recurring meetings, email response times, commit velocity
- [x] `beacon brief` -- generate and display today's briefing
- [x] `beacon actions` -- list prioritized action items across all sources
- [x] `beacon focus` -- show a distraction-free view of today's top 3 priorities

## Phase 4 -- Web Dashboard (Sessions 17-22)

- [x] FastAPI server with Jinja2 templates
- [x] Landing page: Beacon branding, feature overview, quickstart
- [x] Dashboard: unified timeline of events across all sources
- [x] Briefing view: formatted daily briefing with action items
- [x] Calendar view: visual day/week layout with meeting details
- [x] Source health panel: connection status, last sync, error indicators
- [x] Settings page: manage sources, preferences, notification rules
- [x] Dark mode (default) with light mode toggle

## Phase 5 -- Notifications & Automation (Sessions 23-28)

- [x] Notification rules engine: configurable triggers (e.g., "PR review requested -> notify")
- [x] Digest scheduler: configurable morning/evening digest delivery
- [x] Slack/Discord webhook integration for notifications
- [x] Email digest sender: HTML-formatted daily summary
- [x] Smart silence: suppress notifications during focus blocks or after hours
- [x] `beacon notify` -- test notification delivery
- [x] `beacon digest` -- manually trigger a digest

## Phase 6 -- Advanced Intelligence (Sessions 29+)

- [x] Weekly retrospective: auto-generate a summary of the week's activity
- [x] Meeting prep: pull context for upcoming meetings (attendee info, related emails, docs)
- [x] Relationship tracker: who you interact with most, response patterns
- [x] Time audit: how your time is spent across meetings, deep work, admin
- [x] Trend detection: flag unusual patterns (spike in PRs, drop in response time)
- [x] Export system: PDF/HTML/JSON briefing export
- [x] API: RESTful endpoints for all data and briefings
- [x] Plugin marketplace: community-contributed connectors

## Phase 7 -- Persistence & Query (Sessions 33+)

- [x] Persistent local store: SQLite-backed event/action storage (no more ephemeral sync cache)
- [x] `beacon ingest` -- import the latest sync cache JSON into the local store (dedupe by event/action id)
- [x] `beacon query` -- basic query/filter of events and action items (by source, date range, priority, completion)
- [x] Web dashboard: read from the store when available (fallback to sync cache)
- [x] Store-backed API endpoints: query events/action items directly from SQLite (with filters)

## Phase 8 -- Ops & Observability (Sessions 37+)

- [x] Web UI: show backend info (store vs sync cache) + active db_path on health/status panel
- [x] CLI: `beacon db` command to print db_path + counts for events/action_items
- [x] Store queries: add pagination (cursor or offset) + stable sorting options
- [x] Web API: add /api/store/stats (counts by source_type, completed vs pending)
- [x] Export: allow exporting directly from store queries (no cache required)

## Phase 9 -- Resilience & Developer Experience

- [x] `beacon export` -- CLI command to export store data to JSON/HTML/PDF with filters
- [x] `beacon health` -- CLI health diagnostics (config, store, sync cache, sources)
- [x] Scheduled sync: cron-friendly `beacon sync --daemon` mode with configurable interval
- [x] Retry logic: exponential backoff helper + initial CLI integration for transient failures
- [x] Config validation: `beacon check` command to lint beacon.toml for common errors
- [ ] Migration system: versioned store schema migrations (auto-upgrade on startup)
- [ ] `beacon shell` -- interactive REPL for ad-hoc queries and exploration
- [ ] Structured logging: JSON log output with levels, timestamps, request IDs
- [ ] Performance benchmarks: pytest-benchmark suite for store queries and sync pipeline
- [ ] Plugin SDK: documented API + scaffold command for third-party connector development
