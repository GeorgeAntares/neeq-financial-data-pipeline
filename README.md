<p align="center">
  <img src="https://img.shields.io/badge/Python-3.9+-blue?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey" alt="Platform">
  <img src="https://img.shields.io/badge/License-MIT-green" alt="License">
</p>

<h1 align="center">📊 中小微上市公司财报爬虫</h1>

<p align="center">从新三板与巨潮资讯网抓取年报 PDF，自动解析三大财务报表并导出为结构化 CSV</p>

---

## 📑 目录

- [功能特性](#-功能特性)
- [环境要求](#-环境要求)
- [快速开始](#-快速开始)
- [命令行参数](#-命令行参数)
- [输出文件](#-输出文件)
- [项目结构](#-项目结构)
- [CSV 可视化](#-csv-可视化)
- [数据源](#-数据源)
- [已知局限](#-已知局限)
- [适用场景](#-适用场景)

---

## ✨ 功能特性

- 🔍 搜索新三板与巨潮资讯网的年报公告
- 📥 自动下载年报 PDF，支持断点续爬
- ⚡ 双重引擎解析财务表格（pdfplumber 主引擎 + pymupdf 回退）
- 📋 导出标准格式的 CSV 财务数据（三大报表）
- ⏸️ 支持纯下载模式、优雅停止、备份 PDF 批量重解析

---

## 🔧 环境要求

| 依赖 | 版本 |
|------|------|
| Python | 3.9 及以上 |
| 操作系统 | Windows / macOS / Linux |

```bash
# 克隆项目
git clone https://github.com/GeorgeAntares/neeq-financial-crawler.git
cd neeq-financial-crawler

# 安装依赖
pip install -r requirements.txt
```

---

## 🚀 快速开始

### ① 搜索年报并下载 PDF

```bash
# 按公告发布日期查询并下载，不解析 CSV
python main.py --source neeq --start-date 2025-01-01 --end-date 2025-12-31 --skip-parse

# 仅查询公告并写入 SQLite，不下载 PDF
python main.py --source neeq --year 2025 --skip-download
```

### ② 续爬模式

再次执行相同命令时，程序根据 `output/crawl_state.db` 自动跳过已下载 PDF。
`--resume` 只用于将旧版公告列表 CSV 导入 SQLite：

```bash
python main.py --source neeq --resume
```

### ③ 纯下载模式

只下载 PDF，跳过解析（速度提升 25~30 倍）：

```bash
python main.py --source neeq --year 2025 --skip-parse
```

### ④ 批量重解析备份 PDF

```bash
python retry_backup_pdfs.py
```

### ⑤ 优雅停止

在项目根目录创建 `STOP.txt`，爬虫将在当前公司处理完毕后自动退出：

```bash
# Windows PowerShell
New-Item STOP.txt

# macOS / Linux
touch STOP.txt
```

---

## 🗄️ SQLite 状态库设计

项目使用 SQLite 替代页码爬取，通过日期范围查询 NEEQ 官方 API，彻底解决"新公告导致页码内容漂移"的问题。

### 为什么选 SQLite

| 对比维度 | SQLite | MySQL / MongoDB |
|---------|--------|-----------------|
| 部署成本 | **零依赖**，Python 标准库自带 | 需安装服务端、配置用户权限 |
| 数据量级 | 年报项目最多数万条，完全够用 | 适合百万级以上 |
| 项目可迁移性 | 单文件 `crawl_state.db`，复制即迁移 | 需导出/导入数据库 |
| 数据类型安全 | `CHECK` 约束强制类型校验 | 依赖应用层或 Schema 定义 |

### 数据表结构

**`announcements`** — 公告与下载状态

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `source` | TEXT | NOT NULL | 数据源（`neeq` / `cninfo`） |
| `pdf_url` | TEXT | NOT NULL | PDF 下载链接 |
| `company_code` | TEXT | | 公司代码 |
| `company_name` | TEXT | | 公司简称 |
| `publish_date` | TEXT | ISO 8601 格式 | 公告发布日期 |
| `title` | TEXT | | 公告标题 |
| `report_year` | INTEGER | `>= 1990` | 推断的财报所属年份 |
| `status` | TEXT | CHECK IN (`pending`, `downloading`, `downloaded`, `failed`) | 下载状态 |
| `file_path` | TEXT | | 本地 PDF 路径 |
| `file_size` | INTEGER | `>= 0` | 文件大小（字节） |
| `attempts` | INTEGER | `>= 0` | 重试次数 |
| `error_message` | TEXT | | 失败原因 |
| `discovered_count` | INTEGER | `>= 0` | 累计发现次数 |

> **唯一约束**：`(source, pdf_url)` — 同一公告不会被重复记录

**`crawl_runs`** — 爬取运行记录

| 字段 | 类型 | 说明 |
|------|------|------|
| `started_at` | TEXT | 运行开始时间 |
| `finished_at` | TEXT | 运行结束时间 |
| `status` | TEXT | `running` / `completed` / `failed` / `interrupted` |
| `total_discovered` | INTEGER | 本次发现公告数 |
| `total_downloaded` | INTEGER | 本次下载成功数 |

### 下载状态机

```
pending  ──→  downloading  ──→  downloaded
  │                                │
  └──────────  failed  ←───────────┘
```

- 程序启动时自动执行 `recover_incomplete_downloads()`，将残留的 `downloading` 重置为 `pending`
- 再次运行相同命令时，已 `downloaded` 且 PDF 有效的记录会被自动跳过
- 数据库启用 WAL 模式 + `busy_timeout=5000ms`，避免并发写入冲突

---

## 📋 命令行参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--source` | 数据源：`cninfo`（巨潮资讯网）或 `neeq`（新三板） | `cninfo` |
| `--year` | 公告发布日期年份，不等同于财报所属年份 | 去年 |
| `--start-date` | 公告起始日期 `YYYY-MM-DD` | 无 |
| `--end-date` | 公告截止日期 `YYYY-MM-DD` | 无 |
| `--start-page` | 查询结果起始页，仅用于故障恢复 | `1` |
| `--max-pages` | 最大翻页数，`0` 表示不限 | `0` |
| `--resume` | 将旧公告 CSV 导入 SQLite 并续爬 | 关闭 |
| `--skip-parse` | 纯下载模式，只下载不解析 | 关闭 |
| `--skip-download` | 仅搜索公告列表，不下载 | 关闭 |

---

## 📁 输出文件

```
output/
├── crawl_state.db                ← SQLite 公告与下载状态库
├── pdf/
│   └── 00_待分类/              ← 解析失败或待重试的 PDF 备份
├── csv/
│   ├── announcements_list.csv  ← 公告列表
│   ├── 代码_名称_年份_合并资产负债表.csv
│   ├── 代码_名称_年份_合并利润表.csv
│   └── 代码_名称_年份_合并现金流量表.csv
├── log/                        ← 运行日志
└── html/                       ← HTML 可视化报表（选配）
```

### CSV 标准化列名

| 报表类型 | 列名 |
|----------|------|
| 合并资产负债表 | 项目、期末余额、期初余额 |
| 合并利润表 | 项目、本期金额、上期金额 |
| 合并现金流量表 | 项目、本期金额、上期金额 |

---

## 📂 项目结构

```
neeq-financial-crawler/
├── main.py                 # 入口：爬虫主流程
├── neeq_crawler.py         # 新三板公告搜索与下载
├── cninfo_api.py           # 巨潮资讯网数据源接口
├── database.py             # SQLite 公告与下载状态
├── pdf_parser.py           # PDF 表格解析引擎（pdfplumber + pymupdf）
├── data_exporter.py        # 解析结果导出为 CSV
├── csv_to_pdf.py           # CSV 转 HTML 可视化报表
├── retry_backup_pdfs.py    # 批量重解析备份 PDF
├── config.py               # 全局配置常量
├── tests/                  # SQLite 与爬虫单元测试
├── requirements.txt        # Python 依赖
├── .gitignore              # Git 忽略规则
└── README.md
```

---

## 🖨️ CSV 可视化（选配）

将 CSV 转为可直接打印的 HTML 财务报表：

```bash
python csv_to_pdf.py
```

浏览器打开 `output/html/index.html`，点击报表链接即可预览，右上角可"打印/导出 PDF"。

---

## 🔗 数据源

- [全国股转系统信息披露平台](https://www.neeq.com.cn/m/disclosure/announcement.html)
- [巨潮资讯网](https://www.cninfo.com.cn/)

---

## ⚠️ 已知局限

> - 图片型表格（扫描件 PDF）当前无法提取，约 **10~15%** 的资产负债表受此影响
> - 利润表识别准确率约 **60~70%**，持续优化中
> - PDF 附注内容可能被误判为财务报表数据，需后续清洗

---

## 🎯 适用场景

- 新三板及中小上市公司财报批量采集
- 金融数据分析、财务指标计算
- 学术研究中需要大量结构化财报数据
