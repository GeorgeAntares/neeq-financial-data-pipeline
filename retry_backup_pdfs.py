"""
批量重新解析 00_待分类 目录下的备份 PDF

用法: python retry_backup_pdfs.py [--reprocess-all]

  --reprocess-all  不跳过已有完整三表的公司，全部重新解析并覆盖
"""
import os
import sys
import shutil
import logging
import argparse
from config import OUTPUT_DIR, STOP_FILE
from pdf_parser import PDFParser
from data_exporter import DataExporter

logger = logging.getLogger(__name__)


def setup_logging():
    log_file = os.path.join(OUTPUT_DIR['log'], 'retry_backup_20260729.log')
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )


def has_complete_csvs(stock_code, csv_dir):
    """检查公司是否已有完整的三表CSV"""
    report_names = ['合并资产负债表', '合并利润表', '合并现金流量表']
    for rn in report_names:
        found = False
        for f in os.listdir(csv_dir):
            if f.startswith(f'{stock_code}_') and f.endswith(f'_{rn}.csv'):
                if os.path.getsize(os.path.join(csv_dir, f)) > 200:
                    found = True
                    break
        if not found:
            return False
    return True


def main():
    setup_logging()
    
    parser_arg = argparse.ArgumentParser(description='批量重新解析备份目录下的PDF')
    parser_arg.add_argument('--reprocess-all', action='store_true',
                            help='不跳过已有完整三表的公司，全部重新解析')
    args = parser_arg.parse_args()
    
    csv_dir = OUTPUT_DIR['csv']
    pdf_dir = OUTPUT_DIR['pdf']
    backup_dir = os.path.join(pdf_dir, '00_待分类')
    
    if not os.path.exists(backup_dir):
        logger.error(f'备份目录不存在: {backup_dir}')
        return
    
    # 收集所有待处理PDF
    backup_pdfs = []
    for f in os.listdir(backup_dir):
        if f.endswith('.pdf'):
            # 从文件名提取股票代码
            code = f.split('_')[0]
            backup_pdfs.append((code, f, os.path.join(backup_dir, f)))
    
    logger.info(f'备份目录中共有 {len(backup_pdfs)} 个PDF文件')
    
    pdf_parser = PDFParser()
    exporter = DataExporter()
    
    skipped_complete = 0
    skipped_no_name = 0
    processed = 0
    failed = 0
    total_parsed = {'balance_sheet': 0, 'income_statement': 0, 'cash_flow': 0}
    
    for i, (code, filename, src_path) in enumerate(backup_pdfs, 1):
        logger.info(f'\n[{i}/{len(backup_pdfs)}] {filename}')
        
        # 提取代码和名称
        parts = filename.split('_')
        if len(parts) < 2:
            logger.warning(f'无法从文件名提取股票信息，跳过: {filename}')
            skipped_no_name += 1
            continue
        
        stock_code = parts[0]
        stock_name = parts[1] if len(parts) > 1 else ''
        
        # 检查是否已有完整数据
        if not args.reprocess_all and has_complete_csvs(stock_code, csv_dir):
            logger.info(f'{stock_code} 已有完整三表，跳过')
            skipped_complete += 1
            continue
        
        # 移动PDF到正式目录
        dst_path = os.path.join(pdf_dir, filename)
        try:
            shutil.move(src_path, dst_path)
            src_path = dst_path  # 更新路径
        except Exception as e:
            logger.warning(f'移动PDF失败: {e}，尝试直接解析原路径')
        
        # 解析PDF
        logger.info(f'开始解析: {stock_code} {stock_name}')
        try:
            reports = pdf_parser.parse_pdf(src_path)
        except Exception as e:
            logger.error(f'解析异常: {e}')
            failed += 1
            continue
        
        # 导出结果
        exporter.export_all_reports(reports, stock_code, stock_name, 2025)
        
        parsed_count = 0
        for key, df in reports.items():
            if df is not None:
                parsed_count += 1
                total_parsed[key] += 1
        
        logger.info(f'结果: 成功提取 {parsed_count}/3 张报表')
        
        if parsed_count > 0:
            processed += 1
        else:
            failed += 1
        
        # 检查停止标记
        if os.path.exists(STOP_FILE):
            logger.info('检测到停止标记，退出...')
            os.remove(STOP_FILE)
            break
    
    # 统计总结
    logger.info('\n' + '=' * 50)
    logger.info('批量重新解析完成')
    logger.info('=' * 50)
    logger.info(f'总PDF数: {len(backup_pdfs)}')
    logger.info(f'跳过(已有完整数据): {skipped_complete}')
    logger.info(f'跳过(无法识别): {skipped_no_name}')
    logger.info(f'成功处理: {processed}')
    logger.info(f'解析失败: {failed}')
    logger.info(f'各报表提取数: 资产负债表={total_parsed["balance_sheet"]}, '
                f'利润表={total_parsed["income_statement"]}, '
                f'现金流量表={total_parsed["cash_flow"]}')


if __name__ == '__main__':
    main()
