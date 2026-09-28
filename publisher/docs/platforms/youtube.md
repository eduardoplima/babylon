# YouTube (Data API v3 + Analytics API v2)

Research checked 2026-09-27 against the official pages below. Items marked **não confirmado** are
`TODO(verificar)` in code or config.

## Upload
- `POST https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status`.
  The session URI comes back in `Location`; PUT the bytes to it.
  To resume, send `PUT` with `Content-Range: bytes */N`; the response is 308 with `Range`.
  - https://developers.google.com/youtube/v3/docs/videos/insert
  - https://developers.google.com/youtube/v3/guides/using_resumable_upload_protocol
- Fields used: `snippet.title/description/tags/categoryId`, `status.privacyStatus`,
  `status.selfDeclaredMadeForKids`, `status.containsSyntheticMedia` (added 2024-10-30), and `notifySubscribers`.
  `status.publishAt` works only for private videos that have never been published.
  https://developers.google.com/youtube/v3/docs/videos
- **Quota:** own bucket of **100 `videos.insert` calls per day**, plus 10,000 units per day for other calls
  (separate buckets since 2026-06-01).
  - https://developers.google.com/youtube/v3/getting-started
  - https://developers.google.com/youtube/v3/determine_quota_cost
- **Unaudited projects:** "All videos uploaded via the videos.insert endpoint from unverified API projects
  created after 28 July 2020 will be restricted to private viewing mode."
  - Audit form: https://support.google.com/youtube/contact/yt_api_form
  - Guide: https://developers.google.com/youtube/v3/guides/quota_and_compliance_audits
  - No SLA is given.
- **Policy:** "users must have final control over the data that will be published".
  https://developers.google.com/youtube/terms/developer-policies

## Shorts
- A video is a Short if it is square or vertical and up to 3 minutes long (uploads from 2024-10-15).
  The API has no Shorts flag. https://support.google.com/youtube/answer/15424877
- **Encoding:** MP4 with moov at the front, H.264, AAC-LC/Opus at 48 kHz. https://support.google.com/youtube/answer/1722171

## Status
`videos.list?part=status,processingDetails`:
- `processingStatus`: processing / succeeded / failed / terminated.
- `uploadStatus`: uploaded / processed / failed / rejected / deleted.
- `failureReason` and `rejectionReason` explain failures.

## OAuth
- Loopback flow (`InstalledAppFlow.run_local_server`); the OOB flow is deprecated.
  https://developers.google.com/youtube/v3/guides/auth/installed-apps
- **Scopes:** `youtube.upload`, plus `youtube.readonly` and `yt-analytics.readonly` for metrics.
  `reports.query` now also requires `youtube.readonly`.
- A consent screen in **Testing** makes refresh tokens **expire in 7 days**.
  https://developers.google.com/identity/protocols/oauth2
  - Not confirmed (**não confirmado**): whether these scopes count as sensitive, which would require verification in Production.

## Errors
- **Transient:** 5xx, `backendError`, `rateLimitExceeded`.
- **Permanent:** `quotaExceeded` (403), `uploadLimitExceeded` (per-channel daily cap; the number is **não confirmado**),
  `forbidden*`, `invalid*`.
- https://developers.google.com/youtube/v3/docs/errors

## Metrics (phase 4)
- **Data API `statistics`:** `viewCount`, `likeCount`, `commentCount`. `dislikeCount` is private.
- **Analytics `reports.query`:** `views`, `engagedViews`, `estimatedMinutesWatched`, `averageViewDuration`,
  `averageViewPercentage`, `shares`, `likes`, `comments`, `subscribersGained`.
  - Retention: `elapsedVideoTimeRatio` with `audienceWatchRatio`. Support for Shorts is **não confirmado**.
  - Latency 48–72 h. https://developers.google.com/youtube/analytics/metrics
- **Shorts views** count every start or replay since 2025-03-31; `engagedViews` keeps the old definition.
  https://developers.google.com/youtube/analytics/revision_history

## Metrics collection (verified 2026-09-28)
- **`videos.list?part=statistics&id=a,b`** (up to 50 ids, 1 unit) returns `viewCount`, `likeCount` and `commentCount` as **strings**.
- **`GET https://youtubeanalytics.googleapis.com/v2/reports`**, one request per video, with **no dimension** and `filters=video==ID`.
  This is the documented "basic user activity" form. The "top videos" report (`dimensions=video`) does not list `video` as a filter.
  - Parameters: `ids=channel==MINE`, `startDate` = publish date, `endDate` = today, and the metrics
    `views, engagedViews, estimatedMinutesWatched, averageViewDuration, averageViewPercentage, likes, comments, shares, subscribersGained`.
  - `rows` is omitted until data exists.
