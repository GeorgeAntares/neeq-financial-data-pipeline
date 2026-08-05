import os
import csv
import logging
import pandas as pd
from config import OUTPUT_DIR

logger = logging.getLogger(__name__)


class DataExporter:
    def __init__(self):
        self.csv_dir = OUTPUT_DIR['csv']
        self.pdf_dir = OUTPUT_DIR['pdf']

    def export_to_csv(self, df, filename):
        """
        导出DataFrame到CSV文件
        :param df: DataFrame
        :param filename: 文件名
        :return: 保存路径
        """
        save_path = os.path.join(self.csv_dir, filename)
        try:
            df.to_csv(save_path, index=False, encoding='utf-8-sig')
            logger.info(f'数据已导出: {save_path}')
            return save_path
        except Exception as e:
            logger.error(f'CSV导出失败: {filename}, 错误: {e}')
            return None

    def export_all_reports(self, reports, stock_code, stock_name, year):
        """
        导出所有报表
        :param reports: 报表字典
        :param stock_code: 股票代码
        :param stock_name: 股票名称
        :param year: 年份
        """
        report_names = {
            'balance_sheet': '合并资产负债表',
            'income_statement': '合并利润表',
            'cash_flow': '合并现金流量表'
        }
        
        for key, df in reports.items():
            if df is not None:
                filename = f'{stock_code}_{stock_name}_{year}_{report_names[key]}.csv'
                self.export_to_csv(df, filename)
            else:
                logger.warning(f'{stock_code} {stock_name} {year}年{report_names[key]}解析失败')

    def export_announcements_list(self, announcements, filename='announcements_list.csv'):
        """
        导出公告列表
        :param announcements: 公告列表
        :param filename: 文件名
        :return: 保存路径
        """
        save_path = os.path.join(self.csv_dir, filename)
        
        try:
            # 提取关键字段
            fields = ['secCode', 'secName', 'announcementTitle', 'announcementDate',
                      'adjunctSize', 'adjunctUrl', 'detailUrl']
            
            with open(save_path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=fields)
                writer.writeheader()
                for ann in announcements:
                    row = {field: ann.get(field, '') for field in fields}
                    writer.writerow(row)
            
            logger.info(f'公告列表已导出: {save_path}')
            return save_path
        except Exception as e:
            logger.error(f'公告列表导出失败: {e}')
            return None

    def get_pdf_save_path(self, stock_code, stock_name, year, title):
        """
        生成PDF保存路径
        :param stock_code: 股票代码
        :param stock_name: 股票名称
        :param year: 年份
        :param title: 公告标题
        :return: 保存路径
        """
        # 清理文件名中的特殊字符
        safe_title = self._sanitize_filename(title)[:50]
        filename = f'{stock_code}_{stock_name}_{year}_{safe_title}.pdf'
        return os.path.join(self.pdf_dir, filename)

    def _sanitize_filename(self, filename):
        """
        清理文件名中的特殊字符
        """
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '')
        return filename.strip()