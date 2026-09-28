# TikTok (Content Posting API, inbox/draft mode)

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

## Request formats used (verified 2026-09-28)
- **Init:** `POST https://open.tiktokapis.com/v2/post/publish/inbox/video/init/` with the headers
  `Authorization: Bearer <token>` and `Content-Type: application/json; charset=UTF-8`.
  - Body: `{"source_info": {"source": "FILE_UPLOAD", "video_size", "chunk_size", "total_chunk_count"}}`.
  - Response: `data.publish_id` and `data.upload_url` (valid 1 h), plus `error.code == "ok"`.
  - **Inbox mode has no `post_info`**, so no caption or privacy. The creator sets both in the app.
- **Upload:** `PUT <upload_url>` with `Content-Type: video/mp4`, `Content-Length` and `Content-Range: bytes a-b/total`, sent in order.
  - Responses: 206 means more chunks follow; 201 means done; 403 means the URL expired; 5xx means retry the chunk.
  - Chunking: files up to 64 MB go in one piece. Larger files use 10 MiB chunks, with `total_chunk_count = floor(size/chunk)`,
    and the last chunk takes the remainder (up to 128 MB).
- **Status:** `POST /v2/post/publish/status/fetch/` with `{"publish_id"}` returns `data.status`, `data.fail_reason` and
  `data.publicaly_available_post_id` (a list, spelled that way).
  - Inbox uploads rest at `SEND_TO_USER_INBOX`. They reach `PUBLISH_COMPLETE` once the creator posts,
    and the public id appears after moderation.
- **OAuth:**
  - Authorize at `https://www.tiktok.com/v2/auth/authorize/?client_key&scope=a,b&response_type=code&redirect_uri&state&code_challenge&code_challenge_method=S256`.
  - **The challenge is the HEX-encoded SHA-256** of the verifier.
  - Token: `POST /v2/oauth/token/`, form-encoded, with `client_key`, `client_secret`, `code`, `grant_type`, `redirect_uri` and `code_verifier`.
    The refresh request uses `grant_type=refresh_token&refresh_token`, and the refresh token rotates.
  - OAuth errors are flat: `{"error", "error_description", "log_id"}`.

## Implementation decisions
- **Crash recovery:** an upload interrupted mid-way starts over with a new init; the chunk URL lasts 1 h and resuming is not described.
  If the process died after a finished upload, the status (`SEND_TO_USER_INBOX`) shows it and nothing is resent.
  - TODO(verificar): whether an abandoned init counts toward the 5 pending shares.
- **`sent_to_inbox` is terminal** for publishing. `publisher link` moves it to `published` using the public post id,
  either looked up from the status or passed by hand.
- **Error handling:**

| Error | Handling |
|---|---|
| `internal_error`, `rate_limit_exceeded`, 5xx | Transient |
| `access_token_invalid` | Refresh the token once, then retry |
| `spam_risk_too_many_pending_share`, fail reason `spam_risk_too_many_posts` | Retry after an hour |
| fail reason `internal` | New upload |
| Other fail reasons | Permanent |

- **Não confirmado:** whether an unaudited app with only `video.upload` can post from your own account.
  The upload get-started page mentions no audit, but a search snippet suggests private-only restrictions.
  Your first real run will tell.
