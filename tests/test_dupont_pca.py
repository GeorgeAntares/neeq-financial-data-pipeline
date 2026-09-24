import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from dupont_pca import (
    add_size_logs,
    dupont_factor_assoc,
    dupont_identity,
    fit_pca,
    log_variance_shares,
    spearman_matrix,
    standardize,
    theme_for_loadings,
)


class DupontPcaTest(unittest.TestCase):
    def test_identity_holds_on_product(self):
        nm, at, em = 0.1, 2.0, 1.5
        df = pd.DataFrame({
            "net_margin": [nm, 0.05],
            "asset_turnover": [at, 0.8],
            "equity_multiplier": [em, 3.0],
        })
        df["dupont_product"] = df["net_margin"] * df["asset_turnover"] * df["equity_multiplier"]
        df["roe"] = df["dupont_product"]
        result = dupont_identity(df)
        self.assertEqual(result["n"], 2)
        self.assertEqual(result["n_match"], 2)
        self.assertLess(result["max_abs_gap"], 1e-12)

    def test_spearman_diagonal_is_one(self):
        df = pd.DataFrame({"a": [1, 2, 3, 4, 5], "b": [2, 4, 6, 8, 10], "c": [5, 1, 4, 2, 3]})
        corr = spearman_matrix(df, ["a", "b", "c"])
        self.assertAlmostEqual(corr.loc["a", "a"], 1.0)
        self.assertAlmostEqual(corr.loc["a", "b"], 1.0)

    def test_pca_recovers_dominant_direction(self):
        rng = np.random.default_rng(0)
        z = rng.normal(size=120)
        matrix = np.column_stack([z, 1.5 * z + 0.02 * rng.normal(size=120)])
        scaled, _, _ = standardize(matrix)
        loadings, ratio, _ = fit_pca(scaled)
        self.assertGreater(ratio[0], 0.95)
        self.assertGreater(abs(loadings[0, 0]), 0.6)
        self.assertGreater(abs(loadings[1, 0]), 0.6)

    def test_theme_follows_largest_abs_group(self):
        names = [
            "log_revenue", "log_assets", "debt_ratio_w", "equity_multiplier_w",
            "current_ratio_w", "ar_to_revenue_w", "inventory_to_revenue_w", "ocf_to_revenue_w",
        ]
        loadings = np.array([0.7, 0.6, 0.05, 0.05, 0.02, 0.02, 0.01, 0.01])
        self.assertEqual(theme_for_loadings(loadings, names), "规模")
        mixed = np.array([0.50, 0.45, 0.40, 0.27, 0.26, 0.17, 0.33, 0.34])
        self.assertEqual(theme_for_loadings(mixed, names), "规模")

    def test_log_variance_shares_sum_near_one_if_uncorrelated(self):
        rng = np.random.default_rng(1)
        n = 200
        log_nm = rng.normal(0, 1.0, size=n)
        log_at = rng.normal(0, 1.0, size=n)
        log_em = rng.normal(0, 1.0, size=n)
        df = pd.DataFrame({
            "net_margin": np.exp(log_nm),
            "asset_turnover": np.exp(log_at),
            "equity_multiplier": np.exp(log_em),
        })
        df["roe"] = df["net_margin"] * df["asset_turnover"] * df["equity_multiplier"]
        shares = log_variance_shares(df)
        total = shares["var_share"].sum()
        self.assertTrue((shares["var_share"] > 0.15).all())
        self.assertGreater(total, 0.7)
        self.assertLess(total, 1.3)

    def test_factor_assoc_tracks_net_margin(self):
        df = pd.DataFrame({
            "roe": [0.2, 0.1, 0.0, -0.1, -0.2],
            "net_margin": [0.2, 0.1, 0.0, -0.1, -0.2],
            "asset_turnover": [1.0, 1.0, 1.0, 1.0, 1.0],
            "equity_multiplier": [1.0, 1.0, 1.0, 1.0, 1.0],
        })
        assoc = dupont_factor_assoc(df).set_index("factor")
        self.assertAlmostEqual(assoc.loc["net_margin", "spearman_with_roe"], 1.0)

    def test_add_size_logs_skips_nonpositive(self):
        df = add_size_logs(pd.DataFrame({"revenue": [100.0, 0.0], "avg_assets": [50.0, -1.0]}))
        self.assertTrue(np.isfinite(df.loc[0, "log_revenue"]))
        self.assertTrue(np.isnan(df.loc[1, "log_revenue"]))
        self.assertTrue(np.isnan(df.loc[1, "log_assets"]))

    def test_main_guard_present(self):
        text = Path(__file__).resolve().parents[1].joinpath("dupont_pca.py").read_text(encoding="utf-8")
        self.assertIn("def main(", text)
        self.assertIn('if __name__ == "__main__":', text)


if __name__ == "__main__":
    unittest.main()
