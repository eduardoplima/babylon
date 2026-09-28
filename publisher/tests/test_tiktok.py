import hashlib
import json
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import respx

from publisher import content, db, service
from publisher.platforms.base import AuthRequired
from publisher.platforms.tiktok import TikTok, TikTokAuth, authorize_url, chunk_plan, chunk_ranges, pkce_pair
from publisher.tokens import TokenStore
from conftest import make_video, write_content

API = "open.tiktokapis.com"
UPLOAD_URL = "https://open-upload.tiktokapis.com/video/?upload_id=1&upload_token=x"
NOW = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)
noop = lambda s: None
MB = 1024 * 1024


class FakeAuth:
    def __init__(self):
        self.forced = 0

    def token(self, force=False):
        self.forced += force
        return "fresh" if force else "tok"


def ok(data):
    return httpx.Response(200, json={"data": data, "error": {"code": "ok", "message": "", "log_id": "L"}})


def err(http, code, msg="x"):
    return httpx.Response(http, json={"data": {}, "error": {"code": code, "message": msg, "log_id": "L"}})


@pytest.fixture(scope="module")
def clip(tmp_path_factory):
    return make_video(tmp_path_factory.mktemp("tt") / "clip.mp4", w=360, h=640, seconds=2)


@pytest.fixture
def item(settings, clip):
    d = write_content(settings, "001-test", clip, youtube=None, tiktok={"caption": "Every empire gets eaten #rome"})
    return content.load(d, settings)


@pytest.fixture
def tt(settings):
    return TikTok(settings.platform("tiktok"), FakeAuth(), http=httpx.Client(), sleep=noop)


@pytest.fixture
def api():
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as r:
        r.init = r.post(f"https://{API}/v2/post/publish/inbox/video/init/")
        r.put_ = r.put(UPLOAD_URL)
        r.status = r.post(f"https://{API}/v2/post/publish/status/fetch/")
        yield r


def happy(api):
    api.init.mock(return_value=ok({"publish_id": "v_inbox_file~v2.1", "upload_url": UPLOAD_URL}))
    api.put_.mock(return_value=httpx.Response(201))
    api.status.mock(side_effect=[ok({"status": "PROCESSING_UPLOAD"}), ok({"status": "SEND_TO_USER_INBOX"})])


# -- chunking rules (media transfer guide) --------------------------------

def test_chunk_plan_matches_guide(settings):
    cfg = settings.platform("tiktok")
    assert chunk_plan(3 * MB, cfg) == (3 * MB, 1)            # < 5 MB: whole file
    assert chunk_plan(47 * MB, cfg) == (47 * MB, 1)          # <= 64 MB: one piece
    chunk, count = chunk_plan(50_000_123 * 2, cfg)           # > 64 MB: 10 MiB chunks, floor
    assert chunk == 10 * MB and count == (100_000_246 // chunk)
    ranges = chunk_ranges(100_000_246, chunk, count)
    assert ranges[0] == (0, chunk - 1) and ranges[-1][1] == 100_000_245
    assert all(b + 1 == c for (_, b), (c, _) in zip(ranges, ranges[1:]))
    assert ranges[-1][1] - ranges[-1][0] + 1 <= 128 * MB     # last chunk absorbs the remainder


def test_guide_worked_example():
    # video_size 50000123, chunk_size 10000000 -> 5 chunks, the last one 40000000-50000122
    ranges = chunk_ranges(50_000_123, 10_000_000, 50_000_123 // 10_000_000)
    assert len(ranges) == 5 and ranges[-1] == (40_000_000, 50_000_122)


# -- publishing ----------------------------------------------------------

def test_inbox_upload_happy_path(item, tt, conn, api):
    happy(api)
    out = service.publish(item, tt, conn, live=True, sleep=noop)
    assert out.action == "sent_to_inbox" and "Every empire gets eaten #rome" in out.detail

    init = api.init.calls[0].request
    size = item.video.stat().st_size
    assert init.headers["Authorization"] == "Bearer tok"
    assert init.headers["Content-Type"] == "application/json; charset=UTF-8"
    assert json.loads(init.content) == {"source_info": {"source": "FILE_UPLOAD", "video_size": size,
                                                        "chunk_size": size, "total_chunk_count": 1}}
    put = api.put_.calls[0].request
    assert put.headers["Content-Range"] == f"bytes 0-{size - 1}/{size}" and put.headers["Content-Type"] == "video/mp4"
    assert put.content == item.video.read_bytes()
    assert json.loads(api.status.calls[0].request.content) == {"publish_id": "v_inbox_file~v2.1"}
    row = db.get(conn, "001-test", "tiktok")
    assert row["state"] == db.SENT_TO_INBOX and row["upload_session"] == "v_inbox_file~v2.1"


def test_multi_chunk_upload(item, settings, conn, api):
    cfg = {**settings.platform("tiktok"), "single_chunk_max_bytes": 1000, "chunk_size_bytes": 4000}
    tt = TikTok(cfg, FakeAuth(), http=httpx.Client(), sleep=noop)
    size = item.video.stat().st_size
    count = size // 4000
    happy(api)
    api.put_.mock(side_effect=[httpx.Response(206)] * (count - 1) + [httpx.Response(201)])
    assert service.publish(item, tt, conn, live=True, sleep=noop).action == "sent_to_inbox"
    body = json.loads(api.init.calls[0].request.content)["source_info"]
    assert (body["chunk_size"], body["total_chunk_count"]) == (4000, count)
    got = b"".join(c.request.content for c in api.put_.calls)
    assert got == item.video.read_bytes()
    assert api.put_.calls[-1].request.headers["Content-Range"] == f"bytes {(count - 1) * 4000}-{size - 1}/{size}"


def test_inbox_is_terminal(item, tt, conn, api, settings):
    happy(api)
    args = dict(live=True, now=NOW, tz=settings.tz, daily_caps={"tiktok": 5}, sleep=noop)
    assert service.publish_due([item], {"tiktok": tt}, conn, **args)[0].action == "sent_to_inbox"
    assert service.publish_due([item], {"tiktok": tt}, conn, **args)[0].action == "skipped"
    assert api.init.call_count == 1


def test_pending_share_cap(item, tt, conn, api, settings):
    out = service.publish_due([item], {"tiktok": tt}, conn, live=True, now=NOW, tz=settings.tz,
                              daily_caps={"tiktok": 0}, sleep=noop)
    assert out[0].action == "skipped" and "daily cap" in out[0].detail and not api.calls


def test_too_many_pending_shares_waits(item, tt, conn, api):
    api.init.mock(return_value=err(403, "spam_risk_too_many_pending_share"))
    out = service.publish(item, tt, conn, live=True, sleep=noop, now=NOW)
    row = db.get(conn, "001-test", "tiktok")
    assert out.action == "failed" and row["retryable"] == 1 and row["retry_after"] and api.init.call_count == 1


def test_expired_upload_url_restarts(item, tt, conn, api):
    happy(api)
    api.init.mock(side_effect=[ok({"publish_id": "p1", "upload_url": UPLOAD_URL}),
                               ok({"publish_id": "p2", "upload_url": UPLOAD_URL})])
    api.put_.mock(side_effect=[httpx.Response(403), httpx.Response(201)])
    api.status.mock(return_value=ok({"status": "SEND_TO_USER_INBOX"}))
    assert service.publish(item, tt, conn, live=True, sleep=noop).action == "sent_to_inbox"
    assert db.get(conn, "001-test", "tiktok")["upload_session"] == "p2"


def test_chunk_5xx_is_retried_in_place(item, tt, conn, api):
    happy(api)
    api.put_.mock(side_effect=[httpx.Response(502), httpx.Response(201)])
    api.status.mock(return_value=ok({"status": "SEND_TO_USER_INBOX"}))
    assert service.publish(item, tt, conn, live=True, sleep=noop).action == "sent_to_inbox"
    assert api.init.call_count == 1 and api.put_.call_count == 2


def test_crash_after_upload_is_recognised(item, tt, conn, api):
    row = db.ensure(conn, "001-test", "tiktok")
    db.update(conn, row["id"], state=db.UPLOADING, upload_session="p1")
    api.status.mock(return_value=ok({"status": "SEND_TO_USER_INBOX"}))
    assert service.publish(item, tt, conn, live=True, sleep=noop).action == "sent_to_inbox"
    assert not api.init.called and not api.put_.called


def test_crash_mid_upload_starts_over(item, tt, conn, api):
    row = db.ensure(conn, "001-test", "tiktok")
    db.update(conn, row["id"], state=db.UPLOADING, upload_session="p1")
    happy(api)
    api.status.mock(side_effect=[ok({"status": "PROCESSING_UPLOAD"}), ok({"status": "SEND_TO_USER_INBOX"})])
    assert service.publish(item, tt, conn, live=True, sleep=noop).action == "sent_to_inbox"
    assert api.init.call_count == 1


def test_rejected_video_is_permanent(item, tt, conn, api):
    happy(api)
    api.status.mock(return_value=ok({"status": "FAILED", "fail_reason": "frame_rate_check_failed"}))
    out = service.publish(item, tt, conn, live=True, sleep=noop)
    assert out.action == "failed" and "frame_rate_check_failed" in out.detail
    assert db.get(conn, "001-test", "tiktok")["retryable"] == 0


def test_internal_fail_reason_retries_with_new_upload(item, tt, conn, api):
    happy(api)
    api.init.mock(side_effect=[ok({"publish_id": "p1", "upload_url": UPLOAD_URL}),
                               ok({"publish_id": "p2", "upload_url": UPLOAD_URL})])
    api.status.mock(side_effect=[ok({"status": "FAILED", "fail_reason": "internal"}), ok({"status": "SEND_TO_USER_INBOX"})])
    assert service.publish(item, tt, conn, live=True, sleep=noop).action == "sent_to_inbox"
    assert api.init.call_count == 2


def test_invalid_token_refreshes_once(item, tt, conn, api):
    happy(api)
    api.init.mock(side_effect=[err(401, "access_token_invalid"), ok({"publish_id": "p1", "upload_url": UPLOAD_URL})])
    assert service.publish(item, tt, conn, live=True, sleep=noop).action == "sent_to_inbox"
    assert api.init.calls[1].request.headers["Authorization"] == "Bearer fresh"


def test_rate_limit_is_transient(item, tt, conn, api):
    happy(api)
    api.init.mock(side_effect=[err(429, "rate_limit_exceeded"), ok({"publish_id": "p1", "upload_url": UPLOAD_URL})])
    assert service.publish(item, tt, conn, live=True, sleep=noop).action == "sent_to_inbox"


def test_public_post_id(tt, api):
    api.status.mock(side_effect=[ok({"status": "SEND_TO_USER_INBOX", "publicaly_available_post_id": []}),
                                 ok({"status": "PUBLISH_COMPLETE", "publicaly_available_post_id": [7300000000000000001]})])
    assert tt.public_post_id("p1") is None
    assert tt.public_post_id("p1") == "7300000000000000001"


def test_dry_run_silent(item, tt, conn, api, settings):
    out = service.publish_due([item], {"tiktok": tt}, conn, live=False, now=NOW, tz=settings.tz, daily_caps={})
    assert out[0].action == "dry-run" and "inbox as a draft" in out[0].detail and not api.calls


# -- OAuth ---------------------------------------------------------------

def test_pkce_is_hex_sha256():
    verifier, challenge = pkce_pair()
    assert 43 <= len(verifier) <= 128
    assert challenge == hashlib.sha256(verifier.encode()).hexdigest()
    assert len(challenge) == 64 and all(c in "0123456789abcdef" for c in challenge)


def test_authorize_url(settings):
    url = authorize_url(settings.platform("tiktok"), "CK", "http://127.0.0.1:5555/callback/", "S", "CH")
    q = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
    assert url.startswith("https://www.tiktok.com/v2/auth/authorize/?")
    assert q == {"client_key": "CK", "scope": "video.upload,video.list", "response_type": "code",
                 "redirect_uri": "http://127.0.0.1:5555/callback/", "state": "S", "code_challenge": "CH",
                 "code_challenge_method": "S256"}


TOKEN_BODY = {"access_token": "act.1", "expires_in": 86400, "open_id": "o", "refresh_expires_in": 31536000,
              "refresh_token": "rft.1", "scope": "video.upload,video.list", "token_type": "Bearer"}


@pytest.fixture
def store(tmp_path):
    return TokenStore(tmp_path / ".secrets")


def auth_for(store, settings, now=NOW):
    return TikTokAuth(store, settings.platform("tiktok"), "CK", "CS", http=httpx.Client(), now=lambda: now)


def test_exchange_code(store, settings):
    with respx.mock(assert_all_mocked=True) as r:
        tok = r.post(f"https://{API}/v2/oauth/token/").mock(return_value=httpx.Response(200, json=TOKEN_BODY))
        info = auth_for(store, settings).exchange_code("C+1", "http://127.0.0.1:5555/callback/", "V")
    form = parse_qs(tok.calls[0].request.content.decode())
    assert tok.calls[0].request.headers["Content-Type"] == "application/x-www-form-urlencoded"
    assert {k: v[0] for k, v in form.items()} == {"client_key": "CK", "client_secret": "CS", "code": "C+1",
                                                  "grant_type": "authorization_code", "code_verifier": "V",
                                                  "redirect_uri": "http://127.0.0.1:5555/callback/"}
    assert info["expires_at"].startswith("2026-10-03") and store.read("tiktok")["refresh_token"] == "rft.1"


def test_refresh_rotates_refresh_token(store, settings):
    store.write("tiktok", {"access_token": "act.0", "refresh_token": "rft.0", "open_id": "o", "scope": "",
                           "expires_at": (NOW + timedelta(minutes=2)).isoformat(),
                           "refresh_expires_at": (NOW + timedelta(days=300)).isoformat()})
    with respx.mock(assert_all_mocked=True) as r:
        tok = r.post(f"https://{API}/v2/oauth/token/").mock(
            return_value=httpx.Response(200, json={**TOKEN_BODY, "access_token": "act.2", "refresh_token": "rft.2"}))
        assert auth_for(store, settings).token() == "act.2"
    assert parse_qs(tok.calls[0].request.content.decode())["refresh_token"] == ["rft.0"]
    assert store.read("tiktok")["refresh_token"] == "rft.2"


def test_valid_token_not_refreshed(store, settings):
    store.write("tiktok", {"access_token": "act.0", "refresh_token": "rft.0", "open_id": "o", "scope": "",
                           "expires_at": (NOW + timedelta(hours=5)).isoformat(),
                           "refresh_expires_at": (NOW + timedelta(days=300)).isoformat()})
    with respx.mock(assert_all_mocked=True):
        assert auth_for(store, settings).token() == "act.0"


def test_oauth_error_is_flat_and_requires_login(store, settings):
    with respx.mock(assert_all_mocked=True) as r:
        r.post(f"https://{API}/v2/oauth/token/").mock(return_value=httpx.Response(
            400, json={"error": "invalid_request", "error_description": "Redirect_uri is not matched", "log_id": "L"}))
        with pytest.raises(AuthRequired, match="Redirect_uri is not matched"):
            auth_for(store, settings).exchange_code("C", "http://127.0.0.1:1/callback/", "V")


def test_expired_authorization(store, settings):
    store.write("tiktok", {"access_token": "a", "refresh_token": "r", "expires_at": NOW.isoformat(),
                           "refresh_expires_at": (NOW - timedelta(days=1)).isoformat()})
    with pytest.raises(AuthRequired, match="365 days"):
        auth_for(store, settings).token()


def test_run_login_end_to_end(store, settings):
    """The browser is simulated: it follows the authorize URL's redirect_uri with code + state."""
    import threading
    import urllib.request

    from publisher.platforms.tiktok import run_login

    seen = {}

    def browser(url):
        q = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
        seen.update(q)
        cb = f"{q['redirect_uri']}?code=CODE%2B1&scopes=video.upload&state={q['state']}"
        threading.Thread(target=lambda: seen.setdefault("page", urllib.request.urlopen(cb).read())).start()

    with respx.mock(assert_all_mocked=True) as r:  # the callback itself is a real loopback request via urllib
        tok = r.post(f"https://{API}/v2/oauth/token/").mock(return_value=httpx.Response(200, json=TOKEN_BODY))
        info = run_login(auth_for(store, settings), settings.platform("tiktok"), browser)
    form = {k: v[0] for k, v in parse_qs(tok.calls[0].request.content.decode()).items()}
    assert form["code"] == "CODE+1"                       # URL-decoded before the exchange
    assert hashlib.sha256(form["code_verifier"].encode()).hexdigest() == seen["code_challenge"]
    assert form["redirect_uri"] == seen["redirect_uri"] and seen["redirect_uri"].startswith("http://127.0.0.1:")
    assert info["access_token"] == "act.1"


def test_run_login_rejects_wrong_state(store, settings):
    import threading
    import urllib.request

    from publisher.platforms.tiktok import run_login

    def browser(url):
        q = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
        threading.Thread(target=lambda: urllib.request.urlopen(f"{q['redirect_uri']}?code=C&state=forged").read()).start()

    with pytest.raises(AuthRequired, match="state mismatch"):
        run_login(auth_for(store, settings), settings.platform("tiktok"), browser)
