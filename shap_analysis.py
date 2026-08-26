"""
NEEQ 财务健康度模型可解释性分析 / NEEQ Financial Health Model Interpretability (SHAP)
======================================================================================
使用 SHAP (TreeExplainer) 对随机森林财务健康度分类模型进行可解释性分析，
输出特征重要性排序、方向性影响，并结合财务知识给出业务解读。
Uses SHAP (TreeExplainer) to interpret the Random Forest financial health classifier,
outputs feature importance ranking, directional impact, and business-level insights.

解读要点 / Key Insights:
    特征均为绝对金额（元），SHAP 揭示的主要是规模效应与现金流结构信号；
    Feature values are absolute amounts (CNY), so SHAP mainly reveals scale effects
    and cash-flow structure signals.

输出 / Outputs (output/analysis/):
    shap_summary.png      - SHAP beeswarm 图 / SHAP beeswarm summary plot
    shap_importance.png   - 平均 |SHAP| 特征重要性 / Mean |SHAP| importance bar chart
    shap_insights.md      - 结合财务知识的解读报告 / Financial-knowledge insight report
"""

import os
import re
import glob
import warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from sklearn.ensemble import RandomForestClassifier

warnings.filterwarnings('ignore')

# ============================================================
# 配置 / Configuration
# ============================================================

matplotlib.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
matplotlib.rcParams['axes.unicode_minus'] = False

CSV_DIR = os.path.join(os.path.dirname(__file__), 'output', 'csv')
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), 'output', 'analysis')
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 与 ml_financial_health.py 保持一致的特征定义 / Same features as ml_financial_health.py
FEATURE_ITEMS = {
    'sales_cash': ['销售商品、提供劳务收到的现金'],
    'tax_refund': ['收到的税费返还'],
    'purchase_cash': ['购买商品、接受劳务支付的现金'],
    'employee_cost': ['支付给职工以及为职工支付的现金'],
    'tax_paid': ['支付的各项税费'],
    'ocf': ['经营活动产生的现金流量净额'],
    'icf': ['投资活动产生的现金流量净额'],
    'fcf': ['筹资活动产生的现金流量净额'],
    'net_cash_increase': ['现金及现金等价物净增加额'],
}

# 模型特征（排除 ocf 防数据泄露）/ Model features (ocf excluded to avoid leakage)
FEATURE_COLS_MODEL = ['sales_cash', 'tax_refund', 'purchase_cash',
                      'employee_cost', 'tax_paid', 'icf', 'fcf']

# 财务知识解读库 / Financial-knowledge interpretation library
FINANCE_KNOWLEDGE = {
    'sales_cash': '销售商品、提供劳务收到的现金（销售收现）：衡量主营业务现金回款能力，是经营现金流的基石',
    'tax_refund': '收到的税费返还：反映税收优惠与退税情况，通常为弱信号',
    'purchase_cash': '购买商品、接受劳务支付的现金（采购付现）：主营业务现金流出规模',
    'employee_cost': '支付给职工以及为职工支付的现金：人力成本规模',
    'tax_paid': '支付的各项税费：税负规模，反映盈利与合规水平',
    'icf': '投资活动产生的现金流量净额：负值通常意味着扩张性投资，短期内消耗现金',
    'fcf': '筹资活动产生的现金流量净额：正值依赖外部融资，可能反映内生造血能力不足',
}


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


def extract_features(csv_dir):
    """从现金流量表 CSV 提取特征 / Extract features from cash flow CSVs"""
    files = glob.glob(os.path.join(csv_dir, '*现金流量表*.csv'))
    records = []
    for f in files:
        parts = os.path.basename(f).replace('.csv', '').split('_')
        if len(parts) < 4:
            continue
        stock_code, company_name = parts[0], parts[1]
        try:
            df = pd.read_csv(f, encoding='utf-8-sig')
        except Exception:
            continue
        cols = df.columns.tolist()
        if len(cols) < 2:
            continue
        item_col, val_col = cols[0], cols[1]
        features = {'stock_code': stock_code, 'company_name': company_name}
        for _, row in df.iterrows():
            item = str(row[item_col]).strip()
            val = to_numeric_safe(row[val_col])
            if pd.isna(val):
                continue
            for feat_name, keywords in FEATURE_ITEMS.items():
                if any(kw in item for kw in keywords):
                    if feat_name not in features or pd.isna(features.get(feat_name)):
                        features[feat_name] = val
        records.append(features)
    return pd.DataFrame(records)


print("=" * 60)
print("NEEQ 模型可解释性分析 (SHAP) / Model Interpretability (SHAP)")
print("=" * 60)

print("\n[1/5] 提取特征 / Extracting features...")
raw_df = extract_features(CSV_DIR)
df = raw_df.dropna(subset=['ocf', 'net_cash_increase']).copy()
for col in FEATURE_COLS_MODEL:
    if col in df.columns:
        df[col] = df[col].fillna(0)
print(f"  有效企业数 / Valid companies: {len(df)}")

print("\n[2/5] 构建标签 / Building labels...")
df['healthy'] = ((df['ocf'] > 0) & (df['net_cash_increase'] > 0)).astype(int)
print(f"  健康 / Healthy (1): {df['healthy'].sum()}  不健康 / Unhealthy (0): {(1 - df['healthy']).sum()}")

print("\n[3/5] 训练随机森林（全量数据，配置与 ML 模块一致）/ Training Random Forest on full data...")
X = df[FEATURE_COLS_MODEL]
y = df['healthy'].values
clf = RandomForestClassifier(n_estimators=100, random_state=42, max_depth=5)
clf.fit(X, y)
print(f"  完成 / Done.")

print("\n[4/5] 计算 SHAP 值 / Computing SHAP values...")
import shap
explainer = shap.TreeExplainer(clf)
shap_values = explainer.shap_values(X)
# 二分类取正类（健康）/ For binary classification take the positive class
if isinstance(shap_values, list):
    shap_values_pos = shap_values[1]
elif hasattr(shap_values, 'ndim') and shap_values.ndim == 3:
    shap_values_pos = shap_values[:, :, 1]
else:
    shap_values_pos = shap_values
print(f"  SHAP matrix: {shap_values_pos.shape}")

mean_abs_shap = np.abs(shap_values_pos).mean(axis=0)
order = np.argsort(mean_abs_shap)[::-1]
print("\n  特征重要性（平均 |SHAP|）/ Mean |SHAP| importance:")
for i, idx in enumerate(order):
    print(f"    {i+1}. {FEATURE_COLS_MODEL[idx]:<15s} {mean_abs_shap[idx]:.6f}")

# 方向性判断 / Directionality: correlation between feature value and SHAP
print("\n  方向性影响 / Directional impact (corr(feature, SHAP)):")
direction = {}
for i, feat in enumerate(FEATURE_COLS_MODEL):
    corr = np.corrcoef(X[feat].values, shap_values_pos[:, i])[0, 1]
    direction[feat] = corr
    arrow = '↑ 越高越健康' if corr > 0.05 else ('↓ 越高越不健康' if corr < -0.05 else '~ 非线性/弱')
    print(f"    {feat:<15s} corr={corr:+.3f}  {arrow}")

print("\n[5/5] 生成图表与解读报告 / Generating charts & insight report...")

# ---- 图1: SHAP beeswarm 图 / Beeswarm summary plot ----
plt.figure(figsize=(11, 7))
shap.summary_plot(shap_values_pos, X, show=False, max_display=len(FEATURE_COLS_MODEL))
plt.title('SHAP 特征影响（红=特征值高，蓝=特征值低）\nSHAP Feature Impact (red=high value, blue=low value)', fontsize=13, fontweight='bold')
plt.tight_layout()
plt.savefig(os.path.join(OUTPUT_DIR, 'shap_summary.png'), dpi=150, bbox_inches='tight')
plt.close()
print(f"  图表已保存 / Chart saved: output/analysis/shap_summary.png")

# ---- 图2: 平均 |SHAP| 条形图 / Mean |SHAP| bar chart ----
plt.figure(figsize=(9, 6))
names = [FEATURE_COLS_MODEL[i] for i in order]
colors = plt.cm.viridis(np.linspace(0.2, 0.8, len(order)))
bars = plt.barh(range(len(order)), mean_abs_shap[order], color=colors, edgecolor='white')
plt.yticks(range(len(order)), names, fontsize=10)
plt.gca().invert_yaxis()
plt.xlabel('平均 |SHAP| / Mean |SHAP|', fontsize=11)
plt.title('随机森林特征重要性（SHAP 视角）\nFeature Importance by SHAP', fontsize=13, fontweight='bold')
for bar, val in zip(bars, mean_abs_shap[order]):
    plt.text(bar.get_width() + 0.0005, bar.get_y() + bar.get_height()/2,
             f'{val:.4f}', va='center', fontsize=9)
plt.tight_layout()
plt.savefig(os.path.join(OUTPUT_DIR, 'shap_importance.png'), dpi=150, bbox_inches='tight')
plt.close()
print(f"  图表已保存 / Chart saved: output/analysis/shap_importance.png")

# ---- 解读报告 / Insight report ----
def describe_direction(corr):
    if corr > 0.05:
        return '正向', '该指标金额越高，模型越倾向于判定为财务健康'
    if corr < -0.05:
        return '负向', '该指标金额越高，模型越倾向于判定为不健康'
    return '弱/非线性', '该指标与健康度呈弱或非线性关系，需结合具体样本解读'

lines = []
lines.append('# NEEQ 财务健康模型 SHAP 解读报告 / SHAP Insight Report\n')
lines.append(f'- 样本量 / Samples: {len(df)} 家企业')
lines.append(f'- 模型 / Model: RandomForest (100 trees, max_depth=5)，与 ML 模块配置一致')
lines.append(f'- 标签定义 / Label: 经营现金流为正 且 现金净增加额为正 (OCF>0 AND net cash increase>0)\n')
lines.append('## 特征重要性排序（平均 |SHAP|）/ Feature Importance (Mean |SHAP|)\n')
for rank, idx in enumerate(order, 1):
    lines.append(f"{rank}. **{FEATURE_COLS_MODEL[idx]}**: {mean_abs_shap[idx]:.6f}")
lines.append('\n## 方向性解读与财务知识 / Directional Insights with Financial Knowledge\n')
for rank, idx in enumerate(order, 1):
    feat = FEATURE_COLS_MODEL[idx]
    corr = direction[feat]
    kind, meaning = describe_direction(corr)
    lines.append(f"### {rank}. {feat}（{kind}）")
    lines.append(f"- 财务含义 / Financial meaning: {FINANCE_KNOWLEDGE[feat]}")
    lines.append(f"- 模型行为 / Model behaviour: {meaning}（corr={corr:+.3f}）")
    if feat == 'sales_cash' and corr > 0.05:
        lines.append("- 解读 / Insight: 销售收现规模是健康度最强的正向信号，主营业务现金回款能力直接决定企业能否维持正向经营现金流，符合财务常识（现金为王）。")
    elif feat == 'fcf' and corr < -0.05:
        lines.append("- 解读 / Insight: 筹资净流入越多越可能被判定为不健康，反映企业对外部融资的依赖——'内生造血能力不足才需持续融资'的财务逻辑。这是模型最具业务含义的发现。")
    elif feat == 'icf' and corr < -0.05:
        lines.append("- 解读 / Insight: 投资活动净流出越大（扩张性投资），短期财务健康度越低——扩张期企业现金消耗大，与'投资激进→现金流承压'的财务直觉一致。")
    elif feat == 'icf' and corr > 0.05:
        lines.append("- 解读 / Insight: 投资活动净流入（处置资产、收回投资）与健康度正相关，可能反映企业收缩聚焦或投资回报兑现，与财务直觉一致。")
    else:
        lines.append("- 解读 / Insight: 该指标主要反映企业规模效应，绝对值特征下规模本身成为健康度的代理变量。")
    lines.append("")
lines.append('## 局限与下一步 / Limitations & Next Steps\n')
lines.append('- 当前特征为绝对金额，SHAP 主要揭示规模效应；后续可加入财务比率特征（如经营现金比率 OCF/Sales、现金转化率）以获得更纯粹的"质量"信号')
lines.append('- 模型准确率约 58%（80/20 划分），属中低水平：SHAP 解释的是模型行为而非因果，解读需结合业务判断')
lines.append('- 可进一步用 SHAP dependence plot 深入单个特征的非线性效应')

md_path = os.path.join(OUTPUT_DIR, 'shap_insights.md')
with open(md_path, 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))
print(f"  解读报告已保存 / Report saved: output/analysis/shap_insights.md")

print("\n" + "=" * 60)
print("SHAP 分析完成 / SHAP Analysis Complete")
print("=" * 60)
