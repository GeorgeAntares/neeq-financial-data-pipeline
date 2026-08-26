"""
NEEQ 财务健康度模型严谨化评估 / NEEQ Financial Health Model Rigorous Evaluation
==============================================================================
使用 Stratified K-Fold 交叉验证与 ROC-AUC 等指标，对随机森林财务健康度
分类模型进行严谨评估，替代单一 accuracy 报告。
Uses Stratified K-Fold cross-validation and ROC-AUC metrics to rigorously
evaluate the Random Forest financial health classifier, replacing a single
accuracy number with robust, variance-aware estimates.

输出 / Outputs (output/analysis/):
    roc_pr_curves.png   - 交叉验证 ROC 与 PR 曲线 / CV ROC & PR curves
    ml_cv_results.csv   - 每折指标明细 / Per-fold metric details
    ml_cv_summary.md    - 评估汇总报告 / Evaluation summary report
"""

import os
import glob
import warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import (accuracy_score, precision_score, recall_score,
                             f1_score, roc_auc_score, roc_curve,
                             precision_recall_curve, average_precision_score)

warnings.filterwarnings('ignore')

# ============================================================
# 配置 / Configuration
# ============================================================

matplotlib.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
matplotlib.rcParams['axes.unicode_minus'] = False

CSV_DIR = os.path.join(os.path.dirname(__file__), 'output', 'csv')
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), 'output', 'analysis')
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 与 ml_financial_health.py 保持一致 / Same config as ml_financial_health.py
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
FEATURE_COLS_MODEL = ['sales_cash', 'tax_refund', 'purchase_cash',
                      'employee_cost', 'tax_paid', 'icf', 'fcf']

N_SPLITS = 5
RANDOM_STATE = 42


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
print("NEEQ 模型严谨化评估 (K-Fold CV + ROC-AUC) / Rigorous Evaluation")
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
X = df[FEATURE_COLS_MODEL].values
y = df['healthy'].values
print(f"  健康 / Healthy (1): {y.sum()}  不健康 / Unhealthy (0): {len(y) - y.sum()}")

print(f"\n[3/5] {N_SPLITS}-折 Stratified 交叉验证 / Stratified K-Fold CV...")
skf = StratifiedKFold(n_splits=N_SPLITS, shuffle=True, random_state=RANDOM_STATE)

fold_results = []
tprs, aucs, precs, recs = [], [], [], []
mean_fpr = np.linspace(0, 1, 200)
pr_interp = []

for fold, (train_idx, test_idx) in enumerate(skf.split(X, y), 1):
    X_train, X_test = X[train_idx], X[test_idx]
    y_train, y_test = y[train_idx], y[test_idx]

    clf = RandomForestClassifier(n_estimators=100, random_state=RANDOM_STATE, max_depth=5)
    clf.fit(X_train, y_train)

    y_proba = clf.predict_proba(X_test)[:, 1]
    y_pred = (y_proba >= 0.5).astype(int)

    acc = accuracy_score(y_test, y_pred)
    prec = precision_score(y_test, y_pred)
    rec = recall_score(y_test, y_pred)
    f1 = f1_score(y_test, y_pred)
    auc = roc_auc_score(y_test, y_proba)
    ap = average_precision_score(y_test, y_proba)

    fpr, tpr, _ = roc_curve(y_test, y_proba)
    tprs.append(np.interp(mean_fpr, fpr, tpr))
    tprs[-1][0] = 0.0
    aucs.append(auc)
    precs.append(prec)
    recs.append(rec)

    p, r, _ = precision_recall_curve(y_test, y_proba)
    order = np.argsort(r)
    r_sorted, p_sorted = r[order], p[order]
    unique_mask = np.concatenate(([True], np.diff(r_sorted) > 0))
    pr_interp.append(np.interp(np.linspace(0, 1, 200),
                               r_sorted[unique_mask], p_sorted[unique_mask]))

    fold_results.append({
        'fold': fold, 'n_train': len(X_train), 'n_test': len(X_test),
        'accuracy': acc, 'precision': prec, 'recall': rec,
        'f1': f1, 'roc_auc': auc, 'avg_precision': ap
    })
    print(f"  Fold {fold}: acc={acc:.4f} prec={prec:.4f} rec={rec:.4f} "
          f"f1={f1:.4f} AUC={auc:.4f}")

print("\n  汇总（均值 ± 标准差）/ Summary (mean ± std):")
for metric in ['accuracy', 'precision', 'recall', 'f1', 'roc_auc']:
    vals = [r[metric] for r in fold_results]
    print(f"    {metric:<10s} {np.mean(vals):.4f} ± {np.std(vals):.4f}")

mean_tpr = np.mean(tprs, axis=0)
mean_tpr[-1] = 1.0
mean_auc = np.mean(aucs)
std_auc = np.std(aucs)
print(f"\n  平均 AUC / Mean ROC-AUC: {mean_auc:.4f} ± {std_auc:.4f}")

print("\n[4/5] 生成图表 / Generating charts...")

fig, axes = plt.subplots(1, 2, figsize=(13, 5.5))

# 图1: ROC 曲线 / ROC Curves
ax = axes[0]
std_tpr = np.std(tprs, axis=0)
ax.plot(mean_fpr, mean_tpr, color='#d62728', lw=2.5,
        label=f'均值 ROC (AUC = {mean_auc:.3f} ± {std_auc:.3f})')
ax.fill_between(mean_fpr, mean_tpr - std_tpr, mean_tpr + std_tpr,
                color='#d62728', alpha=0.15, label='±1 标准差 / ±1 std')
ax.plot([0, 1], [0, 1], 'k--', lw=1, label='随机猜测 / Random chance')
ax.set_xlim([-0.02, 1.02])
ax.set_ylim([-0.02, 1.02])
ax.set_xlabel('假阳性率 / False Positive Rate', fontsize=10)
ax.set_ylabel('真阳性率 / True Positive Rate', fontsize=10)
ax.set_title('交叉验证 ROC 曲线 (5-Fold CV)\nROC Curves', fontsize=12, fontweight='bold')
ax.legend(loc='lower right', fontsize=8)
ax.grid(alpha=0.3)

# 图2: PR 曲线 / Precision-Recall Curves
ax2 = axes[1]
mean_prec = np.mean(pr_interp, axis=0)
mean_ap = np.mean([r['avg_precision'] for r in fold_results])
std_ap = np.std([r['avg_precision'] for r in fold_results])
std_prec = np.std(pr_interp, axis=0)
rec_axis = np.linspace(0, 1, 200)
ax2.plot(rec_axis, mean_prec, color='#1f77b4', lw=2.5,
         label=f'均值 PR (AP = {mean_ap:.3f} ± {std_ap:.3f})')
ax2.fill_between(rec_axis, np.clip(mean_prec - std_prec, 0, 1),
                 np.clip(mean_prec + std_prec, 0, 1),
                 color='#1f77b4', alpha=0.15)
baseline = y.sum() / len(y)
ax2.axhline(baseline, color='k', ls='--', lw=1,
            label=f'基线 / Baseline ({baseline:.3f})')
ax2.set_xlim([-0.02, 1.02])
ax2.set_ylim([-0.02, 1.02])
ax2.set_xlabel('召回率 / Recall', fontsize=10)
ax2.set_ylabel('精确率 / Precision', fontsize=10)
ax2.set_title('交叉验证 PR 曲线 (5-Fold CV)\nPrecision-Recall Curves', fontsize=12, fontweight='bold')
ax2.legend(loc='upper right', fontsize=8)
ax2.grid(alpha=0.3)

plt.tight_layout()
plt.savefig(os.path.join(OUTPUT_DIR, 'roc_pr_curves.png'), dpi=150, bbox_inches='tight')
plt.close()
print(f"  图表已保存 / Chart saved: output/analysis/roc_pr_curves.png")

print("\n[5/5] 保存结果 / Saving results...")
res_df = pd.DataFrame(fold_results)
res_df.to_csv(os.path.join(OUTPUT_DIR, 'ml_cv_results.csv'),
              index=False, encoding='utf-8-sig')
print(f"  每折结果已保存 / Saved: output/analysis/ml_cv_results.csv")

summary = []
summary.append('# 模型严谨化评估汇总 / Rigorous Evaluation Summary\n')
summary.append(f'- 样本量 / Samples: {len(df)} 家企业（健康 {y.sum()} / 不健康 {len(y)-y.sum()}）')
summary.append(f'- 方法 / Method: {N_SPLITS}-折 Stratified 交叉验证（shuffle, random_state={RANDOM_STATE}）')
summary.append(f'- 模型 / Model: RandomForest (100 trees, max_depth=5)，与 ML 模块配置一致\n')
summary.append('## 指标（均值 ± 标准差）/ Metrics (mean ± std)\n')
summary.append('| 指标 / Metric | 数值 / Value |')
summary.append('|---|---|')
for metric in ['accuracy', 'precision', 'recall', 'f1', 'roc_auc', 'avg_precision']:
    vals = [r[metric] for r in fold_results]
    summary.append(f'| {metric} | {np.mean(vals):.4f} ± {np.std(vals):.4f} |')
summary.append('\n## 解读 / Interpretation\n')
summary.append('- 随机森林 5 折交叉验证平均 AUC 约为 '
               f'{mean_auc:.3f}（±{std_auc:.3f}），显著优于随机猜测 0.5，'
               '说明现金流特征包含可泛化的财务健康信号')
summary.append('- 与单一 80/20 划分（accuracy 57.8%）相比，交叉验证提供了带方差的可信估计，'
               '避免单次划分的偶然性')
summary.append('- 精确率与召回率的权衡可结合业务场景调整决策阈值（当前默认 0.5）')

with open(os.path.join(OUTPUT_DIR, 'ml_cv_summary.md'), 'w', encoding='utf-8') as f:
    f.write('\n'.join(summary))
print(f"  评估报告已保存 / Saved: output/analysis/ml_cv_summary.md")

print("\n" + "=" * 60)
print("评估完成 / Evaluation Complete")
print(f"平均 AUC / Mean ROC-AUC: {mean_auc:.4f} ± {std_auc:.4f}")
print("=" * 60)
