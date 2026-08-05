"""
新三板（NEEQ）财报爬虫
数据源: neeq.cs.com.cn (新三板信息披露平台)
"""
import requests
import time
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

NEEQ_BASE = "https://neeq.cs.com.cn"
NEEQ_LIST_API = f"{NEEQ_BASE}/xsb/v1/new"  # {page}.json
REQUEST_DELAY = 0.5  # 请求间隔（秒），避免被封


def search_annual_reports(start_date="2025-01-01", end_date="2025-12-31", max_pages=2000, start_page=1):
    """
    搜索新三板年度报告公告（翻页过滤法）
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": f"{NEEQ_BASE}/gongSiGG.html",
    }
    
    results = []
    page = start_page
    null_pages = 0
    
    while page <= max_pages:
        url = f"{NEEQ_LIST_API}/{page}.json"
        
        try:
            resp = requests.get(url, headers=headers, timeout=(5, 20))
            
            if resp.status_code != 200:
                logger.warning(f"第{page}页 HTTP {resp.status_code}")
                page += 1
                time.sleep(1)
                continue
            
            data = resp.json()
            inner = data.get('data')
            
            if inner is None:
                null_pages += 1
                if null_pages >= 3:
                    logger.info(f"连续{null_pages}页无数据(skip)，结束搜索") if null_pages >= 3 else None
                logger.debug(f"第{page}页 null (连续{null_pages})")
                page += 1
                time.sleep(0.2)
                continue
            else:
                null_pages = 0
            
            items = inner.get('data', [])
            if not items:
                logger.info(f"第{page}页空列表，停止")
                break
            
            earliest_date = ""
            for item in items:
                title = item.get('f002v', '')
                date_str = (item.get('f001d', '') or '')[:10]
                if date_str and (not earliest_date or date_str < earliest_date):
                    earliest_date = date_str
                # 筛选所有定期报告（年报/半年报/季报/月报），排除审计/摘要/更正/延期/风险提示
                if '[定期报告]' in title:
                    exclude_kw = ['审计报告', '摘要', '更正', '延期', '无法', '风险提示']
                    if not any(kw in title for kw in exclude_kw):
                        results.append({
                            'secCode': item.get('seccode', ''),
                            'secName': item.get('secname', ''),
                            'announcementTitle': title,
                            'adjunctUrl': item.get('f003v', ''),
                            'announcementDate': date_str,
                            'adjunctType': item.get('f004v', 'PDF'),
                        })
            
            if page % 20 == 0 or page <= 5:
                logger.info(f"第{page}页 | 已找到{len(results)}条年报 | 日期:{earliest_date}")
            
            if earliest_date and earliest_date < start_date:
                logger.info(f"日期超出范围({earliest_date} < {start_date})，停止")
                break
            
            page += 1
            time.sleep(REQUEST_DELAY)
            
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError,
                requests.exceptions.ReadTimeout, requests.exceptions.ConnectTimeout,
                TimeoutError, ConnectionError):
            logger.warning(f"第{page}页网络错误，重试...")
            time.sleep(3)
            continue
        except Exception as e:
            logger.error(f"第{page}页异常: {type(e).__name__}")
            page += 1
            time.sleep(1)
            continue
    
    logger.info(f"搜索完成: 扫描{page}页, 找到{len(results)}条年度报告")
    return results


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
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://neeq.cs.com.cn/",
    }
    
    for retry in range(3):
        try:
            resp = requests.get(url, headers=headers, timeout=60, stream=True)
            if resp.status_code == 200:
                with open(save_path, 'wb') as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        f.write(chunk)
                logger.info(f"PDF下载成功: {path.name}")
                return True
            else:
                logger.warning(f"PDF下载失败({resp.status_code}): {url[:60]}")
        except Exception as e:
            logger.warning(f"PDF下载异常(重试{retry+1}/3): {e}")
        
        time.sleep(2)
    
    return False
