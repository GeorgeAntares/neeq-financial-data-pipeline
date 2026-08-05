import logging
import argparse
from datetime import datetime
import os
from config import PLATE_CODES, CATEGORY_CODES, OUTPUT_DIR, STOP_FILE
from cninfo_api import CNInfoAPI
from pdf_parser import PDFParser
from data_exporter import DataExporter


def setup_logging():
    """设置日志配置"""
    log_file = OUTPUT_DIR['log'] + f'/crawler_{datetime.now().strftime("%Y%m%d")}.log'
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description='中小微上市公司财报爬虫')
    
    parser.add_argument('--source', type=str, default='cninfo',
                        choices=['cninfo', 'neeq'],
                        help='数据源: cninfo(巨潮资讯网) 或 neeq(新三板)')
    parser.add_argument('--plate', type=str, default='szcy', 
                        help=f'板块代码，可选: {", ".join(PLATE_CODES.keys())}')
    parser.add_argument('--category', type=str, default='年报',
                        help=f'公告类型，可选: {", ".join(CATEGORY_CODES.keys())}')
    parser.add_argument('--year', type=int, default=datetime.now().year - 1,
                        help='年份（默认去年）')
    parser.add_argument('--start-date', type=str, default=None,
                        help='开始日期，格式 YYYY-MM-DD')
    parser.add_argument('--end-date', type=str, default=None,
                        help='结束日期，格式 YYYY-MM-DD')
    parser.add_argument('--stock', type=str, default=None,
                        help='股票代码（可选）')
    parser.add_argument('--max-pages', type=int, default=0,
                        help='最大翻页/搜索结果页数，0表示不限')
    parser.add_argument('--start-page', type=int, default=1,
                        help='起始页码（用于跳过大段历史数据）')
    parser.add_argument('--skip-download', action='store_true',
                        help='跳过PDF下载，仅搜索公告列表')
    parser.add_argument('--resume', action='store_true',
                        help='续爬模式：从已有 announcements_list.csv 加载公告列表，跳过搜索阶段')
    parser.add_argument('--skip-parse', action='store_true',
                        help='仅下载PDF，跳过解析（纯下载模式）')
    
    return parser.parse_args()


def run_cninfo(args, logger):
    """巨潮资讯网模式"""
    plate_code = PLATE_CODES.get(args.plate, args.plate)
    logger.info(f'板块: {args.plate} ({plate_code})')
    
    category_code = CATEGORY_CODES.get(args.category, args.category)
    logger.info(f'公告类型: {args.category} ({category_code})')
    
    if args.start_date and args.end_date:
        start_date = args.start_date
        end_date = args.end_date
    else:
        year = args.year
        start_date = f'{year}-01-01'
        end_date = f'{year}-12-31'
    logger.info(f'日期范围: {start_date} ~ {end_date}')
    
    api = CNInfoAPI()
    parser = PDFParser()
    exporter = DataExporter()
    
    try:
        logger.info('开始搜索公告...')
        announcements = api.search_announcements(
            plate=plate_code,
            category=category_code,
            start_date=start_date,
            end_date=end_date,
            stock_code=args.stock,
            max_pages=args.max_pages
        )
        
        if not announcements:
            logger.warning('未找到符合条件的公告')
            return
        
        logger.info(f'共找到 {len(announcements)} 条公告')
        exporter.export_announcements_list(announcements)
        
        if args.skip_download:
            logger.info('已跳过PDF下载')
            return
        
        process_announcements(announcements, args, api, parser, exporter, logger, source='cninfo')
        
    finally:
        api.close()


def run_neeq(args, logger):
    """新三板模式"""
    from neeq_crawler import search_annual_reports, download_pdf
    
    if args.start_date and args.end_date:
        start_date = args.start_date
        end_date = args.end_date
    else:
        year = args.year
        start_date = f'{year}-01-01'
        end_date = f'{year}-12-31'
    
    logger.info(f'数据源: 新三板 (neeq.cs.com.cn)')
    logger.info(f'公告发布日期范围: {start_date} ~ {end_date}')
    logger.info(f'搜索方式: 翻页过滤（只抓"年度报告"）')
    logger.info(f'起始页码: {args.start_page}')
    
    parser = PDFParser()
    exporter = DataExporter()
    
    max_pages = args.max_pages if args.max_pages > 0 else 5000
    # 如果指定了 start_page，则 max_pages 是从 start_page 起翻的总页数上限
    max_pages = args.start_page + max_pages - 1
    logger.info(f'翻页范围: {args.start_page} ~ {max_pages}（约{max_pages - args.start_page + 1}页）')
    
    # 搜索年报公告
    logger.info('开始搜索新三板年度报告公告...')
    announcements = search_annual_reports(
        start_date=start_date,
        end_date=end_date,
        max_pages=max_pages,
        start_page=args.start_page
    )
    
    if not announcements:
        logger.warning('未找到符合条件的公告')
        return
    
    logger.info(f'共找到 {len(announcements)} 条年度报告公告')
    exporter.export_announcements_list(announcements)
    
    if args.skip_download:
        logger.info('已跳过PDF下载')
        return
    
    # 统计跳过/处理数量
    skipped = 0
    processed = 0
    
    report_names_cn = ['合并资产负债表', '合并利润表', '合并现金流量表']
    csv_dir = OUTPUT_DIR['csv']
    
    def _has_complete_csvs(stock_code):
        for rn in report_names_cn:
            found = False
            for f in os.listdir(csv_dir):
                if f.startswith(f'{stock_code}_') and f.endswith(f'_{rn}.csv'):
                    if os.path.getsize(os.path.join(csv_dir, f)) > 200:
                        found = True
                        break
            if not found:
                return False
        return True
    
    # 处理每条公告
    for i, ann in enumerate(announcements, 1):
        stock_code = ann.get('secCode', '')
        stock_name = ann.get('secName', '')
        title = ann.get('announcementTitle', '').strip()
        announcement_date = ann.get('announcementDate', '')
        adjunct_url = ann.get('adjunctUrl', '')
        
        # 断点续爬：跳过已完整解析的公司
        if _has_complete_csvs(stock_code):
            skipped += 1
            continue
        
        logger.info(f'\n[{i}/{len(announcements)}] {stock_code} {stock_name}')
        logger.info(f'标题: {title}')
        logger.info(f'公告日期: {announcement_date}')
        
        # 下载PDF
        pdf_path = exporter.get_pdf_save_path(stock_code, stock_name, args.year, title)
        if not download_pdf(adjunct_url, pdf_path):
            continue
        
        # 解析PDF
        logger.info('开始解析PDF...')
        reports = parser.parse_pdf(pdf_path)
        
        # 导出数据
        exporter.export_all_reports(reports, stock_code, stock_name, args.year)
        
        parsed_count = sum(1 for v in reports.values() if v is not None)
        logger.info(f'解析完成，成功提取 {parsed_count}/3 张报表')
        processed += 1
        
        # 检查优雅停止标记
        if os.path.exists(STOP_FILE):
            logger.info('检测到停止标记，将在当前公司处理完毕后退出...')
            os.remove(STOP_FILE)
            break
    
    logger.info(f'\n本次: 跳过 {skipped} 家（已完整）, 新处理 {processed} 家')
    
    logger.info('\n' + '=' * 50)
    logger.info('新三板爬虫任务完成')
    logger.info('=' * 50)


def run_neeq_resume(args, logger):
    """新三板续爬模式：从 CSV 加载公告列表，跳过搜索"""
    import csv
    from neeq_crawler import download_pdf
    
    csv_path = os.path.join(OUTPUT_DIR['csv'], 'announcements_list.csv')
    if not os.path.exists(csv_path):
        logger.error(f'公告列表不存在: {csv_path}，请先执行一次完整搜索')
        return
    
    announcements = []
    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if '年度报告' in row.get('announcementTitle', '') and '摘要' not in row.get('announcementTitle', ''):
                announcements.append(row)
    
    logger.info(f'续爬模式：从 {csv_path} 加载 {len(announcements)} 条年度报告公告')
    
    skip_parse = args.skip_parse
    if skip_parse:
        logger.info('纯下载模式：仅下载PDF，跳过解析')
    
    parser = PDFParser() if not skip_parse else None
    exporter = DataExporter()
    
    skipped = 0
    processed = 0
    moved_from_backup = 0
    
    report_names_cn = ['合并资产负债表', '合并利润表', '合并现金流量表']
    csv_dir = OUTPUT_DIR['csv']
    pdf_dir = OUTPUT_DIR['pdf']
    backup_dir = os.path.join(pdf_dir, '00_待分类')
    
    # 预扫描备份目录中的 PDF
    backup_pdfs = {}
    if os.path.exists(backup_dir):
        for f in os.listdir(backup_dir):
            if f.endswith('.pdf'):
                code = f.split('_')[0]
                backup_pdfs[code] = os.path.join(backup_dir, f)
    logger.info(f'备份目录中发现 {len(backup_pdfs)} 个PDF')
    
    def _has_complete_csvs(stock_code):
        for rn in report_names_cn:
            found = False
            for d in [csv_dir, backup_dir]:
                if not os.path.exists(d):
                    continue
                for f in os.listdir(d):
                    if f.startswith(f'{stock_code}_') and f.endswith(f'_{rn}.csv'):
                        if os.path.getsize(os.path.join(d, f)) > 200:
                            found = True
                            break
                if found:
                    break
            if not found:
                return False
        return True
    
    def _has_pdf(stock_code):
        """纯下载模式：检查是否已有该公司的PDF"""
        for f in os.listdir(pdf_dir):
            if f.startswith(f'{stock_code}_') and f.endswith('.pdf'):
                if os.path.getsize(os.path.join(pdf_dir, f)) > 1000:
                    return True
        return False
    
    for i, ann in enumerate(announcements, 1):
        stock_code = ann.get('secCode', '')
        stock_name = ann.get('secName', '')
        title = ann.get('announcementTitle', '').strip()
        announcement_date = ann.get('announcementDate', '')
        adjunct_url = ann.get('adjunctUrl', '')
        
        # 纯下载模式：跳过已有PDF的公司；非纯下载：跳过已有完整CSV的公司
        if skip_parse:
            if _has_pdf(stock_code) or stock_code in backup_pdfs:
                skipped += 1
                continue
        else:
            if _has_complete_csvs(stock_code):
                skipped += 1
                continue
        
        logger.info(f'\n[{i}/{len(announcements)}] {stock_code} {stock_name}')
        logger.info(f'标题: {title}')
        logger.info(f'公告日期: {announcement_date}')
        
        pdf_path = exporter.get_pdf_save_path(stock_code, stock_name, args.year, title)
        
        # 优先使用备份目录中已有的PDF
        if stock_code in backup_pdfs and os.path.exists(backup_pdfs[stock_code]):
            import shutil
            shutil.move(backup_pdfs[stock_code], pdf_path)
            logger.info(f'从备份目录恢复PDF: {os.path.basename(pdf_path)}')
            moved_from_backup += 1
            processed += 1
            continue
        elif not download_pdf(adjunct_url, pdf_path):
            continue
        
        if skip_parse:
            logger.info('已下载（跳过解析）')
            processed += 1
        else:
            logger.info('开始解析PDF...')
            reports = parser.parse_pdf(pdf_path)
            exporter.export_all_reports(reports, stock_code, stock_name, args.year)
            
            parsed_count = sum(1 for v in reports.values() if v is not None)
            logger.info(f'解析完成，成功提取 {parsed_count}/3 张报表')
            processed += 1
        
        if os.path.exists(STOP_FILE):
            logger.info('检测到停止标记，将在当前公司处理完毕后退出...')
            os.remove(STOP_FILE)
            break
    
    if skip_parse:
        logger.info(f'\n本次: 跳过 {skipped} 家（已有PDF）, 恢复备份 {moved_from_backup} 个, 下载 {processed - moved_from_backup} 个')
    else:
        logger.info(f'\n本次: 跳过 {skipped} 家（已完整）, 恢复备份 {moved_from_backup} 个PDF, 新处理 {processed} 家')
    logger.info('\n' + '=' * 50)
    logger.info('新三板续爬任务完成')
    logger.info('=' * 50)


def process_announcements(announcements, args, api, parser, exporter, logger, source='cninfo'):
    """处理公告列表"""
    for i, ann in enumerate(announcements, 1):
        stock_code = ann.get('secCode', '')
        stock_name = ann.get('secName', '')
        title = ann.get('announcementTitle', '').strip()
        announcement_date = ann.get('announcementDate', '')
        adjunct_url = ann.get('adjunctUrl', '')
        
        logger.info(f'\n[{i}/{len(announcements)}] {stock_code} {stock_name}')
        logger.info(f'标题: {title}')
        logger.info(f'公告日期: {announcement_date}')
        
        adjunct_type = ann.get('adjunctType', '')
        if adjunct_type.upper() != 'PDF':
            logger.warning(f'非PDF格式({adjunct_type})，跳过')
            continue
        
        if '年度报告' not in title or '摘要' in title:
            logger.info(f'非年度报告正文，跳过')
            continue
        
        pdf_path = exporter.get_pdf_save_path(stock_code, stock_name, args.year, title)
        if source == 'neeq':
            from neeq_crawler import download_pdf
            if not download_pdf(adjunct_url, pdf_path):
                continue
        else:
            if not api.download_pdf(adjunct_url, pdf_path):
                continue
        
        logger.info('开始解析PDF...')
        reports = parser.parse_pdf(pdf_path)
        
        exporter.export_all_reports(reports, stock_code, stock_name, args.year)
        
        parsed_count = sum(1 for v in reports.values() if v is not None)
        logger.info(f'解析完成，成功提取 {parsed_count}/3 张报表')
        
        if os.path.exists(STOP_FILE):
            logger.info('检测到停止标记，将在当前公司处理完毕后退出...')
            os.remove(STOP_FILE)
            break


def main():
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info('=' * 50)
    logger.info('中小微上市公司财报爬虫启动')
    logger.info('=' * 50)
    
    args = parse_args()
    
    try:
        if args.source == 'neeq':
            if args.resume:
                run_neeq_resume(args, logger)
            else:
                run_neeq(args, logger)
        else:
            run_cninfo(args, logger)
    except Exception as e:
        logger.error(f'爬虫执行失败: {e}', exc_info=True)


if __name__ == '__main__':
    main()
