# 中小微上市公司财报爬虫

从新三板信息披露平台抓取上市公司年度报告 PDF，自动解析三大财务报表（资产负债表、利润表、现金流量表）并导出为结构化 CSV 文件。

## 功能

- 搜索新三板和巨潮资讯网的年报公告
- 自动下载年报 PDF 文件
- 双重引擎解析财务表格（pdfplumber + pymupdf 回退）
- 导出标准格式的 CSV 财务数据
- 支持断点续爬、纯下载模式、备份 PDF 重新解析

## 环境要求

- Python 3.9+
- Windows / macOS / Linux

## 安装

```bash
# 克隆项目
git clone https://github.com/你的用户名/项目名.git
cd 项目名

# 安装依赖
pip install -r requirements.txt
```

## 快速开始

### 1. 搜索年报公告并下载 PDF

```bash
# 新三板，搜索 2025 年年报，从第 1 页开始
python main.py --source neeq --year 2025

# 指定页码范围（跳过前面已处理过的页面）
python main.py --source neeq --year 2025 --start-page 1000 --max-pages 500
```

### 2. 续爬模式（已有公告列表 CSV，跳过搜索直接下载）

```bash
python main.py --source neeq --resume
```

### 3. 纯下载模式（不解析，只下载 PDF）

```bash
python main.py --source neeq --resume --skip-parse
```

### 4. 批量重新解析备份 PDF

```bash
python retry_backup_pdfs.py
```

### 5. 优雅停止

在项目根目录创建一个空的 `STOP.txt` 文件，爬虫会在处理完当前公司后自动退出：

```bash
# Windows PowerShell
New-Item STOP.txt

# macOS / Linux
touch STOP.txt
```

## 命令行参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--source` | 数据源：`cninfo`（巨潮资讯网）或 `neeq`（新三板） | `cninfo` |
| `--year` | 年报年份 | 去年 |
| `--start-date` / `--end-date` | 公告日期范围（格式 YYYY-MM-DD） | 无 |
| `--start-page` | 起始页码，用于跳过历史数据 | 1 |
| `--max-pages` | 最大翻页数，0 表示不限 | 0 |
| `--resume` | 续爬模式：从已有 CSV 加载公告列表，跳过搜索 | 关闭 |
| `--skip-parse` | 纯下载模式：只下载 PDF，不解析 | 关闭 |
| `--skip-download` | 仅搜索公告列表，不下载 | 关闭 |

## 输出文件

```
output/
├── pdf/                    # 下载的年报 PDF 文件
│   └── 00_待分类/          # 备份目录（解析失败或待重试的 PDF）
├── csv/                    # 解析后的 CSV 文件
│   ├── announcements_list.csv   # 公告列表
│   ├── 代码_名称_年份_合并资产负债表.csv
│   ├── 代码_名称_年份_合并利润表.csv
│   └── 代码_名称_年份_合并现金流量表.csv
├── log/                    # 运行日志
└── html/                   # CSV 转 HTML 可视化报表（选配）
```

CSV 标准化列名：

| 报表类型 | 列名 |
|----------|------|
| 合并资产负债表 | 项目、期末余额、期初余额 |
| 合并利润表 | 项目、本期金额、上期金额 |
| 合并现金流量表 | 项目、本期金额、上期金额 |

## CSV 可视化（选配）

生成可直接打印的 HTML 格式财务报表：

```bash
python csv_to_pdf.py
```

在浏览器中打开生成的 `output/html/index.html`，点击报表链接即可查看。点击右上角"打印/导出 PDF"可保存为正式 PDF。

## 数据源

- [新三板信息披露平台](https://neeq.cs.com.cn/)
- [巨潮资讯网](https://www.cninfo.com.cn/)

## 已知局限

- 图片型表格（PDF 中的扫描件）当前无法提取，约 10-15% 的资产负债表受此影响
- 利润表识别准确率约为 60-70%，持续优化中
- PDF 附注内容可能被误判为财务报表数据，需后续清洗

## 适用场景

- 新三板及中小上市公司财报批量采集
- 金融数据分析、财务指标计算
- 学术研究中需要大量结构化财报数据
