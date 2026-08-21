# NEEQ 财报数据分析报告 / NEEQ Financial Data Analysis Report

> 新三板企业财务数据自动化采集与分析项目
> Automated Financial Data Collection and Analysis Pipeline for NEEQ-listed Companies

---

## 项目概述 / Project Overview

本项目实现了一套完整的财报数据采集与分析 pipeline，涵盖从数据采集、PDF 解析、结构化提取到统计分析与可视化的全流程。

This project implements a complete financial data collection and analysis pipeline, covering the full workflow from data acquisition, PDF parsing, structured extraction to statistical analysis and visualization.

## 技术架构 / Tech Stack

| 层级 Layer | 技术 Technology | 用途 Purpose |
|-----------|----------------|-------------|
| 数据采集 Data Collection | requests, NEEQ API, CNInfo API | 自动检索下载年报 PDF / Auto-retrieve annual report PDFs |
| PDF 解析 PDF Parsing | pdfplumber, PyMuPDF | 非结构化 PDF → 结构化表格 / Unstructured PDF → structured tables |
| 数据存储 Data Storage | SQLite, CSV | 采集状态管理 + 数据导出 / Crawl state management + data export |
| 数据分析 Data Analysis | pandas, numpy | 财务指标计算 / Financial metric computation |
| 数据可视化 Visualization | matplotlib | 图表生成 / Chart generation |

## 数据规模 / Data Scale

| 指标 Metric | 数值 Value |
|------------|-----------|
| 采集 PDF 数量 PDFs Downloaded | 883 |
| 结构化 CSV 数量 CSVs Generated | 1,547 |
| 资产负债表 Balance Sheets | 687 |
| 利润表 Income Statements | 100 |
| 现金流量表 Cash Flow Statements | 759 |

## 分析模块 / Analysis Modules

### 1. 营收分析 / Revenue Analysis
- 营收分布统计（均值、中位数、标准差）
- 营收区间分布（<1000万 / 1000万-5000万 / 5000万-1亿 / 1-5亿 / 5-10亿 / >10亿）
- 营收 Top 20 企业排名

### 2. 盈利能力分析 / Profitability Analysis
- 毛利率计算（营收 - 营业成本）
- 盈亏企业比例
- 毛利率分布（<0% / 0-10% / 10-20% / 20-30% / 30-50% / >50%）

### 3. 现金流分析 / Cash Flow Analysis
- 经营活动现金流净额统计
- 正/负现金流企业比例
- 现金流分布

### 4. 可视化 / Visualization
- 营收分布直方图（对数刻度）
- 毛利率分布直方图
- 营收 Top 15 企业横向条形图
- 经营现金流正负对比图

## 运行方式 / How to Run

```bash
# 安装依赖 Install dependencies
pip install pandas numpy matplotlib

# 运行分析 Run analysis
python financial_analysis.py
```

输出文件 / Output files:
- `output/analysis/financial_analysis.png` — 四合一分析图表
- `output/analysis/summary_statistics.csv` — 汇总统计表

## 数据流程 / Data Pipeline

```
NEEQ / CNInfo API
       │
       ▼
  PDF 下载 Download (883 files)
       │
       ▼
  PDF 解析 Parse (pdfplumber + PyMuPDF)
       │
       ▼
  结构化 CSV Extract (1,547 files)
       │
       ▼
  pandas 数据清洗 Clean & Normalize
       │
       ▼
  统计分析 Analyze (营收/毛利率/现金流)
       │
       ▼
  matplotlib 可视化 Visualize
```

## 项目亮点 / Key Highlights

- **端到端自动化**：从 API 检索到 PDF 下载、解析、结构化、分析的全自动流程
- **双引擎 PDF 解析**：pdfplumber 主引擎 + PyMuPDF 兜底，提升解析覆盖率
- **状态管理**：SQLite 追踪每份报告的采集状态，支持断点续传
- **大规模数据**：已处理 800+ 份年报，生成 1,500+ 份结构化数据文件
- **领域知识结合**：结合会计学和财务管理课程基础，实现财务三表标准化提取
