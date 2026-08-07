import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import main
from database import CrawlRepository


class NeeqDownloadFlowTest(unittest.TestCase):
    def test_second_run_uses_downloaded_pdf_from_sqlite(self):
        announcement = {
            "secCode": "001234",
            "secName": "测试公司",
            "announcementTitle": "测试公司：2024年年度报告",
            "announcementDate": "2025-04-20",
            "adjunctUrl": "https://example.com/report.pdf",
            "adjunctType": "PDF",
        }
        args = SimpleNamespace(skip_parse=True, year=2025)

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output_dirs = {
                "pdf": str(root / "pdf"),
                "csv": str(root / "csv"),
                "log": str(root / "log"),
            }
            for directory in output_dirs.values():
                Path(directory).mkdir(parents=True)

            def fake_download(_url, save_path):
                Path(save_path).write_bytes(b"%PDF-1.7\ncontent")
                return True

            with patch.dict(main.OUTPUT_DIR, output_dirs):
                with patch.object(
                    main,
                    "STOP_FILE",
                    str(root / "STOP.txt"),
                ):
                    with patch(
                        "neeq_crawler.download_pdf",
                        side_effect=fake_download,
                    ) as download_mock:
                        with CrawlRepository(
                            root / "crawl_state.db"
                        ) as repository:
                            repository.upsert_announcements(
                                [announcement],
                                source="neeq",
                            )
                            first_stats = main._process_neeq_announcements(
                                [announcement],
                                args,
                                main.logging.getLogger("test"),
                                repository,
                            )
                            second_stats = main._process_neeq_announcements(
                                [announcement],
                                args,
                                main.logging.getLogger("test"),
                                repository,
                            )
                            record = repository.get_announcement(
                                "neeq",
                                announcement["adjunctUrl"],
                            )

            self.assertEqual(download_mock.call_count, 1)
            self.assertEqual(first_stats["downloaded"], 1)
            self.assertEqual(second_stats["existing"], 1)
            self.assertEqual(record["status"], "downloaded")
            self.assertEqual(record["attempts"], 1)
            self.assertGreater(record["file_size"], 0)


if __name__ == "__main__":
    unittest.main()
