# Instagram Reels (Instagram API with Instagram Login)

Research checked 2026-09-27. Graph API v26.0 is current; the docs' examples use v25.0, which is the version pinned in config.

- **Account:** a Professional account (Business or Creator). No Facebook Page is needed.
  **Standard Access**, with no App Review, covers accounts you own or manage.
  - https://developers.facebook.com/docs/instagram-platform/overview
  - https://developers.facebook.com/docs/instagram-platform/app-review
- **Flow:**
  1. `POST /<IG_ID>/media` with `media_type=REELS`, `upload_type=resumable`, `caption`, `share_to_feed`,
     `thumb_offset` and `is_ai_generated`.
  2. `POST https://rupload.facebook.com/ig-api-upload/<ver>/<container>` with the headers
     `Authorization: OAuth <token>`, `offset` and `file_size`, and the local file as the body. **No public URL is needed.**
  3. Poll `GET /<container>?fields=status_code` (IN_PROGRESS / FINISHED / ERROR / EXPIRED / PUBLISHED).
  4. `POST /<IG_ID>/media_publish` with `creation_id`.
  - https://developers.facebook.com/docs/instagram-platform/content-publishing
- **No private posts and no native scheduling.** Containers expire after 24 h.
- **Daily limit:** the docs contradict each other (100 vs 50 per 24 h), so read `GET /<IG_ID>/content_publishing_limit` at runtime.
  There is also a cap of 400 containers per 24 h.
- **Specs:** MP4/MOV with moov at the front, H.264/HEVC, 23–60 fps, at most 1920 px wide, up to 25 Mbps,
  AAC up to 48 kHz, 3 s to 15 min, 300 MB.
  https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/media
- **Tokens:** a short-lived token (1 h) is exchanged with `ig_exchange_token` for a long-lived one (60 days),
  which is refreshed with `ig_refresh_token` once it is at least 24 h old and before it expires.
  - https://developers.facebook.com/docs/instagram-platform/reference/access_token
  - https://developers.facebook.com/docs/instagram-platform/reference/refresh_access_token
- **Metrics:** `views`, `reach`, `likes`, `comments`, `shares`, `saved`, `total_interactions`,
  `ig_reels_avg_watch_time`, `ig_reels_video_view_total_time`, `reels_skip_rate`.
  - There is no retention curve.
  - Latency is up to 48 h.
  - https://developers.facebook.com/docs/instagram-platform/reference/instagram-media/insights

## Request formats used (verified 2026-09-28)
- **Create container:** `POST https://graph.instagram.com/v25.0/<IG_ID>/media` with everything in the query string:
  `media_type=REELS&upload_type=resumable&caption=…&thumb_offset=…&is_ai_generated=true|false&share_to_feed=…&access_token=…`.
  The response is `{"id": "<container>"}`.
  - `share_to_feed` with resumable upload is **não confirmado** (TODO(verificar)).
  - Whether the response also includes `uri` is **não confirmado**, so the rupload URL is built from the id.
- **Upload:** `POST https://rupload.facebook.com/ig-api-upload/v25.0/<container>` with the headers
  `Authorization: OAuth <token>`, `offset: 0` and `file_size: <bytes>`, and the file as the body.
  - Success: `{"success": true, "message": "Upload successful."}`.
  - Failure: `{"debug_info": {"retriable": …, "type": …, "message": …}}`.
- **Status:** `GET /<container>?fields=status_code,status`. When `status_code` is `ERROR`, `status` holds the error subcode.
  Poll once a minute for at most 5 minutes; after that, the next run keeps polling.
- **Publish:** `POST /<IG_ID>/media_publish?creation_id=<container>` returns `{"id": "<media>"}`.
  Then `GET /<media>?fields=permalink`.
- **Quota:** `GET /<IG_ID>/content_publishing_limit?fields=quota_usage,config` returns
  `data[0].quota_usage` and `data[0].config.quota_total`.
- **IG_ID:** use `user_id` from `GET /v25.0/me?fields=user_id,username`. The response may or may not be wrapped in `data[]`, so both are parsed.

## Implementation decisions
- **Resuming a rupload** from a non-zero offset is not documented. An interrupted or retriable upload therefore
  creates a **new container**. A container that is never published expires after 24 h, so this cannot double-publish.
- **Only `media_publish` makes a Reel public**, and it is called only when the container is `FINISHED`.
  A container already `PUBLISHED` with no recorded media id becomes `needs_reconcile`, never a second publication.
- **Error handling**, following the Graph API error guide and the IG error-codes page:

| Error | Handling |
|---|---|
| codes 1, 2, 4, 17, 341; subcodes 2207001/003/006/008/027/052 | Transient: retried |
| subcodes 2207020/032/053 | New container |
| 9/2207042 (max posts) | Retry after an hour |
| subcodes 2207010/026/050/051/057; codes 102/190 (token) | Permanent |
