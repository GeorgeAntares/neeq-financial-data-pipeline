import tempfile
import unittest
from pathlib import Path

import pandas as pd

from industry_groups import (
    GROUP_MANUFACTURING,
    GROUP_OTHER,
    GROUP_SOFTWARE,
    assign_industries,
    group_from_folder,
    scan_pdf_folders,
)
from industry_portrait import add_derived, attach_industry, industry_tables, render_report


def touch_pdf(folder, name):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_bytes(b"%PDF-1.4\n")


class IndustryGroupsTest(unittest.TestCase):
    def test_folder_collapse(self):
        self.assertEqual(group_from_folder("01_制造业"), GROUP_MANUFACTURING)
        self.assertEqual(group_from_folder("02_信息传输_软件和信息技术服务业"), GROUP_SOFTWARE)
        self.assertEqual(group_from_folder("03_批发和零售业"), GROUP_OTHER)
        self.assertEqual(group_from_folder("00_待分类"), GROUP_OTHER)
        self.assertEqual(group_from_folder(""), GROUP_OTHER)

    def test_prefers_csrc_folder_over_unclassified(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            touch_pdf(root / "00_待分类", "430001_甲_2025_x.pdf")
            touch_pdf(root / "01_制造业", "430001_甲_2025_x.pdf")
            touch_pdf(root / "02_信息传输_软件和信息技术服务业", "430002_乙_2025_x.pdf")
            touch_pdf(root / "03_批发和零售业", "430003_丙_2025_x.pdf")
            touch_pdf(root, "430004_丁_2025_x.pdf")
            mapping = scan_pdf_folders(root)
            self.assertEqual(mapping["430001"], "01_制造业")
            assigned = {row["stock_code"]: row["industry"] for row in assign_industries(
                ["430001", "430002", "430003", "430004", "430099"], pdf_root=root
            )}
            self.assertEqual(assigned["430001"], GROUP_MANUFACTURING)
            self.assertEqual(assigned["430002"], GROUP_SOFTWARE)
            self.assertEqual(assigned["430003"], GROUP_OTHER)
            self.assertEqual(assigned["430004"], GROUP_OTHER)
            self.assertEqual(assigned["430099"], GROUP_OTHER)


class IndustryPortraitTest(unittest.TestCase):
    def test_cash_gap_share_and_report(self):
        metrics = pd.DataFrame({
            "stock_code": ["430001", "430002", "430003", "430004"],
            "company_name": ["甲", "乙", "丙", "丁"],
            "year": ["2025"] * 4,
            "industry": [GROUP_MANUFACTURING, GROUP_MANUFACTURING, GROUP_SOFTWARE, GROUP_SOFTWARE],
            "revenue": [1e8, 2e8, 3e7, 4e7],
            "gross_margin": [0.20, 0.22, 0.50, 0.55],
            "net_margin": [0.02, 0.03, 0.10, 0.08],
            "ar_to_revenue": [0.40, 0.35, 0.20, 0.15],
            "inventory_to_revenue": [0.30, 0.25, 0.02, 0.00],
            "ocf_to_revenue": [0.05, -0.10, 0.20, -0.30],
            "current_ratio": [1.2, 1.4, 2.0, 2.2],
            "debt_ratio": [0.5, 0.55, 0.3, 0.25],
            "revenue_yoy": [0.1, 0.0, 0.2, -0.1],
            "net_profit": [10.0, 8.0, 5.0, 4.0],
            "ocf": [3.0, -2.0, 6.0, -1.0],
            "ocf_yoy": [0.1, -0.2, 0.8, -1.5],
        })
        labeled, summary = industry_tables(metrics)
        by_ind = summary.set_index("industry")
        self.assertEqual(int(by_ind.loc[GROUP_MANUFACTURING, "n"]), 2)
        self.assertAlmostEqual(by_ind.loc[GROUP_MANUFACTURING, "share_profit_pos_ocf_neg"], 0.5)
        self.assertAlmostEqual(by_ind.loc[GROUP_SOFTWARE, "share_profit_pos_ocf_neg"], 0.5)
        self.assertGreater(
            by_ind.loc[GROUP_MANUFACTURING, "median_inventory_to_revenue"],
            by_ind.loc[GROUP_SOFTWARE, "median_inventory_to_revenue"],
        )
        self.assertGreater(
            by_ind.loc[GROUP_SOFTWARE, "median_gross_margin"],
            by_ind.loc[GROUP_MANUFACTURING, "median_gross_margin"],
        )
        derived = add_derived(metrics)
        self.assertAlmostEqual(derived.iloc[0]["wc_to_revenue"], 0.70)
        text = render_report(summary, n_total=4)
        self.assertIn("制造", text)
        self.assertIn("软件信息", text)
        self.assertIn("利润为正且 OCF 为负", text)

    def test_attach_uses_pdf_folders(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            touch_pdf(root / "01_制造业", "430010_戊_2025_x.pdf")
            metrics = pd.DataFrame({
                "stock_code": [430010],
                "company_name": ["戊"],
                "year": ["2025"],
                "revenue": [1e8],
            })
            labeled = attach_industry(metrics, pdf_root=root)
            self.assertEqual(labeled.iloc[0]["industry"], GROUP_MANUFACTURING)

    def test_main_guard_present(self):
        text = Path(__file__).resolve().parents[1].joinpath("industry_portrait.py").read_text(encoding="utf-8")
        self.assertIn("def main(", text)
        self.assertIn('if __name__ == "__main__":', text)


if __name__ == "__main__":
    unittest.main()
