<p align="center">
  <img src="https://img.shields.io/badge/Python-3.9+-blue?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey" alt="Platform">
  <img src="https://img.shields.io/badge/License-MIT-green" alt="License">
</p>

<h1 align="center">📊 NEEQ 上市公司财报数据采集与分析 / NEEQ Listed Company Financial Report Data Collection & Analysis</h1>

<p align="center">从新三板与巨潮资讯网抓取年报 PDF，三级引擎解析三大财务报表，导出结构化 CSV 并进行统计分析与可视化<br>Fetch annual report PDFs from NEEQ & CNINFO, parse three major financial statements via a three-tier engine, export structured CSV, and perform statistical analysis & visualisation</p>

---

## 📑 目录 / Table of Contents

- [功能特性 / Features](#-功能特性--features)
- [环境要求 / Requirements](#-环境要求--requirements)
- [快速开始 / Quick Start](#-快速开始--quick-start)
- [命令行参数 / CLI Arguments](#-命令行参数--cli-arguments)
- [数据分析 / Data Analysis](#-数据分析--data-analysis)
- [输出文件 / Output Files](#-输出文件--output-files)
- [项目结构 / Project Structure](#-项目结构--project-structure)
- [CSV 可视化 / CSV Visualisation](#-csv-可视化--csv-visualisation)
- [技术架构 / Technical Architecture](#-技术架构--technical-architecture)
- [数据源 / Data Sources](#-数据源--data-sources)
- [已知局限 / Known Limitations](#-已知局限--known-limitations)
- [适用场景 / Use Cases](#-适用场景--use-cases)

---

## ✨ 功能特性 / Features

- 🔍 搜索新三板与巨潮资讯网的年报公告 / Search annual report announcements on NEEQ & CNINFO
- 📥 自动下载年报 PDF，支持断点续爬 / Auto-download PDFs with resume support
- ⚡ 三级引擎解析财务表格（pdfplumber → PyMuPDF → RapidOCR OCR 回退）/ Three-tier parsing engine (pdfplumber → PyMuPDF → RapidOCR OCR fallback)
- 📋 导出标准格式的 CSV 财务数据（三大报表）/ Export standardised CSV for three major financial statements
- 📊 营收分析、盈利能力分析、现金流分析、统计可视化 / Revenue analysis, profitability analysis, cash flow analysis, statistical visualisation
- 🤖 机器学习财务健康度分类（随机森林，542家企业，7维特征）/ ML financial health classification (Random Forest, 542 companies, 7 features)
- ⏸️ 支持纯下载模式、优雅停止、备份 PDF 批量重解析 / Download-only mode, graceful stop, batch re-parse for backup PDFs

---

## 🔧 环境要求 / Requirements

| 依赖 / Dependency | 版本 / Version |
|------|------|
| Python | 3.9 及以上 / 3.9+ |
| 操作系统 / OS | Windows / macOS / Linux |

```bash
# 克隆项目 / Clone the repository
git clone https://github.com/GeorgeAntares/neeq-financial-crawler.git
cd neeq-financial-crawler

# 安装依赖 / Install dependencies
pip install -r requirements.txt
```

---

## 🚀 快速开始 / Quick Start

### ① 搜索年报并下载 PDF / Search & Download Annual Reports

```bash
# 按公告发布日期查询并下载，不解析 CSV / Query by announcement date, skip CSV parsing
python main.py --source neeq --start-date 2025-01-01 --end-date 2025-12-31 --skip-parse

# 仅查询公告并写入 SQLite，不下载 PDF / Query announcements into SQLite only, skip download
python main.py --source neeq --year 2025 --skip-download
```

### ② 续爬模式 / Resume Mode

再次执行相同命令时，程序根据 `output/crawl_state.db` 自动跳过已下载 PDF。
Re-running the same command auto-skips already-downloaded PDFs based on `output/crawl_state.db`.

`--resume` 只用于将旧版公告列表 CSV 导入 SQLite：
`--resume` is only used to import legacy announcement CSV lists into SQLite:

```bash
python main.py --source neeq --resume
```

### ③ 纯下载模式 / Download-Only Mode

只下载 PDF，跳过解析（速度提升 25~30 倍）：
Download PDFs only, skip parsing (25-30x faster):

```bash
python main.py --source neeq --year 2025 --skip-parse
```

### ④ 批量重解析备份 PDF / Batch Re-parse Backup PDFs

```bash
python retry_backup_pdfs.py
```

### ⑤ 优雅停止 / Graceful Stop

在项目根目录创建 `STOP.txt`，爬虫将在当前公司处理完毕后自动退出：
Create `STOP.txt` in the project root; the crawler exits after finishing the current company:

```bash
# Windows PowerShell
New-Item STOP.txt

# macOS / Linux
touch STOP.txt
```

---

## 🗄️ SQLite 状态库设计 / SQLite State Database Design

项目使用 SQLite 替代页码爬取，通过日期范围查询 NEEQ 官方 API，彻底解决"新公告导致页码内容漂移"的问题。
The project uses SQLite instead of page-based crawling, querying the NEEQ API by date range, eliminating "page content drift caused by new announcements".

### 为什么选 SQLite / Why SQLite

| 对比维度 / Dimension | SQLite | MySQL / MongoDB |
|---------|--------|-----------------|
| 部署成本 / Deployment cost | **零依赖**，Python 标准库自带 / Zero dependency, built into Python | 需安装服务端、配置用户权限 / Requires server install & user config |
| 数据量级 / Data scale | 年报项目最多数万条，完全够用 / Tens of thousands of records, sufficient | 适合百万级以上 / For millions+ records |
| 项目可迁移性 / Portability | 单文件 `crawl_state.db`，复制即迁移 / Single file, copy to migrate | 需导出/导入数据库 / Requires export/import |
| 数据类型安全 / Type safety | `CHECK` 约束强制类型校验 / `CHECK` constraints enforce type validation | 依赖应用层或 Schema 定义 / Depends on app layer or schema |

### 数据表结构 / Table Schema

**`announcements`** — 公告与下载状态 / Announcement & Download Status

| 字段 / Field | 类型 / Type | 约束 / Constraint | 说明 / Description |
|------|------|------|------|
| `source` | TEXT | NOT NULL | 数据源（`neeq` / `cninfo`）/ Data source |
| `pdf_url` | TEXT | NOT NULL | PDF 下载链接 / PDF download URL |
| `company_code` | TEXT | | 公司代码 / Company code |
| `company_name` | TEXT | | 公司简称 / Company name |
| `publish_date` | TEXT | ISO 8601 格式 / ISO 8601 | 公告发布日期 / Announcement date |
| `title` | TEXT | | 公告标题 / Announcement title |
| `report_year` | INTEGER | `>= 1990` | 推断的财报所属年份 / Inferred report year |
| `status` | TEXT | CHECK IN (`pending`, `downloading`, `downloaded`, `failed`) | 下载状态 / Download status |
| `file_path` | TEXT | | 本地 PDF 路径 / Local PDF path |
| `file_size` | INTEGER | `>= 0` | 文件大小（字节）/ File size in bytes |
| `attempts` | INTEGER | `>= 0` | 重试次数 / Retry count |
| `error_message` | TEXT | | 失败原因 / Error message |
| `discovered_count` | INTEGER | `>= 0` | 累计发现次数 / Total discovery count |

> **唯一约束 / Unique Constraint**：`(source, pdf_url)` — 同一公告不会被重复记录 / The same announcement is never recorded twice

**`crawl_runs`** — 爬取运行记录 / Crawl Run Log

| 字段 / Field | 类型 / Type | 说明 / Description |
|------|------|------|
| `started_at` | TEXT | 运行开始时间 / Run start time |
| `finished_at` | TEXT | 运行结束时间 / Run end time |
| `status` | TEXT | `running` / `completed` / `failed` / `interrupted` |
| `total_discovered` | INTEGER | 本次发现公告数 / Announcements discovered this run |
| `total_downloaded` | INTEGER | 本次下载成功数 / PDFs downloaded this run |

### 下载状态机 / Download State Machine

```
pending  ──→  downloading  ──→  downloaded
  │                                │
  └──────────  failed  ←───────────┘
```

- 程序启动时自动执行 `recover_incomplete_downloads()`，将残留的 `downloading` 重置为 `pending`
  On startup, `recover_incomplete_downloads()` resets stale `downloading` entries to `pending`
- 再次运行相同命令时，已 `downloaded` 且 PDF 有效的记录会被自动跳过
  Re-running skips records already marked `downloaded` with valid PDFs
- 数据库启用 WAL 模式 + `busy_timeout=5000ms`，避免并发写入冲突
  Database uses WAL mode + `busy_timeout=5000ms` to avoid concurrent write conflicts

---

## 📋 命令行参数 / CLI Arguments

| 参数 / Argument | 说明 / Description | 默认值 / Default |
|------|------|--------|
| `--source` | 数据源：`cninfo`（巨潮资讯网）或 `neeq`（新三板）/ Data source: `cninfo` or `neeq` | `cninfo` |
| `--year` | 公告发布日期年份，不等同于财报所属年份 / Announcement year, not necessarily the report year | 去年 / Last year |
| `--start-date` | 公告起始日期 `YYYY-MM-DD` / Start date | 无 / None |
| `--end-date` | 公告截止日期 `YYYY-MM-DD` / End date | 无 / None |
| `--start-page` | 查询结果起始页，仅用于故障恢复 / Start page, for recovery only | `1` |
| `--max-pages` | 最大翻页数，`0` 表示不限 / Max pages, `0` = unlimited | `0` |
| `--resume` | 将旧公告 CSV 导入 SQLite 并续爬 / Import legacy CSV into SQLite & resume | 关闭 / Off |
| `--skip-parse` | 纯下载模式，只下载不解析 / Download only, skip parsing | 关闭 / Off |
| `--skip-download` | 仅搜索公告列表，不下载 / Search only, skip download | 关闭 / Off |

---

## 📊 数据分析 / Data Analysis

对已导出的 CSV 财务数据进行统计分析与可视化：
Perform statistical analysis and visualisation on exported CSV financial data:

```bash
python financial_analysis.py
```

### 分析模块 / Analysis Modules

| 模块 / Module | 内容 / Content |
|------|------|
| 数据加载 / Data Loading | 批量读取 CSV，解析公司代码、年份、报表项目 / Batch-read CSVs, parse company code, year, line items |
| 营收分析 / Revenue Analysis | 营收均值/中位数/分布区间、Top 20 企业排名 / Mean, median, distribution, Top 20 ranking |
| 盈利能力 / Profitability | 毛利率计算、盈亏企业占比、毛利率分布 / Gross margin, profit/loss ratio, margin distribution |
| 现金流分析 / Cash Flow Analysis | 经营活动现金流净额、正/负现金流企业占比 / Operating cash flow, positive/negative OCF ratio |
| 可视化 / Visualisation | 营收分布直方图、毛利率分布、Top 15 柱状图、现金流对比 / Revenue histogram, margin distribution, Top 15 bar chart, OCF comparison |
| 汇总统计 / Summary Statistics | 输出 `summary_statistics.csv` 关键指标汇总 / Export key metrics to `summary_statistics.csv` |

### 输出 / Output

```
output/analysis/
├── financial_analysis.png     ← 四合一可视化图表 / 4-in-1 visualisation chart
└── summary_statistics.csv     ← 关键指标汇总 / Key metrics summary
```

---

## 🤖 机器学习 / Machine Learning

基于现金流数据构建7维特征，使用随机森林对企业财务健康度进行二分类预测：
Builds 7 features from cash flow data, uses Random Forest for binary classification of company financial health:

```bash
python ml_financial_health.py
```

### 模型设计 / Model Design

| 项目 / Item | 说明 / Description |
|------|------|
| 样本量 / Sample size | 542 家企业 / 542 companies |
| 特征 / Features | 7维（销售收现、税费返还、采购付现、职工薪酬、税费支出、投资现金流、筹资现金流）/ 7-dim |
| 标签 / Label | 财务健康（经营现金流为正 且 现金净增加额为正）/ Financially healthy (OCF > 0 AND net cash increase > 0) |
| 模型 / Model | RandomForestClassifier, 100 trees, max_depth=5 |
| 划分 / Split | 80/20 stratified train-test split |

### 输出 / Output

```
output/analysis/
├── ml_classification.png     ← 特征重要性 + 混淆矩阵 / Feature importance + confusion matrix
└── ml_predictions.csv        ← 542家企业预测结果 / 542-company predictions
```

---

## 📁 输出文件 / Output Files

```
output/
├── crawl_state.db                ← SQLite 公告与下载状态库 / SQLite announcement & download state
├── pdf/
│   └── 00_待分类/              ← 解析失败或待重试的 PDF 备份 / Failed/pending PDF backups
├── csv/
│   ├── announcements_list.csv  ← 公告列表 / Announcement list
│   ├── 代码_名称_年份_合并资产负债表.csv
│   ├── 代码_名称_年份_合并利润表.csv
│   └── 代码_名称_年份_合并现金流量表.csv
├── analysis/                    ← 数据分析输出 / Data analysis output
│   ├── financial_analysis.png  ← 统计可视化图表 / Statistical charts
│   ├── summary_statistics.csv  ← 汇总统计 / Summary statistics
│   ├── ml_classification.png   ← ML特征重要性+混淆矩阵 / ML feature importance + confusion matrix
│   └── ml_predictions.csv       ← 542家企业ML预测结果 / 542-company ML predictions
├── log/                        ← 运行日志 / Runtime logs
└── html/                       ← HTML 可视化报表（选配）/ HTML reports (optional)
```

### CSV 标准化列名 / Standardised CSV Column Names

| 报表类型 / Statement Type | 列名 / Columns |
|----------|------|
| 合并资产负债表 / Consolidated Balance Sheet | 项目、期末余额、期初余额 / Item, Ending Balance, Beginning Balance |
| 合并利润表 / Consolidated Income Statement | 项目、本期金额、上期金额 / Item, Current Period, Prior Period |
| 合并现金流量表 / Consolidated Cash Flow Statement | 项目、本期金额、上期金额 / Item, Current Period, Prior Period |

---

## 📂 项目结构 / Project Structure

```
neeq-financial-crawler/
├── main.py                 # 入口：爬虫主流程 / Entry point: crawler main flow
├── neeq_crawler.py         # 新三板公告搜索与下载 / NEEQ announcement search & download
├── cninfo_api.py           # 巨潮资讯网数据源接口 / CNINFO data source API
├── database.py             # SQLite 公告与下载状态 / SQLite announcement & download state
├── pdf_parser.py           # PDF 表格解析引擎 / PDF table parsing engine (pdfplumber + PyMuPDF + RapidOCR)
├── data_exporter.py        # 解析结果导出为 CSV / Export parsed results to CSV
├── financial_analysis.py   # 数据分析与可视化 / Data analysis & visualisation (pandas + matplotlib)
├── ml_financial_health.py  # 机器学习财务健康度分类 / ML financial health classification (scikit-learn)
├── csv_to_pdf.py           # CSV 转 HTML 可视化报表 / CSV to HTML report converter
├── retry_backup_pdfs.py    # 批量重解析备份 PDF / Batch re-parse backup PDFs
├── smoke_test.py           # 端到端冒烟测试 / End-to-end smoke test
├── config.py               # 全局配置常量 / Global configuration constants
├── tests/                  # SQLite 与爬虫单元测试 / SQLite & crawler unit tests
├── requirements.txt        # Python 依赖 / Python dependencies
├── .gitignore              # Git 忽略规则 / Git ignore rules
└── README.md
```

---

## 🖨️ CSV 可视化 / CSV Visualisation

将 CSV 转为可直接打印的 HTML 财务报表：
Convert CSV to printable HTML financial reports:

```bash
python csv_to_pdf.py
```

浏览器打开 `output/html/index.html`，点击报表链接即可预览，右上角可"打印/导出 PDF"。
Open `output/html/index.html` in a browser, click a report link to preview, and use "Print / Export PDF" in the top-right corner.

---

## 🏗️ 技术架构 / Technical Architecture

### PDF 解析三级回退 / Three-Tier PDF Parsing Fallback

```
pdfplumber (文本层提取)  →  PyMuPDF (备用文本层)  →  RapidOCR (视觉识别)
  (Text-layer extraction)     (Fallback text layer)     (Visual recognition)
     ↓                         ↓                          ↓
   主引擎                    第二级回退                   第三级回退
  Primary engine            2nd-tier fallback           3rd-tier fallback
  速度快                     速度快                      速度慢但最鲁棒
  Fast                      Fast                        Slow but most robust
  规范PDF有效               复杂排版有效                图片型PDF有效
  Standard PDFs             Complex layouts             Image-based PDFs
```

| 引擎 / Engine | 原理 / Principle | 优势 / Advantage | 局限 / Limitation |
|------|------|------|------|
| pdfplumber | PDF文本层+坐标对齐 / Text layer + coordinate alignment | 速度快，结构清晰 / Fast, clear structure | 合并单元格易错位 / Merged cells misalign |
| PyMuPDF | PDF文本层直接提取 / Direct text-layer extraction | 兼容性好，速度快 / Good compatibility, fast | 复杂排版仍可能失败 / May fail on complex layouts |
| RapidOCR | 渲染为图片+ONNX视觉识别 / Render to image + ONNX visual recognition | 最鲁棒，图片型PDF也能识别 / Most robust, handles image PDFs | 速度慢（秒/页）/ Slow (~1s/page) |

> RapidOCR 使用与 PaddleOCR 相同的 PP-OCR 模型，但基于 ONNX Runtime 推理，避免了 PaddlePaddle 在 Windows 上的 oneDNN 兼容问题。
> RapidOCR uses the same PP-OCR models as PaddleOCR but runs on ONNX Runtime, avoiding PaddlePaddle's oneDNN compatibility issue on Windows.

### 技术栈 / Tech Stack

| 层级 / Layer | 技术 / Technology |
|------|------|
| 数据采集 / Data Acquisition | requests, NEEQ/CNINFO API |
| PDF解析 / PDF Parsing | pdfplumber, PyMuPDF, RapidOCR (ONNX) |
| 数据存储 / Data Storage | SQLite (状态管理 / state), CSV (数据导出 / export) |
| 数据分析 / Data Analysis | pandas, NumPy |
| 机器学习 / Machine Learning | scikit-learn (Random Forest, classification) |
| 可视化 / Visualisation | matplotlib |

---

## 🔗 数据源 / Data Sources

- [全国股转系统信息披露平台 / NEEQ Disclosure Platform](https://www.neeq.com.cn/m/disclosure/announcement.html)
- [巨潮资讯网 / CNINFO](https://www.cninfo.com.cn/)

---

## ⚠️ 已知局限 / Known Limitations

> - 三级回退已覆盖大部分 PDF 类型，但极少数扫描质量过低的图片型表格仍可能失败 / The three-tier fallback covers most PDF types, but a few low-quality scanned images may still fail
> - PDF 附注内容可能被误判为财务报表数据，需后续清洗 / PDF footnotes may be misidentified as statement data, requiring further cleaning
> - `financial_analysis.py` 中利润表有效数据量较少（受限于 CSV 解析成功率），现金流数据覆盖率较高 / Income statement data is limited by CSV parsing success rate; cash flow data has higher coverage
> - OCR 回退速度约为 1-2 秒/页，批量处理 800+ PDF 时耗时较长 / OCR fallback runs at ~1-2s per page, making batch processing of 800+ PDFs time-consuming

---

## 🎯 适用场景 / Use Cases

- 新三板及中小上市公司财报批量采集 / Batch collection of NEEQ & SME financial reports
- 金融数据分析、财务指标计算 / Financial data analysis, indicator calculation
- 学术研究中需要大量结构化财报数据 / Academic research requiring large-scale structured financial data
- 端到端数据流水线实践：采集 → 解析 → 清洗 → 分析 → 机器学习 → 可视化 / End-to-end data pipeline: collect → parse → clean → analyse → ML → visualise
