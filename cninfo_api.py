import logging
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

import requests

from config import CNINFO_API, MAX_RETRIES, PLATE_COLUMN, REQUEST_INTERVAL
from neeq_crawler import is_valid_pdf

logger = logging.getLogger(__name__)


class CNInfoAPI:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(CNINFO_API['headers'])

    def search_announcements(self, plate=None, category='category_ndbg_szsh', 
                            start_date=None, end_date=None, stock_code=None,
                            max_pages=0):
        """
        搜索公告
        :param plate: 板块代码，如 'szcy' (创业板), 'bj' (北交所)
        :param category: 公告类型代码
        :param start_date: 开始日期，格式 'YYYY-MM-DD'
        :param end_date: 结束日期，格式 'YYYY-MM-DD'
        :param stock_code: 股票代码（可选）
        :param max_pages: 最大页数，0表示不限
        :return: 公告列表
        """
        all_announcements = []
        page_num = 1
        
        while True:
            try:
                data = {
                    'pageNum': page_num,
                    'pageSize': 50,
                    'column': PLATE_COLUMN.get(plate, 'szse'),
                    'tabName': 'fulltext',
                    'plate': plate or '',
                    'stock': stock_code or '',
                    'searchkey': '',
                    'secid': '',
                    'category': category,
                    'trade': '',
                    'seDate': f'{start_date}~{end_date}' if start_date and end_date else '',
                    'sortName': '',
                    'sortType': '',
                    'limit': '',
                    'showTitle': '',
                    'isHLtitle': 'true',
                }
                
                response = self.session.post(
                    CNINFO_API['search_url'],
                    data=data,
                    timeout=(10, 30),
                )
                response.raise_for_status()
                
                result = response.json()
                announcements = result.get('announcements', [])
                
                # 转换时间戳字段为日期字符串
                for ann in announcements:
                    ts = ann.get('announcementTime')
                    if ts and isinstance(ts, (int, float)):
                        try:
                            ann['announcementDate'] = datetime.fromtimestamp(ts / 1000).strftime('%Y-%m-%d')
                        except Exception:
                            ann['announcementDate'] = str(ts)
                
                if not announcements:
                    logger.info(f'第 {page_num} 页无数据，搜索结束')
                    break
                
                all_announcements.extend(announcements)
                logger.info(f'获取第 {page_num} 页数据，共 {len(announcements)} 条，累计 {len(all_announcements)} 条')
                
                total_pages = result.get('totalpages', 0)
                if max_pages > 0 and page_num >= max_pages:
                    logger.info(f'已达到最大页数 {max_pages}')
                    break
                if page_num >= total_pages:
                    break
                
                page_num += 1
                time.sleep(REQUEST_INTERVAL)
                
            except Exception as e:
                logger.error(f'第 {page_num} 页请求失败: {e}')
                break
        
        return all_announcements

    def download_pdf(self, adjunct_url, save_path):
        """
        下载PDF文件：跳过已有有效文件，.part 原子写入，校验 %PDF- 头。
        """
        if not adjunct_url:
            return False

        pdf_url = (
            adjunct_url
            if str(adjunct_url).startswith(('http://', 'https://'))
            else urljoin(CNINFO_API['pdf_base_url'], str(adjunct_url).lstrip('/'))
        )
        path = Path(save_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if is_valid_pdf(path):
            logger.info('PDF已存在，跳过下载: %s', path.name)
            return True

        part_path = path.with_suffix(path.suffix + '.part')
        for attempt in range(MAX_RETRIES):
            try:
                response = self.session.get(pdf_url, timeout=(10, 120), stream=True)
                response.raise_for_status()
                with part_path.open('wb') as file:
                    for chunk in response.iter_content(chunk_size=64 * 1024):
                        if chunk:
                            file.write(chunk)
                if not is_valid_pdf(part_path):
                    raise ValueError('响应内容不是有效的 PDF 文件')
                part_path.replace(path)
                logger.info('PDF下载成功: %s', path.name)
                return True
            except Exception as exc:
                logger.warning(
                    'PDF下载失败(第%s次): %s, 错误: %s',
                    attempt + 1,
                    pdf_url,
                    exc,
                )
                if part_path.exists():
                    part_path.unlink()
                if attempt < MAX_RETRIES - 1:
                    time.sleep(REQUEST_INTERVAL * (attempt + 1))

        logger.error('PDF下载失败，已重试%s次: %s', MAX_RETRIES, pdf_url)
        return False

    def close(self):
        self.session.close()