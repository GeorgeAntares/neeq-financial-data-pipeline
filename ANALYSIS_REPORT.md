# NEEQ 年报分析报告 / NEEQ Annual-Report Analysis

样本是新解析器导出的约 255 套 CSV（`output/analysis/_csv_255`），一家一年一行。只读每个文件的第一张合并报表；后半段母公司表或其它年份表不参与。营收低于 10 万元的行丢掉（附注编号常会进金额列）。

This note uses the ~255-statement CSV set from the current parser. Each file contributes only its first consolidated block. Rows with revenue below 100,000 CNY are dropped.

复现：

```bash
python company_metrics.py --csv-dir output/analysis/_csv_255
python industry_portrait.py --metrics output/analysis/company_metrics.csv --pdf-dir output/pdf
python dupont_pca.py --metrics output/analysis/company_metrics.csv
python cash_gap_model.py --metrics output/analysis/company_metrics.csv --pdf-dir output/pdf
```

科目公式见 [`company_metrics_dictionary.md`](company_metrics_dictionary.md)。分节底稿：[`industry_portrait.md`](industry_portrait.md)、[`dupont_pca.md`](dupont_pca.md)、[`cash_gap_model.md`](cash_gap_model.md)。

---

## 1. 数据与清洗 / Data and cleaning

| 口径 | 数量 |
|------|------|
| 新解析器 CSV 套数 | ~255（三大表合计 727 个文件） |
| 有效营收（≥10 万元） | **195** 家，均为 2025 年报 |
| 净利润可取 | 125 / 195（64%） |
| 经营现金流可取 | 154 / 195 |
| 杜邦三项齐全 | 104 |
| 同时有净利润和 OCF | 109 |

净利润覆盖低于营收，是因为不少利润表第一张表在「净利润」行之前被截断。缺失记为 NaN，不用母公司净利润去补合并营收。

清洗：

- 成本优先「营业成本」（含标准格式里的「其中：营业成本」），没有时才用含期间费用的「营业总成本」
- 权益优先「所有者权益合计」，不用「负债和所有者权益」
- 比率主列保留原始值，`*_w` 为样本 1% / 99% 分位截尾

有效营收 195 家的中位数：营收 1.64 亿元，毛利率 25.7%，净利率 1.5%，OCF/收入 7.4%，应收/收入 31.7%，存货/收入 22.9%，流动比率 1.50，资产负债率 52.1%。

PDF 集合里可能混入非新三板代码（例如创业板）。本报告不按板块再筛。

---

## 2. 指标定义 / Metric definitions

杜邦：ROE = 净利润 / 平均权益 = 净利率 × 总资产周转 × 权益乘数。

资产和权益用期初期末平均；缺期初时用期末。同比为 \((\text{本期}-\text{上期})/|\text{上期}|\)。营运资本强度为应收/收入 + 存货/收入。

完整列名、科目命中规则和截尾约定见数据字典，不在这里重复。

---

## 3. 行业画像 / Industry portraits

行业来自本地 `output/pdf/` 证监会门类文件夹，合并为 **制造 / 软件信息 / 其他**。`00_待分类` 和 PDF 根目录归入其他。

| 行业 | 家数 | 有净利润且有 OCF | 营收中位数 | 毛利率 | 净利率 | 应收/收入 | 存货/收入 | 营运资本/收入 |
|------|------|------------------|------------|--------|--------|-----------|-----------|---------------|
| 制造 | 90 | 47 | 2.55 亿 | 26.0% | 4.4% | 29.3% | 25.6% | 55.4% |
| 软件信息 | 26 | 15 | 1.03 亿 | 30.6% | −0.8% | 49.1% | 22.3% | 85.0% |
| 其他 | 79 | 47 | 1.28 亿 | 23.3% | −0.2% | 38.0% | 21.1% | 66.5% |

「利润为正且 OCF 为负」在同时有两科目的公司中：制造 8.5%，软件 0%，其他 17.0%。软件利润为正的只有 40%，这个缺口标签更少出现。软件 |OCF 同比| 中位数 86.6%，制造 47.9%。

读数：软件应收更重，更像项目制回款；制造存货只略高。软件毛利率更高、经营现金更跳，净利率中位数为负。图：`output/analysis/industry_portrait.png`、`industry_cash_gap.png`。

---

## 4. 杜邦与主成分 / DuPont and PCA

104 家杜邦三项齐全时，净利率 × 周转 × 权益乘数与 ROE 的最大差距为 3.6×10⁻¹⁵，恒等式成立。

ROE 与三个因子的 Spearman：净利率 0.72，周转 0.27，权益乘数 −0.39。利润、周转、杠杆均为正的 60 家里，Var(log 净利率) / Var(log ROE) 为 109%——净利率比 ROE 更散，周转和杠杆在对冲。存货/收入与 ROE 的 Spearman 为 −0.50。

PCA 用 numpy SVD（列标准化，不用 scikit-learn），111 家完整个案，8 个截尾指标：

| 成分 | 解释比例 | 累计 | 含义 |
|------|----------|------|------|
| PC1 | 34.4% | 34.4% | 规模（log 营收、log 资产；小公司杠杆更高） |
| PC2 | 20.0% | 54.4% | 杠杆（流动比率 vs 资产负债率 / 权益乘数） |
| PC3 | 14.0% | 68.4% | 现金（OCF/收入） |

图：`output/analysis/dupont_pca.png`。

---

## 5. 现金缺口分类 / Cash-gap classification

标签：净利润 > 0 **且** 经营现金流净额 < 0。109 家里 12 个正例（11%）。

特征：毛利率、周转、流动比率、资产负债率、权益乘数、应收/收入、存货/收入、收入同比、log 营收、行业哑变量。训练折内中位数填补。**不放** OCF 分项、OCF/收入、净利率、ROE。

模型：随机森林（100 棵、`max_depth=5`、`class_weight=balanced`）对照 L2 逻辑回归。分层 5 折折外 ROC / PR。

| 模型 | ROC-AUC | PR-AUC | 召回 |
|------|---------|--------|------|
| 逻辑回归 | 0.52 ± 0.11 | 0.19 ± 0.09 | 0.23 |
| 随机森林 | 0.31 ± 0.12 | 0.11 ± 0.02 | 0 |

PR 无信息基线是 11%。逻辑回归只略高一点。随机森林在 0.5 阈值下折外没有正预测，ROC 低于 0.5，当作小样本噪声。不把标签两半喂进特征之后，浅层资产负债比率分不开这个缺口。

逻辑回归里软件哑变量为负（这类公司几乎没有「赚钱却没经营现金」），应收/收入为正（应收占款更像缺口）。SHAP 全样本再拟合只看方向，不替代折外评价。图：`output/analysis/cash_gap_roc.png`、`cash_gap_shap.png`。

旧脚本 `ml_financial_health.py` / `ml_evaluation.py` / `shap_analysis.py` / `dl_financial_health.py` 仍用「OCF>0 且现金净增加>0」和现金流科目，542 家 5 折 ROC-AUC 约 0.62。当作对照实验，不是本报告的封面结论，也不是信用评级。MLP 只作附录。

---

## 6. 局限 / Limits

- 单期年报加表内上期列，不是多年面板。
- 制造 90 家、软件 26 家，「其他」混了待分类和若干小行业。
- 没有违约或 ST 标签；现金缺口只是利润和经营现金的符号组合。
- 净利润、OCF 覆盖低于营收；PCA 和分类用的是更小的完整个案。
- 正例 12 个，5 折每折只有两三个正例，AUC 标准差大。
- 行业来自本地 PDF 文件夹；解析截断造成的缺失没有用后一张表补。

这些约束下，站得住的是：指标有定义、杜邦恒等式对得上、行业画像和主成分能描述规模 / 杠杆 / 现金，以及「不用 OCF 预测 OCF 符号」时分类几乎没有信号。
