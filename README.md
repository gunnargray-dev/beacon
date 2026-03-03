# Beacon

**Your personal ops agent.** A self-hosted command center that aggregates email, calendar, GitHub, and connected services into unified daily briefings, prioritized action items, and smart notifications.

> Built autonomously by [Perplexity Computer](https://perplexity.ai) -- an AI agent that reads the repo, picks tasks, writes code, runs tests, and pushes PRs every 2 hours. Zero human commits.

---

## Stats

| Metric | Count |
|--------|-------|
| Sessions | 8 |
| PRs merged | 12 |
| Source modules | 7 |
| Intelligence modules | 5 |
| Notification modules | 5 |
| Advanced modules | 8 |
| Tests passing | 540+ |
| CLI commands | 15 |
| Roadmap phases complete | 6/6 + Phase 7 |

## What It Does

- **Morning Briefing**: Wake up to a structured summary of everything that matters -- meetings, PRs to review, emails to answer, deadlines approaching
- **Action Items**: Automatically extract todos, review requests, and deadlines from all your connected services
- **Priority Scoring**: Items ranked by urgency, sender importance, and deadline proximity
- **Unified Timeline**: One view across GitHub, Calendar, Email, News, and more
- **Smart Notifications**: Configurable rules engine -- route events to notify, digest, or silence. Slack/Discord webhooks and email digests
- **Web Dashboard**: Clean, dark-mode-first interface for your command center
- **CLI**: `beacon brief`, `beacon actions`, `beacon focus`, `beacon notify`, `beacon digest` -- everything from the terminal
- **Advanced Intelligence**: Weekly retrospectives, meeting prep, relationship tracking, time audits, trend detection

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
    cli.py             # CLI framework (12 commands)
    connectors/        # Source connectors (GitHub, Calendar, Email, Weather, News, HN)
    intelligence/      # Briefing generator, priority scorer, conflict detector, pattern analyzer
    notifications/     # Rules engine, digest compiler, webhooks (Slack/Discord), email sender, silence
    web/               # FastAPI dashboard with Jinja2 templates
    advanced/          # Retrospective, meeting prep, relationships, time audit, trends, export, API
  tests/               # 537+ tests
  beacon.toml          # Configuration
  ROADMAP.md           # All 6 phases complete
  SESSION_LOG.md
  .github/
    BEACON_RULES.md
```

## Development

This project is built autonomously by Perplexity Computer. Each session:

1. Reads repo state (roadmap, session log, code)
2. Picks the next tasks from the roadmap
3. Writes code, runs tests, iterates
4. Pushes a PR, merges it, updates the log
5. Fires again in 2 hours

Want to steer development? Open an issue with the `human-priority` label.

## License

MIT
