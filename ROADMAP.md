# Beacon Roadmap

> A self-hosted personal ops agent that aggregates email, calendar, GitHub, and connected services into a single command center with daily briefings, action items, and smart notifications.

## Phase 1 -- Foundation (Sessions 1-4)

- [ ] Core data models: User, Source, Event, ActionItem, Briefing
- [ ] Plugin architecture: base connector class with register/discover/load pattern
- [ ] Configuration system: beacon.toml with per-source credentials and preferences
- [ ] CLI framework: `beacon` command with subcommand routing
- [ ] `beacon status` -- show connected sources, last sync time, pending action items
- [ ] Test framework: pytest with fixtures, >90% coverage target
- [ ] CI pipeline: GitHub Actions on Python 3.11/3.12

## Phase 2 -- Connectors (Sessions 5-10)

- [ ] GitHub connector: notifications, PR reviews requested, issues assigned, recent commits
- [ ] Calendar connector: today's meetings, upcoming conflicts, free/busy blocks
- [ ] Email connector: unread count, flagged messages, sender frequency analysis
- [ ] Weather connector: current conditions + forecast for configured location
- [ ] News/RSS connector: headlines from configured feeds, keyword filtering
- [ ] Hacker News connector: top stories, trending topics
- [ ] `beacon sync` -- pull latest data from all connected sources
- [ ] `beacon sources` -- list/add/remove/test connectors

## Phase 3 -- Intelligence Engine (Sessions 11-16)

- [ ] Daily briefing generator: structured morning summary across all sources
- [ ] Action item extractor: surface todos, review requests, deadlines from all sources
- [ ] Priority scorer: rank items by urgency, sender importance, deadline proximity
- [ ] Conflict detector: flag calendar overlaps, double-booked slots
- [ ] Pattern analyzer: identify recurring meetings, email response times, commit velocity
- [ ] `beacon brief` -- generate and display today's briefing
- [ ] `beacon actions` -- list prioritized action items across all sources
- [ ] `beacon focus` -- show a distraction-free view of today's top 3 priorities

## Phase 4 -- Web Dashboard (Sessions 17-22)

- [ ] FastAPI server with Jinja2 templates
- [ ] Landing page: Beacon branding, feature overview, quickstart
- [ ] Dashboard: unified timeline of events across all sources
- [ ] Briefing view: formatted daily briefing with action items
- [ ] Calendar view: visual day/week layout with meeting details
- [ ] Source health panel: connection status, last sync, error indicators
- [ ] Settings page: manage sources, preferences, notification rules
- [ ] Dark mode (default) with light mode toggle

## Phase 5 -- Notifications & Automation (Sessions 23-28)

- [ ] Notification rules engine: configurable triggers (e.g., "PR review requested -> notify")
- [ ] Digest scheduler: configurable morning/evening digest delivery
- [ ] Slack/Discord webhook integration for notifications
- [ ] Email digest sender: HTML-formatted daily summary
- [ ] Smart silence: suppress notifications during focus blocks or after hours
- [ ] `beacon notify` -- test notification delivery
- [ ] `beacon digest` -- manually trigger a digest

## Phase 6 -- Advanced Intelligence (Sessions 29+)

- [ ] Weekly retrospective: auto-generate a summary of the week's activity
- [ ] Meeting prep: pull context for upcoming meetings (attendee info, related emails, docs)
- [ ] Relationship tracker: who you interact with most, response patterns
- [ ] Time audit: how your time is spent across meetings, deep work, admin
- [ ] Trend detection: flag unusual patterns (spike in PRs, drop in response time)
- [ ] Export system: PDF/HTML/JSON briefing export
- [ ] API: RESTful endpoints for all data and briefings
- [ ] Plugin marketplace: community-contributed connectors
