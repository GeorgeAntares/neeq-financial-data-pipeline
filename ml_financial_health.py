"""
NEEQ 企业财务健康度机器学习分类 / NEEQ Financial Health ML Classification
==========================================================================
基于现金流数据构建特征，使用随机森林预测企业财务健康状况。
Builds features from cash flow data, uses Random Forest to predict company financial health.

模型目标 / Model Objective:
    预测企业是否"财务健康" / Predict whether a company is "financially healthy"
    定义 / Definition: 经营现金流为正 且 现金净增加额为正
    OCF > 0 AND net cash increase > 0

特征 / Features (8):
    1. sales_cash (销售商品收到的现金)
    2. tax_refund (收到的税费返还)
    3. purchase_cash (购买商品支付的现金)
    4. employee_cost (支付给职工的现金)
    5. tax_paid (支付的各项税费)
    6. ocf (经营活动现金流净额)
    7. icf (投资活动现金流净额)
    8. fcf (筹资活动现金流净额)

模型 / Model:
    RandomForestClassifier, 80/20 train-test split
    输出分类报告、特征重要性、混淆矩阵 / Classification report, feature importance, confusion matrix
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib
import glob
import os
import re
import warnings
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score

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
# 1. 特征提取 / Feature Extraction
# ============================================================

# 需要提取的现金流行项 / Cash flow line items to extract
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
    """
    从现金流量表CSV中提取特征 / Extract features from cash flow CSVs
    Returns DataFrame with one row per company
    """
    files = glob.glob(os.path.join(csv_dir, '*现金流量表*.csv'))
    records = []

    for f in files:
        parts = os.path.basename(f).replace('.csv', '').split('_')
        if len(parts) < 4:
            continue
        stock_code = parts[0]
        company_name = parts[1]

        try:
            df = pd.read_csv(f, encoding='utf-8-sig')
        except Exception:
            continue

        cols = df.columns.tolist()
        if len(cols) < 2:
            continue

        item_col = cols[0]
        val_col = cols[1]

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
print("NEEQ 财务健康度 ML 分类 / Financial Health ML Classification")
print("=" * 60)

print("\n[1/5] 提取特征 / Extracting features...")
raw_df = extract_features(CSV_DIR)
print(f"  原始企业数 / Raw companies: {len(raw_df)}")

# 过滤掉缺失关键特征的公司 / Drop companies missing key features
required = ['ocf', 'net_cash_increase']
df = raw_df.dropna(subset=required).copy()
print(f"  有效企业数 / Valid companies: {len(df)}")

# 填充其余特征的缺失值 / Fill remaining NaN with 0
feature_cols = list(FEATURE_ITEMS.keys())
for col in feature_cols:
    if col in df.columns:
        df[col] = df[col].fillna(0)

# ============================================================
# 2. 构建标签 / Build Labels
# ============================================================

print("\n[2/5] 构建标签 / Building labels...")
df['healthy'] = ((df['ocf'] > 0) & (df['net_cash_increase'] > 0)).astype(int)
healthy_count = df['healthy'].sum()
unhealthy_count = len(df) - healthy_count
print(f"  健康 Healthy (1): {healthy_count} ({healthy_count/len(df)*100:.1f}%)")
print(f"  不健康 Unhealthy (0): {unhealthy_count} ({unhealthy_count/len(df)*100:.1f}%)")

# ============================================================
# 3. 准备训练数据 / Prepare Training Data
# ============================================================

print("\n[3/5] 准备训练数据 / Preparing training data...")

# 使用ocf以外的特征来预测 / Use features other than ocf directly
# (因为ocf是标签的组成部分，用它做特征会数据泄露)
# (ocf is part of the label, using it as feature = data leakage)
feature_cols_model = ['sales_cash', 'tax_refund', 'purchase_cash',
                      'employee_cost', 'tax_paid', 'icf', 'fcf']
X = df[feature_cols_model].values
y = df['healthy'].values

# 标准化 / Standardise
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)

X_train, X_test, y_train, y_test = train_test_split(
    X_scaled, y, test_size=0.2, random_state=42, stratify=y
)
print(f"  训练集 / Train: {len(X_train)} 样本 / samples")
print(f"  测试集 / Test: {len(X_test)} 样本 / samples")

# ============================================================
# 4. 训练与评估 / Train & Evaluate
# ============================================================

print("\n[4/5] 训练随机森林 / Training Random Forest...")
clf = RandomForestClassifier(n_estimators=100, random_state=42, max_depth=5)
clf.fit(X_train, y_train)

y_pred = clf.predict(X_test)
accuracy = accuracy_score(y_test, y_pred)

print(f"\n  准确率 / Accuracy: {accuracy:.4f}")
print(f"\n  分类报告 / Classification Report:")
print(classification_report(y_test, y_pred, target_names=['不健康 Unhealthy', '健康 Healthy']))

# 特征重要性 / Feature Importance
importances = clf.feature_importances_
indices = np.argsort(importances)[::-1]
print("  特征重要性 / Feature Importance:")
for i, idx in enumerate(indices):
    print(f"    {i+1}. {feature_cols_model[idx]}: {importances[idx]:.4f}")

# 混淆矩阵 / Confusion Matrix
cm = confusion_matrix(y_test, y_pred)
print(f"\n  混淆矩阵 / Confusion Matrix:")
print(f"    TN={cm[0,0]}, FP={cm[0,1]}")
print(f"    FN={cm[1,0]}, TP={cm[1,1]}")

# ============================================================
# 5. 可视化 / Visualisation
# ============================================================

print("\n[5/5] 生成图表 / Generating charts...")

fig, axes = plt.subplots(1, 2, figsize=(14, 5))

# 图1: 特征重要性 / Feature Importance
ax1 = axes[0]
sorted_names = [feature_cols_model[i] for i in indices]
colors = plt.cm.viridis(np.linspace(0.2, 0.8, len(indices)))
bars = ax1.barh(range(len(indices)), importances[indices], color=colors, edgecolor='white')
ax1.set_yticks(range(len(indices)))
ax1.set_yticklabels(sorted_names, fontsize=9)
ax1.invert_yaxis()
ax1.set_xlabel('重要性 / Importance', fontsize=10)
ax1.set_title('随机森林特征重要性\nRandom Forest Feature Importance', fontsize=12, fontweight='bold')
for bar, val in zip(bars, importances[indices]):
    ax1.text(bar.get_width() + 0.005, bar.get_y() + bar.get_height()/2,
             f'{val:.3f}', va='center', fontsize=9)

# 图2: 混淆矩阵热力图 / Confusion Matrix Heatmap
ax2 = axes[1]
im = ax2.imshow(cm, interpolation='nearest', cmap=plt.cm.Blues)
ax2.set_title('混淆矩阵\nConfusion Matrix', fontsize=12, fontweight='bold')
tick_marks = [0, 1]
ax2.set_xticks(tick_marks)
ax2.set_xticklabels(['不健康\nUnhealthy', '健康\nHealthy'], fontsize=9)
ax2.set_yticks(tick_marks)
ax2.set_yticklabels(['不健康\nUnhealthy', '健康\nHealthy'], fontsize=9)
ax2.set_ylabel('真实标签 / True Label', fontsize=10)
ax2.set_xlabel('预测标签 / Predicted Label', fontsize=10)
for i in range(2):
    for j in range(2):
        ax2.text(j, i, str(cm[i, j]), ha='center', va='center',
                 fontsize=16, fontweight='bold',
                 color='white' if cm[i, j] > cm.max()/2 else 'black')

plt.tight_layout()
plt.savefig(os.path.join(OUTPUT_DIR, 'ml_classification.png'), dpi=150, bbox_inches='tight')
print(f"  图表已保存 / Chart saved: output/analysis/ml_classification.png")

# 保存预测结果 / Save predictions
df['predicted_healthy'] = clf.predict(X_scaled)
df['prediction_proba'] = clf.predict_proba(X_scaled)[:, 1]
output_csv = os.path.join(OUTPUT_DIR, 'ml_predictions.csv')
df[['stock_code', 'company_name', 'ocf', 'net_cash_increase',
    'healthy', 'predicted_healthy', 'prediction_proba']].to_csv(
    output_csv, index=False, encoding='utf-8-sig')
print(f"  预测结果已保存 / Predictions saved: output/analysis/ml_predictions.csv")

print("\n" + "=" * 60)
print("ML 分析完成 / ML Analysis Complete")
print(f"模型准确率 / Model Accuracy: {accuracy:.2%}")
print(f"样本量 / Sample size: {len(df)} companies")
print("=" * 60)
