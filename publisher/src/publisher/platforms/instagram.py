"""Instagram Reels via the Instagram API with Instagram Login (graph.instagram.com).

Official references (checked 2026-09-28):
- publishing guide: https://developers.facebook.com/docs/instagram-platform/content-publishing
- container creation (REELS, upload_type=resumable, rupload):
  https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/media
- container status: https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-container
- media_publish: https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/media_publish
- publishing limit: https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/content_publishing_limit
- errors: https://developers.facebook.com/docs/graph-api/guides/error-handling and
  https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/error-codes
- tokens: .../instagram-api-with-instagram-login/get-started (dashboard tokens are long-lived, 60 days),
  https://developers.facebook.com/docs/instagram-platform/reference/refresh_access_token
"""
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import httpx

from .. import media
from ..content import ContentItem
from ..db import PROCESSING, PUBLISHED, UPLOADING
from ..media import Issue
from ..retry import PermanentError, TransientError
from ..tokens import TokenStore
from .base import AuthRequired, NeedsReconcile, PublishContext

# Graph API codes (error-handling guide): 1 unknown, 2 service unavailable, 4/17 rate limit, 341 app limit.
TRANSIENT_CODES = {1, 2, 4, 17, 341}
AUTH_CODES = {102, 190}
# IG publishing subcodes (error-codes page).
NEW_CONTAINER_SUBCODES = {2207020, 2207032, 2207053}   # expired / re-create media / unknown upload error
TRANSIENT_SUBCODES = {2207001, 2207003, 2207006, 2207008, 2207027, 2207052}  # 2207027 = not ready yet
QUOTA_SUBCODES = {2207042}                              # "maximum number of posts": retry another day
PERMANENT_SUBCODES = {2207010, 2207026, 2207050, 2207051, 2207057}  # caption, format, restricted, spam, thumb


class ContainerGone(TransientError):
    """The container can't be used any more; start over with a new one."""


def classify(resp: httpx.Response) -> Exception:
    try:
        err = resp.json()["error"]
    except (ValueError, KeyError, TypeError):
        cls = TransientError if resp.status_code >= 500 else PermanentError
        return cls(f"Instagram {resp.status_code}: {resp.text[:300]}", status=resp.status_code)
    code, sub = err.get("code"), err.get("error_subcode")
    reason = f"{code}/{sub}" if sub else str(code)
    text = f"Instagram {resp.status_code} {reason}: {err.get('error_user_msg') or err.get('message')}"
    kw = {"status": resp.status_code, "reason": reason}
    if sub in NEW_CONTAINER_SUBCODES:
        return ContainerGone(text, **kw)
    if sub in QUOTA_SUBCODES:
        return PermanentError(text, retry_later=True, **kw)
    if sub in PERMANENT_SUBCODES:
        return PermanentError(text, **kw)
    if resp.status_code >= 500 or code in TRANSIENT_CODES or sub in TRANSIENT_SUBCODES:
        return TransientError(text, **kw)
    if code in AUTH_CODES:
        return PermanentError(text + " (run `publisher auth instagram`)", **kw)
    return PermanentError(text, **kw)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _data(body: dict[str, Any]) -> dict[str, Any]:
    """Some responses are wrapped in {"data": [...]}, others are flat; accept both."""
    if isinstance(body.get("data"), list) and body["data"]:
        return body["data"][0]
    return body


class InstagramAuth:
    """Long-lived Instagram User token (from the App Dashboard or an OAuth exchange),
    refreshed automatically once it is at least 24 h old and getting close to expiry."""

    def __init__(self, store: TokenStore, cfg: dict[str, Any], http: httpx.Client | None = None,
                 now: Callable[[], datetime] = _now):
        self.store, self.cfg, self.now = store, cfg, now
        self.http = http or httpx.Client(timeout=30.0)

    def save_token(self, access_token: str) -> dict[str, Any]:
        resp = self.http.get(f"{self.cfg['graph_url']}/{self.cfg['api_version']}/me",
                             params={"fields": "user_id,username", "access_token": access_token})
        if resp.status_code != 200:
            raise classify(resp)
        me = _data(resp.json())
        now = self.now()
        info = {"access_token": access_token, "user_id": str(me["user_id"]), "username": me.get("username"),
                "obtained_at": now.isoformat(), "expires_at": (now + timedelta(days=self.cfg["token_lifetime_days"])).isoformat()}
        self.store.write("instagram", info)
        return info

    def _info(self) -> dict[str, Any]:
        info = self.store.read("instagram")
        if not info:
            raise AuthRequired("no Instagram token; run `publisher auth instagram`")
        return info

    def user_id(self) -> str:
        return self._info()["user_id"]

    def days_left(self) -> float:
        info = self._info()
        return (datetime.fromisoformat(info["expires_at"]) - self.now()).total_seconds() / 86400

    def token(self, force: bool = False) -> str:
        info = self._info()
        now = self.now()
        expires = datetime.fromisoformat(info["expires_at"])
        if expires <= now:
            raise AuthRequired("Instagram token expired; generate a new one and run `publisher auth instagram`")
        old_enough = now - datetime.fromisoformat(info["obtained_at"]) >= timedelta(hours=24)
        due = (expires - now) < timedelta(days=self.cfg["refresh_when_days_left"])
        if old_enough and (force or due):
            try:
                info = self._refresh(info)
            except (TransientError, PermanentError, httpx.TransportError):
                if (expires - now) < timedelta(days=7):
                    raise
        return info["access_token"]

    def _refresh(self, info: dict[str, Any]) -> dict[str, Any]:
        resp = self.http.get(f"{self.cfg['graph_url']}/refresh_access_token",
                             params={"grant_type": "ig_refresh_token", "access_token": info["access_token"]})
        if resp.status_code != 200:
            raise classify(resp)
        body = resp.json()
        now = self.now()
        info = {**info, "access_token": body["access_token"], "obtained_at": now.isoformat(),
                "expires_at": (now + timedelta(seconds=int(body["expires_in"]))).isoformat()}
        self.store.write("instagram", info)
        return info


class Instagram:
    name = "instagram"

    def __init__(self, cfg: dict[str, Any], auth, http: httpx.Client | None = None,
                 sleep: Callable[[float], None] = time.sleep):
        self.cfg, self.auth, self.sleep = cfg, auth, sleep
        self.http = http or httpx.Client(timeout=httpx.Timeout(60.0, read=600.0, write=600.0))
        self.base = f"{cfg['graph_url']}/{cfg['api_version']}"

    # -- no network -------------------------------------------------------

    def check(self, item: ContentItem) -> list[Issue]:
        return media.check(media.probe(item.video), self.cfg["limits"])

    def describe(self, item: ContentItem) -> str:
        cap = item.meta.instagram.caption.replace("\n", " ")
        return (f"upload {item.video.name} ({item.video.stat().st_size / 1e6:.1f} MB) as a PUBLIC Reel "
                f"(Instagram has no private posts), caption '{cap[:60]}', ai_generated={item.meta.synthetic_media}")

    @staticmethod
    def container_params(item: ContentItem) -> dict[str, str]:
        ig = item.meta.instagram
        params = {"media_type": "REELS", "upload_type": "resumable", "caption": ig.caption,
                  # TODO(verificar): share_to_feed is documented for Reels but absent from the
                  # resumable example; confirm it is honoured with upload_type=resumable.
                  "share_to_feed": str(ig.share_to_feed).lower(),
                  "is_ai_generated": str(item.meta.synthetic_media).lower()}
        if ig.thumb_offset_ms is not None:
            params["thumb_offset"] = str(ig.thumb_offset_ms)
        return params

    def preflight(self) -> None:
        self.auth.token()
        self.auth.user_id()

    # -- HTTP -------------------------------------------------------------

    def _call(self, method: str, path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        try:
            resp = self.http.request(method, f"{self.base}/{path}",
                                     params={**(params or {}), "access_token": self.auth.token()})
        except httpx.TransportError as exc:
            raise TransientError(f"Instagram network error: {exc}") from exc
        if resp.status_code != 200:
            raise classify(resp)
        return resp.json()

    def create_container(self, item: ContentItem) -> str:
        return self._call("POST", f"{self.auth.user_id()}/media", self.container_params(item))["id"]

    def upload(self, container: str, path: Path) -> None:
        def chunks():
            with open(path, "rb") as f:
                while block := f.read(8 * 1024 * 1024):
                    yield block

        url = f"https://rupload.facebook.com/ig-api-upload/{self.cfg['api_version']}/{container}"
        size = path.stat().st_size
        try:
            resp = self.http.post(url, content=chunks(), headers={
                "Authorization": f"OAuth {self.auth.token()}", "offset": "0", "file_size": str(size),
                "Content-Length": str(size)})
        except httpx.TransportError as exc:
            raise ContainerGone(f"Instagram upload interrupted: {exc}") from exc
        body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        if resp.status_code == 200 and body.get("success"):
            return
        debug = body.get("debug_info", {})
        text = f"Instagram upload failed ({resp.status_code}): {debug.get('message') or resp.text[:300]}"
        if resp.status_code >= 500 or debug.get("retriable"):
            raise ContainerGone(text, status=resp.status_code, reason=debug.get("type"))
        raise PermanentError(text, status=resp.status_code, reason=debug.get("type"))

    def container_status(self, container: str) -> tuple[str, Any]:
        body = self._call("GET", container, {"fields": "status_code,status"})
        return body.get("status_code"), body.get("status")

    def publish_container(self, container: str) -> str:
        return self._call("POST", f"{self.auth.user_id()}/media_publish", {"creation_id": container})["id"]

    def permalink(self, media_id: str) -> str | None:
        try:
            return self._call("GET", media_id, {"fields": "permalink"}).get("permalink")
        except (TransientError, PermanentError):
            return None  # nice to have; the post is already live

    def remaining_quota(self) -> int:
        body = self._call("GET", f"{self.auth.user_id()}/content_publishing_limit", {"fields": "quota_usage,config"})
        d = _data(body)
        return int(d["config"]["quota_total"]) - int(d.get("quota_usage", 0))

    # -- metrics (phase 4) -------------------------------------------------

    # Valid for REELS: https://developers.facebook.com/docs/instagram-platform/reference/instagram-media/insights
    # TODO(verificar): units of ig_reels_avg_watch_time / ig_reels_video_view_total_time are not documented;
    # stored raw.
    INSIGHTS = ["views", "reach", "likes", "comments", "shares", "saved", "total_interactions",
                "ig_reels_avg_watch_time", "ig_reels_video_view_total_time", "reels_skip_rate"]

    def collect(self, pubs: list[dict[str, Any]], today: str) -> dict[int, dict[str, float | None]]:
        """Lifetime insights per Reel (period is always lifetime). The docs warn a multi-metric
        request can fail as a whole, so on a permanent error fall back to one metric at a time."""
        out: dict[int, dict[str, float | None]] = {}
        for p in pubs:
            try:
                values = self._insights(p["remote_id"], self.INSIGHTS)
            except PermanentError:
                values = {}
                for metric in self.INSIGHTS:
                    try:
                        values.update(self._insights(p["remote_id"], [metric]))
                    except PermanentError:
                        values[metric] = None
            out[p["id"]] = values
        return out

    def _insights(self, media_id: str, metrics: list[str]) -> dict[str, float | None]:
        body = self._call("GET", f"{media_id}/insights", {"metric": ",".join(metrics)})
        values = {}
        for d in body.get("data", []):
            v = (d.get("values") or [{}])[0].get("value")
            if v is None and isinstance(d.get("total_value"), dict):
                v = d["total_value"].get("value")
            values[d["name"]] = float(v) if isinstance(v, (int, float)) else None
        return values

    # -- state machine ----------------------------------------------------

    def publish(self, ctx: PublishContext) -> None:
        pub = ctx.pub
        try:
            if not (pub.get("state") == PROCESSING and pub.get("upload_session")):
                # A container whose upload may not have finished is abandoned: resuming a
                # rupload is not documented, and an unpublished container simply expires.
                container = self.create_container(ctx.item)
                ctx.save(upload_session=container, upload_started_at=_now().isoformat(timespec="seconds"))
                self.upload(container, ctx.item.video)
                ctx.save(state=PROCESSING)
                if ctx.log:
                    ctx.log.info("instagram.uploaded", container=container)
            self._finish(ctx)
        except ContainerGone:
            ctx.save(state=UPLOADING, upload_session=None)
            raise

    def _finish(self, ctx: PublishContext) -> None:
        container = ctx.pub["upload_session"]
        deadline = time.monotonic() + self.cfg.get("processing_timeout_seconds", 300)
        while True:
            code, status = self.container_status(container)
            if code == "FINISHED":
                media_id = self.publish_container(container)
                ctx.save(state=PUBLISHED, remote_id=media_id, remote_url=self.permalink(media_id),
                         upload_session=None, published_at=_now().isoformat(timespec="seconds"))
                if ctx.log:
                    ctx.log.info("instagram.published", media_id=media_id)
                return
            if code == "PUBLISHED":
                raise NeedsReconcile(f"container {container} is already published but its media id wasn't recorded; "
                                     "find the Reel and run `publisher resolve <slug> instagram --remote-id <id>`")
            if code == "EXPIRED":
                raise ContainerGone(f"container {container} expired (not published within 24 h)")
            if code == "ERROR":
                raise PermanentError(f"Instagram could not process the video (container {container}, status {status})",
                                     reason=str(status))
            if time.monotonic() > deadline:  # still IN_PROGRESS: next run polls again
                if ctx.log:
                    ctx.log.info("instagram.processing_timeout", container=container)
                return
            self.sleep(self.cfg.get("processing_poll_seconds", 60))
