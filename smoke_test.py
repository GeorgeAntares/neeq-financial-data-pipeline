"""端到端烟雾测试 —— 用最小数据量快速验证整个链路是否正常。

每次修改代码后运行一次，30 秒内出结果。
用法: py smoke_test.py
"""

import os
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

# --- 1. 导入检查：所有核心模块能否正常加载 ---
print("1/5  检查模块导入...")
try:
    from database import CrawlRepository, infer_report_year
    from neeq_crawler import (
        search_annual_reports,
        download_pdf,
        is_valid_pdf,
        _parse_jsonp,
        _normalize_announcement,
        NEEQ_BASE,
        NEEQ_SEARCH_API,
    )
    from data_exporter import DataExporter
    print("     所有模块导入成功")
except ImportError as e:
    print(f"     导入失败: {e}")
    sys.exit(1)

# --- 2. 网络检查：NEEQ API 是否可达 ---
print("2/5  检查 NEEQ API 连通性...")
import requests

try:
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": f"{NEEQ_BASE}/m/disclosure/announcement.html",
        "X-Requested-With": "XMLHttpRequest",
    })
    test_data = [
        ("page", "0"),
        ("companyCd", ""),
        ("isNewThree", "1"),
        ("startTime", date.today().isoformat()),
        ("endDate", date.today().isoformat()),
        ("keyword", ""),
        ("xxfcbj[]", "3"),
        ("disclosureSubtype[]", "9503-1001"),
    ]
    response = session.post(NEEQ_SEARCH_API, data=test_data, timeout=(10, 30))
    response.raise_for_status()
    print(f"     API 响应 {response.status_code}，连通正常")
except requests.RequestException as e:
    print(f"     API 不可达: {e}")
    print("     (如果网络正常但仍失败，可能是网站维护，稍后重试)")
    sys.exit(1)

# --- 3. API 查询检查：最小日期范围能否返回结果 ---
print("3/5  检查公告查询（最近 3 天）...")

end_date = date.today().isoformat()
start_date = (date.today() - timedelta(days=3)).isoformat()

try:
    announcements = search_annual_reports(
        start_date=start_date,
        end_date=end_date,
        max_pages=1,
    )
    print(f"     查询 {start_date} ~ {end_date}，找到 {len(announcements)} 条年度报告")
except Exception as e:
    print(f"     查询失败: {e}")
    sys.exit(1)

if not announcements:
    print("     警告: 最近 3 天无年度报告公告（非年报季属正常现象）")

# --- 4. 数据库检查：SQLite 读写是否正常 ---
print("4/5  检查 SQLite 读写...")
with tempfile.TemporaryDirectory() as tmpdir:
    db_path = Path(tmpdir) / "smoke.db"
    repo = CrawlRepository(db_path)

    try:
        # 写入
        test_announcement = {
            "secCode": "999999",
            "secName": "烟雾测试公司",
            "announcementTitle": "烟雾测试公司：2025年年度报告",
            "announcementDate": "2026-04-20",
            "adjunctUrl": "https://example.com/smoke-test.pdf",
        }
        inserted = repo.upsert_announcements([test_announcement], source="neeq")
        assert inserted == 1, f"预期插入 1 条，实际 {inserted}"

        # 读取
        record = repo.get_announcement("neeq", test_announcement["adjunctUrl"])
        assert record is not None, "读取失败"
        assert record["company_code"] == "999999"
        assert record["report_year"] == 2025
        assert record["status"] == "pending"

        # 状态转换
        repo.mark_downloading("neeq", test_announcement["adjunctUrl"])
        record = repo.get_announcement("neeq", test_announcement["adjunctUrl"])
        assert record["status"] == "downloading"
        assert record["attempts"] == 1

        # 恢复中断
        recovered = repo.recover_incomplete_downloads()
        assert recovered == 1
        record = repo.get_announcement("neeq", test_announcement["adjunctUrl"])
        assert record["status"] == "pending"

        print("     数据库读写、状态转换、中断恢复均正常")
    except AssertionError as e:
        print(f"     数据库验证失败: {e}")
        sys.exit(1)
    finally:
        repo.close()

# --- 5. 数据导出检查 ---
print("5/5  检查 CSV 导出...")
import pandas as pd

with tempfile.TemporaryDirectory() as tmpdir:
    # 临时替换输出目录
    original_csv = DataExporter().csv_dir
    exporter = DataExporter()
    exporter.csv_dir = tmpdir

    try:
        test_df = pd.DataFrame({"项目": ["资产总计"], "期末余额": [1000], "期初余额": [900]})
        path = exporter.export_to_csv(test_df, "烟雾测试_合并资产负债表.csv")
        assert path and os.path.exists(path), "CSV 导出失败"
        assert os.path.getsize(path) > 20, f"CSV 文件过小: {os.path.getsize(path)} 字节"
        print("     CSV 导出正常")
    except Exception as e:
        print(f"     CSV 导出失败: {e}")
        sys.exit(1)

    exporter.csv_dir = original_csv

# --- 结果 ---
print()
print("=" * 50)
print("全部检查通过！项目核心链路正常运行。")
print("=" * 50)
