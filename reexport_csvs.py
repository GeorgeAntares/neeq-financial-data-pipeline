"""
Re-export CSVs from on-disk annual-report PDFs with the current parser.

Skips 半年报 / 已取消 / 摘要 / 季报. Honors STOP.txt. Resumes via
output/analysis/reexport_done.txt.
"""
import json
import logging
import os
import time
from datetime import datetime

from config import OUTPUT_DIR, STOP_FILE
from data_exporter import DataExporter
from neeq_crawler import is_annual_report_title, is_valid_pdf
from pdf_parser import PDFParser

DONE_PATH = os.path.join(OUTPUT_DIR.get('log', 'output/log'), '..', 'analysis', 'reexport_done.txt')
STATUS_PATH = os.path.join('output', 'analysis', 'reexport_status.txt')
SUMMARY_PATH = os.path.join('output', 'analysis', 'reexport_summary.md')
PROGRESS_PATH = os.path.join('output', 'analysis', 'reexport_progress.jsonl')


def _analysis_paths():
    os.makedirs(os.path.join('output', 'analysis'), exist_ok=True)
    return (
        os.path.join('output', 'analysis', 'reexport_done.txt'),
        os.path.join('output', 'analysis', 'reexport_status.txt'),
        os.path.join('output', 'analysis', 'reexport_summary.md'),
        os.path.join('output', 'analysis', 'reexport_progress.jsonl'),
    )


def write_status(text):
    _, status_path, _, _ = _analysis_paths()
    with open(status_path, 'w', encoding='utf-8') as fh:
        fh.write(text)


def collect_pdfs():
    keep = []
    skip = []
    root = OUTPUT_DIR['pdf']
    for dirpath, _, files in os.walk(root):
        for name in files:
            if not name.lower().endswith('.pdf'):
                continue
            path = os.path.join(dirpath, name)
            if is_annual_report_title(name):
                keep.append(path)
            else:
                skip.append(path)
    return sorted(keep), sorted(skip)


def pdf_prefix(path):
    name = os.path.splitext(os.path.basename(path))[0]
    parts = name.split('_')
    if len(parts) >= 3 and parts[2].isdigit() and len(parts[2]) == 4:
        return f'{parts[0]}_{parts[1]}_{parts[2]}_'
    return None


def pdf_meta(path):
    name = os.path.splitext(os.path.basename(path))[0]
    parts = name.split('_')
    code = parts[0] if parts else ''
    cname = parts[1] if len(parts) > 1 else ''
    year = datetime.now().year
    if len(parts) >= 3 and parts[2].isdigit() and len(parts[2]) == 4:
        year = int(parts[2])
    return code, cname, year


def delete_skip_only_csvs(keep, skip, logger):
    keep_prefixes = {pdf_prefix(p) for p in keep}
    keep_prefixes.discard(None)
    skip_prefixes = {pdf_prefix(p) for p in skip}
    skip_prefixes.discard(None)
    orphan = skip_prefixes - keep_prefixes
    csv_dir = OUTPUT_DIR['csv']
    removed = 0
    if not os.path.isdir(csv_dir) or not orphan:
        return 0
    for name in os.listdir(csv_dir):
        if not name.endswith('.csv'):
            continue
        if any(name.startswith(prefix) for prefix in orphan):
            os.remove(os.path.join(csv_dir, name))
            removed += 1
    logger.info('deleted %s CSVs from 半年报/已取消-only prefixes', removed)
    return removed


def load_done():
    done_path, _, _, _ = _analysis_paths()
    if not os.path.exists(done_path):
        return set()
    with open(done_path, encoding='utf-8') as fh:
        return {line.strip() for line in fh if line.strip()}


def mark_done(path):
    done_path, _, _, _ = _analysis_paths()
    with open(done_path, 'a', encoding='utf-8') as fh:
        fh.write(path + '\n')


def stop_requested():
    return os.path.exists(STOP_FILE)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(message)s',
    )
    logger = logging.getLogger('reexport')
    _analysis_paths()
    write_status('RUNNING')
    keep, skip = collect_pdfs()
    logger.info('keep %s skip %s', len(keep), len(skip))
    delete_skip_only_csvs(keep, skip, logger)

    done = load_done()
    pending = [p for p in keep if os.path.abspath(p) not in done and p not in done]
    logger.info('already done %s pending %s', len(keep) - len(pending), len(pending))

    parser = PDFParser()
    exporter = DataExporter()
    stats = {
        'keep': len(keep),
        'skip': len(skip),
        'parsed': 0,
        'ok_bs': 0,
        'ok_is': 0,
        'ok_cf': 0,
        'all3': 0,
        'invalid_pdf': 0,
        'failed': 0,
        'stopped': False,
    }
    t0 = time.time()
    _, _, _, progress_path = _analysis_paths()

    try:
        for i, path in enumerate(pending, 1):
            if stop_requested():
                stats['stopped'] = True
                logger.warning('STOP.txt seen, exiting so the run can resume')
                break
            name = os.path.basename(path)
            logger.info('[%s/%s] %s', i, len(pending), name)
            rec = {'file': name, 'ok_bs': False, 'ok_is': False, 'ok_cf': False}
            if not is_valid_pdf(path):
                stats['invalid_pdf'] += 1
                rec['error'] = 'invalid_pdf'
                mark_done(os.path.abspath(path))
                with open(progress_path, 'a', encoding='utf-8') as fh:
                    fh.write(json.dumps(rec, ensure_ascii=False) + '\n')
                continue
            try:
                reports = parser.parse_pdf(path)
                code, cname, year = pdf_meta(path)
                exporter.export_all_reports(reports, code, cname, year)
                stats['parsed'] += 1
                bs = reports.get('balance_sheet') is not None
                ins = reports.get('income_statement') is not None
                cf = reports.get('cash_flow') is not None
                rec.update({'ok_bs': bs, 'ok_is': ins, 'ok_cf': cf})
                stats['ok_bs'] += int(bs)
                stats['ok_is'] += int(ins)
                stats['ok_cf'] += int(cf)
                stats['all3'] += int(bs and ins and cf)
            except Exception:
                logger.exception('parse failed: %s', path)
                stats['failed'] += 1
                rec['error'] = 'exception'
            mark_done(os.path.abspath(path))
            with open(progress_path, 'a', encoding='utf-8') as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + '\n')

        elapsed = time.time() - t0
        remaining = [p for p in keep if os.path.abspath(p) not in load_done() and p not in load_done()]
        lines = [
            '# CSV re-export',
            f'- keep PDFs: {stats["keep"]}',
            f'- skipped 半年报/已取消/摘要/季报: {stats["skip"]}',
            f'- parsed this run: {stats["parsed"]}',
            f'- invalid PDF: {stats["invalid_pdf"]}',
            f'- exceptions: {stats["failed"]}',
            f'- statements present (not None): BS {stats["ok_bs"]} IS {stats["ok_is"]} CF {stats["ok_cf"]} all3 {stats["all3"]}',
            f'- elapsed {elapsed:.0f}s',
            f'- remaining {len(remaining)}',
            f'- stopped: {stats["stopped"]}',
        ]
        _, _, summary_path, _ = _analysis_paths()
        with open(summary_path, 'w', encoding='utf-8') as fh:
            fh.write('\n'.join(lines) + '\n')
        print('\n'.join(lines))
        if stats['stopped'] or remaining:
            write_status('STOPPED')
            return 2
        write_status('DONE')
        return 0
    except Exception:
        logger.exception('reexport aborted')
        write_status('FAILED')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
