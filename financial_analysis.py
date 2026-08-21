"""
NEEQ 财报数据分析 / NEEQ Financial Data Analysis
=================================================
新三板企业财务数据采集与分析项目 — 数据分析模块
NEEQ Financial Data Collection & Analysis Project — Data Analysis Module

分析内容 / Analysis Contents:
1. 数据概览 / Data Overview
2. 营收分析 / Revenue Analysis
3. 盈利能力分析 / Profitability Analysis
4. 现金流分析 / Cash Flow Analysis
5. 行业对比 / Industry Comparison
6. 可视化 / Visualization
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib
import glob
import os
import re
import warnings

warnings.filterwarnings('ignore')

# ============================================================
# 配置 / Configuration
# ============================================================

matplotlib.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
matplotlib.rcParams['axes.unicode_minus'] = False

CSV_DIR = os.path.join(os.path.dirname(__file__), 'output', 'csv')
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), 'output', 'analysis')

os.makedirs(OUTPUT_DIR, exist_ok=True)

# ============================================================
# 1. 数据加载 / Data Loading
# ============================================================

def load_csvs(statement_type):
    """
    加载指定类型的所有 CSV 文件 / Load all CSVs of a given statement type

    Parameters:
        statement_type: '利润表' or '现金流量表' or '资产负债表'
    Returns:
        DataFrame with columns: [stock_code, company_name, year, item, current, prior]
    """
    pattern = os.path.join(CSV_DIR, f'*{statement_type}*.csv')
    files = glob.glob(pattern)

    records = []
    for f in files:
        filename = os.path.basename(f)
        # 解析文件名: {code}_{name}_{year}_合并{type}.csv
        parts = filename.replace('.csv', '').split('_')
        if len(parts) < 4:
            continue
        stock_code = parts[0]
        company_name = parts[1]
        year = parts[2]

        try:
            df = pd.read_csv(f, encoding='utf-8-sig')
        except Exception:
            continue

        # 获取列名
        cols = df.columns.tolist()
        if len(cols) < 2:
            continue

        item_col = cols[0]
        val_col = cols[1] if len(cols) >= 2 else None
        prior_col = cols[2] if len(cols) >= 3 else None

        for _, row in df.iterrows():
            item = str(row[item_col]).strip()
            if not item or item == 'nan' or '年' in item and len(item) < 10:
                continue

            current = row[val_col] if val_col else None
            prior = row[prior_col] if prior_col else None

            records.append({
                'stock_code': stock_code,
                'company_name': company_name,
                'year': year,
                'item': item,
                'current': current,
                'prior': prior
            })

    return pd.DataFrame(records)


def to_numeric_safe(value):
    """安全转换为数值 / Safely convert to numeric"""
    if pd.isna(value) or value is None:
        return np.nan
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).replace(',', '').replace('%', '').replace('"', '').strip()
    try:
        return float(s)
    except ValueError:
        return np.nan


print("=" * 60)
print("NEEQ 财报数据分析 / NEEQ Financial Data Analysis")
print("=" * 60)

# 加载利润表 / Load income statements
print("\n[1/6] 加载利润表数据 / Loading income statement data...")
income_df = load_csvs('利润表')
print(f"  利润表记录数 Records: {len(income_df)}")
print(f"  企业数 Companies: {income_df['stock_code'].nunique()}")

# 加载现金流量表 / Load cash flow statements
print("\n[2/6] 加载现金流量表数据 / Loading cash flow data...")
cashflow_df = load_csvs('现金流量表')
print(f"  现金流量表记录数 Records: {len(cashflow_df)}")
print(f"  企业数 Companies: {cashflow_df['stock_code'].nunique()}")

# ============================================================
# 2. 营收分析 / Revenue Analysis
# ============================================================

print("\n[3/6] 营收分析 / Revenue Analysis...")

revenue_df = income_df[income_df['item'].str.contains('营业收入', na=False)].copy()
revenue_df['revenue'] = revenue_df['current'].apply(to_numeric_safe)
revenue_df = revenue_df.dropna(subset=['revenue'])
revenue_df = revenue_df[revenue_df['revenue'] > 0]

print(f"\n  有效营收数据企业 Companies with valid revenue: {len(revenue_df)}")
print(f"  营收均值 Mean revenue: {revenue_df['revenue'].mean() / 1e8:.2f} 亿元 / 100M CNY")
print(f"  营收中位数 Median revenue: {revenue_df['revenue'].median() / 1e8:.2f} 亿元 / 100M CNY")
print(f"  营收标准差 Std: {revenue_df['revenue'].std() / 1e8:.2f} 亿元 / 100M CNY")
print(f"  营收最大值 Max: {revenue_df['revenue'].max() / 1e8:.2f} 亿元 / 100M CNY")
print(f"  营收最小值 Min: {revenue_df['revenue'].min() / 1e4:.2f} 万元 / 10K CNY")

# 营收分布区间 / Revenue distribution
bins = [0, 1e7, 5e7, 1e8, 5e8, 1e9, float('inf')]
labels = ['<1000万', '1000万-5000万', '5000万-1亿', '1亿-5亿', '5亿-10亿', '>10亿']
revenue_df['revenue_range'] = pd.cut(revenue_df['revenue'], bins=bins, labels=labels)
print("\n  营收分布 / Revenue Distribution:")
dist = revenue_df['revenue_range'].value_counts().sort_index()
for label, count in dist.items():
    pct = count / len(revenue_df) * 100
    print(f"    {label}: {count} 家 ({pct:.1f}%)")

# 营收 Top 20 / Top 20 by revenue
print("\n  营收 Top 20 企业 / Top 20 Companies by Revenue:")
top20 = revenue_df.nlargest(20, 'revenue')[['company_name', 'stock_code', 'revenue']]
for i, (_, row) in enumerate(top20.iterrows(), 1):
    print(f"    {i:2d}. {row['company_name']} ({row['stock_code']}): {row['revenue'] / 1e8:.2f} 亿元")

# ============================================================
# 3. 盈利能力分析 / Profitability Analysis
# ============================================================

print("\n[4/6] 盈利能力分析 / Profitability Analysis...")

cost_df = income_df[income_df['item'].str.contains('营业成本', na=False)].copy()
cost_df['cost'] = cost_df['current'].apply(to_numeric_safe)
cost_df = cost_df.dropna(subset=['cost'])

# 合并营收和成本 / Merge revenue and cost
profit_df = revenue_df[['stock_code', 'company_name', 'revenue']].merge(
    cost_df[['stock_code', 'cost']], on='stock_code', how='inner'
)
profit_df['gross_profit'] = profit_df['revenue'] - profit_df['cost']
profit_df['gross_margin'] = (profit_df['gross_profit'] / profit_df['revenue']) * 100

print(f"  可计算毛利率的企业 Companies with gross margin: {len(profit_df)}")
print(f"  毛利率均值 Mean gross margin: {profit_df['gross_margin'].mean():.2f}%")
print(f"  毛利率中位数 Median gross margin: {profit_df['gross_margin'].median():.2f}%")

# 盈亏分析 / Profit/Loss analysis
profitable = profit_df[profit_df['gross_profit'] > 0]
loss_making = profit_df[profit_df['gross_profit'] <= 0]
print(f"\n  盈利企业 Profitable: {len(profitable)} ({len(profitable)/len(profit_df)*100:.1f}%)")
print(f"  亏损企业 Loss-making: {len(loss_making)} ({len(loss_making)/len(profit_df)*100:.1f}%)")

# 毛利率分布 / Gross margin distribution
margin_bins = [-float('inf'), 0, 10, 20, 30, 50, float('inf')]
margin_labels = ['<0%', '0-10%', '10-20%', '20-30%', '30-50%', '>50%']
profit_df['margin_range'] = pd.cut(profit_df['gross_margin'], bins=margin_bins, labels=margin_labels)
print("\n  毛利率分布 / Gross Margin Distribution:")
margin_dist = profit_df['margin_range'].value_counts().sort_index()
for label, count in margin_dist.items():
    pct = count / len(profit_df) * 100
    print(f"    {label}: {count} 家 ({pct:.1f}%)")

# ============================================================
# 4. 现金流分析 / Cash Flow Analysis
# ============================================================

print("\n[5/6] 现金流分析 / Cash Flow Analysis...")

operating_cf = cashflow_df[
    cashflow_df['item'].str.contains('经营活动产生的现金流量净额', na=False)
].copy()
operating_cf['ocf'] = operating_cf['current'].apply(to_numeric_safe)
operating_cf = operating_cf.dropna(subset=['ocf'])

print(f"  有效经营现金流企业 Companies with OCF data: {len(operating_cf)}")
print(f"  经营现金流均值 Mean OCF: {operating_cf['ocf'].mean() / 1e8:.2f} 亿元 / 100M CNY")
print(f"  经营现金流中位数 Median OCF: {operating_cf['ocf'].median() / 1e4:.2f} 万元 / 10K CNY")

positive_ocf = operating_cf[operating_cf['ocf'] > 0]
negative_ocf = operating_cf[operating_cf['ocf'] <= 0]
print(f"\n  正现金流 Positive OCF: {len(positive_ocf)} ({len(positive_ocf)/len(operating_cf)*100:.1f}%)")
print(f"  负现金流 Negative OCF: {len(negative_ocf)} ({len(negative_ocf)/len(operating_cf)*100:.1f}%)")

# ============================================================
# 5. 可视化 / Visualization
# ============================================================

print("\n[6/6] 生成图表 / Generating charts...")

# 图1: 营收分布直方图 / Revenue distribution histogram
fig, axes = plt.subplots(2, 2, figsize=(14, 10))

ax1 = axes[0, 0]
log_revenue = np.log10(revenue_df['revenue'][revenue_df['revenue'] > 0])
ax1.hist(log_revenue, bins=30, color='steelblue', edgecolor='white', alpha=0.8)
ax1.set_xlabel('营收（log10 元）/ Revenue (log10 CNY)', fontsize=10)
ax1.set_ylabel('企业数 / Number of Companies', fontsize=10)
ax1.set_title('营收分布 / Revenue Distribution', fontsize=12, fontweight='bold')
ax1.axvline(log_revenue.mean(), color='red', linestyle='--', label=f'均值 Mean: {10**log_revenue.mean()/1e8:.1f}亿')
ax1.legend(fontsize=9)

# 图2: 毛利率分布 / Gross margin distribution
ax2 = axes[0, 1]
margins = profit_df['gross_margin'][(profit_df['gross_margin'] > -100) & (profit_df['gross_margin'] < 200)]
ax2.hist(margins, bins=30, color='coral', edgecolor='white', alpha=0.8)
ax2.axvline(0, color='red', linestyle='--', linewidth=1, label='盈亏平衡 Break-even')
ax2.set_xlabel('毛利率 (%) / Gross Margin (%)', fontsize=10)
ax2.set_ylabel('企业数 / Number of Companies', fontsize=10)
ax2.set_title('毛利率分布 / Gross Margin Distribution', fontsize=12, fontweight='bold')
ax2.legend(fontsize=9)

# 图3: 营收 Top 15 / Top 15 by revenue
ax3 = axes[1, 0]
top15 = revenue_df.nlargest(15, 'revenue').sort_values('revenue')
bars = ax3.barh(top15['company_name'], top15['revenue'] / 1e8, color='teal', alpha=0.8)
ax3.set_xlabel('营收（亿元）/ Revenue (100M CNY)', fontsize=10)
ax3.set_title('营收 Top 15 企业 / Top 15 Companies by Revenue', fontsize=12, fontweight='bold')
ax3.tick_params(axis='y', labelsize=8)

# 图4: 经营现金流正负对比 / OCF positive vs negative
ax4 = axes[1, 1]
categories = ['正现金流\nPositive OCF', '负现金流\nNegative OCF']
values = [len(positive_ocf), len(negative_ocf)]
colors = ['#2ecc71', '#e74c3c']
bars = ax4.bar(categories, values, color=colors, edgecolor='white', alpha=0.85)
ax4.set_ylabel('企业数 / Number of Companies', fontsize=10)
ax4.set_title('经营现金流正负对比 / OCF Positive vs Negative', fontsize=12, fontweight='bold')
for bar, val in zip(bars, values):
    ax4.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1,
             str(val), ha='center', va='bottom', fontsize=11, fontweight='bold')

plt.tight_layout()
plt.savefig(os.path.join(OUTPUT_DIR, 'financial_analysis.png'), dpi=150, bbox_inches='tight')
print(f"  图表已保存 Chart saved: output/analysis/financial_analysis.png")

# ============================================================
# 6. 汇总统计 / Summary Statistics
# ============================================================

summary = pd.DataFrame({
    '指标 Metric': [
        '企业总数 Total Companies (Revenue)',
        '企业总数 Total Companies (OCF)',
        '营收均值 Mean Revenue (CNY)',
        '营收中位数 Median Revenue (CNY)',
        '毛利率均值 Mean Gross Margin (%)',
        '正现金流企业 Positive OCF (%)',
        '营收 Top 1 公司 Top 1 Revenue Company',
    ],
    '值 Value': [
        len(revenue_df),
        len(operating_cf),
        f"{revenue_df['revenue'].mean():,.0f}",
        f"{revenue_df['revenue'].median():,.0f}",
        f"{profit_df['gross_margin'].mean():.2f}%",
        f"{len(positive_ocf) / len(operating_cf) * 100:.1f}%",
        f"{top20.iloc[0]['company_name']} ({top20.iloc[0]['revenue'] / 1e8:.2f}亿)",
    ]
})

summary.to_csv(os.path.join(OUTPUT_DIR, 'summary_statistics.csv'), index=False, encoding='utf-8-sig')
print(f"  汇总统计已保存 Summary saved: output/analysis/summary_statistics.csv")

print("\n" + "=" * 60)
print("分析完成 / Analysis Complete")
print(f"输出目录 Output directory: {OUTPUT_DIR}")
print("=" * 60)
