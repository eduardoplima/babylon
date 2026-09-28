"""Publishing orchestration: idempotent state transitions, attempts log, retries, quotas."""
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from . import db
from .content import ContentItem
from .platforms.base import NeedsReconcile, Platform, PublishContext
from .retry import PermanentError, TransientError, with_retry

MAX_RUNS = 5  # publish-due stops retrying a retryable failure after this many runs
RETRY_LATER = timedelta(hours=1)  # cooldown after a quota-type failure (limits reset daily)


@dataclass
class Outcome:
    slug: str
    platform: str
    action: str   # published | processing | skipped | dry-run | invalid | failed | reconcile
    detail: str = ""

    def __str__(self) -> str:
        return f"{self.slug} [{self.platform}] {self.action}{': ' + self.detail if self.detail else ''}"


def publish(item: ContentItem, adapter: Platform, conn: sqlite3.Connection, *, live: bool,
            log=None, force: bool = False, sleep: Callable[[float], None] | None = None,
            now: datetime | None = None) -> Outcome:
    slug, name = item.slug, adapter.name
    out = lambda action, detail="": Outcome(slug, name, action, detail)

    row = db.get(conn, slug, name)
    state = row["state"] if row else db.PENDING
    if state in db.DONE:
        return out("skipped", f"already {state} ({row['remote_url'] or row['remote_id']})")
    if state == db.NEEDS_RECONCILE:
        return out("skipped", f"needs reconcile: {row['last_error']} → `publisher resolve {slug} {name} ...`")
    if state == db.FAILED and not row["retryable"] and not force:
        return out("skipped", f"failed permanently: {row['last_error']} (use --force to retry)")

    issues = adapter.check(item)
    errors = [i for i in issues if i.level == "error"]
    warnings = "; ".join(str(i) for i in issues if i.level == "warning")
    if errors:
        return out("invalid", "; ".join(str(i) for i in errors))
    if not live:  # dry-run: no network, no DB writes
        resume = f" (resume from state {state})" if row else ""
        return out("dry-run", adapter.describe(item) + resume + (f" [{warnings}]" if warnings else ""))

    adapter.preflight()  # AuthRequired propagates before any state is written
    row = db.ensure(conn, slug, name)
    target = db.PROCESSING if row["state"] == db.PROCESSING else db.UPLOADING
    if not db.claim(conn, row["id"], (db.PENDING, db.FAILED, db.UPLOADING, db.PROCESSING), target):
        return out("skipped", "claimed by another run")
    pub = dict(db.get(conn, slug, name))

    def save(**fields):
        db.update(conn, pub["id"], **fields)
        pub.update(fields)

    log = log.bind(slug=slug, platform=name, publication_id=pub["id"]) if log else None
    attempt = db.start_attempt(conn, pub["id"])
    ctx = PublishContext(item=item, pub=pub, save=save, log=log)
    retry_log = (lambda n, exc, delay: log.warning("retry", attempt=n, error=str(exc), delay_s=round(delay, 1))) if log else None
    try:
        kwargs = {"sleep": sleep} if sleep else {}
        with_retry(lambda: adapter.publish(ctx), on_retry=retry_log, **kwargs)
    except NeedsReconcile as exc:
        save(state=db.NEEDS_RECONCILE, last_error=str(exc))
        return _finish(conn, attempt, log, "error", exc, out("reconcile", str(exc)))
    except PermanentError as exc:
        if exc.retry_later:
            after = ((now or datetime.now(timezone.utc)).astimezone(timezone.utc) + RETRY_LATER).isoformat(timespec="seconds")
            save(state=db.FAILED, retryable=1, retry_after=after, last_error=str(exc))
            return _finish(conn, attempt, log, "permanent", exc, out("failed", f"{exc} (retry after {after})"))
        save(state=db.FAILED, retryable=0, last_error=str(exc))
        return _finish(conn, attempt, log, "permanent", exc, out("failed", str(exc)))
    except TransientError as exc:
        save(state=db.FAILED, retryable=1, last_error=str(exc))
        return _finish(conn, attempt, log, "transient", exc, out("failed", f"{exc} (will retry next run)"))
    except Exception as exc:  # unexpected: keep upload_session so the next run can resume
        save(state=db.FAILED, retryable=1, last_error=f"{type(exc).__name__}: {exc}")
        _finish(conn, attempt, log, "error", exc, None)
        raise

    if pub.get("retry_after"):
        save(retry_after=None)
    db.finish_attempt(conn, attempt, "success")
    if log:
        log.info("publish.ok", state=pub["state"], remote_id=pub.get("remote_id"))
    if pub["state"] == db.PROCESSING:
        return out("processing", f"{pub['remote_url']} still processing; next run will check again")
    return out("published", pub.get("remote_url") or "")


def _finish(conn, attempt: int, log, outcome: str, exc: Exception, result: Outcome | None) -> Outcome | None:
    status = getattr(exc, "status", None)
    reason = getattr(exc, "reason", None)
    db.finish_attempt(conn, attempt, outcome, http_status=status, reason=reason, message=str(exc)[:2000])
    if log:
        log.error("publish.failed", outcome=outcome, http_status=status, reason=reason, error=str(exc))
    return result


def due(items: list[ContentItem], now: datetime, tz) -> list[ContentItem]:
    return [i for i in items if (at := i.meta.schedule_at(tz)) is not None and at <= now]


def publish_due(items: list[ContentItem], adapters: dict[str, Platform], conn: sqlite3.Connection, *,
                live: bool, now: datetime, tz, daily_caps: dict[str, int], log=None,
                sleep: Callable[[float], None] | None = None) -> list[Outcome]:
    """Publish every due (item, platform) that isn't done yet, respecting daily upload caps."""
    outcomes = []
    since = (now.astimezone(timezone.utc) - timedelta(days=1)).isoformat(timespec="seconds")
    used = {p: db.count_uploads_since(conn, p, since) for p in adapters}
    live_quota: dict[str, int] = {}  # platforms that report their remaining quota (asked once per run)
    for item in sorted(due(items, now, tz), key=lambda i: i.meta.schedule_at(tz)):
        for name in item.meta.platforms():
            adapter = adapters.get(name)
            if adapter is None:
                outcomes.append(Outcome(item.slug, name, "skipped", "adapter not implemented yet"))
                continue
            row = db.get(conn, item.slug, name)
            if row and row["retry_after"] and row["retry_after"] > now.astimezone(timezone.utc).isoformat(timespec="seconds"):
                outcomes.append(Outcome(item.slug, name, "skipped", f"waiting until {row['retry_after']}: {row['last_error']}"))
                continue
            if row and row["state"] == db.FAILED and row["retryable"] and row["attempts"] >= MAX_RUNS:
                outcomes.append(Outcome(item.slug, name, "skipped", f"gave up after {row['attempts']} runs: {row['last_error']}"))
                continue
            fresh = row is None or row["upload_started_at"] is None
            if fresh and name in daily_caps and used[name] >= daily_caps[name]:
                outcomes.append(Outcome(item.slug, name, "skipped", f"daily cap {daily_caps[name]} reached"))
                continue
            if live and hasattr(adapter, "remaining_quota") and (row is None or row["state"] != db.PROCESSING):
                if name not in live_quota:
                    live_quota[name] = adapter.remaining_quota()
                if live_quota[name] <= 0:
                    outcomes.append(Outcome(item.slug, name, "skipped", "platform publishing quota used up for now"))
                    continue
            result = publish(item, adapter, conn, live=live, log=log, sleep=sleep, now=now)
            if live and fresh and result.action in ("published", "processing", "failed"):
                used[name] += 1 if db.get(conn, item.slug, name)["upload_started_at"] else 0
            if name in live_quota and result.action == "published":
                live_quota[name] -= 1
            outcomes.append(result)
    return outcomes
