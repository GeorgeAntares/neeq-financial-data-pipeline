import sqlite3
import tempfile
import unittest
from pathlib import Path

from database import CrawlRepository


class CrawlRepositoryTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "crawl_state.db"
        self.repository = CrawlRepository(self.db_path)

    def tearDown(self):
        self.repository.close()
        self.temp_dir.cleanup()

    @staticmethod
    def announcement(**overrides):
        record = {
            "secCode": "001234",
            "secName": "测试公司",
            "announcementTitle": "测试公司：2024年年度报告",
            "announcementDate": "2025-04-20",
            "adjunctUrl": "https://example.com/report.pdf",
        }
        record.update(overrides)
        return record

    def test_preserves_codes_and_uses_expected_storage_types(self):
        inserted = self.repository.upsert_announcements(
            [self.announcement()],
            source="neeq",
        )

        self.assertEqual(inserted, 1)
        record = self.repository.get_announcement(
            "neeq",
            "https://example.com/report.pdf",
        )
        self.assertEqual(record["company_code"], "001234")
        self.assertEqual(record["report_year"], 2024)
        self.assertEqual(record["publish_date"], "2025-04-20")
        self.assertEqual(record["attempts"], 0)

        connection = sqlite3.connect(self.db_path)
        try:
            storage_types = connection.execute(
                """
                SELECT
                    typeof(company_code),
                    typeof(report_year),
                    typeof(publish_date),
                    typeof(attempts)
                FROM announcements
                """
            ).fetchone()
        finally:
            connection.close()
        self.assertEqual(storage_types, ("text", "integer", "text", "integer"))

    def test_upsert_preserves_download_state(self):
        announcement = self.announcement()
        self.repository.upsert_announcements(
            [announcement],
            source="neeq",
        )
        self.repository.mark_downloading(
            "neeq",
            announcement["adjunctUrl"],
        )
        self.repository.mark_downloaded(
            "neeq",
            announcement["adjunctUrl"],
            file_path="output/report.pdf",
            file_size=12345,
        )

        updated = self.announcement(
            announcementTitle="测试公司：2024年年度报告（更正后）"
        )
        self.repository.upsert_announcements([updated], source="neeq")
        record = self.repository.get_announcement(
            "neeq",
            announcement["adjunctUrl"],
        )

        self.assertEqual(record["status"], "downloaded")
        self.assertEqual(record["attempts"], 1)
        self.assertEqual(record["file_size"], 12345)
        self.assertIn("更正后", record["title"])
        count = self.repository.connection.execute(
            "SELECT COUNT(*) FROM announcements"
        ).fetchone()[0]
        self.assertEqual(count, 1)

    def test_download_state_transitions_are_recorded(self):
        announcement = self.announcement()
        url = announcement["adjunctUrl"]
        self.repository.upsert_announcements([announcement], source="neeq")

        self.repository.mark_downloading("neeq", url)
        self.repository.mark_failed("neeq", url, "timeout")
        failed = self.repository.get_announcement("neeq", url)
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["attempts"], 1)
        self.assertEqual(failed["last_error"], "timeout")

        self.repository.mark_downloading("neeq", url)
        self.repository.mark_downloaded(
            "neeq",
            url,
            file_path="output/report.pdf",
            file_size=200,
            sha256="a" * 64,
        )
        downloaded = self.repository.get_announcement("neeq", url)
        self.assertEqual(downloaded["status"], "downloaded")
        self.assertEqual(downloaded["attempts"], 2)
        self.assertIsInstance(downloaded["file_size"], int)
        self.assertEqual(downloaded["sha256"], "a" * 64)

    def test_rejects_invalid_dates_years_and_database_statuses(self):
        with self.assertRaises(ValueError):
            self.repository.upsert_announcements(
                [self.announcement(announcementDate="2025-02-30")],
                source="neeq",
            )
        with self.assertRaises(ValueError):
            self.repository.upsert_announcements(
                [self.announcement(reportYear=True)],
                source="neeq",
            )
        with self.assertRaises(ValueError):
            self.repository.upsert_announcements(
                [self.announcement(reportYear=2024.5)],
                source="neeq",
            )

        self.repository.upsert_announcements(
            [self.announcement()],
            source="neeq",
        )
        with self.assertRaises(sqlite3.IntegrityError):
            with self.repository.connection:
                self.repository.connection.execute(
                    "UPDATE announcements SET status = 'unknown'"
                )
        with self.assertRaises(ValueError):
            self.repository.mark_downloaded(
                "neeq",
                "https://example.com/report.pdf",
                file_path="output/report.pdf",
                file_size=12.5,
            )

    def test_crawl_run_counts_are_integers(self):
        run_id = self.repository.start_run(
            source="neeq",
            start_date="2025-01-01",
            end_date="2025-12-31",
        )
        self.repository.finish_run(
            run_id,
            status="completed",
            discovered_count=12,
            downloaded_count=10,
            failed_count=2,
        )

        row = self.repository.connection.execute(
            "SELECT * FROM crawl_runs WHERE id = ?",
            (run_id,),
        ).fetchone()
        self.assertEqual(row["status"], "completed")
        self.assertEqual(row["discovered_count"], 12)
        self.assertEqual(row["downloaded_count"], 10)
        self.assertEqual(row["failed_count"], 2)
        self.assertIsNotNone(row["finished_at"])


if __name__ == "__main__":
    unittest.main()
