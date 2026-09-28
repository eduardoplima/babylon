"""SQLite state: one row per (slug, platform), a log of every attempt, and metrics.

Plain sqlite3; migrations are an ordered list applied by PRAGMA user_version.
"""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Publication states.
PENDING = "pending"                  # nothing sent yet
UPLOADING = "uploading"              # upload started; upload_session may allow resuming
PROCESSING = "processing"            # platform has the file; waiting for it to finish processing
PUBLISHED = "published"              # done (on YouTube: uploaded and processed, with the configured privacy)
SENT_TO_INBOX = "sent_to_inbox"      # TikTok draft delivered; finished by the creator in the app
FAILED = "failed"                    # last attempt failed; `retryable` says whether publish-due retries it
NEEDS_RECONCILE = "needs_reconcile"  # outcome unknown; never retried automatically

DONE = (PUBLISHED, SENT_TO_INBOX)

MIGRATIONS = [
    """
    CREATE TABLE publications (
        id             INTEGER PRIMARY KEY,
        slug           TEXT NOT NULL,
        platform       TEXT NOT NULL,
        state          TEXT NOT NULL DEFAULT 'pending',
        retryable      INTEGER NOT NULL DEFAULT 1,
        remote_id      TEXT,
        remote_url     TEXT,
        upload_session TEXT,
        attempts       INTEGER NOT NULL DEFAULT 0,
        last_error     TEXT,
        upload_started_at TEXT,       -- when the upload call was made (counts against daily quota)
        published_at   TEXT,
        created_at     TEXT NOT NULL,
        updated_at     TEXT NOT NULL,
        UNIQUE (slug, platform)
    );
    CREATE TABLE attempts (
        id             INTEGER PRIMARY KEY,
        publication_id INTEGER NOT NULL REFERENCES publications(id),
        started_at     TEXT NOT NULL,
        finished_at    TEXT,
        outcome        TEXT,          -- success | transient | permanent | error
        http_status    INTEGER,
        reason         TEXT,
        message        TEXT
    );
    CREATE TABLE metrics (
        id             INTEGER PRIMARY KEY,
        publication_id INTEGER NOT NULL REFERENCES publications(id),
        collected_at   TEXT NOT NULL,
        metric         TEXT NOT NULL,
        value          REAL
    );
    CREATE INDEX metrics_pub ON metrics (publication_id, metric, collected_at);
    """,
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, isolation_level=None)  # autocommit; explicit BEGIN where needed
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    migrate(conn)
    return conn


def migrate(conn: sqlite3.Connection) -> None:
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    for i, sql in enumerate(MIGRATIONS[version:], start=version + 1):
        conn.executescript(f"BEGIN; {sql}; PRAGMA user_version = {i}; COMMIT;")


def get(conn: sqlite3.Connection, slug: str, platform: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM publications WHERE slug = ? AND platform = ?", (slug, platform)).fetchone()


def ensure(conn: sqlite3.Connection, slug: str, platform: str) -> sqlite3.Row:
    ts = now()
    conn.execute("INSERT OR IGNORE INTO publications (slug, platform, created_at, updated_at) VALUES (?, ?, ?, ?)",
                 (slug, platform, ts, ts))
    return get(conn, slug, platform)


def claim(conn: sqlite3.Connection, pub_id: int, from_states: tuple[str, ...], to_state: str) -> bool:
    """Atomically move a publication between states. False if another run got there first
    or the row is in a state we must not touch (e.g. already published)."""
    marks = ",".join("?" * len(from_states))
    cur = conn.execute(
        f"UPDATE publications SET state = ?, attempts = attempts + 1, updated_at = ? WHERE id = ? AND state IN ({marks})",
        (to_state, now(), pub_id, *from_states))
    return cur.rowcount == 1


def update(conn: sqlite3.Connection, pub_id: int, **fields: Any) -> None:
    fields["updated_at"] = now()
    cols = ", ".join(f"{k} = ?" for k in fields)
    conn.execute(f"UPDATE publications SET {cols} WHERE id = ?", (*fields.values(), pub_id))


def start_attempt(conn: sqlite3.Connection, pub_id: int) -> int:
    return conn.execute("INSERT INTO attempts (publication_id, started_at) VALUES (?, ?)", (pub_id, now())).lastrowid


def finish_attempt(conn: sqlite3.Connection, attempt_id: int, outcome: str, *, http_status: int | None = None,
                   reason: str | None = None, message: str | None = None) -> None:
    conn.execute("UPDATE attempts SET finished_at = ?, outcome = ?, http_status = ?, reason = ?, message = ? WHERE id = ?",
                 (now(), outcome, http_status, reason, message, attempt_id))


def count_uploads_since(conn: sqlite3.Connection, platform: str, since_iso: str) -> int:
    """Upload calls made since `since_iso`, for daily quota checks."""
    return conn.execute(
        "SELECT COUNT(*) FROM publications WHERE platform = ? AND upload_started_at >= ?",
        (platform, since_iso)).fetchone()[0]


def all_publications(conn: sqlite3.Connection, slug: str | None = None) -> list[sqlite3.Row]:
    if slug:
        return conn.execute("SELECT * FROM publications WHERE slug = ? ORDER BY platform", (slug,)).fetchall()
    return conn.execute("SELECT * FROM publications ORDER BY slug, platform").fetchall()
