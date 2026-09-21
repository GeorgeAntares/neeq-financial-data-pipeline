import logging
import argparse
from datetime import datetime
import os
import shutil
import sys
from config import (
    PLATE_CODES,
    CATEGORY_CODES,
    OUTPUT_DIR,
    STOP_FILE,
    CRAWL_DB_PATH,
)
from cninfo_api import CNInfoAPI
from database import CrawlRepository, infer_report_year
from neeq_crawler import is_annual_report_title
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
                        help='公告发布日期年份（默认去年）')
    parser.add_argument('--start-date', type=str, default=None,
                        help='开始日期，格式 YYYY-MM-DD')
    parser.add_argument('--end-date', type=str, default=None,
                        help='结束日期，格式 YYYY-MM-DD')
    parser.add_argument('--stock', type=str, default=None,
                        help='股票代码（可选）')
    parser.add_argument('--max-pages', type=int, default=0,
                        help='最大翻页/搜索结果页数，0表示不限')
    parser.add_argument('--start-page', type=int, default=1,
                        help='查询结果起始页（故障恢复使用，通常不设置）')
    parser.add_argument('--skip-download', action='store_true',
                        help='跳过PDF下载，仅搜索公告列表')
    parser.add_argument('--resume', action='store_true',
                        help='兼容模式：从旧 announcements_list.csv 导入SQLite并续爬')
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


def _has_complete_csvs(stock_code, report_year):
    """Check whether all three financial statement CSVs already exist for a given stock and year."""
    report_names = ['合并资产负债表', '合并利润表', '合并现金流量表']
    csv_dir = OUTPUT_DIR['csv']
    year_marker = f'_{report_year}_'
    for report_name in report_names:
        found = any(
            filename.startswith(f'{stock_code}_')
            and year_marker in filename
            and filename.endswith(f'_{report_name}.csv')
            and os.path.getsize(os.path.join(csv_dir, filename)) >= 1024
            for filename in os.listdir(csv_dir)
        )
        if not found:
            return False
    return True


def _find_backup_pdfs():
    from neeq_crawler import is_valid_pdf

    backup_dir = os.path.join(OUTPUT_DIR['pdf'], '00_待分类')
    backup_pdfs = {}
    if not os.path.isdir(backup_dir):
        return backup_pdfs

    for filename in os.listdir(backup_dir):
        file_path = os.path.join(backup_dir, filename)
        if filename.lower().endswith('.pdf') and is_valid_pdf(file_path):
            stock_code = filename.split('_')[0]
            backup_pdfs[stock_code] = file_path
    return backup_pdfs


def _consume_stop_request(logger):
    if not os.path.exists(STOP_FILE):
        return False
    logger.info('检测到停止标记，将在当前公司处理完毕后退出...')
    os.remove(STOP_FILE)
    return True


def _process_neeq_announcements(
    announcements,
    args,
    logger,
    repository,
):
    """Download NEEQ PDFs and persist each state transition."""
    from neeq_crawler import download_pdf, is_valid_pdf

    skip_parse = args.skip_parse
    parser = None if skip_parse else PDFParser()
    exporter = DataExporter()
    backup_pdfs = _find_backup_pdfs()
    stats = {
        'downloaded': 0,
        'existing': 0,
        'restored': 0,
        'failed': 0,
        'parsed': 0,
        'parse_failed': 0,
        'skipped_parse': 0,
        'interrupted': False,
    }

    if skip_parse:
        logger.info('纯下载模式：仅下载PDF，跳过解析')
    logger.info(f'备份目录中发现 {len(backup_pdfs)} 个有效PDF')

    for index, announcement in enumerate(announcements, 1):
        stock_code = str(announcement.get('secCode') or '').strip()
        stock_name = str(announcement.get('secName') or '').strip()
        title = str(announcement.get('announcementTitle') or '').strip()
        announcement_date = str(
            announcement.get('announcementDate') or ''
        ).strip()
        pdf_url = str(announcement.get('adjunctUrl') or '').strip()
        if not pdf_url:
            logger.warning(f'[{index}] 公告缺少PDF地址，跳过')
            continue

        report_year = infer_report_year(title) or args.year
        pdf_path = exporter.get_pdf_save_path(
            stock_code,
            stock_name,
            report_year,
            title,
        )

        if not skip_parse and _has_complete_csvs(stock_code, report_year):
            stats['skipped_parse'] += 1
            if _consume_stop_request(logger):
                stats['interrupted'] = True
                break
            continue

        logger.info(f'\n[{index}/{len(announcements)}] {stock_code} {stock_name}')
        logger.info(f'标题: {title}')
        logger.info(f'公告日期: {announcement_date}')

        record = repository.get_announcement('neeq', pdf_url)
        recorded_path = record.get('file_path') if record else None
        active_pdf_path = None

        for candidate in (recorded_path, pdf_path):
            if candidate and is_valid_pdf(candidate):
                active_pdf_path = candidate
                break

        if active_pdf_path is not None:
            repository.mark_downloaded(
                'neeq',
                pdf_url,
                file_path=active_pdf_path,
                file_size=os.path.getsize(active_pdf_path),
            )
            stats['existing'] += 1
        else:
            backup_path = backup_pdfs.pop(stock_code, None)
            if backup_path and is_valid_pdf(backup_path):
                shutil.move(backup_path, pdf_path)
                active_pdf_path = pdf_path
                repository.mark_downloaded(
                    'neeq',
                    pdf_url,
                    file_path=active_pdf_path,
                    file_size=os.path.getsize(active_pdf_path),
                )
                stats['restored'] += 1
                logger.info(f'从备份目录恢复PDF: {os.path.basename(pdf_path)}')
            else:
                repository.mark_downloading('neeq', pdf_url)
                if not download_pdf(pdf_url, pdf_path):
                    repository.mark_failed(
                        'neeq',
                        pdf_url,
                        'PDF download failed after retries',
                    )
                    stats['failed'] += 1
                    if _consume_stop_request(logger):
                        stats['interrupted'] = True
                        break
                    continue

                active_pdf_path = pdf_path
                repository.mark_downloaded(
                    'neeq',
                    pdf_url,
                    file_path=active_pdf_path,
                    file_size=os.path.getsize(active_pdf_path),
                )
                stats['downloaded'] += 1

        if skip_parse:
            if _consume_stop_request(logger):
                stats['interrupted'] = True
                break
            continue

        logger.info('开始解析PDF...')
        try:
            reports = parser.parse_pdf(active_pdf_path)
        except Exception:
            # 单个损坏/加密/超大 PDF 不应中断整批任务，记录堆栈后继续下一个
            logger.exception(f'解析PDF失败，跳过: {active_pdf_path}')
            stats['parse_failed'] += 1
            if _consume_stop_request(logger):
                stats['interrupted'] = True
                break
            continue

        exporter.export_all_reports(
            reports,
            stock_code,
            stock_name,
            report_year,
        )
        parsed_count = sum(1 for value in reports.values() if value is not None)
        if parsed_count == 0:
            # 三张报表全部解析失败，不计入成功，便于事后定位问题文件
            logger.warning(f'{stock_code} {stock_name} 未提取到任何有效报表')
            stats['parse_failed'] += 1
        else:
            logger.info(f'解析完成，成功提取 {parsed_count}/3 张报表')
            stats['parsed'] += 1

        if _consume_stop_request(logger):
            stats['interrupted'] = True
            break

    logger.info(
        '下载统计: 新下载 %s，已有 %s，恢复备份 %s，失败 %s',
        stats['downloaded'],
        stats['existing'],
        stats['restored'],
        stats['failed'],
    )
    if not skip_parse:
        logger.info(
            '解析统计: 完成 %s，已有CSV跳过 %s，解析失败 %s',
            stats['parsed'],
            stats['skipped_parse'],
            stats['parse_failed'],
        )
    return stats


def run_neeq(args, logger):
    """新三板模式"""
    from neeq_crawler import search_annual_reports

    if args.start_date and args.end_date:
        start_date = args.start_date
        end_date = args.end_date
    else:
        start_date = f'{args.year}-01-01'
        end_date = f'{args.year}-12-31'

    logger.info('数据源: 全国股转系统 (www.neeq.com.cn)')
    logger.info(f'公告发布日期范围: {start_date} ~ {end_date}')
    logger.info('搜索方式: 日期范围 + 年度报告分类')

    repository = CrawlRepository(CRAWL_DB_PATH)
    run_id = None
    run_status = 'failed'
    announcements = []
    stats = {'downloaded': 0, 'failed': 0}

    try:
        recovered = repository.recover_incomplete_downloads()
        if recovered:
            logger.info(f'恢复 {recovered} 条上次中断的下载任务')
        run_id = repository.start_run(
            source='neeq',
            start_date=start_date,
            end_date=end_date,
            report_type='annual',
        )
        logger.info('开始搜索新三板年度报告公告...')
        announcements = search_annual_reports(
            start_date=start_date,
            end_date=end_date,
            max_pages=args.max_pages,
            start_page=args.start_page,
        )
        repository.upsert_announcements(
            announcements,
            source='neeq',
            report_type='annual',
        )

        if not announcements:
            logger.warning('未找到符合条件的公告')
            run_status = 'completed'
            return

        logger.info(f'共找到 {len(announcements)} 条年度报告公告')
        DataExporter().export_announcements_list(announcements)

        if args.skip_download:
            logger.info('已跳过PDF下载，公告元数据已写入SQLite')
            run_status = 'completed'
            return

        stats = _process_neeq_announcements(
            announcements,
            args,
            logger,
            repository,
        )
        run_status = 'interrupted' if stats['interrupted'] else 'completed'
    finally:
        try:
            if run_id is not None:
                repository.finish_run(
                    run_id,
                    status=run_status,
                    discovered_count=len(announcements),
                    downloaded_count=stats['downloaded'],
                    failed_count=stats['failed'],
                )
        finally:
            repository.close()

    logger.info('\n' + '=' * 50)
    logger.info('新三板爬虫任务完成')
    logger.info('=' * 50)


def run_neeq_resume(args, logger):
    """从旧公告 CSV 导入 SQLite，然后按数据库状态续爬。"""
    import csv

    csv_path = os.path.join(OUTPUT_DIR['csv'], 'announcements_list.csv')
    if not os.path.exists(csv_path):
        logger.error(f'公告列表不存在: {csv_path}，请先执行一次完整搜索')
        return

    announcements = []
    with open(csv_path, 'r', encoding='utf-8-sig') as file:
        for row in csv.DictReader(file):
            title = row.get('announcementTitle', '')
            if is_annual_report_title(title):
                announcements.append(row)

    logger.info(
        f'续爬模式：从 {csv_path} 加载 {len(announcements)} 条年度报告公告'
    )
    with CrawlRepository(CRAWL_DB_PATH) as repository:
        repository.recover_incomplete_downloads()
        repository.upsert_announcements(
            announcements,
            source='neeq',
            report_type='annual',
        )
        if args.skip_download:
            logger.info('公告元数据已导入SQLite，跳过PDF下载')
            return
        _process_neeq_announcements(
            announcements,
            args,
            logger,
            repository,
        )


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
        
        if not is_annual_report_title(title):
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
    except Exception:
        # 记录完整堆栈，并以非零退出码结束，
        # 否则定时任务/CI 无法感知失败，会误判为执行成功
        logger.exception('爬虫执行失败')
        return 1
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
