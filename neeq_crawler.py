"""
新三板（NEEQ）财报爬虫
数据源: www.neeq.com.cn (全国股转系统信息披露平台)
"""
import json
import requests
import time
import logging
from datetime import date
from pathlib import Path
from urllib.parse import urljoin

logger = logging.getLogger(__name__)

NEEQ_BASE = "https://www.neeq.com.cn"
NEEQ_SEARCH_API = f"{NEEQ_BASE}/disclosureInfoController/companyAnnouncement.do"
ANNUAL_REPORT_SUBTYPE = "9503-1001"
REQUEST_DELAY = 0.5  # 请求间隔（秒），避免被封
MAX_PAGE_RETRIES = 3

NEEDED_FIELDS = [
    "companyCd",
    "companyName",
    "disclosureTitle",
    "disclosurePostTitle",
    "destFilePath",
    "publishDate",
    "fileExt",
    "xxfcbj",
    "xxzrlx",
]


def _validate_date_range(start_date, end_date):
    try:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
    except ValueError as exc:
        raise ValueError("日期必须使用 YYYY-MM-DD 格式") from exc
    if start > end:
        raise ValueError("开始日期不能晚于结束日期")
    return start.isoformat(), end.isoformat()


def _parse_jsonp(text):
    """Parse the JSONP wrapper returned by the NEEQ website."""
    content = text.strip()
    if content.startswith("[") or content.startswith("{"):
        return json.loads(content)

    start = content.find("(")
    end = content.rfind(")")
    if start < 0 or end <= start:
        raise ValueError("新三板接口返回了无法识别的数据格式")
    return json.loads(content[start + 1:end])


def _request_announcement_page(session, page, start_date, end_date):
    data = [
        ("page", str(page)),
        ("companyCd", ""),
        ("isNewThree", "1"),
        ("startTime", start_date),
        ("endTime", end_date),
        ("keyword", ""),
        ("xxfcbj[]", "3"),
        ("disclosureSubtype[]", ANNUAL_REPORT_SUBTYPE),
    ]
    data.extend(("needFields[]", field) for field in NEEDED_FIELDS)

    last_error = None
    for attempt in range(1, MAX_PAGE_RETRIES + 1):
        try:
            response = session.post(
                NEEQ_SEARCH_API,
                data=data,
                timeout=(10, 30),
            )
            response.raise_for_status()
            payload = _parse_jsonp(response.text)
            if not payload or "listInfo" not in payload[0]:
                raise ValueError("新三板接口响应中缺少 listInfo")
            return payload[0]["listInfo"]
        except (requests.RequestException, ValueError, json.JSONDecodeError) as exc:
            last_error = exc
            logger.warning(
                "公告查询第%s页失败（%s/%s）: %s",
                page + 1,
                attempt,
                MAX_PAGE_RETRIES,
                exc,
            )
            if attempt < MAX_PAGE_RETRIES:
                time.sleep(attempt * 2)

    raise RuntimeError(
        f"公告查询第{page + 1}页连续失败"
    ) from last_error


_NON_ANNUAL_MARKERS = (
    "半年度",
    "半年报",
    "中期报告",
    "一季度",
    "三季度",
    "季度报告",
    "一季报",
    "三季报",
)


def is_annual_report_title(title):
    """True for annual-report body PDFs; false for 摘要/半年报/已取消/季报."""
    text = str(title or "")
    if "已取消" in text or "摘要" in text:
        return False
    if any(marker in text for marker in _NON_ANNUAL_MARKERS):
        return False
    return "年度报告" in text


def _normalize_announcement(item, start_date, end_date):
    title = str(item.get("disclosureTitle") or "").strip()
    post_title = str(item.get("disclosurePostTitle") or "").strip()
    full_title = f"{title}{post_title}"
    publish_date = str(item.get("publishDate") or "")[:10]
    file_type = str(item.get("fileExt") or "").upper()
    file_path = str(item.get("destFilePath") or "").strip()

    if not is_annual_report_title(full_title):
        return None
    if file_type != "PDF" or not file_path:
        return None
    if not start_date <= publish_date <= end_date:
        return None

    return {
        "secCode": str(item.get("companyCd") or "").strip(),
        "secName": str(item.get("companyName") or "").strip(),
        "announcementTitle": full_title,
        "adjunctUrl": urljoin(NEEQ_BASE, file_path),
        "announcementDate": publish_date,
        "adjunctType": "PDF",
    }


def search_annual_reports(
    start_date="2025-01-01",
    end_date="2025-12-31",
    max_pages=0,
    start_page=1,
):
    """
    按发布日期和公告分类搜索新三板年度报告。

    :param start_date: 发布日期下限，YYYY-MM-DD
    :param end_date: 发布日期上限，YYYY-MM-DD
    :param max_pages: 最多查询页数，0 表示不限
    :param start_page: 起始页，保留用于故障恢复，默认从第 1 页开始
    """
    start_date, end_date = _validate_date_range(start_date, end_date)
    if start_page < 1:
        raise ValueError("start_page 必须大于等于 1")
    if max_pages < 0:
        raise ValueError("max_pages 不能小于 0")
    
    results = []
    seen_urls = set()
    page = start_page - 1  # 官网接口页码从 0 开始
    pages_fetched = 0

    with requests.Session() as session:
        session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
            ),
            "Referer": f"{NEEQ_BASE}/m/disclosure/announcement.html",
            "X-Requested-With": "XMLHttpRequest",
        })

        while True:
            list_info = _request_announcement_page(
                session,
                page,
                start_date,
                end_date,
            )
            pages_fetched += 1
            items = list_info.get("content") or []
            total_pages = int(list_info.get("totalPages") or 0)

            for item in items:
                announcement = _normalize_announcement(
                    item,
                    start_date,
                    end_date,
                )
                if announcement is None:
                    continue
                url = announcement["adjunctUrl"]
                if url not in seen_urls:
                    seen_urls.add(url)
                    results.append(announcement)

            if pages_fetched == 1 or pages_fetched % 10 == 0:
                logger.info(
                    "公告查询进度: %s/%s 页，已筛选 %s 份年度报告",
                    page + 1,
                    total_pages,
                    len(results),
                )

            reached_page_limit = max_pages > 0 and pages_fetched >= max_pages
            reached_last_page = total_pages == 0 or page + 1 >= total_pages
            if reached_page_limit or reached_last_page:
                break
            
            page += 1
            time.sleep(REQUEST_DELAY)
            
    logger.info(
        "搜索完成: 查询%s页，找到%s条有效年度报告",
        pages_fetched,
        len(results),
    )
    return results


def is_valid_pdf(path):
    """Return True when a local file has a PDF header and non-empty body."""
    file_path = Path(path)
    if not file_path.is_file() or file_path.stat().st_size < 5:
        return False
    try:
        with file_path.open("rb") as file:
            return file.read(5) == b"%PDF-"
    except OSError:
        return False


def download_pdf(url, save_path):
    """
    下载新三板公告 PDF
    
    :param url: PDF 下载地址
    :param save_path: 保存路径
    :return: 是否成功
    """
    if not url:
        return False
    
    path = Path(save_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if is_valid_pdf(path):
        logger.info("PDF已存在，跳过下载: %s", path.name)
        return True

    part_path = path.with_suffix(path.suffix + ".part")
    
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": f"{NEEQ_BASE}/",
    }
    
    for retry in range(3):
        try:
            with requests.get(
                url,
                headers=headers,
                timeout=(10, 120),
                stream=True,
            ) as response:
                response.raise_for_status()
                with part_path.open("wb") as file:
                    for chunk in response.iter_content(chunk_size=64 * 1024):
                        if chunk:
                            file.write(chunk)

            if not is_valid_pdf(part_path):
                raise ValueError("响应内容不是有效的 PDF 文件")

            part_path.replace(path)
            logger.info("PDF下载成功: %s", path.name)
            return True
        except (requests.RequestException, OSError, ValueError) as exc:
            logger.warning(
                "PDF下载异常（重试%s/3）: %s",
                retry + 1,
                exc,
            )
            try:
                part_path.unlink(missing_ok=True)
            except OSError:
                pass

        if retry < 2:
            time.sleep((retry + 1) * 2)
    
    return False
