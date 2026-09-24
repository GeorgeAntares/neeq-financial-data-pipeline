"""
Company-level financial metrics (one row per stock_code + year).

Reads first statement block only (consolidated). A later ``项目`` header is
treated as the parent-company / extra table and ignored. Missing line items
stay NaN; they are not filled from a later block.
"""
from __future__ import annotations

import argparse
import glob
import os

import numpy as np
import pandas as pd

from financial_analysis import MIN_REVENUE_CNY, to_numeric_safe

ROOT = os.path.dirname(os.path.abspath(__file__))
CSV_255 = os.path.join(ROOT, "output", "analysis", "_csv_255")
CSV_DIR_DEFAULT = CSV_255 if os.path.isdir(CSV_255) else os.path.join(ROOT, "output", "csv")
OUTPUT_DIR_DEFAULT = os.path.join(ROOT, "output", "analysis")

METRICS_NAME = "company_metrics.csv"
COVERAGE_NAME = "company_metrics_coverage.csv"
WINSOR_LIMITS = (0.01, 0.99)

ID_COLS = ["stock_code", "company_name", "year"]

AMOUNT_COLS = [
    "revenue",
    "revenue_prior",
    "cogs",
    "net_profit",
    "net_profit_prior",
    "total_assets",
    "total_assets_begin",
    "current_assets",
    "current_liabilities",
    "total_liabilities",
    "equity",
    "equity_begin",
    "accounts_receivable",
    "inventory",
    "ocf",
    "ocf_prior",
]

RATIO_COLS = [
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
    "revenue_yoy",
    "net_profit_yoy",
    "ocf_yoy",
]


def parse_csv_filename(filename):
    """Parse ``{code}_{name}_{year}_合并{type}.csv``."""
    stem = os.path.basename(filename).replace(".csv", "")
    parts = stem.split("_")
    if len(parts) < 4:
        return None
    year = parts[2]
    if not (len(year) == 4 and year.isdigit()):
        return None
    return parts[0], parts[1], year


def iter_first_block(frame):
    """Yield rows of the first statement; stop at a later ``项目`` header."""
    if frame is None or frame.empty or len(frame.columns) < 2:
        return
    item_col = frame.columns[0]
    seen_data = False
    for _, row in frame.iterrows():
        item = str(row[item_col]).strip()
        if item in ("项目", "nan", ""):
            if seen_data and item == "项目":
                return
            continue
        seen_data = True
        yield row


def load_statement(csv_dir, statement_type):
    """Load first-block rows for 利润表 / 资产负债表 / 现金流量表."""
    pattern = os.path.join(csv_dir, f"*{statement_type}*.csv")
    records = []
    for path in glob.glob(pattern):
        parsed = parse_csv_filename(path)
        if parsed is None:
            continue
        stock_code, company_name, year = parsed
        try:
            frame = pd.read_csv(path, encoding="utf-8-sig")
        except Exception:
            continue
        if len(frame.columns) < 2:
            continue
        item_col = frame.columns[0]
        current_col = frame.columns[1]
        prior_col = frame.columns[2] if len(frame.columns) >= 3 else None
        order = 0
        for row in iter_first_block(frame):
            item = str(row[item_col]).strip()
            records.append(
                {
                    "stock_code": stock_code,
                    "company_name": company_name,
                    "year": year,
                    "item": item,
                    "current": row[current_col],
                    "prior": row[prior_col] if prior_col is not None else np.nan,
                    "row_order": order,
                }
            )
            order += 1
    return pd.DataFrame(records)


def score_revenue(item):
    text = str(item).strip()
    if text.startswith("其中"):
        return 0
    if "占" in text and "营业收入" in text:
        return 0
    if "营业总收入" in text:
        return 2
    if text in ("营业收入", "一、营业收入", "一.营业收入") or text.startswith("一、营业收入"):
        return 1
    return 0


def score_cogs(item):
    text = str(item).strip()
    if "营业总成本" in text:
        return 0
    if text.startswith("其中：营业成本") or text.startswith("其中:营业成本"):
        return 2
    if "营业成本" in text:
        return 1
    return 0


def score_total_operating_cost(item):
    text = str(item).strip()
    if "营业总成本" in text:
        return 1
    return 0


def score_net_profit(item):
    text = str(item).strip()
    if "净利润" not in text:
        return 0
    if text.startswith("其中"):
        return 0
    if any(token in text for token in ("持续经营", "终止经营", "归属于", "被合并", "少数股东")):
        return 0
    if text.startswith("四") or text.startswith("五"):
        return 2
    if text == "净利润" or text.startswith("净利润"):
        return 1
    return 0


def score_total_assets(item):
    return 1 if str(item).strip() == "资产总计" else 0


def score_current_assets(item):
    return 1 if str(item).strip() == "流动资产合计" else 0


def score_current_liabilities(item):
    return 1 if str(item).strip() == "流动负债合计" else 0


def score_total_liabilities(item):
    return 1 if str(item).strip() == "负债合计" else 0


def score_equity(item):
    text = str(item).strip()
    if "所有者权益" not in text:
        return 0
    if text.endswith("：") or text.endswith(":"):
        return 0
    if "负债和" in text:
        return 0
    if "归属于" in text:
        return 1
    if "合计" in text or text.endswith("合") or "股东权益" in text:
        return 2
    return 0


def score_accounts_receivable(item):
    text = str(item).strip()
    if text == "应收账款":
        return 1
    return 0


def score_inventory(item):
    return 1 if str(item).strip() == "存货" else 0


def score_ocf(item):
    text = str(item).strip()
    if "投资" in text or "筹资" in text:
        return 0
    if text == "经营活动产生的现金流量净额":
        return 2
    if text.startswith("经营活动产生的现金流量净"):
        return 1
    return 0


def pick_amount(long_df, score_fn, value_col="current"):
    """One numeric amount per company-year; higher score, then earlier row."""
    empty = pd.DataFrame(columns=ID_COLS + ["item", "value"])
    if long_df is None or long_df.empty:
        return empty
    work = long_df.copy()
    work["score"] = work["item"].map(score_fn)
    work = work[work["score"] > 0].copy()
    if work.empty:
        return empty
    work["value"] = work[value_col].map(to_numeric_safe)
    work = work.dropna(subset=["value"])
    if work.empty:
        return empty
    work = work.sort_values(
        ["stock_code", "year", "score", "row_order"],
        ascending=[True, True, False, True],
    )
    picked = work.drop_duplicates(subset=["stock_code", "year"], keep="first")
    return picked[ID_COLS + ["item", "value"]].reset_index(drop=True)


def _merge_pick(base, picked, value_name, item_name=None):
    keys = ["stock_code", "year"]
    if picked is None or picked.empty:
        if base is None or base.empty:
            cols = ID_COLS + [value_name]
            if item_name:
                cols.append(item_name)
            return pd.DataFrame(columns=cols)
        base = base.copy()
        base[value_name] = np.nan
        if item_name:
            base[item_name] = np.nan
        return base
    keep = keys + ["company_name", "value"]
    if item_name:
        keep = keys + ["company_name", "item", "value"]
    right = picked[keep].rename(columns={"value": value_name})
    if item_name:
        right = right.rename(columns={"item": item_name})
    if base is None or base.empty:
        return right
    merged = base.merge(right.drop(columns=["company_name"]), on=keys, how="outer")
    if "company_name" not in merged.columns:
        merged = merged.merge(right[keys + ["company_name"]], on=keys, how="left")
    else:
        extra = right[keys + ["company_name"]].rename(columns={"company_name": "_name"})
        merged = merged.merge(extra, on=keys, how="left")
        merged["company_name"] = merged["company_name"].fillna(merged["_name"])
        merged = merged.drop(columns=["_name"])
    return merged


def safe_div(numerator, denominator):
    num = pd.to_numeric(numerator, errors="coerce")
    den = pd.to_numeric(denominator, errors="coerce")
    out = num / den
    out = out.mask(den == 0)
    return out


def yoy(current, prior):
    """(current - prior) / |prior|; undefined when prior is 0 or missing."""
    cur = pd.to_numeric(current, errors="coerce")
    old = pd.to_numeric(prior, errors="coerce")
    out = (cur - old) / old.abs()
    out = out.mask(old == 0)
    return out


def winsorize_series(series, limits=WINSOR_LIMITS):
    values = pd.to_numeric(series, errors="coerce")
    if values.notna().sum() < 10:
        return values
    lower = values.quantile(limits[0])
    upper = values.quantile(limits[1])
    return values.clip(lower=lower, upper=upper)


def average_level(end_col, begin_col):
    end = pd.to_numeric(end_col, errors="coerce")
    begin = pd.to_numeric(begin_col, errors="coerce")
    both = end.notna() & begin.notna()
    avg = (end + begin) / 2.0
    return avg.where(both, end)


def build_company_metrics(csv_dir, min_revenue=MIN_REVENUE_CNY):
    """Wide table: amounts, ratios, YoY, DuPont identity, winsorized ratios."""
    income = load_statement(csv_dir, "利润表")
    balance = load_statement(csv_dir, "资产负债表")
    cashflow = load_statement(csv_dir, "现金流量表")

    revenue = pick_amount(income, score_revenue)
    revenue_prior = pick_amount(income, score_revenue, value_col="prior")
    cogs = pick_amount(income, score_cogs)
    total_cost = pick_amount(income, score_total_operating_cost)
    net_profit = pick_amount(income, score_net_profit)
    net_profit_prior = pick_amount(income, score_net_profit, value_col="prior")

    total_assets = pick_amount(balance, score_total_assets)
    total_assets_begin = pick_amount(balance, score_total_assets, value_col="prior")
    current_assets = pick_amount(balance, score_current_assets)
    current_liabilities = pick_amount(balance, score_current_liabilities)
    total_liabilities = pick_amount(balance, score_total_liabilities)
    equity = pick_amount(balance, score_equity)
    equity_begin = pick_amount(balance, score_equity, value_col="prior")
    ar = pick_amount(balance, score_accounts_receivable)
    inventory = pick_amount(balance, score_inventory)

    ocf = pick_amount(cashflow, score_ocf)
    ocf_prior = pick_amount(cashflow, score_ocf, value_col="prior")

    wide = revenue.rename(columns={"value": "revenue", "item": "revenue_item"})
    wide = _merge_pick(wide, revenue_prior, "revenue_prior")
    wide = _merge_pick(wide, cogs, "cogs", item_name="cogs_item")
    wide = _merge_pick(wide, total_cost, "total_operating_cost")
    wide = _merge_pick(wide, net_profit, "net_profit")
    wide = _merge_pick(wide, net_profit_prior, "net_profit_prior")
    wide = _merge_pick(wide, total_assets, "total_assets")
    wide = _merge_pick(wide, total_assets_begin, "total_assets_begin")
    wide = _merge_pick(wide, current_assets, "current_assets")
    wide = _merge_pick(wide, current_liabilities, "current_liabilities")
    wide = _merge_pick(wide, total_liabilities, "total_liabilities")
    wide = _merge_pick(wide, equity, "equity", item_name="equity_item")
    wide = _merge_pick(wide, equity_begin, "equity_begin")
    wide = _merge_pick(wide, ar, "accounts_receivable")
    wide = _merge_pick(wide, inventory, "inventory")
    wide = _merge_pick(wide, ocf, "ocf")
    wide = _merge_pick(wide, ocf_prior, "ocf_prior")

    if wide.empty:
        return wide

    cost_from_cogs = wide["cogs"].notna()
    wide["cogs"] = wide["cogs"].where(cost_from_cogs, wide.get("total_operating_cost"))
    wide["cost_source"] = pd.Series(pd.NA, index=wide.index, dtype="object")
    wide.loc[cost_from_cogs, "cost_source"] = "营业成本"
    wide.loc[~cost_from_cogs & wide["cogs"].notna(), "cost_source"] = "营业总成本"

    wide["equity_source"] = pd.Series(pd.NA, index=wide.index, dtype="object")
    if "equity_item" in wide.columns:
        parent_eq = wide["equity_item"].fillna("").str.contains("归属于", na=False)
        wide.loc[parent_eq, "equity_source"] = "parent"
        wide.loc[wide["equity"].notna() & ~parent_eq, "equity_source"] = "total"

    wide = wide[wide["revenue"].notna() & (wide["revenue"] >= min_revenue)].copy()
    if wide.empty:
        return wide

    wide["avg_assets"] = average_level(wide["total_assets"], wide["total_assets_begin"])
    wide["avg_equity"] = average_level(wide["equity"], wide["equity_begin"])

    wide["gross_margin"] = safe_div(wide["revenue"] - wide["cogs"], wide["revenue"])
    wide["net_margin"] = safe_div(wide["net_profit"], wide["revenue"])
    wide["roe"] = safe_div(wide["net_profit"], wide["avg_equity"])
    wide["asset_turnover"] = safe_div(wide["revenue"], wide["avg_assets"])
    wide["equity_multiplier"] = safe_div(wide["avg_assets"], wide["avg_equity"])
    wide["dupont_product"] = wide["net_margin"] * wide["asset_turnover"] * wide["equity_multiplier"]
    wide["current_ratio"] = safe_div(wide["current_assets"], wide["current_liabilities"])
    wide["debt_ratio"] = safe_div(wide["total_liabilities"], wide["total_assets"])
    wide["ar_to_revenue"] = safe_div(wide["accounts_receivable"], wide["revenue"])
    wide["inventory_to_revenue"] = safe_div(wide["inventory"], wide["revenue"])
    wide["ocf_to_revenue"] = safe_div(wide["ocf"], wide["revenue"])
    wide["ocf_minus_np"] = pd.to_numeric(wide["ocf"], errors="coerce") - pd.to_numeric(
        wide["net_profit"], errors="coerce"
    )
    wide["revenue_yoy"] = yoy(wide["revenue"], wide["revenue_prior"])
    wide["net_profit_yoy"] = yoy(wide["net_profit"], wide["net_profit_prior"])
    wide["ocf_yoy"] = yoy(wide["ocf"], wide["ocf_prior"])

    for col in RATIO_COLS + ["ocf_minus_np"]:
        wide[f"{col}_w"] = winsorize_series(wide[col])

    front = ID_COLS + [
        "revenue_item",
        "cost_source",
        "equity_source",
    ]
    ordered = [col for col in front if col in wide.columns]
    ordered += [col for col in AMOUNT_COLS if col in wide.columns]
    ordered += ["avg_assets", "avg_equity"]
    ordered += RATIO_COLS + ["dupont_product", "ocf_minus_np"]
    ordered += [f"{col}_w" for col in RATIO_COLS + ["ocf_minus_np"]]
    rest = [col for col in wide.columns if col not in ordered and col not in ("cogs_item", "equity_item", "total_operating_cost")]
    wide = wide[ordered + rest].sort_values(["stock_code", "year"]).reset_index(drop=True)
    return wide


def coverage_table(metrics):
    """Non-null counts for the amounts used by later analysis stages."""
    if metrics is None or metrics.empty:
        return pd.DataFrame(columns=["field", "n", "share"])
    n = len(metrics)
    fields = ["revenue", "cogs", "net_profit", "total_assets", "equity", "current_assets",
              "current_liabilities", "accounts_receivable", "inventory", "ocf",
              "gross_margin", "roe", "revenue_yoy"]
    rows = []
    for field in fields:
        if field not in metrics.columns:
            continue
        k = int(metrics[field].notna().sum())
        rows.append({"field": field, "n": k, "share": k / n})
    return pd.DataFrame(rows)


def default_csv_dir():
    return CSV_DIR_DEFAULT


def main(csv_dir=None, output_dir=None, min_revenue=MIN_REVENUE_CNY):
    csv_dir = csv_dir or default_csv_dir()
    output_dir = output_dir or OUTPUT_DIR_DEFAULT
    os.makedirs(output_dir, exist_ok=True)

    print("=" * 60)
    print("Company metrics / 公司级指标库")
    print(f"CSV dir: {csv_dir}")
    print(f"min revenue: {min_revenue:,.0f} CNY")
    print("=" * 60)

    metrics = build_company_metrics(csv_dir, min_revenue=min_revenue)
    if metrics.empty:
        print("No rows after revenue filter.")
        return metrics

    out_path = os.path.join(output_dir, METRICS_NAME)
    if os.path.exists(out_path):
        os.remove(out_path)
    metrics.to_csv(out_path, index=False, encoding="utf-8-sig")

    coverage = coverage_table(metrics)
    cov_path = os.path.join(output_dir, COVERAGE_NAME)
    if os.path.exists(cov_path):
        os.remove(cov_path)
    coverage.to_csv(cov_path, index=False, encoding="utf-8-sig")

    print(f"rows: {len(metrics)}  companies: {metrics['stock_code'].nunique()}")
    print("coverage:")
    for _, row in coverage.iterrows():
        print(f"  {row['field']}: {int(row['n'])} ({row['share'] * 100:.1f}%)")
    if "gross_margin" in metrics.columns:
        print(f"median gross_margin: {metrics['gross_margin'].median():.3f}")
    if "net_margin" in metrics.columns:
        print(f"median net_margin: {metrics['net_margin'].median():.3f}")
    if "ocf_to_revenue" in metrics.columns:
        print(f"median ocf/revenue: {metrics['ocf_to_revenue'].median():.3f}")
    print(f"wrote {out_path}")
    print(f"wrote {cov_path}")
    print("dictionary: company_metrics_dictionary.md")
    return metrics


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build company-level financial metrics")
    parser.add_argument("--csv-dir", default=None, help="CSV folder (default output/analysis/_csv_255)")
    parser.add_argument("--output-dir", default=None, help="Output folder")
    parser.add_argument(
        "--min-revenue",
        type=float,
        default=MIN_REVENUE_CNY,
        help="Drop firms below this revenue (CNY)",
    )
    args = parser.parse_args()
    main(csv_dir=args.csv_dir, output_dir=args.output_dir, min_revenue=args.min_revenue)
