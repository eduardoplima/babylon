# publisher

Publishes Babylon shorts to YouTube Shorts (Instagram Reels and TikTok come in phases 2–3) and
collects metrics back (phase 4). Every publishing command is a **dry run unless `--live`**.

## Setup
```bash
cd publisher
uv sync
cp .env.example .env        # optional; defaults work when run from this folder
```
To authorize YouTube:
1. In Google Cloud Console, enable the **YouTube Data API v3** and the **YouTube Analytics API**.
2. Create an OAuth client of type **Desktop app** and save its JSON as `.secrets/youtube_client_secret.json`.
3. Set the consent screen to **In production**. In "Testing", refresh tokens expire after 7 days.
4. Run `uv run publisher auth youtube` (opens the browser).

## Workflow
```bash
uv run publisher import-babylon ../channels/roman-in-stones/videos/001-tempus-edax-rerum
# edit content/<slug>/meta.yaml: hook_type, format, schedule, captions
uv run publisher validate <slug>
uv run publisher publish <slug> -p youtube            # dry run
uv run publisher publish <slug> -p youtube --live     # uploads (private until the API project is audited)
uv run publisher publish-due --live                   # for cron / systemd timers
uv run publisher status
uv run publisher resolve <slug> youtube --remote-id <id> | --reset   # settle needs_reconcile
```
Example cron line (every 15 min): `*/15 * * * * cd /path/to/babylon/publisher && uv run publisher publish-due --live`.

## Guarantees
- **One publication per (slug, platform):** it is `UNIQUE` in SQLite, claimed atomically, and never republished once done.
- **Interrupted uploads resume** from the saved session.
- **Unknown outcomes** become `needs_reconcile` and are never retried automatically.
- **Transient errors** (5xx, rate limits) retry with exponential backoff. Permanent ones are recorded with the API message.
- **Logging and data:** JSON logs go to `data/publisher.log.jsonl`, and every attempt is stored in the `attempts` table.
- **Secrets** live in `.secrets/` (mode 600), `.env` and `data/`, all gitignored.

Platform research, with official links: `docs/platforms/`. Limits: `config/platforms.yaml`.
Tests: `uv run pytest` (every HTTP call is mocked; real network access is blocked).
