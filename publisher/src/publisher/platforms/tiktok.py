"""TikTok via the Content Posting API in Upload (inbox/draft) mode.

The video lands in the creator's TikTok inbox as a draft; the creator adds the caption,
chooses privacy and posts it in the app. The API accepts no caption or privacy in this mode.

Official references (checked 2026-09-28):
- inbox init: https://developers.tiktok.com/doc/content-posting-api-reference-upload-video
- chunked upload: https://developers.tiktok.com/doc/content-posting-api-media-transfer-guide
- status: https://developers.tiktok.com/doc/content-posting-api-reference-get-video-status
- errors: https://developers.tiktok.com/doc/tiktok-api-v2-error-handling
- desktop OAuth + PKCE: https://developers.tiktok.com/doc/login-kit-desktop
- tokens: https://developers.tiktok.com/doc/oauth-user-access-token-management
"""
import hashlib
import secrets
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlencode

import httpx

from .. import media
from ..content import ContentItem
from ..db import PROCESSING, SENT_TO_INBOX, UPLOADING
from ..media import Issue
from ..retry import PermanentError, TransientError
from ..tokens import TokenStore
from .base import AuthRequired, PublishContext

TRANSIENT_CODES = {"internal_error", "rate_limit_exceeded"}
QUOTA_CODES = {"spam_risk_too_many_pending_share"}  # at most 5 pending shares per 24 h
RETRYABLE_FAIL_REASONS = {"internal"}                # "This is a retryable error."
DONE_STATUSES = {"SEND_TO_USER_INBOX", "PUBLISH_COMPLETE"}


class UploadGone(TransientError):
    """The upload can't continue (URL expired, interrupted); start over with a new init."""


def classify(resp: httpx.Response) -> Exception:
    try:
        err = resp.json()["error"]
        code, message = err.get("code"), err.get("message")
    except (ValueError, KeyError, TypeError, AttributeError):
        code, message = None, resp.text[:300]
    text = f"TikTok {resp.status_code} {code or ''}: {message}".strip()
    kw = {"status": resp.status_code, "reason": code}
    if resp.status_code >= 500 or code in TRANSIENT_CODES:
        return TransientError(text, **kw)
    if code in QUOTA_CODES:
        return PermanentError(text, retry_later=True, **kw)
    if code in ("access_token_invalid", "scope_not_authorized"):
        return PermanentError(text + " (run `publisher auth tiktok`)", **kw)
    return PermanentError(text, **kw)


def chunk_plan(size: int, cfg: dict[str, Any]) -> tuple[int, int]:
    """(chunk_size, total_chunk_count) per the media transfer guide: one piece up to
    single_chunk_max_bytes, otherwise fixed chunks with the remainder in the last one."""
    if size <= cfg["single_chunk_max_bytes"]:
        return size, 1
    chunk = cfg["chunk_size_bytes"]
    return chunk, size // chunk


def chunk_ranges(size: int, chunk: int, count: int) -> list[tuple[int, int]]:
    """Inclusive byte ranges; the last chunk runs to the end of the file."""
    return [(i * chunk, (size - 1) if i == count - 1 else (i + 1) * chunk - 1) for i in range(count)]


def _now() -> datetime:
    return datetime.now(timezone.utc)


# -- OAuth (desktop, PKCE with hex SHA-256) -------------------------------

def pkce_pair() -> tuple[str, str]:
    """(code_verifier, code_challenge). TikTok desktop uses the HEX encoding of SHA-256,
    not RFC 7636's base64url: `CryptoJS.SHA256(code_verifier).toString(CryptoJS.enc.Hex)`."""
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
    verifier = "".join(secrets.choice(alphabet) for _ in range(64))
    return verifier, hashlib.sha256(verifier.encode()).hexdigest()


def authorize_url(cfg: dict[str, Any], client_key: str, redirect_uri: str, state: str, challenge: str) -> str:
    return cfg["auth_url"] + "?" + urlencode({
        "client_key": client_key, "scope": ",".join(cfg["scopes"]), "response_type": "code",
        "redirect_uri": redirect_uri, "state": state, "code_challenge": challenge, "code_challenge_method": "S256"})


class TikTokAuth:
    """Access tokens last 24 h, refresh tokens 365 days and rotate on every refresh."""

    def __init__(self, store: TokenStore, cfg: dict[str, Any], client_key: str, client_secret: str,
                 http: httpx.Client | None = None, now: Callable[[], datetime] = _now):
        self.store, self.cfg, self.now = store, cfg, now
        self.client_key, self.client_secret = client_key, client_secret
        self.http = http or httpx.Client(timeout=30.0)

    def _token_request(self, form: dict[str, str]) -> dict[str, Any]:
        if not self.client_key or not self.client_secret:
            raise AuthRequired("set PUBLISHER_TIKTOK_CLIENT_KEY and PUBLISHER_TIKTOK_CLIENT_SECRET in .env")
        resp = self.http.post(f"{self.cfg['api_url']}/v2/oauth/token/", data={
            "client_key": self.client_key, "client_secret": self.client_secret, **form})
        body = resp.json() if resp.content else {}
        if resp.status_code != 200 or "access_token" not in body:
            # OAuth errors are flat: {"error", "error_description", "log_id"}
            msg = f"TikTok token error {resp.status_code}: {body.get('error')} {body.get('error_description', '')}"
            if resp.status_code >= 500:
                raise TransientError(msg, status=resp.status_code)
            raise AuthRequired(msg + " (run `publisher auth tiktok`)")
        now = self.now()
        info = {"access_token": body["access_token"], "refresh_token": body["refresh_token"],
                "open_id": body.get("open_id"), "scope": body.get("scope"),
                "expires_at": (now + timedelta(seconds=int(body["expires_in"]))).isoformat(),
                "refresh_expires_at": (now + timedelta(seconds=int(body["refresh_expires_in"]))).isoformat()}
        self.store.write("tiktok", info)
        return info

    def exchange_code(self, code: str, redirect_uri: str, verifier: str) -> dict[str, Any]:
        return self._token_request({"code": code, "grant_type": "authorization_code",
                                    "redirect_uri": redirect_uri, "code_verifier": verifier})

    def token(self, force: bool = False) -> str:
        info = self.store.read("tiktok")
        if not info:
            raise AuthRequired("no TikTok token; run `publisher auth tiktok`")
        now = self.now()
        if datetime.fromisoformat(info["refresh_expires_at"]) <= now:
            raise AuthRequired("TikTok authorization expired (365 days); run `publisher auth tiktok`")
        if force or datetime.fromisoformat(info["expires_at"]) - now < timedelta(minutes=5):
            # the returned refresh_token may differ from the old one: always store the new one
            info = self._token_request({"grant_type": "refresh_token", "refresh_token": info["refresh_token"]})
        return info["access_token"]


def run_login(auth: TikTokAuth, cfg: dict[str, Any], open_browser: Callable[[str], Any]) -> dict[str, Any]:
    """Loopback OAuth: listen on 127.0.0.1:<free port>/callback/, open the browser, exchange the code."""
    import http.server
    from urllib.parse import parse_qs, urlparse

    verifier, challenge = pkce_pair()
    state = secrets.token_urlsafe(16)
    result: dict[str, str] = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            url = urlparse(self.path)
            if url.path.rstrip("/") != "/callback":
                self.send_response(404)
                self.end_headers()
                return
            result.update({k: v[0] for k, v in parse_qs(url.query).items()})  # parse_qs URL-decodes the code
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write("TikTok authorization received. You can close this tab.".encode())

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    redirect_uri = f"http://127.0.0.1:{server.server_port}/callback/"
    open_browser(authorize_url(cfg, auth.client_key, redirect_uri, state, challenge))
    while "code" not in result and "error" not in result:
        server.handle_request()
    server.server_close()
    if result.get("error"):
        raise AuthRequired(f"TikTok authorization failed: {result['error']} {result.get('error_description', '')}")
    if result.get("state") != state:
        raise AuthRequired("TikTok authorization failed: state mismatch")
    return auth.exchange_code(result["code"], redirect_uri, verifier)


# -- adapter ---------------------------------------------------------------

class TikTok:
    name = "tiktok"

    def __init__(self, cfg: dict[str, Any], auth, http: httpx.Client | None = None,
                 sleep: Callable[[float], None] = time.sleep):
        self.cfg, self.auth, self.sleep = cfg, auth, sleep
        self.http = http or httpx.Client(timeout=httpx.Timeout(60.0, read=600.0, write=600.0))

    def check(self, item: ContentItem) -> list[Issue]:
        return media.check(media.probe(item.video), self.cfg["limits"])

    def describe(self, item: ContentItem) -> str:
        return (f"send {item.video.name} ({item.video.stat().st_size / 1e6:.1f} MB) to the TikTok inbox as a draft; "
                f"finish it in the app with caption '{item.meta.tiktok.caption[:60]}'")

    def preflight(self) -> None:
        self.auth.token()

    # -- HTTP -------------------------------------------------------------

    def _api(self, path: str, body: dict[str, Any], params: dict[str, str] | None = None) -> dict[str, Any]:
        url = f"{self.cfg['api_url']}{path}"
        headers = {"Content-Type": "application/json; charset=UTF-8"}
        try:
            resp = self.http.post(url, params=params, json=body, headers={**headers, "Authorization": f"Bearer {self.auth.token()}"})
            if resp.status_code == 401 and _code(resp) == "access_token_invalid":
                resp = self.http.post(url, params=params, json=body, headers={**headers, "Authorization": f"Bearer {self.auth.token(True)}"})
        except httpx.TransportError as exc:
            raise TransientError(f"TikTok network error: {exc}") from exc
        if resp.status_code != 200 or _code(resp) != "ok":
            raise classify(resp)
        return resp.json()["data"]

    def init_upload(self, size: int) -> tuple[str, str, int, int]:
        chunk, count = chunk_plan(size, self.cfg)
        data = self._api("/v2/post/publish/inbox/video/init/", {"source_info": {
            "source": "FILE_UPLOAD", "video_size": size, "chunk_size": chunk, "total_chunk_count": count}})
        return data["publish_id"], data["upload_url"], chunk, count

    def put_chunks(self, upload_url: str, path: Path, chunk: int, count: int) -> None:
        size = path.stat().st_size
        with open(path, "rb") as f:
            for first, last in chunk_ranges(size, chunk, count):
                f.seek(first)
                data = f.read(last - first + 1)
                headers = {"Content-Type": "video/mp4", "Content-Length": str(len(data)),
                           "Content-Range": f"bytes {first}-{last}/{size}"}
                for attempt in range(3):  # "retry submitting this chunk" on 5xx
                    try:
                        resp = self.http.put(upload_url, content=data, headers=headers)
                    except httpx.TransportError as exc:
                        raise UploadGone(f"TikTok chunk upload interrupted: {exc}") from exc
                    if resp.status_code < 500:
                        break
                    self.sleep(2 ** attempt)
                if resp.status_code in (201, 206):
                    continue
                if resp.status_code == 403:
                    raise UploadGone("TikTok upload URL expired (valid 1 h)", status=403)
                if resp.status_code >= 500:
                    raise UploadGone(f"TikTok chunk upload failed {resp.status_code}", status=resp.status_code)
                raise PermanentError(f"TikTok chunk upload rejected {resp.status_code} (bytes {first}-{last}/{size})",
                                     status=resp.status_code)

    def fetch_status(self, publish_id: str) -> dict[str, Any]:
        return self._api("/v2/post/publish/status/fetch/", {"publish_id": publish_id})

    # -- state machine ----------------------------------------------------

    def publish(self, ctx: PublishContext) -> None:
        pub = ctx.pub
        try:
            publish_id = pub.get("upload_session")
            if publish_id and pub.get("state") != PROCESSING:
                # A previous run stopped mid-upload. If the upload actually finished, the status says so;
                # otherwise the chunk URL (valid 1 h) can't be trusted and we start over.
                status = self.fetch_status(publish_id)
                if status.get("status") in DONE_STATUSES | {"PROCESSING_DOWNLOAD"}:
                    ctx.save(state=PROCESSING)
                else:
                    publish_id = None
            if not publish_id:
                size = ctx.item.video.stat().st_size
                publish_id, upload_url, chunk, count = self.init_upload(size)
                ctx.save(upload_session=publish_id, upload_started_at=_now().isoformat(timespec="seconds"))
                self.put_chunks(upload_url, ctx.item.video, chunk, count)
                ctx.save(state=PROCESSING)
                if ctx.log:
                    ctx.log.info("tiktok.uploaded", publish_id=publish_id, chunks=count)
            self._wait(ctx)
        except UploadGone:
            ctx.save(state=UPLOADING, upload_session=None)
            raise

    def _wait(self, ctx: PublishContext) -> None:
        publish_id = ctx.pub["upload_session"]
        deadline = time.monotonic() + self.cfg.get("processing_timeout_seconds", 300)
        while True:
            data = self.fetch_status(publish_id)
            status = data.get("status")
            if status in DONE_STATUSES:
                ctx.save(state=SENT_TO_INBOX, published_at=_now().isoformat(timespec="seconds"))
                if ctx.log:
                    ctx.log.info("tiktok.sent_to_inbox", publish_id=publish_id, status=status)
                return
            if status == "FAILED":
                reason = data.get("fail_reason")
                if reason in RETRYABLE_FAIL_REASONS:
                    raise UploadGone(f"TikTok processing failed ({reason}); retrying with a new upload", reason=reason)
                raise PermanentError(f"TikTok rejected the video: {reason}", reason=reason,
                                     retry_later=reason == "spam_risk_too_many_posts")
            if time.monotonic() > deadline:
                return  # still processing: the next run checks again
            self.sleep(self.cfg.get("processing_poll_seconds", 10))

    # -- metrics (phase 4) -------------------------------------------------

    FIELDS = "id,create_time,duration,view_count,like_count,comment_count,share_count"

    def collect(self, pubs: list[dict[str, Any]], today: str) -> dict[int, dict[str, float | None]]:
        """Display API /v2/video/query/ (scope video.list), up to 20 ids per call. There is no
        watch-time or retention data in any official API available to creators."""
        out: dict[int, dict[str, float | None]] = {}
        by_id = {p["remote_id"]: p for p in pubs}
        ids = list(by_id)
        for i in range(0, len(ids), 20):
            data = self._api("/v2/video/query/", {"filters": {"video_ids": ids[i:i + 20]}}, params={"fields": self.FIELDS})
            for v in data.get("videos", []):
                pub = by_id.get(str(v.get("id")))
                if pub:
                    out[pub["id"]] = {k: float(v[k]) for k in ("view_count", "like_count", "comment_count", "share_count", "duration")
                                      if isinstance(v.get(k), (int, float))}
        return out

    def public_post_id(self, publish_id: str) -> str | None:
        """The TikTok video id once the creator has posted it publicly and it passed moderation."""
        data = self.fetch_status(publish_id)
        ids = data.get("publicaly_available_post_id") or []  # sic: the API's spelling
        return str(ids[0]) if data.get("status") == "PUBLISH_COMPLETE" and ids else None


def _code(resp: httpx.Response) -> str | None:
    try:
        return resp.json()["error"]["code"]
    except (ValueError, KeyError, TypeError):
        return None
