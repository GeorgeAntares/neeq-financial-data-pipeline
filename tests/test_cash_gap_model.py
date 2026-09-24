import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from cash_gap_model import (
    FEATURE_COLS,
    assert_features_safe,
    make_labeled_frame,
    model_feature_columns,
)


class CashGapPrepTest(unittest.TestCase):
    def test_label_is_profit_positive_and_ocf_negative(self):
        metrics = pd.DataFrame({
            "stock_code": ["1", "2", "3", "4"],
            "revenue": [1e6, 1e6, 1e6, 1e6],
            "net_profit": [10.0, 10.0, -5.0, np.nan],
            "ocf": [-3.0, 4.0, -1.0, -2.0],
        })
        labeled = make_labeled_frame(metrics)
        self.assertEqual(len(labeled), 3)
        by_code = labeled.set_index("stock_code")["cash_gap"]
        self.assertEqual(int(by_code["1"]), 1)
        self.assertEqual(int(by_code["2"]), 0)
        self.assertEqual(int(by_code["3"]), 0)

    def test_features_exclude_ocf_and_net_profit(self):
        cols = model_feature_columns(["ind_制造"])
        self.assertTrue(assert_features_safe(cols))
        joined = " ".join(cols).lower()
        self.assertNotIn("ocf", joined)
        for leak in ("net_margin", "roe", "net_profit"):
            self.assertNotIn(leak, cols)
        self.assertIn("gross_margin_w", cols)
        self.assertIn("ar_to_revenue_w", cols)
        self.assertIn("ind_制造", cols)

    def test_forbidden_features_raise(self):
        with self.assertRaises(ValueError):
            assert_features_safe(["gross_margin_w", "ocf_to_revenue_w"])
        with self.assertRaises(ValueError):
            assert_features_safe(["net_margin"])

    def test_log_revenue_from_positive_revenue(self):
        labeled = make_labeled_frame(pd.DataFrame({
            "stock_code": ["1"],
            "revenue": [1000.0],
            "net_profit": [1.0],
            "ocf": [-1.0],
        }))
        self.assertAlmostEqual(labeled.iloc[0]["log_revenue"], 3.0)

    def test_main_guard_present(self):
        text = Path(__file__).resolve().parents[1].joinpath("cash_gap_model.py").read_text(encoding="utf-8")
        self.assertIn("def main(", text)
        self.assertIn('if __name__ == "__main__":', text)


class CashGapCvTest(unittest.TestCase):
    def test_cv_runs_when_sklearn_present(self):
        try:
            import sklearn  # noqa: F401
        except ImportError:
            self.skipTest("sklearn not installed in CI")
        from cash_gap_model import _logit, _rf, run_cv, summarize_cv

        rng = np.random.default_rng(0)
        n = 60
        X = pd.DataFrame({
            "gross_margin_w": rng.normal(size=n),
            "ar_to_revenue_w": rng.normal(size=n),
            "current_ratio_w": rng.normal(size=n),
        })
        y = np.array([1] * 12 + [0] * 48)
        X.loc[0, "gross_margin_w"] = np.nan
        rf_folds, rf_oof = run_cv(X, y, _rf, "random_forest")
        logit_folds, logit_oof = run_cv(X, y, _logit, "logit")
        self.assertEqual(len(rf_folds), 5)
        self.assertEqual(np.isfinite(rf_oof).sum(), n)
        summary = summarize_cv(pd.concat([rf_folds, logit_folds]))
        self.assertEqual(set(summary["model"]), {"random_forest", "logit"})
        self.assertTrue((summary["roc_auc_mean"] >= 0).all())


if __name__ == "__main__":
    unittest.main()
