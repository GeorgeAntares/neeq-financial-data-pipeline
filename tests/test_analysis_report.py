import unittest
from pathlib import Path


class AnalysisReportTest(unittest.TestCase):
    def test_report_has_outline_sections(self):
        text = Path(__file__).resolve().parents[1].joinpath("ANALYSIS_REPORT.md").read_text(encoding="utf-8")
        for heading in (
            "数据与清洗",
            "指标定义",
            "行业画像",
            "杜邦与主成分",
            "现金缺口分类",
            "局限",
        ):
            with self.subTest(heading=heading):
                self.assertIn(heading, text)
        self.assertIn("195", text)
        self.assertIn("company_metrics.py", text)
        self.assertIn("cash_gap_model.py", text)


if __name__ == "__main__":
    unittest.main()
