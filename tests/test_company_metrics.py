import tempfile
import unittest
from pathlib import Path

import pandas as pd

from company_metrics import (
    build_company_metrics,
    score_equity,
    score_net_profit,
    score_revenue,
    winsorize_series,
    yoy,
)


def write_csv(folder, name, rows, columns):
    path = Path(folder) / name
    pd.DataFrame(rows, columns=columns).to_csv(path, index=False, encoding="utf-8-sig")
    return path


class CompanyMetricsTest(unittest.TestCase):
    def test_uses_first_block_not_parent_table(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            write_csv(
                temp_dir,
                "430001_测试_2025_合并利润表.csv",
                [
                    ["项目", "", ""],
                    ["一、营业总收入", 1_000_000, 800_000],
                    ["其中：营业收入", 1_000_000, 800_000],
                    ["其中：营业成本", 400_000, 350_000],
                    ["二、营业总成本", 700_000, 600_000],
                    ["五、净利润（净亏损以“－”号填列）", 100_000, 50_000],
                    ["1.持续经营净利润（净亏损以“-”号填列）", 100_000, 50_000],
                    ["2.归属于母公司所有者的净利润", 80_000, 40_000],
                    ["项目", "", ""],
                    ["一、营业收入", 10_000, 9_000],
                    ["减：营业成本", 1_000, 900],
                    ["四、净利润（净亏损以“-”号填列）", 1, 1],
                ],
                ["项目", "本期金额", "上期金额"],
            )
            write_csv(
                temp_dir,
                "430001_测试_2025_合并资产负债表.csv",
                [
                    ["项目", "", ""],
                    ["流动资产合计", 500_000, 450_000],
                    ["应收账款", 120_000, 100_000],
                    ["存货", 80_000, 70_000],
                    ["资产总计", 1_000_000, 900_000],
                    ["流动负债合计", 250_000, 200_000],
                    ["负债合计", 400_000, 350_000],
                    ["所有者权益（或股东权益）合计", 600_000, 550_000],
                    ["负债和所有者权益（或股东权益）总计", 1_000_000, 900_000],
                    ["项目", "", ""],
                    ["资产总计", 50_000, 40_000],
                    ["所有者权益合计", 10_000, 8_000],
                ],
                ["项目", "期末余额", "期初余额"],
            )
            write_csv(
                temp_dir,
                "430001_测试_2025_合并现金流量表.csv",
                [
                    ["项目", "", ""],
                    ["经营活动产生的现金流量净额", 40_000, 20_000],
                    ["投资活动产生的现金流量净额", -10_000, -5_000],
                    ["项目", "", ""],
                    ["经营活动产生的现金流量净额", 999, 1],
                ],
                ["项目", "本期金额", "上期金额"],
            )
            metrics = build_company_metrics(temp_dir)

        self.assertEqual(len(metrics), 1)
        row = metrics.iloc[0]
        self.assertEqual(row["revenue"], 1_000_000)
        self.assertEqual(row["cogs"], 400_000)
        self.assertEqual(row["cost_source"], "营业成本")
        self.assertEqual(row["net_profit"], 100_000)
        self.assertEqual(row["ocf"], 40_000)
        self.assertEqual(row["equity"], 600_000)
        self.assertEqual(row["equity_source"], "total")
        self.assertAlmostEqual(row["gross_margin"], 0.6)
        self.assertAlmostEqual(row["net_margin"], 0.1)
        self.assertAlmostEqual(row["avg_assets"], 950_000)
        self.assertAlmostEqual(row["avg_equity"], 575_000)
        self.assertAlmostEqual(row["asset_turnover"], 1_000_000 / 950_000)
        self.assertAlmostEqual(row["equity_multiplier"], 950_000 / 575_000)
        self.assertAlmostEqual(row["roe"], 100_000 / 575_000)
        self.assertAlmostEqual(row["dupont_product"], row["roe"], places=10)
        self.assertAlmostEqual(row["current_ratio"], 2.0)
        self.assertAlmostEqual(row["debt_ratio"], 0.4)
        self.assertAlmostEqual(row["ar_to_revenue"], 0.12)
        self.assertAlmostEqual(row["inventory_to_revenue"], 0.08)
        self.assertAlmostEqual(row["ocf_to_revenue"], 0.04)
        self.assertEqual(row["ocf_minus_np"], -60_000)
        self.assertAlmostEqual(row["revenue_yoy"], 0.25)
        self.assertAlmostEqual(row["net_profit_yoy"], 1.0)
        self.assertAlmostEqual(row["ocf_yoy"], 1.0)

    def test_drops_tiny_revenue_and_falls_back_to_total_cost(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            write_csv(
                temp_dir,
                "430002_小额_2025_合并利润表.csv",
                [["营业收入", 17.4, 10.0], ["营业总成本", 8.0, 7.0]],
                ["项目", "本期金额", "上期金额"],
            )
            write_csv(
                temp_dir,
                "430003_总成本_2025_合并利润表.csv",
                [
                    ["一、营业总收入", 500_000, 400_000],
                    ["二、营业总成本", 200_000, 180_000],
                    ["五、净利润（净亏损以“－”号填列）", 50_000, 40_000],
                ],
                ["项目", "本期金额", "上期金额"],
            )
            metrics = build_company_metrics(temp_dir)

        self.assertEqual(list(metrics["stock_code"]), ["430003"])
        self.assertEqual(metrics.iloc[0]["cogs"], 200_000)
        self.assertEqual(metrics.iloc[0]["cost_source"], "营业总成本")

    def test_yoy_uses_abs_prior(self):
        series = yoy(pd.Series([10.0, -20.0]), pd.Series([-10.0, -10.0]))
        self.assertAlmostEqual(series.iloc[0], 2.0)
        self.assertAlmostEqual(series.iloc[1], -1.0)

    def test_winsorize_clips_tails(self):
        values = pd.Series([0.2] * 40 + [0.21] * 40 + [50.0, -40.0])
        clipped = winsorize_series(values)
        self.assertLess(clipped.max(), 50.0)
        self.assertGreater(clipped.min(), -40.0)

    def test_score_helpers_reject_footnotes(self):
        self.assertEqual(score_revenue("其中：营业收入"), 0)
        self.assertGreater(score_revenue("一、营业总收入"), score_revenue("一、营业收入"))
        self.assertEqual(score_net_profit("1.持续经营净利润（净亏损以“-”号填列）"), 0)
        self.assertEqual(score_net_profit("2.归属于母公司所有者的净利润"), 0)
        self.assertGreater(score_net_profit("五、净利润（净亏损以“－”号填列）"), 0)
        self.assertEqual(score_equity("负债和所有者权益（或股东权益）总计"), 0)
        self.assertEqual(score_equity("所有者权益（或股东权益）："), 0)
        self.assertGreater(score_equity("所有者权益（或股东权益）合计"), score_equity("归属于母公司所有者权益合计"))

    def test_main_guard_present(self):
        text = Path(__file__).resolve().parents[1].joinpath("company_metrics.py").read_text(encoding="utf-8")
        self.assertIn("def main(", text)
        self.assertIn('if __name__ == "__main__":', text)


if __name__ == "__main__":
    unittest.main()
