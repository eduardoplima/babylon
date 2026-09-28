# TikTok (Content Posting API, inbox/draft mode) — phase 3

Research checked 2026-09-27.

- **Upload mode:** `POST /v2/post/publish/inbox/video/init/` with scope `video.upload`. The creator finishes
  the post in the app from an inbox notification. At most 5 pending shares per 24 h.
  https://developers.tiktok.com/doc/content-posting-api-reference-upload-video
- **Why not Direct Post:** unaudited clients post `SELF_ONLY`, to private accounts only, with a cap of 5 users per 24 h.
  The guidelines list "A utility tool to help upload contents to the account(s) you or your team manages"
  as not acceptable, and require an interactive UX: manual privacy choice with no default, a preview, and consent.
  https://developers.tiktok.com/doc/content-sharing-guidelines
- **FILE_UPLOAD:** send chunks of 5–64 MB (the last one can be up to 128 MB), 1–1000 chunks in total.
  A file under 5 MB goes in a single PUT with `Content-Range`. The upload URL is valid for 1 h.
  https://developers.tiktok.com/doc/content-posting-api-media-transfer-guide
- **Status:** `POST /v2/post/publish/status/fetch/`, limited to 30 requests per minute.
  `publicaly_available_post_id` is returned only once the post is public and has passed moderation.
- **OAuth (desktop):** PKCE S256 with a **hex-encoded** SHA-256 challenge.
  Redirect to `http://127.0.0.1:<port>/callback/`. The access token lasts 24 h and the refresh token 365 days;
  **the refresh token rotates**, so always store the new one.
  - https://developers.tiktok.com/doc/login-kit-desktop
  - https://developers.tiktok.com/doc/oauth-user-access-token-management
- **Metrics:** `/v2/video/query/` (scope `video.list`) returns `view_count`, `like_count`, `comment_count` and
  `share_count`. There is no watch time or retention, and `video/list` returns public videos only.
  https://developers.tiktok.com/docs/en/tiktok-api-v2-video-object
- **Não confirmado:** whether inbox-only apps need the audit; whether `video/query` returns private videos;
  the aspect-ratio rules.
