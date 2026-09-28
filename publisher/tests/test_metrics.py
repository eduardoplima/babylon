import csv
import io
import json
from datetime import datetime, timezone

import httpx
import pytest
import respx

from publisher import content, db, export, service
from publisher.platforms.instagram import Instagram
from publisher.platforms.tiktok import TikTok
from publisher.platforms.youtube import YouTube
from conftest import write_content

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)
noop = lambda s: None


class Auth:
    def token(self, force=False):
        return "tok"

    def user_id(self):
        return "IGID"


def published(conn, slug, platform, remote_id, at="2026-10-02T21:00:00+00:00", **extra):
    row = db.ensure(conn, slug, platform)
    db.update(conn, row["id"], state=db.PUBLISHED, remote_id=remote_id, published_at=at, **extra)
    return db.get(conn, slug, platform)


@pytest.fixture
def yt(settings):
    return YouTube(settings.platform("youtube"), lambda force=False: "tok", http=httpx.Client(), sleep=noop)


@pytest.fixture
def ig(settings):
    return Instagram(settings.platform("instagram"), Auth(), http=httpx.Client(), sleep=noop)


@pytest.fixture
def tt(settings):
    return TikTok(settings.platform("tiktok"), Auth(), http=httpx.Client(), sleep=noop)


ANALYTICS_HEADERS = [{"name": n, "columnType": "METRIC", "dataType": "FLOAT"} for n in YouTube.ANALYTICS_METRICS]


# -- YouTube ---------------------------------------------------------------

def test_youtube_statistics_and_analytics(yt, conn):
    pub = dict(published(conn, "001", "youtube", "vid1"))
    with respx.mock(assert_all_mocked=True) as r:
        stats = r.get("https://www.googleapis.com/youtube/v3/videos").mock(return_value=httpx.Response(200, json={
            "items": [{"id": "vid1", "statistics": {"viewCount": "1500", "likeCount": "90", "favoriteCount": "0", "commentCount": "7"}}]}))
        rep = r.get("https://youtubeanalytics.googleapis.com/v2/reports").mock(return_value=httpx.Response(200, json={
            "kind": "youtubeAnalytics#resultTable", "columnHeaders": ANALYTICS_HEADERS,
            "rows": [[1800, 1400, 700.5, 23.4, 41.2, 90, 7, 12, 3]]}))
        got = yt.collect([pub], "2026-10-05")[pub["id"]]
    assert stats.calls[0].request.url.params["part"] == "statistics"
    q = rep.calls[0].request.url.params
    assert (q["ids"], q["startDate"], q["endDate"], q["filters"]) == ("channel==MINE", "2026-10-02", "2026-10-05", "video==vid1")
    assert "dimensions" not in q  # the documented per-video form has no dimension
    assert got["viewCount"] == 1500 and got["engagedViews"] == 1400 and got["averageViewPercentage"] == 41.2


def test_youtube_analytics_not_ready_keeps_statistics(yt, conn):
    pub = dict(published(conn, "001", "youtube", "vid1"))
    with respx.mock(assert_all_mocked=True) as r:
        r.get("https://www.googleapis.com/youtube/v3/videos").mock(return_value=httpx.Response(200, json={
            "items": [{"id": "vid1", "statistics": {"viewCount": "10", "likeCount": "1", "commentCount": "0"}}]}))
        r.get("https://youtubeanalytics.googleapis.com/v2/reports").mock(return_value=httpx.Response(200, json={
            "kind": "youtubeAnalytics#resultTable", "columnHeaders": ANALYTICS_HEADERS}))  # no "rows" yet
        assert yt.collect([pub], "2026-10-05")[pub["id"]] == {"viewCount": 10, "likeCount": 1, "commentCount": 0}


# -- Instagram -----------------------------------------------------------

def insight(name, value):
    return {"name": name, "period": "lifetime", "values": [{"value": value}], "title": name, "id": f"M1/insights/{name}/lifetime"}


def test_instagram_insights(ig, conn):
    pub = dict(published(conn, "001", "instagram", "M1"))
    with respx.mock(assert_all_mocked=True) as r:
        route = r.get("https://graph.instagram.com/v25.0/M1/insights").mock(return_value=httpx.Response(200, json={
            "data": [insight(m, i + 1) for i, m in enumerate(Instagram.INSIGHTS)]}))
        got = ig.collect([pub], "2026-10-05")[pub["id"]]
    assert route.calls[0].request.url.params["metric"] == ",".join(Instagram.INSIGHTS)
    assert "period" not in route.calls[0].request.url.params  # always lifetime
    assert got["views"] == 1 and got["reels_skip_rate"] == 10


def test_instagram_falls_back_to_one_metric_at_a_time(ig, conn):
    pub = dict(published(conn, "001", "instagram", "M1"))

    def answer(request):
        metric = request.url.params["metric"]
        if "," in metric or metric == "reels_skip_rate":
            return httpx.Response(400, json={"error": {"message": "An unknown error has occurred.", "code": 100}})
        return httpx.Response(200, json={"data": [insight(metric, 5)]})

    with respx.mock(assert_all_mocked=True) as r:
        r.get("https://graph.instagram.com/v25.0/M1/insights").mock(side_effect=answer)
        got = ig.collect([pub], "2026-10-05")[pub["id"]]
    assert got["views"] == 5 and got["reels_skip_rate"] is None and len(got) == len(Instagram.INSIGHTS)


# -- TikTok --------------------------------------------------------------

def test_tiktok_video_query_batches_of_20(tt, conn):
    pubs = [dict(published(conn, f"{i:03}", "tiktok", f"7{i:018}")) for i in range(25)]

    def answer(request):
        ids = json.loads(request.content)["filters"]["video_ids"]
        return httpx.Response(200, json={"data": {"videos": [
            {"id": v, "view_count": 100, "like_count": 9, "comment_count": 1, "share_count": 2, "duration": 57} for v in ids]},
            "error": {"code": "ok", "message": "", "log_id": "L"}})

    with respx.mock(assert_all_mocked=True) as r:
        route = r.post("https://open.tiktokapis.com/v2/video/query/").mock(side_effect=answer)
        got = tt.collect(pubs, "2026-10-05")
    assert route.call_count == 2 and len(json.loads(route.calls[0].request.content)["filters"]["video_ids"]) == 20
    assert route.calls[0].request.url.params["fields"] == TikTok.FIELDS
    assert got[pubs[0]["id"]] == {"view_count": 100, "like_count": 9, "comment_count": 1, "share_count": 2, "duration": 57}


# -- orchestration + export ------------------------------------------------

def test_collect_links_tiktok_drafts_and_isolates_failures(tt, ig, conn):
    row = db.ensure(conn, "001", "tiktok")
    db.update(conn, row["id"], state=db.SENT_TO_INBOX, upload_session="p1", published_at="2026-10-02T21:00:00+00:00")
    published(conn, "001", "instagram", "M1")
    with respx.mock(assert_all_mocked=True) as r:
        r.post("https://open.tiktokapis.com/v2/post/publish/status/fetch/").mock(return_value=httpx.Response(200, json={
            "data": {"status": "PUBLISH_COMPLETE", "publicaly_available_post_id": [7300000000000000001]},
            "error": {"code": "ok", "message": "", "log_id": "L"}}))
        r.post("https://open.tiktokapis.com/v2/video/query/").mock(return_value=httpx.Response(200, json={
            "data": {"videos": [{"id": "7300000000000000001", "view_count": 50}]}, "error": {"code": "ok"}}))
        r.get("https://graph.instagram.com/v25.0/M1/insights").mock(return_value=httpx.Response(503))
        out = service.collect_metrics({"tiktok": tt, "instagram": ig}, conn, now=NOW, sleep=noop)
    actions = {(o.platform, o.action) for o in out}
    assert ("tiktok", "linked") in actions and ("tiktok", "collected") in actions and ("instagram", "failed") in actions
    assert db.get(conn, "001", "tiktok")["remote_id"] == "7300000000000000001"
    assert db.latest_metrics(conn)[row["id"]] == ("2026-10-05T12:00:00+00:00", {"view_count": 50})


def test_export_joins_meta_and_uses_latest_collection(settings, vertical_video, conn):
    item = content.load(write_content(settings, "001-test", vertical_video, hook_type="foreign-quote"), settings)
    yt_pub = published(conn, "001-test", "youtube", "vid1", remote_url="https://www.youtube.com/shorts/vid1")
    tt_pub = published(conn, "001-test", "tiktok", "7300")
    db.insert_metrics(conn, yt_pub["id"], {"viewCount": 10, "likeCount": 1}, "2026-10-03T21:00:00+00:00")
    db.insert_metrics(conn, yt_pub["id"], {"viewCount": 900, "likeCount": 40, "views": 1000, "averageViewPercentage": 41.25},
                      "2026-10-05T21:00:00+00:00")
    db.insert_metrics(conn, tt_pub["id"], {"view_count": 300, "share_count": 4}, "2026-10-05T21:00:00+00:00")

    buf = io.StringIO()
    assert export.write(conn, {item.slug: item}, buf) == 2
    rows = {r["platform"]: r for r in csv.DictReader(io.StringIO(buf.getvalue()))}
    y, t = rows["youtube"], rows["tiktok"]
    assert (y["hook_type"], y["format"], y["channel"]) == ("foreign-quote", "loop-paintings-narrated", "roman-in-stones")
    assert y["views"] == "1000" and y["likes"] == "40"             # Analytics wins; likes falls back to likeCount
    assert y["avg_view_percent"] == "41.25" and y["hours_since_publish"] == "72.0"
    assert y["youtube.viewCount"] == "900"                          # raw columns keep everything
    assert t["views"] == "300" and t["shares"] == "4" and t["avg_view_seconds"] == ""  # TikTok has no watch time
