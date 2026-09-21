import tempfile
import unittest
from pathlib import Path

from neeq_crawler import (
    _normalize_announcement,
    _parse_jsonp,
    is_annual_report_title,
    is_valid_pdf,
)


class NeeqCrawlerTest(unittest.TestCase):
    @staticmethod
    def source_item(**overrides):
        item = {
            "companyCd": "000001",
            "companyName": "测试公司",
            "disclosureTitle": "测试公司：2024年年度报告",
            "disclosurePostTitle": "",
            "destFilePath": "/disclosure/2025/report.PDF",
            "publishDate": "2025-04-20",
            "fileExt": "PDF",
        }
        item.update(overrides)
        return item

    def test_parses_neeq_jsonp_response(self):
        parsed = _parse_jsonp(
            'null([{"listInfo":{"content":[],"totalPages":0}}])'
        )
        self.assertEqual(parsed[0]["listInfo"]["totalPages"], 0)

    def test_normalizes_valid_annual_report(self):
        result = _normalize_announcement(
            self.source_item(),
            "2025-04-01",
            "2025-04-30",
        )

        self.assertEqual(result["secCode"], "000001")
        self.assertEqual(result["announcementDate"], "2025-04-20")
        self.assertEqual(
            result["adjunctUrl"],
            "https://www.neeq.com.cn/disclosure/2025/report.PDF",
        )

    def test_filters_summaries_cancelled_and_out_of_range_records(self):
        summary = self.source_item(
            disclosureTitle="测试公司：2024年年度报告摘要"
        )
        cancelled = self.source_item(disclosurePostTitle="（已取消）")
        half_year = self.source_item(
            disclosureTitle="测试公司：2026年半年度报告"
        )
        out_of_range = self.source_item(publishDate="2025-05-01")

        for item in (summary, cancelled, half_year, out_of_range):
            with self.subTest(item=item):
                self.assertIsNone(
                    _normalize_announcement(
                        item,
                        "2025-04-01",
                        "2025-04-30",
                    )
                )

    def test_annual_report_title_rejects_interim_and_cancelled(self):
        self.assertTrue(is_annual_report_title("测试公司：2025年年度报告"))
        self.assertFalse(is_annual_report_title("测试公司：2026年半年度报告"))
        self.assertFalse(is_annual_report_title("测试公司：2025年年度报告（已取消）"))
        self.assertFalse(is_annual_report_title("测试公司：2025年年度报告摘要"))
        self.assertFalse(is_annual_report_title("测试公司：2025年第三季度报告"))

    def test_pdf_validation_uses_file_header(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            valid_pdf = Path(temp_dir) / "valid.pdf"
            invalid_pdf = Path(temp_dir) / "invalid.pdf"
            valid_pdf.write_bytes(b"%PDF-1.7\ncontent")
            invalid_pdf.write_bytes(b"<html>error</html>")

            self.assertTrue(is_valid_pdf(valid_pdf))
            self.assertFalse(is_valid_pdf(invalid_pdf))
            self.assertFalse(is_valid_pdf(Path(temp_dir) / "missing.pdf"))


if __name__ == "__main__":
    unittest.main()
