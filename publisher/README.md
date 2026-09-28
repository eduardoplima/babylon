# publisher

Publishes Babylon shorts to YouTube Shorts, Instagram Reels and TikTok (as inbox drafts) and
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

To authorize Instagram (an Instagram **Professional** account; no Facebook Page is needed):
1. In the Meta App Dashboard, create an app with **Instagram → API setup with Instagram business login**.
2. Add your Instagram account, then click **Generate token** next to it. Dashboard tokens are long-lived (60 days).
3. Run `uv run publisher auth instagram` and paste the token (it is not echoed).
4. Tokens are refreshed automatically once they are at least 24 h old. Run `uv run publisher auth refresh` daily from cron to be safe.

To authorize TikTok:
1. At developers.tiktok.com, create an app with **Login Kit (Desktop)** and the **Content Posting API**, using the scopes `video.upload` and `video.list`.
2. Register the redirect URI `http://127.0.0.1:*/callback/`.
3. Put `PUBLISHER_TIKTOK_CLIENT_KEY` and `PUBLISHER_TIKTOK_CLIENT_SECRET` in `.env`.
4. Run `uv run publisher auth tiktok` (opens the browser).

Access tokens renew themselves daily; you have to log in again once a year.

**TikTok videos arrive as drafts in your TikTok inbox.** The API takes no caption or privacy in this mode. Open the
notification, paste the caption that `publish` prints, post it, then run `uv run publisher link <slug> tiktok` to
record the public video (it is looked up automatically once TikTok's moderation approves it). At most 5 drafts
can be pending per 24 h.

**Instagram has no private posts.** `--live` publishes a public Reel, so run it only when the video is ready.

## Workflow
```bash
uv run publisher import-babylon ../channels/roman-in-stones/videos/001-tempus-edax-rerum
# edit content/<slug>/meta.yaml: hook_type, format, schedule, captions
uv run publisher validate <slug>
uv run publisher publish <slug> -p youtube            # dry run
uv run publisher publish <slug> -p youtube --live     # uploads (private until the API project is audited)
uv run publisher publish <slug> -p instagram --live   # publishes a PUBLIC Reel
uv run publisher publish <slug> -p tiktok --live      # sends a draft to your TikTok inbox
uv run publisher link <slug> tiktok [<video_id>]      # after posting the draft in the app
uv run publisher publish-due --live                   # for cron / systemd timers
uv run publisher status
uv run publisher resolve <slug> youtube --remote-id <id> | --reset   # settle needs_reconcile
```
Example cron lines:
```
*/15 * * * * cd /path/to/babylon/publisher && uv run publisher publish-due --live
0 9 * * *    cd /path/to/babylon/publisher && uv run publisher auth refresh
```

## Guarantees
- **One publication per (slug, platform):** it is `UNIQUE` in SQLite, claimed atomically, and never republished once done.
- **Interrupted uploads resume** from the saved session.
- **Unknown outcomes** become `needs_reconcile` and are never retried automatically.
- **Transient errors** (5xx, rate limits) retry with exponential backoff. Permanent ones are recorded with the API message.
- **Daily quotas** (YouTube `quotaExceeded`, Instagram "maximum number of posts") are not retried immediately; `publish-due` tries again after an hour. Instagram's remaining quota is read live before publishing.
- **Credentials are checked before any state changes**, so a missing token leaves nothing behind.
- **Logging and data:** JSON logs go to `data/publisher.log.jsonl`, and every attempt is stored in the `attempts` table.
- **Secrets** live in `.secrets/` (mode 600), `.env` and `data/`, all gitignored.

Platform research, with official links: `docs/platforms/`. Limits: `config/platforms.yaml`.
Tests: `uv run pytest` (every HTTP call is mocked; real network access is blocked).
