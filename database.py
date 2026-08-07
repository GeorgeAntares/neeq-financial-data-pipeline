"""SQLite persistence for crawl metadata and download state."""

from __future__ import annotations

import re
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Union


REPORT_TYPES = {"annual", "half_year", "q1", "q3", "other"}
DOWNLOAD_STATUSES = {"pending", "downloading", "downloaded", "failed"}
RUN_STATUSES = {"running", "completed", "failed", "interrupted"}

_REPORT_YEAR_PATTERN = re.compile(
    r"(?<!\d)((?:19|20)\d{2})\s*年?(?:年度报告|年报)"
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS announcements (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL
        CHECK (typeof(source) = 'text' AND length(trim(source)) > 0),
    company_code TEXT NOT NULL DEFAULT ''
        CHECK (typeof(company_code) = 'text'),
    company_name TEXT NOT NULL DEFAULT ''
        CHECK (typeof(company_name) = 'text'),
    title TEXT NOT NULL
        CHECK (typeof(title) = 'text' AND length(trim(title)) > 0),
    report_type TEXT NOT NULL DEFAULT 'annual'
        CHECK (report_type IN ('annual', 'half_year', 'q1', 'q3', 'other')),
    report_year INTEGER
        CHECK (
            report_year IS NULL OR
            (typeof(report_year) = 'integer' AND report_year BETWEEN 1900 AND 2100)
        ),
    publish_date TEXT
        CHECK (
            publish_date IS NULL OR
            (
                typeof(publish_date) = 'text' AND
                publish_date GLOB
                    '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'
            )
        ),
    pdf_url TEXT NOT NULL
        CHECK (typeof(pdf_url) = 'text' AND length(trim(pdf_url)) > 0),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'downloading', 'downloaded', 'failed')),
    attempts INTEGER NOT NULL DEFAULT 0
        CHECK (typeof(attempts) = 'integer' AND attempts >= 0),
    file_path TEXT
        CHECK (file_path IS NULL OR typeof(file_path) = 'text'),
    file_size INTEGER
        CHECK (
            file_size IS NULL OR
            (typeof(file_size) = 'integer' AND file_size >= 0)
        ),
    sha256 TEXT
        CHECK (
            sha256 IS NULL OR
            (
                typeof(sha256) = 'text' AND
                length(sha256) = 64 AND
                sha256 NOT GLOB '*[^0-9a-f]*'
            )
        ),
    last_error TEXT
        CHECK (last_error IS NULL OR typeof(last_error) = 'text'),
    downloaded_at TEXT,
    created_at TEXT NOT NULL
        DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL
        DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (source, pdf_url)
);

CREATE INDEX IF NOT EXISTS idx_announcements_status_date
    ON announcements (status, publish_date);

CREATE INDEX IF NOT EXISTS idx_announcements_company_report
    ON announcements (company_code, report_type, report_year);

CREATE TABLE IF NOT EXISTS crawl_runs (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL
        CHECK (typeof(source) = 'text' AND length(trim(source)) > 0),
    start_date TEXT
        CHECK (
            start_date IS NULL OR
            start_date GLOB
                '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'
        ),
    end_date TEXT
        CHECK (
            end_date IS NULL OR
            end_date GLOB
                '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'
        ),
    report_type TEXT NOT NULL DEFAULT 'annual'
        CHECK (report_type IN ('annual', 'half_year', 'q1', 'q3', 'other')),
    status TEXT NOT NULL DEFAULT 'running'
        CHECK (status IN ('running', 'completed', 'failed', 'interrupted')),
    discovered_count INTEGER NOT NULL DEFAULT 0
        CHECK (typeof(discovered_count) = 'integer' AND discovered_count >= 0),
    downloaded_count INTEGER NOT NULL DEFAULT 0
        CHECK (typeof(downloaded_count) = 'integer' AND downloaded_count >= 0),
    failed_count INTEGER NOT NULL DEFAULT 0
        CHECK (typeof(failed_count) = 'integer' AND failed_count >= 0),
    started_at TEXT NOT NULL
        DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    finished_at TEXT
);
"""


def infer_report_year(title: str) -> Optional[int]:
    """Extract a report year from an announcement title."""
    match = _REPORT_YEAR_PATTERN.search(str(title))
    return int(match.group(1)) if match else None


def _normalize_date(value: Any) -> Optional[str]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()

    text = str(value).strip()
    if len(text) >= 10:
        text = text[:10]
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise ValueError(f"Invalid ISO date: {value!r}") from exc


def _normalize_year(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError("Boolean values are not valid report years")
    if isinstance(value, float) and not value.is_integer():
        raise ValueError(f"Invalid report year: {value!r}")
    if isinstance(value, str) and not re.fullmatch(r"[+-]?\d+", value.strip()):
        raise ValueError(f"Invalid report year: {value!r}")
    try:
        year = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"Invalid report year: {value!r}") from exc
    if not 1900 <= year <= 2100:
        raise ValueError(f"Report year out of range: {year}")
    return year


def _normalize_nonnegative_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a non-negative integer")
    if isinstance(value, float) and not value.is_integer():
        raise ValueError(f"{field_name} must be a non-negative integer")
    if isinstance(value, str) and not re.fullmatch(r"\+?\d+", value.strip()):
        raise ValueError(f"{field_name} must be a non-negative integer")
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(
            f"{field_name} must be a non-negative integer"
        ) from exc
    if number < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return number


class CrawlRepository:
    """Store announcements and crawl progress in a local SQLite database."""

    def __init__(self, db_path: Union[str, Path]):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(
            self.db_path,
            timeout=5.0,
        )
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA busy_timeout = 5000")
        self.connection.execute("PRAGMA journal_mode = WAL")
        self.connection.execute("PRAGMA synchronous = NORMAL")
        self.connection.executescript(_SCHEMA)
        self.connection.execute("PRAGMA user_version = 1")

    def __enter__(self) -> "CrawlRepository":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def close(self) -> None:
        self.connection.close()

    def recover_incomplete_downloads(self) -> int:
        """Make downloads interrupted by a prior process eligible for retry."""
        with self.connection:
            cursor = self.connection.execute(
                """
                UPDATE announcements
                SET status = 'pending',
                    last_error = 'Previous download was interrupted',
                    updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                WHERE status = 'downloading'
                """
            )
        return cursor.rowcount

    def upsert_announcements(
        self,
        announcements: Iterable[Mapping[str, Any]],
        *,
        source: str,
        report_type: str = "annual",
    ) -> int:
        """Insert new announcements while preserving existing download state."""
        source = str(source).strip().lower()
        if not source:
            raise ValueError("source cannot be empty")
        if report_type not in REPORT_TYPES:
            raise ValueError(f"Unsupported report type: {report_type}")

        rows = []
        for announcement in announcements:
            pdf_url = str(
                announcement.get("adjunctUrl")
                or announcement.get("pdf_url")
                or ""
            ).strip()
            title = str(
                announcement.get("announcementTitle")
                or announcement.get("title")
                or ""
            ).strip()
            if not pdf_url or not title:
                continue

            explicit_year = (
                announcement.get("reportYear")
                or announcement.get("report_year")
            )
            report_year = _normalize_year(
                explicit_year
                if explicit_year not in (None, "")
                else infer_report_year(title)
            )
            publish_date = _normalize_date(
                announcement.get("announcementDate")
                or announcement.get("publish_date")
            )
            rows.append(
                (
                    source,
                    str(
                        announcement.get("secCode")
                        or announcement.get("company_code")
                        or ""
                    ).strip(),
                    str(
                        announcement.get("secName")
                        or announcement.get("company_name")
                        or ""
                    ).strip(),
                    title,
                    report_type,
                    report_year,
                    publish_date,
                    pdf_url,
                )
            )

        if not rows:
            return 0

        with self.connection:
            self.connection.executemany(
                """
                INSERT INTO announcements (
                    source,
                    company_code,
                    company_name,
                    title,
                    report_type,
                    report_year,
                    publish_date,
                    pdf_url
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source, pdf_url) DO UPDATE SET
                    company_code = excluded.company_code,
                    company_name = excluded.company_name,
                    title = excluded.title,
                    report_type = excluded.report_type,
                    report_year = COALESCE(
                        excluded.report_year,
                        announcements.report_year
                    ),
                    publish_date = COALESCE(
                        excluded.publish_date,
                        announcements.publish_date
                    ),
                    updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                """,
                rows,
            )
        return len(rows)

    def get_announcement(
        self,
        source: str,
        pdf_url: str,
    ) -> Optional[dict[str, Any]]:
        row = self.connection.execute(
            """
            SELECT *
            FROM announcements
            WHERE source = ? AND pdf_url = ?
            """,
            (str(source).strip().lower(), str(pdf_url).strip()),
        ).fetchone()
        return dict(row) if row else None

    def mark_downloading(self, source: str, pdf_url: str) -> None:
        with self.connection:
            cursor = self.connection.execute(
                """
                UPDATE announcements
                SET status = 'downloading',
                    attempts = attempts + 1,
                    last_error = NULL,
                    updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                WHERE source = ? AND pdf_url = ?
                """,
                (str(source).strip().lower(), str(pdf_url).strip()),
            )
        self._require_updated(cursor, source, pdf_url)

    def mark_downloaded(
        self,
        source: str,
        pdf_url: str,
        *,
        file_path: Union[str, Path],
        file_size: int,
        sha256: Optional[str] = None,
    ) -> None:
        normalized_size = _normalize_nonnegative_int(file_size, "file_size")
        normalized_sha256 = None
        if sha256 is not None:
            normalized_sha256 = str(sha256).strip().lower()
            if not re.fullmatch(r"[0-9a-f]{64}", normalized_sha256):
                raise ValueError("sha256 must contain exactly 64 hex characters")

        with self.connection:
            cursor = self.connection.execute(
                """
                UPDATE announcements
                SET status = 'downloaded',
                    file_path = ?,
                    file_size = ?,
                    sha256 = ?,
                    last_error = NULL,
                    downloaded_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now'),
                    updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                WHERE source = ? AND pdf_url = ?
                """,
                (
                    str(Path(file_path)),
                    normalized_size,
                    normalized_sha256,
                    str(source).strip().lower(),
                    str(pdf_url).strip(),
                ),
            )
        self._require_updated(cursor, source, pdf_url)

    def mark_failed(self, source: str, pdf_url: str, error: Any) -> None:
        error_text = str(error).strip() or "Unknown download error"
        with self.connection:
            cursor = self.connection.execute(
                """
                UPDATE announcements
                SET status = 'failed',
                    last_error = ?,
                    updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                WHERE source = ? AND pdf_url = ?
                """,
                (
                    error_text,
                    str(source).strip().lower(),
                    str(pdf_url).strip(),
                ),
            )
        self._require_updated(cursor, source, pdf_url)

    def status_counts(
        self,
        source: Optional[str] = None,
    ) -> dict[str, int]:
        if source is None:
            rows = self.connection.execute(
                """
                SELECT status, COUNT(*) AS count
                FROM announcements
                GROUP BY status
                """
            ).fetchall()
        else:
            rows = self.connection.execute(
                """
                SELECT status, COUNT(*) AS count
                FROM announcements
                WHERE source = ?
                GROUP BY status
                """,
                (str(source).strip().lower(),),
            ).fetchall()

        counts = {status: 0 for status in DOWNLOAD_STATUSES}
        counts.update({row["status"]: int(row["count"]) for row in rows})
        return counts

    def start_run(
        self,
        *,
        source: str,
        start_date: Any = None,
        end_date: Any = None,
        report_type: str = "annual",
    ) -> int:
        if report_type not in REPORT_TYPES:
            raise ValueError(f"Unsupported report type: {report_type}")
        normalized_start = _normalize_date(start_date)
        normalized_end = _normalize_date(end_date)
        if (
            normalized_start is not None
            and normalized_end is not None
            and normalized_start > normalized_end
        ):
            raise ValueError("start_date cannot be after end_date")

        with self.connection:
            cursor = self.connection.execute(
                """
                INSERT INTO crawl_runs (
                    source,
                    start_date,
                    end_date,
                    report_type
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    str(source).strip().lower(),
                    normalized_start,
                    normalized_end,
                    report_type,
                ),
            )
        return int(cursor.lastrowid)

    def finish_run(
        self,
        run_id: int,
        *,
        status: str,
        discovered_count: int = 0,
        downloaded_count: int = 0,
        failed_count: int = 0,
    ) -> None:
        if status not in RUN_STATUSES - {"running"}:
            raise ValueError(f"Invalid final run status: {status}")
        run_id = _normalize_nonnegative_int(run_id, "run_id")
        discovered_count = _normalize_nonnegative_int(
            discovered_count,
            "discovered_count",
        )
        downloaded_count = _normalize_nonnegative_int(
            downloaded_count,
            "downloaded_count",
        )
        failed_count = _normalize_nonnegative_int(
            failed_count,
            "failed_count",
        )

        with self.connection:
            cursor = self.connection.execute(
                """
                UPDATE crawl_runs
                SET status = ?,
                    discovered_count = ?,
                    downloaded_count = ?,
                    failed_count = ?,
                    finished_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                WHERE id = ?
                """,
                (
                    status,
                    discovered_count,
                    downloaded_count,
                    failed_count,
                    run_id,
                ),
            )
        if cursor.rowcount != 1:
            raise KeyError(f"Crawl run not found: {run_id}")

    @staticmethod
    def _require_updated(
        cursor: sqlite3.Cursor,
        source: str,
        pdf_url: str,
    ) -> None:
        if cursor.rowcount != 1:
            raise KeyError(
                f"Announcement not found: {source!r}, {pdf_url!r}"
            )
