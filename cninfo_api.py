import requests
import time
import logging
from datetime import datetime
from config import CNINFO_API, REQUEST_INTERVAL, MAX_RETRIES, PLATE_COLUMN

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
                
                response = self.session.post(CNINFO_API['search_url'], data=data)
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
        下载PDF文件
        :param adjunct_url: PDF附件相对路径
        :param save_path: 保存路径
        :return: 是否成功
        """
        pdf_url = CNINFO_API['pdf_base_url'] + adjunct_url
        
        for attempt in range(MAX_RETRIES):
            try:
                response = self.session.get(pdf_url, timeout=30)
                response.raise_for_status()
                
                with open(save_path, 'wb') as f:
                    f.write(response.content)
                
                logger.info(f'PDF下载成功: {save_path}')
                return True
                
            except Exception as e:
                logger.warning(f'PDF下载失败(第{attempt+1}次): {pdf_url}, 错误: {e}')
                if attempt < MAX_RETRIES - 1:
                    time.sleep(REQUEST_INTERVAL * (attempt + 1))
        
        logger.error(f'PDF下载失败，已重试{MAX_RETRIES}次: {pdf_url}')
        return False

    def close(self):
        self.session.close()