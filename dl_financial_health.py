"""
NEEQ 企业财务健康度深度学习分类 / NEEQ Financial Health DL Classification
==========================================================================
使用 PyTorch 构建多层感知机（MLP）对企业财务健康度进行二分类预测，
与 scikit-learn 随机森林结果对比，展示从传统ML到DL的进阶。
Builds a Multi-Layer Perceptron (MLP) with PyTorch for binary classification
of company financial health, compared against the Random Forest baseline.

模型结构 / Model Architecture:
    Input(7) → Linear(64) → BatchNorm → ReLU → Dropout(0.3)
             → Linear(32) → BatchNorm → ReLU → Dropout(0.3)
             → Linear(1) → Sigmoid

训练 / Training:
    Loss: BCELoss
    Optimizer: Adam, lr=0.001
    Epochs: 200, batch_size=32
    Early stopping: patience=20
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib
import glob
import os
import sys
import warnings

# PyTorch 安装在 C:\torch（绕过 Windows 路径长度限制）
# PyTorch installed at C:\torch (bypassing Windows path length limit)
_torch_path = r'C:\torch'
if _torch_path not in sys.path:
    sys.path.insert(0, _torch_path)

from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score, roc_curve, auc
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset

warnings.filterwarnings('ignore')

# ============================================================
# 配置 / Configuration
# ============================================================

matplotlib.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
matplotlib.rcParams['axes.unicode_minus'] = False

CSV_DIR = os.path.join(os.path.dirname(__file__), 'output', 'csv')
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), 'output', 'analysis')
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 设备选择 / Device selection
DEVICE = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
print(f"设备 / Device: {DEVICE}")

# 随机种子 / Random seed
SEED = 42
torch.manual_seed(SEED)
np.random.seed(SEED)

# ============================================================
# 1. 特征提取 / Feature Extraction
# ============================================================

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
print("NEEQ 财务健康度 DL 分类 / Financial Health DL Classification")
print("=" * 60)

print("\n[1/6] 提取特征 / Extracting features...")
raw_df = extract_features(CSV_DIR)
print(f"  原始企业数 / Raw companies: {len(raw_df)}")

required = ['ocf', 'net_cash_increase']
df = raw_df.dropna(subset=required).copy()
print(f"  有效企业数 / Valid companies: {len(df)}")

feature_cols = list(FEATURE_ITEMS.keys())
for col in feature_cols:
    if col in df.columns:
        df[col] = df[col].fillna(0)

# ============================================================
# 2. 构建标签 / Build Labels
# ============================================================

print("\n[2/6] 构建标签 / Building labels...")
df['healthy'] = ((df['ocf'] > 0) & (df['net_cash_increase'] > 0)).astype(int)
healthy_count = df['healthy'].sum()
unhealthy_count = len(df) - healthy_count
print(f"  健康 Healthy (1): {healthy_count} ({healthy_count/len(df)*100:.1f}%)")
print(f"  不健康 Unhealthy (0): {unhealthy_count} ({unhealthy_count/len(df)*100:.1f}%)")

# ============================================================
# 3. 准备训练数据 / Prepare Training Data
# ============================================================

print("\n[3/6] 准备训练数据 / Preparing training data...")

# 排除ocf（标签组成部分，防数据泄露）/ Exclude ocf (part of label, prevent leakage)
feature_cols_model = ['sales_cash', 'tax_refund', 'purchase_cash',
                      'employee_cost', 'tax_paid', 'icf', 'fcf']
X = df[feature_cols_model].values
y = df['healthy'].values

scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)

X_train, X_test, y_train, y_test = train_test_split(
    X_scaled, y, test_size=0.2, random_state=SEED, stratify=y
)

# 转为 PyTorch 张量 / Convert to PyTorch tensors
X_train_tensor = torch.FloatTensor(X_train).to(DEVICE)
y_train_tensor = torch.FloatTensor(y_train).to(DEVICE)
X_test_tensor = torch.FloatTensor(X_test).to(DEVICE)
y_test_tensor = torch.FloatTensor(y_test).to(DEVICE)

train_dataset = TensorDataset(X_train_tensor, y_train_tensor)
train_loader = DataLoader(train_dataset, batch_size=32, shuffle=True)

print(f"  训练集 / Train: {len(X_train)} samples")
print(f"  测试集 / Test: {len(X_test)} samples")

# ============================================================
# 4. 构建MLP模型 / Build MLP Model
# ============================================================

print("\n[4/6] 构建MLP模型 / Building MLP model...")


class FinancialHealthMLP(nn.Module):
    """
    多层感知机用于财务健康度分类
    Multi-Layer Perceptron for financial health classification
    """

    def __init__(self, input_dim=7, hidden1=64, hidden2=32, dropout=0.3):
        super().__init__()
        self.fc1 = nn.Linear(input_dim, hidden1)
        self.bn1 = nn.BatchNorm1d(hidden1)
        self.relu1 = nn.ReLU()
        self.drop1 = nn.Dropout(dropout)

        self.fc2 = nn.Linear(hidden1, hidden2)
        self.bn2 = nn.BatchNorm1d(hidden2)
        self.relu2 = nn.ReLU()
        self.drop2 = nn.Dropout(dropout)

        self.fc3 = nn.Linear(hidden2, 1)
        self.sigmoid = nn.Sigmoid()

    def forward(self, x):
        x = self.drop1(self.relu1(self.bn1(self.fc1(x))))
        x = self.drop2(self.relu2(self.bn2(self.fc2(x))))
        x = self.sigmoid(self.fc3(x))
        return x.squeeze()


model = FinancialHealthMLP(input_dim=7).to(DEVICE)
criterion = nn.BCELoss()
optimizer = optim.Adam(model.parameters(), lr=0.001)

total_params = sum(p.numel() for p in model.parameters())
print(f"  模型参数量 / Parameters: {total_params}")
print(f"  架构 / Architecture: 7→64→32→1 (BatchNorm+ReLU+Dropout)")

# ============================================================
# 5. 训练 / Training
# ============================================================

print("\n[5/6] 训练模型 / Training model...")

num_epochs = 200
patience = 20
best_loss = float('inf')
patience_counter = 0
train_losses = []
val_losses = []

for epoch in range(num_epochs):
    model.train()
    epoch_loss = 0
    for batch_X, batch_y in train_loader:
        optimizer.zero_grad()
        outputs = model(batch_X)
        loss = criterion(outputs, batch_y)
        loss.backward()
        optimizer.step()
        epoch_loss += loss.item()

    avg_train_loss = epoch_loss / len(train_loader)
    train_losses.append(avg_train_loss)

    model.eval()
    with torch.no_grad():
        val_outputs = model(X_test_tensor)
        val_loss = criterion(val_outputs, y_test_tensor).item()
        val_losses.append(val_loss)

    if val_loss < best_loss:
        best_loss = val_loss
        patience_counter = 0
        best_model_state = model.state_dict()
    else:
        patience_counter += 1

    if (epoch + 1) % 20 == 0:
        print(f"  Epoch {epoch+1}/{num_epochs} | "
              f"Train Loss: {avg_train_loss:.4f} | Val Loss: {val_loss:.4f}")

    if patience_counter >= patience:
        print(f"  Early stopping at epoch {epoch+1} (patience={patience})")
        break

model.load_state_dict(best_model_state)

# ============================================================
# 6. 评估与可视化 / Evaluation & Visualisation
# ============================================================

print("\n[6/6] 评估模型 / Evaluating model...")

model.eval()
with torch.no_grad():
    y_prob = model(X_test_tensor).cpu().numpy()
    y_pred = (y_prob >= 0.5).astype(int)

accuracy = accuracy_score(y_test, y_pred)
print(f"\n  准确率 / Accuracy: {accuracy:.4f}")
print(f"\n  分类报告 / Classification Report:")
print(classification_report(y_test, y_pred, target_names=['不健康 Unhealthy', '健康 Healthy']))

cm = confusion_matrix(y_test, y_pred)
print(f"\n  混淆矩阵 / Confusion Matrix:")
print(f"    TN={cm[0,0]}, FP={cm[0,1]}")
print(f"    FN={cm[1,0]}, TP={cm[1,1]}")

# ROC曲线 / ROC Curve
fpr, tpr, _ = roc_curve(y_test, y_prob)
roc_auc = auc(fpr, tpr)
print(f"  AUC: {roc_auc:.4f}")

# 可视化 / Visualisation
fig, axes = plt.subplots(1, 3, figsize=(18, 5))

# 图1: 训练损失曲线 / Training Loss Curve
ax1 = axes[0]
ax1.plot(train_losses, label='训练损失 / Train Loss', color='#2196F3', linewidth=1.5)
ax1.plot(val_losses, label='验证损失 / Val Loss', color='#FF5722', linewidth=1.5)
ax1.set_xlabel('Epoch', fontsize=10)
ax1.set_ylabel('Loss (BCE)', fontsize=10)
ax1.set_title('训练损失曲线\nTraining Loss Curve', fontsize=12, fontweight='bold')
ax1.legend(fontsize=9)
ax1.grid(True, alpha=0.3)

# 图2: 混淆矩阵 / Confusion Matrix
ax2 = axes[1]
im = ax2.imshow(cm, interpolation='nearest', cmap=plt.cm.Blues)
ax2.set_title('混淆矩阵\nConfusion Matrix (MLP)', fontsize=12, fontweight='bold')
ax2.set_xticks([0, 1])
ax2.set_xticklabels(['不健康\nUnhealthy', '健康\nHealthy'], fontsize=9)
ax2.set_yticks([0, 1])
ax2.set_yticklabels(['不健康\nUnhealthy', '健康\nHealthy'], fontsize=9)
ax2.set_ylabel('真实标签 / True Label', fontsize=10)
ax2.set_xlabel('预测标签 / Predicted Label', fontsize=10)
for i in range(2):
    for j in range(2):
        ax2.text(j, i, str(cm[i, j]), ha='center', va='center',
                 fontsize=16, fontweight='bold',
                 color='white' if cm[i, j] > cm.max()/2 else 'black')

# 图3: ROC曲线 / ROC Curve
ax3 = axes[2]
ax3.plot(fpr, tpr, color='#4CAF50', linewidth=2, label=f'MLP (AUC = {roc_auc:.3f})')
ax3.plot([0, 1], [0, 1], 'k--', alpha=0.3, label='Random (AUC = 0.5)')
ax3.set_xlabel('假阳性率 / False Positive Rate', fontsize=10)
ax3.set_ylabel('真阳性率 / True Positive Rate', fontsize=10)
ax3.set_title('ROC 曲线\nROC Curve', fontsize=12, fontweight='bold')
ax3.legend(fontsize=9, loc='lower right')
ax3.grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig(os.path.join(OUTPUT_DIR, 'dl_classification.png'), dpi=150, bbox_inches='tight')
print(f"\n  图表已保存 / Chart saved: output/analysis/dl_classification.png")

# 保存预测结果 / Save predictions
with torch.no_grad():
    all_prob = model(torch.FloatTensor(X_scaled).to(DEVICE)).cpu().numpy()
    all_pred = (all_prob >= 0.5).astype(int)

df['dl_predicted'] = all_pred
df['dl_probability'] = all_prob
output_csv = os.path.join(OUTPUT_DIR, 'dl_predictions.csv')
df[['stock_code', 'company_name', 'ocf', 'net_cash_increase',
    'healthy', 'dl_predicted', 'dl_probability']].to_csv(
    output_csv, index=False, encoding='utf-8-sig')
print(f"  预测结果已保存 / Predictions saved: output/analysis/dl_predictions.csv")

# ============================================================
# 对比汇总 / Comparison Summary
# ============================================================

print("\n" + "=" * 60)
print("DL 分析完成 / DL Analysis Complete")
print("=" * 60)
print(f"模型 / Model: PyTorch MLP (7→64→32→1)")
print(f"参数量 / Parameters: {total_params}")
print(f"准确率 / Accuracy: {accuracy:.2%}")
print(f"AUC: {roc_auc:.4f}")
print(f"样本量 / Sample size: {len(df)} companies")
print("=" * 60)
print("\n与 scikit-learn 随机森林对比 / vs scikit-learn Random Forest:")
print(f"  Random Forest Accuracy: 57.8% (100 trees)")
print(f"  MLP Accuracy:          {accuracy:.1%} (PyTorch)")
print("  注: 样本量542偏小，DL优势未充分发挥 / Note: small sample size limits DL advantage")
