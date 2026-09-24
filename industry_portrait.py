"""
Industry portraits on the company-metrics wide table.

Groups: 制造 / 软件信息 / 其他, from output/pdf subfolders.
"""
from __future__ import annotations

import argparse
import os

import numpy as np
import pandas as pd

from company_metrics import OUTPUT_DIR_DEFAULT, build_company_metrics, default_csv_dir
from industry_groups import (
    GROUP_MANUFACTURING,
    GROUP_ORDER,
    GROUP_OTHER,
    GROUP_SOFTWARE,
    PDF_DIR_DEFAULT,
    assign_industries,
    normalize_code,
)

MEDIAN_COLS = [
    "revenue",
    "gross_margin",
    "net_margin",
    "ar_to_revenue",
    "inventory_to_revenue",
    "wc_to_revenue",
    "ocf_to_revenue",
    "current_ratio",
    "debt_ratio",
    "revenue_yoy",
]

BOXPLOT_COLS = [
    ("gross_margin_w", "毛利率（截尾）"),
    ("ar_to_revenue_w", "应收 / 收入（截尾）"),
    ("inventory_to_revenue_w", "存货 / 收入（截尾）"),
    ("ocf_to_revenue_w", "OCF / 收入（截尾）"),
]

PORTRAIT_CHART = "industry_portrait.png"
CASH_GAP_CHART = "industry_cash_gap.png"
MEDIANS_NAME = "industry_medians.csv"
ASSIGN_NAME = "industry_assignments.csv"
REPORT_NAME = "industry_portrait.md"


def attach_industry(metrics, pdf_root=None):
    frame = metrics.copy()
    frame["stock_code"] = frame["stock_code"].map(normalize_code)
    assigned = pd.DataFrame(assign_industries(frame["stock_code"], pdf_root=pdf_root))
    assigned = assigned.drop_duplicates(subset=["stock_code"])
    if "industry" in frame.columns:
        frame = frame.drop(columns=["industry", "industry_raw"], errors="ignore")
    return frame.merge(assigned, on="stock_code", how="left")


def add_derived(metrics):
    frame = metrics.copy()
    if "ar_to_revenue" in frame.columns and "inventory_to_revenue" in frame.columns:
        frame["wc_to_revenue"] = (
            pd.to_numeric(frame["ar_to_revenue"], errors="coerce")
            + pd.to_numeric(frame["inventory_to_revenue"], errors="coerce")
        )
    np_ok = pd.to_numeric(frame.get("net_profit"), errors="coerce")
    ocf_ok = pd.to_numeric(frame.get("ocf"), errors="coerce")
    frame["has_np_ocf"] = np_ok.notna() & ocf_ok.notna()
    frame["profit_positive"] = np_ok > 0
    frame["ocf_negative"] = ocf_ok < 0
    frame["profit_pos_ocf_neg"] = frame["has_np_ocf"] & (np_ok > 0) & (ocf_ok < 0)
    ocf_yoy = pd.to_numeric(frame.get("ocf_yoy"), errors="coerce")
    frame["ocf_yoy_abs"] = ocf_yoy.abs()
    return frame


def _iqr(series):
    values = pd.to_numeric(series, errors="coerce").dropna()
    if values.empty:
        return np.nan
    return float(values.quantile(0.75) - values.quantile(0.25))


def industry_tables(metrics):
    """Median table and cash-gap rates, one row per industry group."""
    frame = add_derived(metrics)
    if "industry" not in frame.columns:
        raise ValueError("metrics need an industry column; call attach_industry first")
    frame["industry"] = pd.Categorical(frame["industry"], categories=GROUP_ORDER, ordered=True)

    rows = []
    for group, part in frame.groupby("industry", observed=False):
        labeled = part[part["has_np_ocf"]]
        row = {
            "industry": group,
            "n": int(len(part)),
            "n_np_ocf": int(len(labeled)),
        }
        for col in MEDIAN_COLS:
            if col in part.columns:
                row[f"median_{col}"] = part[col].median()
            else:
                row[f"median_{col}"] = np.nan
        row["iqr_ocf_to_revenue"] = _iqr(part.get("ocf_to_revenue"))
        row["median_ocf_yoy_abs"] = part["ocf_yoy_abs"].median()
        if labeled.empty:
            row["share_profit_pos"] = np.nan
            row["share_ocf_neg"] = np.nan
            row["share_profit_pos_ocf_neg"] = np.nan
        else:
            row["share_profit_pos"] = float(labeled["profit_positive"].mean())
            row["share_ocf_neg"] = float(labeled["ocf_negative"].mean())
            row["share_profit_pos_ocf_neg"] = float(labeled["profit_pos_ocf_neg"].mean())
        rows.append(row)
    summary = pd.DataFrame(rows)
    return frame, summary


def _pct(value):
    if value is None or pd.isna(value):
        return "n/a"
    return f"{float(value) * 100:.1f}%"


def _num(value, digits=3):
    if value is None or pd.isna(value):
        return "n/a"
    return f"{float(value):.{digits}f}"


def _row(summary, industry):
    hit = summary[summary["industry"] == industry]
    if hit.empty:
        return None
    return hit.iloc[0]


def render_report(summary, n_total):
    """Chinese findings section built from the median table (no hardcoded sample)."""
    mfg = _row(summary, GROUP_MANUFACTURING)
    sw = _row(summary, GROUP_SOFTWARE)
    lines = [
        "# 行业画像",
        "",
        f"样本 {n_total} 家，行业来自 `output/pdf/` 子目录（证监会门类），合并为 **制造 / 软件信息 / 其他**。",
        "`00_待分类` 和 PDF 根目录归入其他，不单独建模。",
        "",
        "## 样本",
        "",
        "| 行业 | 家数 | 有净利润且有 OCF |",
        "|------|------|------------------|",
    ]
    for _, row in summary.iterrows():
        lines.append(f"| {row['industry']} | {int(row['n'])} | {int(row['n_np_ocf'])} |")
    lines += [
        "",
        "## 中位数",
        "",
        "| 行业 | 营收（元） | 毛利率 | 净利率 | 应收/收入 | 存货/收入 | 营运资本/收入 | OCF/收入 | 流动比率 | 资产负债率 |",
        "|------|------------|--------|--------|-----------|-----------|---------------|----------|----------|------------|",
    ]
    for _, row in summary.iterrows():
        lines.append(
            "| {industry} | {rev:,.0f} | {gm} | {nm} | {ar} | {inv} | {wc} | {ocf} | {cr} | {dr} |".format(
                industry=row["industry"],
                rev=row["median_revenue"] if pd.notna(row["median_revenue"]) else 0,
                gm=_pct(row["median_gross_margin"]),
                nm=_pct(row["median_net_margin"]),
                ar=_pct(row["median_ar_to_revenue"]),
                inv=_pct(row["median_inventory_to_revenue"]),
                wc=_pct(row["median_wc_to_revenue"]),
                ocf=_pct(row["median_ocf_to_revenue"]),
                cr=_num(row["median_current_ratio"], 2),
                dr=_pct(row["median_debt_ratio"]),
            )
        )
    lines += [
        "",
        "## 利润与经营现金",
        "",
        "分母是同时有净利润和 OCF 的公司。",
        "",
        "| 行业 | 利润为正 | OCF 为负 | 利润为正且 OCF 为负 | OCF/收入 IQR | \\|OCF 同比\\| 中位数 |",
        "|------|----------|----------|---------------------|--------------|-------------------|",
    ]
    for _, row in summary.iterrows():
        lines.append(
            "| {industry} | {pp} | {on} | {gap} | {iqr} | {yoy} |".format(
                industry=row["industry"],
                pp=_pct(row["share_profit_pos"]),
                on=_pct(row["share_ocf_neg"]),
                gap=_pct(row["share_profit_pos_ocf_neg"]),
                iqr=_num(row["iqr_ocf_to_revenue"]),
                yoy=_pct(row["median_ocf_yoy_abs"]),
            )
        )

    lines += ["", "## 读数", ""]
    if mfg is not None and sw is not None:
        if mfg["median_ar_to_revenue"] > sw["median_ar_to_revenue"]:
            ar_note = "制造应收更重"
        else:
            ar_note = "软件应收更重，更像项目制回款而不是「制造压货」"
        if mfg["median_inventory_to_revenue"] > sw["median_inventory_to_revenue"]:
            inv_note = "制造存货略高"
        else:
            inv_note = "软件存货并不低（门类里常有软硬一体）"
        lines.append(
            "1. **营运资本**：应收/收入制造 {mfg_ar}、软件 {sw_ar}（{ar_note}）；"
            "存货/收入制造 {mfg_inv}、软件 {sw_inv}（{inv_note}）；"
            "两者合计软件 {sw_wc}、制造 {mfg_wc}。".format(
                mfg_ar=_pct(mfg["median_ar_to_revenue"]),
                sw_ar=_pct(sw["median_ar_to_revenue"]),
                mfg_inv=_pct(mfg["median_inventory_to_revenue"]),
                sw_inv=_pct(sw["median_inventory_to_revenue"]),
                sw_wc=_pct(sw["median_wc_to_revenue"]),
                mfg_wc=_pct(mfg["median_wc_to_revenue"]),
                ar_note=ar_note,
                inv_note=inv_note,
            )
        )
        gm_note = "软件毛利率更高" if sw["median_gross_margin"] > mfg["median_gross_margin"] else "制造毛利率更高"
        yoy_note = (
            "软件经营现金同比更跳"
            if sw["median_ocf_yoy_abs"] > mfg["median_ocf_yoy_abs"]
            else "制造经营现金同比更跳"
        )
        lines.append(
            "2. **毛利与现金**：毛利率软件 {sw_gm}、制造 {mfg_gm}（{gm_note}）；"
            "净利率软件 {sw_nm}、制造 {mfg_nm}；"
            "OCF/收入四分位距软件 {sw_iqr}、制造 {mfg_iqr}；"
            "|OCF 同比| 中位数软件 {sw_yoy}、制造 {mfg_yoy}（{yoy_note}）。".format(
                sw_gm=_pct(sw["median_gross_margin"]),
                mfg_gm=_pct(mfg["median_gross_margin"]),
                sw_nm=_pct(sw["median_net_margin"]),
                mfg_nm=_pct(mfg["median_net_margin"]),
                sw_iqr=_num(sw["iqr_ocf_to_revenue"]),
                mfg_iqr=_num(mfg["iqr_ocf_to_revenue"]),
                sw_yoy=_pct(sw["median_ocf_yoy_abs"]),
                mfg_yoy=_pct(mfg["median_ocf_yoy_abs"]),
                gm_note=gm_note,
                yoy_note=yoy_note,
            )
        )
        other = _row(summary, GROUP_OTHER)
        other_gap = _pct(other["share_profit_pos_ocf_neg"]) if other is not None else "n/a"
        lines.append(
            "3. **利润为正且 OCF 为负**：制造 {mfg_gap}，软件 {sw_gap}，其他 {other_gap}。"
            "软件利润为正的只有 {sw_pp}，亏损家数多，这个缺口标签更少出现。".format(
                mfg_gap=_pct(mfg["share_profit_pos_ocf_neg"]),
                sw_gap=_pct(sw["share_profit_pos_ocf_neg"]),
                other_gap=other_gap,
                sw_pp=_pct(sw["share_profit_pos"]),
            )
        )
    lines += [
        "",
        "## 局限",
        "",
        "- 软件样本小，中位数对单家公司敏感。",
        "- 「其他」混了批发、科研、待分类和未进子目录的 PDF，不是一个行业。",
        "- 单期年报；净利润覆盖低于营收，现金缺口占比的分母更小。",
        "- 行业标签来自本地 PDF 文件夹，不是交易所实时行业。",
        "",
    ]
    return "\n".join(lines)


def _save_fig(path, fig):
    if os.path.exists(path):
        os.remove(path)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    import matplotlib.pyplot as plt
    plt.close(fig)


def plot_boxplots(metrics, output_dir):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    matplotlib.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "DejaVu Sans"]
    matplotlib.rcParams["axes.unicode_minus"] = False

    frame = metrics.copy()
    frame["industry"] = pd.Categorical(frame["industry"], categories=GROUP_ORDER, ordered=True)
    fig, axes = plt.subplots(2, 2, figsize=(12, 9))
    for ax, (col, title) in zip(axes.ravel(), BOXPLOT_COLS):
        if col not in frame.columns:
            ax.set_visible(False)
            continue
        data = [frame.loc[frame["industry"] == g, col].dropna().values for g in GROUP_ORDER]
        ax.boxplot(data, tick_labels=GROUP_ORDER, showfliers=False)
        ax.set_title(title, fontsize=11, fontweight="bold")
        ax.axhline(0, color="#999999", linewidth=0.8, linestyle="--")
    fig.suptitle("三类行业分布（1%/99% 截尾）", fontsize=13, fontweight="bold")
    fig.tight_layout()
    path = os.path.join(output_dir, PORTRAIT_CHART)
    _save_fig(path, fig)
    return path


def plot_cash_gap(summary, output_dir):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    matplotlib.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "DejaVu Sans"]
    matplotlib.rcParams["axes.unicode_minus"] = False

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    industries = summary["industry"].tolist()
    gap = summary["share_profit_pos_ocf_neg"].fillna(0) * 100
    axes[0].bar(industries, gap, color=["#4c78a8", "#f58518", "#54a24b"], edgecolor="white")
    axes[0].set_ylabel("占比 (%)")
    axes[0].set_title("利润为正且 OCF 为负", fontsize=11, fontweight="bold")
    for x, y, n in zip(industries, gap, summary["n_np_ocf"]):
        axes[0].text(x, y + 0.5, f"{y:.1f}%\nn={int(n)}", ha="center", va="bottom", fontsize=8)
    axes[0].set_ylim(0, max(gap.max() * 1.25, 5))

    x = np.arange(len(industries))
    width = 0.25
    ar = summary["median_ar_to_revenue"].fillna(0) * 100
    inv = summary["median_inventory_to_revenue"].fillna(0) * 100
    gm = summary["median_gross_margin"].fillna(0) * 100
    axes[1].bar(x - width, ar, width, label="应收/收入", color="#4c78a8")
    axes[1].bar(x, inv, width, label="存货/收入", color="#f58518")
    axes[1].bar(x + width, gm, width, label="毛利率", color="#54a24b")
    axes[1].set_xticks(x, industries)
    axes[1].set_ylabel("%")
    axes[1].set_title("中位数：营运资本 vs 毛利", fontsize=11, fontweight="bold")
    axes[1].legend(fontsize=8)
    fig.tight_layout()
    path = os.path.join(output_dir, CASH_GAP_CHART)
    _save_fig(path, fig)
    return path


def load_or_build_metrics(metrics_path, csv_dir):
    if metrics_path and os.path.isfile(metrics_path):
        return pd.read_csv(metrics_path, encoding="utf-8-sig")
    default_metrics = os.path.join(OUTPUT_DIR_DEFAULT, "company_metrics.csv")
    if os.path.isfile(default_metrics):
        return pd.read_csv(default_metrics, encoding="utf-8-sig")
    return build_company_metrics(csv_dir or default_csv_dir())


def main(metrics_path=None, csv_dir=None, pdf_dir=None, output_dir=None, report_path=None):
    output_dir = output_dir or OUTPUT_DIR_DEFAULT
    pdf_dir = pdf_dir or PDF_DIR_DEFAULT
    os.makedirs(output_dir, exist_ok=True)

    print("=" * 60)
    print("Industry portrait / 行业画像")
    print(f"PDF dir: {pdf_dir}")
    print("=" * 60)

    metrics = load_or_build_metrics(metrics_path, csv_dir)
    if metrics is None or metrics.empty:
        print("No company metrics.")
        return None
    labeled = attach_industry(metrics, pdf_root=pdf_dir)
    labeled, summary = industry_tables(labeled)

    assign_path = os.path.join(output_dir, ASSIGN_NAME)
    labeled[["stock_code", "company_name", "year", "industry", "industry_raw"]].to_csv(
        assign_path, index=False, encoding="utf-8-sig"
    )
    med_path = os.path.join(output_dir, MEDIANS_NAME)
    summary.to_csv(med_path, index=False, encoding="utf-8-sig")

    report = render_report(summary, n_total=len(labeled))
    md_path = os.path.join(output_dir, REPORT_NAME)
    with open(md_path, "w", encoding="utf-8") as handle:
        handle.write(report)
    if report_path:
        with open(report_path, "w", encoding="utf-8") as handle:
            handle.write(report)

    box_path = plot_boxplots(labeled, output_dir)
    gap_path = plot_cash_gap(summary, output_dir)

    print(summary.to_string(index=False))
    print(f"wrote {assign_path}")
    print(f"wrote {med_path}")
    print(f"wrote {md_path}")
    print(f"wrote {box_path}")
    print(f"wrote {gap_path}")
    if report_path:
        print(f"wrote {report_path}")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NEEQ industry portraits")
    parser.add_argument("--metrics", default=None, help="company_metrics.csv")
    parser.add_argument("--csv-dir", default=None, help="CSV folder if metrics file is missing")
    parser.add_argument("--pdf-dir", default=None, help="PDF folder with industry subdirs")
    parser.add_argument("--output-dir", default=None, help="Charts and tables")
    parser.add_argument("--report", default=None, help="Optional extra markdown path")
    args = parser.parse_args()
    main(
        metrics_path=args.metrics,
        csv_dir=args.csv_dir,
        pdf_dir=args.pdf_dir,
        output_dir=args.output_dir,
        report_path=args.report,
    )
