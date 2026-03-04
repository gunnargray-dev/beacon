# Beacon

**Your personal ops agent.** A self-hosted command center that aggregates email, calendar, GitHub, and connected services into unified daily briefings, prioritized action items, and smart notifications.

> Built autonomously by [Perplexity Computer](https://perplexity.ai) -- an AI agent that reads the repo, picks tasks, writes code, runs tests, and pushes PRs every 2 hours. Zero human commits.

---

## Stats

| Metric | Count |
|--------|-------|
| Sessions | 14 |
| PRs merged | 18 |
| Source modules | 7 |
| Intelligence modules | 5 |
| Notification modules | 5 |
| Advanced modules | 8 |
| Tests passing | 688 |
| CLI commands | 20 |
| Roadmap phases complete | 8/8 + Phase 9 in progress |

## What It Does

- **Morning Briefing**: Wake up to a structured summary of everything that matters -- meetings, PRs to review, emails to answer, deadlines approaching
- **Action Items**: Automatically extract todos, review requests, and deadlines from all your connected services
- **Priority Scoring**: Items ranked by urgency, sender importance, and deadline proximity
- **Unified Timeline**: One view across GitHub, Calendar, Email, News, and more
- **Smart Notifications**: Configurable rules engine -- route events to notify, digest, or silence. Slack/Discord webhooks and email digests
- **Web Dashboard**: Clean, dark-mode-first interface for your command center
- **CLI**: `beacon brief`, `beacon actions`, `beacon focus`, `beacon export`, `beacon health`, `beacon check` -- everything from the terminal
- **Advanced Intelligence**: Weekly retrospectives, meeting prep, relationship tracking, time audits, trend detection
- **Health Diagnostics**: Built-in health checks for config, store, sync cache, and sources

## Quickstart

```bash
git clone https://github.com/gunnargray-dev/beacon.git
cd beacon
pip install -e .
beacon status
```

## Architecture

```
beacon/
  src/
    models.py          # Core data models
    config.py          # Configuration system
    cli.py             # CLI framework (20 commands)
    health.py          # Health diagnostics
    connectors/        # Source connectors (GitHub, Calendar, Email, Weather, News, HN)
    intelligence/      # Briefing generator, priority scorer, conflict detector, pattern analyzer
    notifications/     # Rules engine, digest compiler, webhooks (Slack/Discord), email sender, silence
    web/               # FastAPI dashboard with Jinja2 templates
    advanced/          # Retrospective, meeting prep, relationships, time audit, trends, export, API
    store_export/      # Store-backed export to JSON/HTML/PDF
  tests/               # 688 tests
  beacon.toml          # Configuration
```

## Connectors

Beacon ships with these built-in connectors:

- **GitHub** -- notifications, review requests, assigned issues, recent commits
- **Calendar** -- upcoming meetings, free/busy blocks, conflict detection
- **Email** -- unread counts, flagged messages, sender frequency analysis
- **Weather** -- current conditions and forecast for configured location
- **News/RSS** -- configured feeds, keyword filtering, top headlines
- **Hacker News** -- top stories, trending topics

## Installation

```bash
pip install -e .
```

## Configuration

Create `~/.config/beacon/beacon.toml` (or run `beacon init`):

```toml
[user]
name = "Your Name"
email = "you@example.com"
timezone = "America/Chicago"

[[sources]]
name = "gh"
type = "github"
enabled = true
github_token = "..."
```

## Commands

- `beacon status`
- `beacon init`
- `beacon sources`
- `beacon sources test [name]`
- `beacon sync`
- `beacon sync --daemon`
- `beacon brief`
- `beacon actions`
- `beacon focus`
- `beacon notify`
- `beacon digest`
- `beacon ingest`
- `beacon query`
- `beacon web`
- `beacon health`
- `beacon export`
- `beacon db`
- `beacon check`

## License

MIT
