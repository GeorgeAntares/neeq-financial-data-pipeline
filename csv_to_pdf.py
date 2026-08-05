"""
CSV 转财报格式 HTML/PDF
读取 output/csv/ 中的财报 CSV，生成中国上市公司财务报表格式的 HTML 文件。
在浏览器中打开 HTML → 打印 → 另存为 PDF 即可获得正式财报 PDF。
"""

import os
import csv
import re
import glob
import webbrowser
from config import OUTPUT_DIR


def format_number(value):
    """将数值格式化为千分位分隔的字符串，保留两位小数"""
    if value is None or value == '' or value == '-':
        return '-'
    try:
        num = float(str(value).replace(',', ''))
        if num == int(num):
            return f'{int(num):,}'
        else:
            return f'{num:,.2f}'
    except (ValueError, TypeError):
        return str(value)


def is_number_column(col_name):
    """判断是否为数值列（期末余额/期初余额等）"""
    return any(kw in str(col_name) for kw in ['余额', '金额', '合计', '总计'])


def is_section_header(row_text):
    """判断是否为分类标题行（如 流动资产：, 非流动资产：）"""
    if not row_text:
        return False
    text = str(row_text).strip()
    return text.endswith('：') or text.endswith(':') or text in [
        '流动资产', '非流动资产', '流动负债', '非流动负债',
        '所有者权益', '股东权益', '负债和所有者权益',
    ]


def is_noise_row(row):
    """判断是否为无效数据行"""
    values = [str(v).strip() for v in row if v and str(v).strip()]
    if len(values) == 0:
        return True
    # 全是数字列有值，但项目列为空或为纯数字的跳过
    project = str(row[0]).strip() if len(row) > 0 else ''
    if project in ['', '项目', '期末余额', '期初余额', '本期金额', '上期金额', '年初余额']:
        return True
    if re.match(r'^\d{4}\s*年', project):  # "2024 年度" 之类
        return True
    return False


def generate_html_for_csv(csv_path, output_dir):
    """为单个 CSV 文件生成 HTML"""
    # 从文件名解析信息
    basename = os.path.basename(csv_path)
    name_no_ext = basename.replace('.csv', '')
    parts = name_no_ext.split('_', 2)
    stock_code = parts[0] if len(parts) > 0 else ''
    stock_name = parts[1] if len(parts) > 1 else ''
    rest = parts[2] if len(parts) > 2 else ''

    # 从剩余部分解析年份和报表类型
    year = '2025'
    report_type = rest
    year_match = re.match(r'(\d{4})_(.+)', rest)
    if year_match:
        year = year_match.group(1)
        report_type = year_match.group(2)

    # 读取 CSV
    rows = []
    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        for row in reader:
            rows.append(row)

    if len(rows) < 2:
        return None

    # 解析表头
    header = rows[0]
    data_rows = []
    for row in rows[1:]:
        if not is_noise_row(row):
            data_rows.append(row)

    if len(data_rows) == 0:
        return None

    # 确定报表标题
    report_titles = {
        '合并资产负债表': '合并资产负债表',
        '合并利润表': '合并利润表',
        '合并现金流量表': '合并现金流量表',
    }
    title_full = report_titles.get(report_type, report_type)
    title_text = f'{stock_name} ({stock_code})'
    subtitle_text = f'{title_full}'
    date_text = f'{year}年12月31日' if '负债表' in title_full else f'{year}年度'
    unit_text = '单位：人民币元'

    # 构建 HTML 表格行
    table_rows_html = ''
    # 表头行
    th_cells = ''
    for col in header:
        th_cells += f'<th>{col}</th>'
    table_rows_html += f'<tr class="header-row">{th_cells}</tr>'

    for row in data_rows:
        if len(row) == 0:
            continue

        project = str(row[0]).strip() if len(row) > 0 else ''
        is_header = is_section_header(project)

        td_cells = ''
        for i, cell in enumerate(row):
            cell_str = str(cell).strip() if cell else ''
            if i == 0:
                # 项目列
                if is_header:
                    td_cells += f'<td class="section-header">{cell_str}</td>'
                else:
                    indent = '　　' if not project.startswith('其中') and not project.startswith('1.') and not project.startswith('2.') and not project.startswith('3.') and not project.startswith('4.') and not project.startswith('（') else ''
                    td_cells += f'<td class="project-name">{indent}{cell_str}</td>'
            else:
                # 数值列
                td_cells += f'<td class="number-cell">{format_number(cell_str)}</td>'

        row_class = 'section-row' if is_header else 'data-row'
        table_rows_html += f'<tr class="{row_class}">{td_cells}</tr>'

    # 构建完整 HTML
    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title_text} - {subtitle_text}</title>
<style>
    @media print {{
        @page {{
            size: A4 landscape;
            margin: 15mm;
        }}
        body {{
            -webkit-print-color-adjust: exact;
            print-color-adjust: exact;
        }}
        .page-break {{
            page-break-before: always;
        }}
    }}

    * {{
        margin: 0;
        padding: 0;
        box-sizing: border-box;
    }}

    body {{
        font-family: "SimSun", "宋体", "Noto Serif CJK SC", serif;
        font-size: 13px;
        color: #000;
        background: #fff;
        padding: 30px 40px;
        line-height: 1.6;
    }}

    .report-container {{
        max-width: 1200px;
        margin: 0 auto;
    }}

    .report-title {{
        text-align: center;
        font-size: 18px;
        font-weight: bold;
        margin-bottom: 4px;
        font-family: "SimHei", "黑体", "Noto Sans CJK SC", sans-serif;
    }}

    .report-subtitle {{
        text-align: center;
        font-size: 15px;
        font-weight: bold;
        margin-bottom: 2px;
        font-family: "SimHei", "黑体", sans-serif;
    }}

    .report-info {{
        display: flex;
        justify-content: space-between;
        font-size: 12px;
        margin-bottom: 10px;
        border-bottom: 1px solid #000;
        padding-bottom: 4px;
    }}

    .report-info .date {{
        text-align: left;
    }}

    .report-info .unit {{
        text-align: right;
    }}

    table {{
        width: 100%;
        border-collapse: collapse;
        table-layout: auto;
    }}

    th {{
        text-align: center;
        font-weight: bold;
        padding: 6px 8px;
        border-top: 2px solid #000;
        border-bottom: 1px solid #000;
        background-color: #f0f0f0;
        font-size: 12px;
        white-space: nowrap;
    }}

    .data-row td {{
        padding: 3px 8px;
        border-bottom: 1px solid #ddd;
    }}

    .section-row td {{
        padding: 5px 8px;
        font-weight: bold;
        background-color: #fafafa;
        border-top: 1px solid #999;
        border-bottom: 1px solid #999;
    }}

    .section-header {{
        font-weight: bold;
        font-size: 13px;
    }}

    .project-name {{
        text-align: left;
        white-space: nowrap;
        min-width: 200px;
    }}

    .number-cell {{
        text-align: right;
        white-space: nowrap;
        font-family: "Consolas", "Courier New", monospace;
        min-width: 120px;
    }}

    .header-row th {{
        font-family: "SimHei", "黑体", sans-serif;
    }}

    .footer-info {{
        text-align: right;
        font-size: 11px;
        color: #666;
        margin-top: 20px;
        border-top: 1px solid #ccc;
        padding-top: 8px;
    }}

    .btn-print {{
        position: fixed;
        top: 15px;
        right: 20px;
        padding: 8px 20px;
        background: #1a73e8;
        color: #fff;
        border: none;
        border-radius: 4px;
        cursor: pointer;
        font-size: 14px;
        z-index: 1000;
    }}
    .btn-print:hover {{
        background: #1557b0;
    }}
    @media print {{
        .btn-print {{
            display: none;
        }}
    }}
</style>
</head>
<body>
<button class="btn-print" onclick="window.print()">打印 / 导出 PDF</button>

<div class="report-container">
    <div class="report-title">{title_text}</div>
    <div class="report-subtitle">{subtitle_text}</div>
    <div class="report-info">
        <span class="date">{date_text}</span>
        <span class="unit">{unit_text}</span>
    </div>

    <table>
        {table_rows_html}
    </table>

    <div class="footer-info">
        数据来源：巨潮资讯网 (cninfo.com.cn) | 由爬虫程序自动生成
    </div>
</div>
</body>
</html>'''

    # 写入 HTML 文件
    html_filename = f'{name_no_ext}.html'
    html_path = os.path.join(output_dir, html_filename)
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html)

    return html_path


def generate_index_page(html_files, output_dir):
    """生成索引页面，方便浏览所有财报"""
    items_html = ''
    for f in sorted(html_files):
        basename = os.path.basename(f)
        items_html += f'<li><a href="{basename}" target="_blank">{basename.replace(".html", "")}</a></li>\n'

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>财报 HTML 索引</title>
<style>
    body {{
        font-family: "Microsoft YaHei", "微软雅黑", sans-serif;
        max-width: 900px;
        margin: 30px auto;
        padding: 20px;
        background: #f5f5f5;
    }}
    h1 {{
        text-align: center;
        color: #333;
        border-bottom: 2px solid #1a73e8;
        padding-bottom: 10px;
    }}
    ul {{
        list-style: none;
        padding: 0;
    }}
    li {{
        margin: 6px 0;
    }}
    a {{
        display: block;
        padding: 8px 15px;
        background: #fff;
        border: 1px solid #ddd;
        border-radius: 4px;
        text-decoration: none;
        color: #1a73e8;
        transition: background 0.2s;
    }}
    a:hover {{
        background: #e8f0fe;
        border-color: #1a73e8;
    }}
    .count {{
        text-align: center;
        color: #666;
        margin-bottom: 20px;
    }}
</style>
</head>
<body>
    <h1>上市公司财报 HTML 报表</h1>
    <p class="count">共 {len(html_files)} 份报表</p>
    <ul>
        {items_html}
    </ul>
    <p style="text-align:center;color:#999;margin-top:30px;">
        点击任意链接查看报表 → 点击右上角"打印 / 导出 PDF"按钮即可保存为 PDF
    </p>
</body>
</html>'''

    index_path = os.path.join(output_dir, 'index.html')
    with open(index_path, 'w', encoding='utf-8') as f:
        f.write(html)

    return index_path


def main():
    csv_dir = OUTPUT_DIR['csv']
    html_dir = os.path.join(os.path.dirname(csv_dir), 'html')
    os.makedirs(html_dir, exist_ok=True)

    # 查找所有财报 CSV（排除 announcements_list.csv）
    csv_files = glob.glob(os.path.join(csv_dir, '*.csv'))
    csv_files = [f for f in csv_files if 'announcements_list' not in f]

    if not csv_files:
        print('未找到 CSV 文件')
        return

    print(f'找到 {len(csv_files)} 个 CSV 文件，开始转换...')

    html_files = []
    for csv_path in sorted(csv_files):
        try:
            html_path = generate_html_for_csv(csv_path, html_dir)
            if html_path:
                html_files.append(html_path)
                print(f'  OK: {os.path.basename(html_path)}')
            else:
                print(f' SKIP: {os.path.basename(csv_path)} (无有效数据)')
        except Exception as e:
            print(f'  ERR: {os.path.basename(csv_path)} - {e}')

    # 生成索引页
    index_path = generate_index_page(html_files, html_dir)
    print(f'\n转换完成！共生成 {len(html_files)} 个 HTML 文件')
    print(f'索引页面: {index_path}')

    # 用浏览器打开索引页
    webbrowser.open(f'file:///{index_path.replace(os.sep, "/")}')


if __name__ == '__main__':
    main()
