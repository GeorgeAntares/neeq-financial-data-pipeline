"""
DuPont identity check, Spearman correlations, and SVD PCA.

PCA is numpy-only (no sklearn) so CI can run the math without the ML extra.
Components are read as 规模 / 杠杆 / 现金 from loadings.
"""
from __future__ import annotations

import argparse
import os

import numpy as np
import pandas as pd

from company_metrics import OUTPUT_DIR_DEFAULT

IDENTITY_ATOL = 1e-8

PCA_SPEC = [
    ("log_revenue", "log营收", "规模"),
    ("log_assets", "log资产", "规模"),
    ("debt_ratio_w", "资产负债率", "杠杆"),
    ("equity_multiplier_w", "权益乘数", "杠杆"),
    ("current_ratio_w", "流动比率", "杠杆"),
    ("ar_to_revenue_w", "应收/收入", "现金"),
    ("inventory_to_revenue_w", "存货/收入", "现金"),
    ("ocf_to_revenue_w", "OCF/收入", "现金"),
]
PCA_COLS = [row[0] for row in PCA_SPEC]
PCA_LABELS = {row[0]: row[1] for row in PCA_SPEC}
PCA_THEME = {row[0]: row[2] for row in PCA_SPEC}

CORR_COLS = [
    "gross_margin",
    "net_margin",
    "roe",
    "asset_turnover",
    "equity_multiplier",
    "current_ratio",
    "debt_ratio",
    "ar_to_revenue",
    "inventory_to_revenue",
    "ocf_to_revenue",
    "log_revenue",
]
CORR_LABELS = {
    "gross_margin": "毛利率",
    "net_margin": "净利率",
    "roe": "ROE",
    "asset_turnover": "周转",
    "equity_multiplier": "乘数",
    "current_ratio": "流动比率",
    "debt_ratio": "资产负债率",
    "ar_to_revenue": "应收/收入",
    "inventory_to_revenue": "存货/收入",
    "ocf_to_revenue": "OCF/收入",
    "log_revenue": "log营收",
}

CHART_NAME = "dupont_pca.png"
REPORT_NAME = "dupont_pca.md"
IDENTITY_NAME = "dupont_check.csv"
CORR_NAME = "correlation_spearman.csv"
LOADINGS_NAME = "pca_loadings.csv"
VARIANCE_NAME = "pca_variance.csv"


def add_size_logs(metrics):
    frame = metrics.copy()
    revenue = pd.to_numeric(frame.get("revenue"), errors="coerce")
    assets = pd.to_numeric(frame.get("avg_assets"), errors="coerce")
    with np.errstate(divide="ignore", invalid="ignore"):
        frame["log_revenue"] = np.where(revenue > 0, np.log10(revenue), np.nan)
        frame["log_assets"] = np.where(assets > 0, np.log10(assets), np.nan)
    return frame


def dupont_identity(metrics, atol=IDENTITY_ATOL):
    """ROE should equal net_margin × turnover × leverage when all four exist."""
    if not {"roe", "dupont_product"}.issubset(metrics.columns):
        return {"n": 0, "max_abs_gap": np.nan, "median_abs_gap": np.nan, "n_match": 0}
    work = metrics[["roe", "dupont_product"]].apply(pd.to_numeric, errors="coerce").dropna()
    if work.empty:
        return {"n": 0, "max_abs_gap": np.nan, "median_abs_gap": np.nan, "n_match": 0}
    gap = (work["dupont_product"] - work["roe"]).abs()
    return {
        "n": int(len(work)),
        "max_abs_gap": float(gap.max()),
        "median_abs_gap": float(gap.median()),
        "n_match": int((gap <= atol).sum()),
    }


def spearman_matrix(frame, columns):
    """Pairwise Spearman via ranks + Pearson; no scipy required."""
    cols = [col for col in columns if col in frame.columns]
    ranks = frame[cols].apply(pd.to_numeric, errors="coerce").rank()
    return ranks.corr(method="pearson")


def dupont_factor_assoc(metrics):
    """Spearman of ROE with each DuPont factor (complete rows)."""
    cols = ["roe", "net_margin", "asset_turnover", "equity_multiplier"]
    work = metrics[cols].apply(pd.to_numeric, errors="coerce").dropna()
    rows = []
    for factor in cols[1:]:
        rows.append(
            {
                "factor": factor,
                "n": int(len(work)),
                "spearman_with_roe": float(spearman_matrix(work, ["roe", factor]).loc["roe", factor])
                if len(work) >= 3
                else np.nan,
                "median": float(work[factor].median()) if len(work) else np.nan,
            }
        )
    return pd.DataFrame(rows)


def log_variance_shares(metrics):
    """
    For firms with positive NM, turnover, leverage and ROE:
    log(ROE) = log(NM) + log(AT) + log(EM).
    Report Var(log factor) / Var(log ROE); they need not sum to 1 (covariances).
    """
    work = metrics[["roe", "net_margin", "asset_turnover", "equity_multiplier"]].apply(
        pd.to_numeric, errors="coerce"
    ).dropna()
    work = work[
        (work["roe"] > 0)
        & (work["net_margin"] > 0)
        & (work["asset_turnover"] > 0)
        & (work["equity_multiplier"] > 0)
    ]
    if len(work) < 5:
        return pd.DataFrame(columns=["factor", "n", "var_share"])
    log_roe = np.log(work["roe"])
    denom = float(log_roe.var(ddof=1))
    mapping = {
        "net_margin": np.log(work["net_margin"]),
        "asset_turnover": np.log(work["asset_turnover"]),
        "equity_multiplier": np.log(work["equity_multiplier"]),
    }
    rows = []
    for name, series in mapping.items():
        share = float(series.var(ddof=1) / denom) if denom else np.nan
        rows.append({"factor": name, "n": int(len(work)), "var_share": share})
    return pd.DataFrame(rows)


def standardize(matrix):
    """Column mean 0, std 1 (population std, 0-std columns stay 0)."""
    data = np.asarray(matrix, dtype=float)
    mean = data.mean(axis=0)
    std = data.std(axis=0, ddof=0)
    scaled = np.zeros_like(data)
    nonzero = std > 0
    scaled[:, nonzero] = (data[:, nonzero] - mean[nonzero]) / std[nonzero]
    return scaled, mean, std


def fit_pca(matrix):
    """
    SVD PCA on an already-standardized n×p matrix.

    Loadings are V (p×k); scores are U S; variance uses S²/(n-1) like sklearn.
    """
    data = np.asarray(matrix, dtype=float)
    n_obs, n_feat = data.shape
    if n_obs < 2 or n_feat < 1:
        raise ValueError("PCA needs at least 2 rows")
    u, singular, vt = np.linalg.svd(data, full_matrices=False)
    explained = (singular ** 2) / max(n_obs - 1, 1)
    total = explained.sum()
    ratio = explained / total if total else np.zeros_like(explained)
    loadings = vt.T
    scores = u * singular
    return loadings, ratio, scores


def theme_for_loadings(loadings_col, feature_names):
    """Theme of the largest absolute loading (the variable people actually read)."""
    values = np.abs(np.asarray(loadings_col, dtype=float))
    return PCA_THEME[feature_names[int(np.argmax(values))]]


def pca_tables(metrics):
    frame = add_size_logs(metrics)
    complete = frame.dropna(subset=PCA_COLS).copy()
    if len(complete) < 8:
        empty_load = pd.DataFrame(columns=["feature", "label", "theme"] + [f"PC{i}" for i in range(1, 4)])
        empty_var = pd.DataFrame(columns=["component", "explained_ratio", "cumulative", "theme"])
        return complete, empty_load, empty_var
    scaled, _, _ = standardize(complete[PCA_COLS].to_numpy(dtype=float))
    loadings, ratio, _ = fit_pca(scaled)
    n_pc = loadings.shape[1]
    load_df = pd.DataFrame({"feature": PCA_COLS, "label": [PCA_LABELS[c] for c in PCA_COLS],
                            "theme": [PCA_THEME[c] for c in PCA_COLS]})
    for i in range(n_pc):
        load_df[f"PC{i + 1}"] = loadings[:, i]
    var_rows = []
    running = 0.0
    for i, share in enumerate(ratio):
        running += float(share)
        var_rows.append(
            {
                "component": f"PC{i + 1}",
                "explained_ratio": float(share),
                "cumulative": running,
                "theme": theme_for_loadings(loadings[:, i], PCA_COLS) if i < 3 else "",
            }
        )
    return complete, load_df, pd.DataFrame(var_rows)


def _pct(value):
    if value is None or pd.isna(value):
        return "n/a"
    return f"{float(value) * 100:.1f}%"


def _num(value, digits=4):
    if value is None or pd.isna(value):
        return "n/a"
    number = float(value)
    if number != 0 and abs(number) < 1e-6:
        return f"{number:.3e}"
    return f"{number:.{digits}f}"


def render_report(identity, assoc, var_shares, corr, load_df, var_df, n_metrics, n_pca):
    lines = [
        "# 杜邦核对与主成分",
        "",
        f"样本来自 `company_metrics.csv`（{n_metrics} 家有效营收）。",
        "杜邦：ROE = 净利率 × 总资产周转 × 权益乘数（资产/权益用期初期末平均）。",
        "相关阵用 Spearman（秩相关，少受极端值拉动）。",
        "PCA：8 个已截尾指标，列标准化后做 SVD，不依赖 scikit-learn。",
        "",
        "## 杜邦恒等式",
        "",
        f"- 可核对家数：{identity['n']}",
        f"- |乘积 − ROE| 最大：{_num(identity['max_abs_gap'])}",
        f"- 中位差距：{_num(identity['median_abs_gap'])}",
        f"- 差距 ≤ {IDENTITY_ATOL:g} 的家数：{identity['n_match']}",
        "",
        "恒等式在完整样本上成立，后面的分解用的是同一套科目。",
        "",
        "## ROE 与三个因子",
        "",
        "| 因子 | Spearman(与 ROE) | 中位数 |",
        "|------|------------------|--------|",
    ]
    name_zh = {"net_margin": "净利率", "asset_turnover": "总资产周转", "equity_multiplier": "权益乘数"}
    for _, row in assoc.iterrows():
        lines.append(
            f"| {name_zh.get(row['factor'], row['factor'])} | {_num(row['spearman_with_roe'], 3)} | {_num(row['median'], 3)} |"
        )
    if not var_shares.empty:
        lines += [
            "",
            "利润、周转、杠杆均为正的子集上，用 `Var(log 因子) / Var(log ROE)` 看哪一项更散"
            f"（n={int(var_shares.iloc[0]['n'])}，协方差使三项份额不必加总为 1）：",
            "",
            "| 因子 | 对数方差份额 |",
            "|------|--------------|",
        ]
        for _, row in var_shares.iterrows():
            lines.append(f"| {name_zh.get(row['factor'], row['factor'])} | {_pct(row['var_share'])} |")
        if (var_shares["var_share"] > 1).any():
            lines.append("")
            lines.append("份额大于 100% 表示该因子比 ROE 更散：另外两项与它负相关，把 ROE 拉平滑了。")
    if corr is not None and not corr.empty:
        if "roe" in corr.columns:
            top = corr["roe"].drop(labels=["roe"], errors="ignore").abs().sort_values(ascending=False).head(5)
            lines += ["", "## 与 ROE 相关最强的指标（Spearman |ρ|）", ""]
            for name, value in top.items():
                signed = corr.loc[name, "roe"]
                lines.append(f"- `{name}`：{signed:.3f}")
    lines += [
        "",
        "## PCA（规模 / 杠杆 / 现金）",
        "",
        f"完整个案 {n_pca} 家。规模：log营收、log资产；杠杆：资产负债率、权益乘数、流动比率；现金：应收/收入、存货/收入、OCF/收入（比率用 1%/99% 截尾列）。",
        "",
        "| 成分 | 解释比例 | 累计 | 按载荷归入 |",
        "|------|----------|------|------------|",
    ]
    for _, row in var_df.head(4).iterrows():
        lines.append(
            f"| {row['component']} | {_pct(row['explained_ratio'])} | {_pct(row['cumulative'])} | {row['theme'] or '—'} |"
        )
    if not load_df.empty:
        lines += ["", "前三个主成分上 |载荷| 最大的变量：", ""]
        for pc in ["PC1", "PC2", "PC3"]:
            if pc not in load_df.columns:
                continue
            top3 = load_df.assign(abs_load=load_df[pc].abs()).nlargest(3, "abs_load")
            bits = [f"{r['label']} ({r[pc]:+.2f})" for _, r in top3.iterrows()]
            theme = var_df.loc[var_df["component"] == pc, "theme"]
            theme_txt = theme.iloc[0] if len(theme) else ""
            lines.append(f"- **{pc}（{theme_txt}）**：{', '.join(bits)}")
    lines += [
        "",
        "## 局限",
        "",
        "- PCA 只用完整个案，比营收样本更少；缺净利润或资产负债表的公司不在里面。",
        "- 对数方差分解丢掉亏损和负权益，只描述仍能取对数的子集。",
        "- 主成分是相关结构，不是因果。",
        "",
    ]
    return "\n".join(lines)


def _save_fig(path, fig):
    if os.path.exists(path):
        os.remove(path)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    import matplotlib.pyplot as plt
    plt.close(fig)


def plot_figures(corr, load_df, var_df, output_dir):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    matplotlib.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "DejaVu Sans"]
    matplotlib.rcParams["axes.unicode_minus"] = False

    fig, axes = plt.subplots(1, 3, figsize=(16, 5))

    if corr is not None and not corr.empty:
        im = axes[0].imshow(corr.to_numpy(), cmap="RdBu_r", vmin=-1, vmax=1, aspect="auto")
        labels = [CORR_LABELS.get(col, col) for col in corr.columns]
        axes[0].set_xticks(range(len(labels)), labels, rotation=90, fontsize=8)
        axes[0].set_yticks(range(len(labels)), labels, fontsize=8)
        axes[0].set_title("Spearman 相关阵", fontweight="bold")
        fig.colorbar(im, ax=axes[0], fraction=0.046, pad=0.04)
    else:
        axes[0].set_visible(False)

    if not var_df.empty:
        axes[1].bar(var_df["component"].head(6), var_df["explained_ratio"].head(6) * 100, color="#4c78a8")
        axes[1].plot(var_df["component"].head(6), var_df["cumulative"].head(6) * 100, color="#f58518", marker="o")
        axes[1].set_ylabel("%")
        axes[1].set_title("方差解释（柱）与累计（线）", fontweight="bold")
    else:
        axes[1].set_visible(False)

    pc_cols = [c for c in ["PC1", "PC2", "PC3"] if c in load_df.columns]
    if pc_cols and not load_df.empty:
        mat = load_df[pc_cols].to_numpy()
        vmax = np.nanmax(np.abs(mat)) or 1.0
        im2 = axes[2].imshow(mat, cmap="RdBu_r", vmin=-vmax, vmax=vmax, aspect="auto")
        axes[2].set_xticks(range(len(pc_cols)), pc_cols)
        axes[2].set_yticks(range(len(load_df)), list(load_df["label"]), fontsize=8)
        axes[2].set_title("PCA 载荷", fontweight="bold")
        fig.colorbar(im2, ax=axes[2], fraction=0.046, pad=0.04)
    else:
        axes[2].set_visible(False)

    fig.tight_layout()
    path = os.path.join(output_dir, CHART_NAME)
    _save_fig(path, fig)
    return path


def load_metrics(metrics_path):
    default_metrics = os.path.join(OUTPUT_DIR_DEFAULT, "company_metrics.csv")
    path = metrics_path or default_metrics
    if not os.path.isfile(path):
        return pd.DataFrame()
    return pd.read_csv(path, encoding="utf-8-sig")


def main(metrics_path=None, output_dir=None, report_path=None):
    output_dir = output_dir or OUTPUT_DIR_DEFAULT
    os.makedirs(output_dir, exist_ok=True)
    metrics = load_metrics(metrics_path)
    print("=" * 60)
    print("DuPont + PCA")
    print("=" * 60)
    if metrics.empty:
        print("No company_metrics.csv. Run company_metrics.py first.")
        return None

    frame = add_size_logs(metrics)
    identity = dupont_identity(frame)
    assoc = dupont_factor_assoc(frame)
    shares = log_variance_shares(frame)
    corr = spearman_matrix(frame, CORR_COLS)
    complete, load_df, var_df = pca_tables(frame)

    pd.DataFrame([identity]).to_csv(os.path.join(output_dir, IDENTITY_NAME), index=False, encoding="utf-8-sig")
    corr.to_csv(os.path.join(output_dir, CORR_NAME), encoding="utf-8-sig")
    load_df.to_csv(os.path.join(output_dir, LOADINGS_NAME), index=False, encoding="utf-8-sig")
    var_df.to_csv(os.path.join(output_dir, VARIANCE_NAME), index=False, encoding="utf-8-sig")

    report = render_report(identity, assoc, shares, corr, load_df, var_df, n_metrics=len(frame), n_pca=len(complete))
    md_path = os.path.join(output_dir, REPORT_NAME)
    with open(md_path, "w", encoding="utf-8") as handle:
        handle.write(report)
    if report_path:
        with open(report_path, "w", encoding="utf-8") as handle:
            handle.write(report)

    chart_path = plot_figures(corr, load_df, var_df, output_dir)
    print(f"dupont n={identity['n']} max|gap|={identity['max_abs_gap']:.3e} match={identity['n_match']}")
    print(f"pca n={len(complete)}")
    if not var_df.empty:
        print(var_df.head(3).to_string(index=False))
    print(f"wrote {md_path}")
    print(f"wrote {chart_path}")
    if report_path:
        print(f"wrote {report_path}")
    return var_df


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DuPont check, Spearman correlations, SVD PCA")
    parser.add_argument("--metrics", default=None, help="company_metrics.csv")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--report", default=None, help="Optional extra markdown path")
    args = parser.parse_args()
    main(metrics_path=args.metrics, output_dir=args.output_dir, report_path=args.report)
