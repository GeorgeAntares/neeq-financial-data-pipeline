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
from sklearn.model_selection import train_test_split, cross_val_predict
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score

from cashflow_features import FEATURE_COLS_MODEL, labeled_cashflow_frame

warnings.filterwarnings('ignore')

# ============================================================
# 配置 / Configuration
# ============================================================

matplotlib.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
matplotlib.rcParams['axes.unicode_minus'] = False

CSV_DIR = os.path.join(os.path.dirname(__file__), 'output', 'csv')
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), 'output', 'analysis')


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print("=" * 60)
    print("NEEQ 财务健康度 ML 分类 / Financial Health ML Classification")
    print("=" * 60)

    print("\n[1/5] 提取特征 / Extracting features...")
    df = labeled_cashflow_frame(CSV_DIR)
    print(f"  有效企业数 / Valid companies: {len(df)}")

    print("\n[2/5] 构建标签 / Building labels...")
    healthy_count = int(df['healthy'].sum())
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
    feature_cols_model = FEATURE_COLS_MODEL
    X = df[feature_cols_model].values
    y = df['healthy'].values

    # 标准化 / Standardise
    # 仅在训练集上 fit，避免测试集信息渗入（标准化泄漏）
    X_train_raw, X_test_raw, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    scaler = StandardScaler()
    X_train = scaler.fit_transform(X_train_raw)
    X_test = scaler.transform(X_test_raw)

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
    # 用交叉验证获取"样本外"预测：clf 已见过全部训练数据，
    # 若直接对全量数据 predict，输出的会是训练集上的拟合值（乐观偏差），
    # 不能反映模型的真实判别能力。cross_val_predict 保证每行的预测都
    # 来自没见过该行的模型。
    X_all_scaled = scaler.transform(X)
    cv_pred = cross_val_predict(
        RandomForestClassifier(n_estimators=100, random_state=42, max_depth=5),
        X_all_scaled,
        y,
        cv=5,
        method='predict',
    )
    cv_proba = cross_val_predict(
        RandomForestClassifier(n_estimators=100, random_state=42, max_depth=5),
        X_all_scaled,
        y,
        cv=5,
        method='predict_proba',
    )[:, 1]

    df['predicted_healthy'] = cv_pred
    df['prediction_proba'] = cv_proba
    cv_accuracy = accuracy_score(y, cv_pred)
    print(f"  交叉验证准确率 / Cross-validated accuracy: {cv_accuracy:.4f}")

    output_csv = os.path.join(OUTPUT_DIR, 'ml_predictions.csv')
    df[['stock_code', 'company_name', 'ocf', 'net_cash_increase',
        'healthy', 'predicted_healthy', 'prediction_proba']].to_csv(
        output_csv, index=False, encoding='utf-8-sig')
    print(f"  预测结果已保存 / Predictions saved: output/analysis/ml_predictions.csv")

    print("\n" + "=" * 60)
    print("ML 分析完成 / ML Analysis Complete")
    print(f"模型准确率（留出测试集）/ Hold-out accuracy: {accuracy:.2%}")
    print(f"交叉验证准确率 / Cross-validated accuracy: {cv_accuracy:.2%}")
    print(f"样本量 / Sample size: {len(df)} companies")
    print("=" * 60)


if __name__ == "__main__":
    main()
