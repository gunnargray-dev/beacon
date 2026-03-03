# Beacon Rules

> These rules govern how Computer operates during autonomous development sessions.

## Identity

- **Project**: Beacon -- Personal Ops Agent
- **Repo**: github.com/gunnargray-dev/beacon
- **Owner**: Gunnar (gunnar@perplexity.ai)
- **Builder**: Perplexity Computer (autonomous AI agent)

## Session Protocol

1. **Read state**: Fetch ROADMAP.md, SESSION_LOG.md, and state.json from GitHub
2. **Assess**: Identify the next unchecked roadmap items to work on
3. **Plan**: Pick 2-4 items that form a coherent unit of work
4. **Build**: Write code in the sandbox, run tests, iterate until passing
5. **Push**: Create a feature branch, push all changes, open a PR
6. **Merge**: If tests pass and code is clean, merge via squash
7. **Update**: Check off roadmap items, append session entry to SESSION_LOG.md, update README stats
8. **Notify**: Send a push notification summarizing what shipped
9. **Persist**: Save state.json for the next session

## Code Standards

- **Pure Python stdlib** for core logic -- no runtime dependencies
- FastAPI + Jinja2 for web dashboard (optional dependencies)
- httpx or urllib for HTTP calls to external APIs
- All code in `src/`, all tests in `tests/`
- Every module must have corresponding tests
- Commit messages use `[beacon]` prefix
- PR descriptions include: what changed, why, how to test
- Target >90% test coverage

## Decision Making

- **Always build new features** over fixing non-critical issues
- **Always write tests** with every new module
- **Never break existing tests** -- if a test fails, fix it before moving on
- **Prefer simplicity** -- solve the problem directly, don't over-architect
- When the roadmap is fully checked off, **add ambitious new items and keep building**
- If stuck on an issue for >15 minutes, skip it, log it, and move to the next task

## Human Interaction

- Issues labeled `human-priority` are addressed first in the next session
- Gunnar may open PRs -- merge them if they're clean, resolve conflicts if needed
- Gunnar may add roadmap items -- treat them as high priority

## Naming Conventions

- CLI command: `beacon`
- Config file: `beacon.toml`
- Log file: `SESSION_LOG.md`
- Rules file: `.github/BEACON_RULES.md`
- Commit prefix: `[beacon]`
