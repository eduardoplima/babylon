"""YouTube Shorts via the YouTube Data API v3 (resumable upload over plain httpx).

Official references (checked 2026-09-27):
- videos.insert: https://developers.google.com/youtube/v3/docs/videos/insert
- resumable protocol: https://developers.google.com/youtube/v3/guides/using_resumable_upload_protocol
- videos resource (status, processingDetails): https://developers.google.com/youtube/v3/docs/videos
- errors: https://developers.google.com/youtube/v3/docs/errors
- installed-app OAuth: https://developers.google.com/youtube/v3/guides/auth/installed-apps
"""
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import httpx

from .. import media
from ..content import ContentItem, Meta
from ..db import PROCESSING, PUBLISHED
from ..media import Issue
from ..retry import PermanentError, TransientError
from ..tokens import TokenStore
from .base import AuthRequired, NeedsReconcile, PublishContext

# youtube.upload: videos.insert. youtube.readonly + yt-analytics.readonly: metrics (phase 4);
# reports.query now also requires youtube.readonly.
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]

# Error reasons worth retrying (the official upload sample retries 500/502/503/504).
TRANSIENT_REASONS = {"backendError", "rateLimitExceeded", "internalError"}
# Daily limits that reset: don't retry now, retry on a later run.
QUOTA_REASONS = {"quotaExceeded", "uploadLimitExceeded"}


def classify(resp: httpx.Response) -> TransientError | PermanentError:
    """Turn an error response into TransientError or PermanentError using the
    Google error body {"error": {"code", "message", "errors": [{"reason"}]}}."""
    reason, message = None, resp.text[:500]
    try:
        err = resp.json()["error"]
        message = err.get("message", message)
        reason = (err.get("errors") or [{}])[0].get("reason") or err.get("status")
    except (ValueError, KeyError, TypeError):
        pass
    text = f"YouTube {resp.status_code} {reason or ''}: {message}".strip()
    if resp.status_code >= 500 or reason in TRANSIENT_REASONS:
        return TransientError(text, status=resp.status_code, reason=reason)
    return PermanentError(text, status=resp.status_code, reason=reason, retry_later=reason in QUOTA_REASONS)


class YouTube:
    name = "youtube"

    def __init__(self, cfg: dict[str, Any], token: Callable[[bool], str], http: httpx.Client | None = None,
                 sleep: Callable[[float], None] = time.sleep):
        self.cfg = cfg
        self.token = token
        self.http = http or httpx.Client(timeout=httpx.Timeout(60.0, read=600.0, write=600.0))
        self.sleep = sleep

    # -- no network -------------------------------------------------------

    def check(self, item: ContentItem) -> list[Issue]:
        return media.check(media.probe(item.video), self.cfg["limits"])

    def describe(self, item: ContentItem) -> str:
        yt = item.meta.youtube
        return (f"upload {item.video.name} ({item.video.stat().st_size / 1e6:.1f} MB) as {yt.privacy}, "
                f"title '{yt.title}', synthetic={item.meta.synthetic_media}")

    @staticmethod
    def video_body(meta: Meta) -> dict[str, Any]:
        yt = meta.youtube
        snippet: dict[str, Any] = {"title": yt.title, "description": yt.description, "categoryId": yt.category_id}
        if yt.tags:
            snippet["tags"] = yt.tags
        return {
            "snippet": snippet,
            "status": {
                "privacyStatus": yt.privacy,
                "selfDeclaredMadeForKids": yt.made_for_kids,
                "containsSyntheticMedia": meta.synthetic_media,
            },
        }

    def preflight(self) -> None:
        self.token(False)

    # -- HTTP -------------------------------------------------------------

    def _request(self, method: str, url: str, **kw) -> httpx.Response:
        """Authorized request; on 401 refresh the token once and retry."""
        headers = kw.pop("headers", {})
        try:
            resp = self.http.request(method, url, headers={**headers, "Authorization": f"Bearer {self.token(False)}"}, **kw)
            if resp.status_code == 401:
                resp = self.http.request(method, url, headers={**headers, "Authorization": f"Bearer {self.token(True)}"}, **kw)
        except httpx.TransportError as exc:
            raise TransientError(f"YouTube network error: {exc}") from exc
        return resp

    def start_session(self, path: Path, body: dict[str, Any], notify: bool) -> str:
        resp = self._request(
            "POST", self.cfg["upload_url"],
            params={"uploadType": "resumable", "part": "snippet,status", "notifySubscribers": str(notify).lower()},
            headers={"X-Upload-Content-Length": str(path.stat().st_size), "X-Upload-Content-Type": "video/mp4"},
            json=body)
        if resp.status_code != 200 or "location" not in resp.headers:
            raise classify(resp)
        return resp.headers["location"]

    def query_session(self, uri: str, size: int) -> tuple[str, Any]:
        """Where an interrupted upload stands: ("complete", video), ("incomplete", next_byte)
        or ("expired", None)."""
        resp = self._request("PUT", uri, headers={"Content-Range": f"bytes */{size}", "Content-Length": "0"})
        if resp.status_code in (200, 201):
            return "complete", resp.json()
        if resp.status_code == 308:
            rng = resp.headers.get("range")  # "bytes=0-12345"
            return "incomplete", int(rng.rsplit("-", 1)[1]) + 1 if rng else 0
        # TODO(verificar): the status code for an expired/unknown upload session is not stated
        # in the resumable-upload guide; 404/410 are treated as expired.
        if resp.status_code in (404, 410):
            return "expired", None
        raise classify(resp)

    def send(self, uri: str, path: Path, offset: int, size: int) -> dict[str, Any]:
        def chunks():
            with open(path, "rb") as f:
                f.seek(offset)
                while block := f.read(8 * 1024 * 1024):
                    yield block

        headers = {"Content-Length": str(size - offset), "Content-Type": "video/mp4"}
        if offset:
            headers["Content-Range"] = f"bytes {offset}-{size - 1}/{size}"
        resp = self._request("PUT", uri, headers=headers, content=chunks())
        if resp.status_code in (200, 201):
            return resp.json()
        if resp.status_code == 308:
            raise TransientError("YouTube upload incomplete (308); will resume", status=308)
        raise classify(resp)

    def get_video(self, video_id: str) -> dict[str, Any] | None:
        resp = self._request("GET", f"{self.cfg['api_url']}/videos",
                             params={"id": video_id, "part": "status,processingDetails"})
        if resp.status_code != 200:
            raise classify(resp)
        items = resp.json().get("items", [])
        return items[0] if items else None

    # -- state machine ----------------------------------------------------

    def publish(self, ctx: PublishContext) -> None:
        item, pub = ctx.item, ctx.pub
        if not (pub.get("state") == PROCESSING and pub.get("remote_id")):
            self._upload(ctx)
        self._wait_processed(ctx)

    def _upload(self, ctx: PublishContext) -> None:
        item, pub = ctx.item, ctx.pub
        size = item.video.stat().st_size
        session, offset = pub.get("upload_session"), 0
        if session:
            kind, value = self.query_session(session, size)
            if kind == "complete":
                return self._uploaded(ctx, value)
            if kind == "expired":
                raise NeedsReconcile("YouTube upload session expired before we recorded the result; "
                                     "check YouTube Studio for this video, then `publisher resolve`")
            offset = value
        else:
            session = self.start_session(item.video, self.video_body(item.meta), item.meta.youtube.notify_subscribers)
            ctx.save(upload_session=session, upload_started_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
        if ctx.log:
            ctx.log.info("youtube.upload", offset=offset, size=size)
        self._uploaded(ctx, self.send(session, item.video, offset, size))

    def _uploaded(self, ctx: PublishContext, video: dict[str, Any]) -> None:
        vid = video["id"]
        ctx.save(state=PROCESSING, remote_id=vid, remote_url=f"https://www.youtube.com/shorts/{vid}", upload_session=None)
        if ctx.log:
            ctx.log.info("youtube.uploaded", video_id=vid)

    def _wait_processed(self, ctx: PublishContext) -> None:
        """Poll until processing finishes. On timeout the row stays `processing` and the next run polls again."""
        vid = ctx.pub["remote_id"]
        deadline = time.monotonic() + self.cfg.get("processing_timeout_seconds", 900)
        while True:
            video = self.get_video(vid)
            if video is None:
                raise NeedsReconcile(f"uploaded video {vid} not found via videos.list")
            status = video.get("status", {})
            proc = video.get("processingDetails", {}).get("processingStatus")
            if status.get("uploadStatus") in ("failed", "rejected", "deleted") or proc in ("failed", "terminated"):
                why = status.get("failureReason") or status.get("rejectionReason") or proc
                raise PermanentError(f"YouTube rejected {vid}: uploadStatus={status.get('uploadStatus')} reason={why}",
                                     reason=why)
            if proc == "succeeded" or status.get("uploadStatus") == "processed":
                ctx.save(state=PUBLISHED, published_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
                return
            if time.monotonic() > deadline:
                if ctx.log:
                    ctx.log.info("youtube.processing_timeout", video_id=vid)
                return
            self.sleep(self.cfg.get("processing_poll_seconds", 15))


# -- credentials ----------------------------------------------------------

def authorize(client_secrets: Path, store: TokenStore) -> None:
    """Interactive loopback OAuth (opens the browser) and store the refresh token."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    if not client_secrets.exists():
        raise AuthRequired(f"OAuth client file not found: {client_secrets} (Google Cloud Console → Credentials → "
                           "OAuth client ID → Desktop app → download JSON)")
    flow = InstalledAppFlow.from_client_secrets_file(str(client_secrets), scopes=SCOPES)
    # access_type=offline asks for a refresh token; prompt=consent makes Google return one
    # even if the user authorized before. TODO(verificar): prompt=consent behaviour.
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    store.write("youtube", _creds_to_dict(creds))


def token_provider(store: TokenStore) -> Callable[[bool], str]:
    """Returns token(force_refresh) -> access token, refreshing and saving as needed."""
    from google.auth.exceptions import RefreshError
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    def token(force: bool = False) -> str:
        info = store.read("youtube")
        if not info:
            raise AuthRequired("no YouTube token; run `publisher auth youtube`")
        creds = Credentials.from_authorized_user_info(info, SCOPES)
        if force or not creds.valid:
            try:
                creds.refresh(Request())
            except RefreshError as exc:
                # e.g. consent screen in "Testing" (refresh tokens expire after 7 days) or revoked access
                raise AuthRequired(f"YouTube refresh failed ({exc}); run `publisher auth youtube` again") from exc
            store.write("youtube", _creds_to_dict(creds))
        return creds.token

    return token


def _creds_to_dict(creds) -> dict[str, Any]:
    import json
    return json.loads(creds.to_json())
