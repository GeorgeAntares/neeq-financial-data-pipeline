import pdfplumber
import re
import logging
import pandas as pd
import fitz  # pymupdf，图片型PDF的备用提取方案

logger = logging.getLogger(__name__)


class PDFParser:
    """年报PDF财务报表解析器"""
    
    # 三大报表的识别特征
    STATEMENT_MARKERS = {
        'balance_sheet': {
            'title': ['合并资产负债表', '资产负债表'],
            'headers': ['期末余额', '期初余额', '期末数', '期初数'],
        },
        'income_statement': {
            'title': ['合并利润表', '利润表'],
            'headers': ['本期金额', '上期金额', '营业收入', '营业总收入', '营业成本', '净利润'],
        },
        'cash_flow': {
            'title': ['合并现金流量表', '现金流量表'],
            'headers': ['本期金额', '上期金额', '经营活动', '投资活动', '筹资活动'],
        },
    }
    
    def parse_pdf(self, pdf_path):
        """
        解析PDF，提取三大报表
        先用 pdfplumber (lines策略)，数据不足时回退到 pymupdf 文本解析
        :param pdf_path: PDF文件路径
        :return: 字典，包含三大报表的pandas DataFrame
        """
        result = {
            'balance_sheet': None,
            'income_statement': None,
            'cash_flow': None
        }
        
        try:
            with pdfplumber.open(pdf_path) as pdf:
                total_pages = len(pdf.pages)
                
                statement_ranges = self._find_statement_pages(pdf, total_pages)
                
                # 如果 pdfplumber 找不到报表范围，用 pymupdf 找
                if len(statement_ranges) < 2:
                    logger.info(f'pdfplumber只找到{len(statement_ranges)}张报表，尝试pymupdf定位')
                    pymupdf_ranges = self._find_statement_pages_pymupdf(pdf_path, total_pages)
                    if len(pymupdf_ranges) > len(statement_ranges):
                        statement_ranges = pymupdf_ranges
                
                logger.info(f'报表页码范围: {statement_ranges}')
                
                for stmt_type, (start_page, end_page) in statement_ranges.items():
                    all_rows = []
                    columns = None
                    
                    for pn in range(start_page, end_page + 1):
                        if pn > total_pages:
                            break
                        
                        tables = self._extract_tables_from_page(pdf.pages[pn - 1])
                        
                        for table in tables:
                            if self._is_main_financial_table(table, stmt_type):
                                rows = self._clean_table_rows(table, stmt_type, columns is None)
                                
                                if not rows:
                                    continue
                                
                                if columns is None:
                                    if self._is_valid_header(rows[0]):
                                        columns = self._normalize_columns(rows[0], stmt_type)
                                        rows = rows[1:]
                                    else:
                                        columns = self._generate_default_columns(stmt_type, len(rows[0]))
                                
                                filtered_rows = []
                                for row in rows:
                                    if not self._is_header_row(row, columns):
                                        filtered_rows.append(row)
                                
                                all_rows.extend(filtered_rows)
                    
                    if columns:
                        df = self._rows_to_dataframe(all_rows, columns)
                        df = self._clean_dataframe(df)
                    else:
                        df = None
                    
                    # pymupdf 回退：如果 pdfplumber 提取不到足够数据，用 pymupdf
                    if df is None or len(df) < 5 or not self._is_quality_data(df, stmt_type):
                        logger.info(f'{stmt_type} pdfplumber数据质量不足，尝试pymupdf回退')
                        pymupdf_end = min(start_page + 12, end_page)
                        df_pymupdf = self._parse_with_pymupdf(pdf_path, stmt_type, start_page, pymupdf_end)
                        if df_pymupdf is not None and len(df_pymupdf) >= 5 and self._is_quality_data(df_pymupdf, stmt_type):
                            df = df_pymupdf
                            logger.info(f'{stmt_type} pymupdf回退成功: {len(df)}行数据')
                        else:
                            logger.warning(f'{stmt_type} pymupdf也无法提取有效数据，跳过（可能是图片型表格）')
                    
                    result[stmt_type] = df
                    if df is not None:
                        logger.info(f'{stmt_type} 解析成功: {len(df)}行数据')
                    else:
                        logger.warning(f'{stmt_type} 未找到有效数据')
                            
        except Exception as e:
            logger.error(f'PDF解析失败: {pdf_path}, 错误: {e}', exc_info=True)
        
        return result

    def _extract_tables_from_page(self, page):
        """
        使用 lines 策略从单页提取所有表格
        """
        try:
            tables = page.extract_tables({
                'vertical_strategy': 'lines',
                'horizontal_strategy': 'lines',
            })
            return tables or []
        except Exception:
            return []

    def _find_statement_pages(self, pdf, total_pages):
        """
        扫描全部页面，定位每张报表的起始页
        BS和CF用文本+标题检测，IS用表格特征检测
        :return: {'balance_sheet': (start, end), ...}
        """
        positions = {}  # {页码: 报表类型}
        found_types = set()
        
        # 第一轮：三大报表用文本检测
        for pn in range(1, total_pages + 1):
            page = pdf.pages[pn - 1]
            text = page.extract_text() or ''
            tables = page.extract_tables({
                'vertical_strategy': 'lines',
                'horizontal_strategy': 'lines',
            }) or []
            
            for stmt_type, markers in self.STATEMENT_MARKERS.items():
                if stmt_type in found_types:
                    continue
                
                title_match = any(t in text for t in markers['title'])
                header_match = any(h in text for h in markers['headers'])
                
                if title_match and header_match:
                    positions[pn] = stmt_type
                    found_types.add(stmt_type)
                    logger.info(f'找到{stmt_type}起始页: 第{pn}页 (文本匹配)')
                    continue
                
                if title_match and tables:
                    for table in tables:
                        if len(table) > 0 and table[0]:
                            first_row_text = ' '.join(c or '' for c in table[0])
                            if any(h in first_row_text for h in markers['headers']):
                                positions[pn] = stmt_type
                                found_types.add(stmt_type)
                                logger.info(f'找到{stmt_type}起始页: 第{pn}页 (表格匹配)')
                                break
        
        # 第二轮：利润表备用检测（在第一轮没找到时）
        if 'income_statement' not in found_types and len(sorted_pages) >= 1:
            # 在有报表的页面附近搜索IS：BS之后到CF之前，或已知报表前后10页
            if len(sorted_pages) == 1:
                search_start = max(1, sorted_pages[0] - 5)
                search_end = min(sorted_pages[0] + 15, total_pages)
            else:
                search_start = sorted_pages[0] + 1
                search_end = sorted_pages[-1] - 1
            
            for pn in range(search_start, min(search_end + 1, total_pages + 1)):
                page = pdf.pages[pn - 1]
                text = page.extract_text() or ''
                # 优先用文本匹配（更可靠）
                if ('合并利润表' in text or '利润表' in text) and \
                   ('本期金额' in text or '上期金额' in text or '营业收入' in text or '营业总收入' in text):
                    positions[pn] = 'income_statement'
                    found_types.add('income_statement')
                    logger.info(f'找到income_statement起始页: 第{pn}页 (文本匹配-备用)')
                    break
                
                tables = page.extract_tables({
                    'vertical_strategy': 'lines',
                    'horizontal_strategy': 'lines',
                }) or []
                
                for table in tables:
                    if len(table) > 5:
                        all_text = ' '.join(' '.join(c or '' for c in row) for row in table[:20])
                        if ('营业收入' in all_text or '营业总收入' in all_text) and \
                           ('营业成本' in all_text or '利润总额' in all_text or '净利润' in all_text):
                            # 排除现金流量表（含"经营活动"）
                            if '经营活动' not in all_text and '投资活动' not in all_text:
                                positions[pn] = 'income_statement'
                                found_types.add('income_statement')
                                logger.info(f'找到income_statement起始页: 第{pn}页 (表格特征-备用)')
                                break
                if 'income_statement' in found_types:
                    break
        
        # 重新排序，确定页码范围
        sorted_pages = sorted(positions.keys())
        ranges = {}
        for i, st_page in enumerate(sorted_pages):
            stmt_type = positions[st_page]
            end_page = sorted_pages[i + 1] - 1 if i + 1 < len(sorted_pages) else total_pages
            ranges[stmt_type] = (st_page, end_page)
        
        return ranges

    def _find_statement_pages_pymupdf(self, pdf_path, total_pages):
        """
        使用 pymupdf 定位报表起始页（图片型PDF回退方案）
        """
        ranges = {}
        try:
            doc = fitz.open(pdf_path)
            total = min(total_pages, doc.page_count)
            
            found = {'balance_sheet': None, 'income_statement': None, 'cash_flow': None}
            
            stmt_keywords = {
                'balance_sheet': ['合并资产负债表', '资产负债表'],
                'income_statement': ['合并利润表', '利润表'],
                'cash_flow': ['合并现金流量表', '现金流量表'],
            }
            
            for pn in range(total):
                text = doc[pn].get_text()
                
                for stmt_type, keywords in stmt_keywords.items():
                    if found[stmt_type] is not None:
                        continue
                    for kw in keywords:
                        if kw in text:
                            # 检查是否真的进入了报表页面（而非审计报告引用）
                            if stmt_type == 'balance_sheet' and ('期末余额' in text or '期末数' in text):
                                found[stmt_type] = pn + 1
                                logger.info(f'[pymupdf] 找到{stmt_type}起始页: 第{pn+1}页')
                            elif stmt_type == 'income_statement' and ('营业收入' in text or '营业总收入' in text or '本期金额' in text and '上期金额' in text):
                                found[stmt_type] = pn + 1
                                logger.info(f'[pymupdf] 找到{stmt_type}起始页: 第{pn+1}页')
                            elif stmt_type == 'cash_flow' and ('经营活动' in text):
                                found[stmt_type] = pn + 1
                                logger.info(f'[pymupdf] 找到{stmt_type}起始页: 第{pn+1}页')
                            break
            
            doc.close()
            
            # 构建页码范围
            found_pages = {k: v for k, v in found.items() if v is not None}
            sorted_pages = sorted(found_pages.items(), key=lambda x: x[1])
            
            for i, (stmt_type, st_page) in enumerate(sorted_pages):
                end_page = sorted_pages[i + 1][1] - 1 if i + 1 < len(sorted_pages) else total
                ranges[stmt_type] = (st_page, end_page)
                
        except Exception as e:
            logger.warning(f'pymupdf locate pages failed: {e}')
        
        return ranges

    def _is_quality_data(self, df, stmt_type):
        """
        检查提取的数据是否像是真正的财务报表（而非附注杂表）
        """
        if df is None or len(df) < 3:
            return False
        
        # 取"项目"列的前20个值
        items = [str(v).strip() for v in df.iloc[:20, 0].tolist() if v and str(v).strip()]
        
        # 资产负债表特征项
        bs_items = ['货币资金', '流动资产', '应收账款', '存货', '固定资产',
                     '资产总计', '短期借款', '应付账款', '负债合计', '所有者权益']
        # 利润表特征项
        is_items = ['营业收入', '营业成本', '利润总额', '净利润', '营业利润', '营业总收入', '研发费用']
        # 现金流量表特征项
        cf_items = ['经营活动', '投资活动', '筹资活动', '销售商品', '现金及现金等价物']
        
        check_map = {
            'balance_sheet': bs_items,
            'income_statement': is_items,
            'cash_flow': cf_items,
        }
        
        check_items = check_map.get(stmt_type, [])
        items_text = ' '.join(items)
        match_count = sum(1 for item in check_items if item in items_text)
        
        return match_count >= 2

    def _is_main_financial_table(self, table, stmt_type):
        """
        判断是否为主要的财务报表（排除附注小表格）
        """
        if not table or len(table) < 5:
            return False
        
        # 检查前几行是否包含金额数据
        has_numbers = False
        for row in table[:10]:
            for cell in row:
                if cell and re.search(r'[\d,]+\.?\d*', str(cell)):
                    has_numbers = True
                    break
        
        return has_numbers

    def _is_header_row(self, row, columns):
        """
        判断是否为重复的表头行（跨页表格常见）
        """
        if not columns:
            return False
        
        # 如果行内容和columns高度相似，就是表头
        row_clean = [self._clean_cell(c) for c in row]
        cols_clean = [self._clean_cell(c) for c in columns]
        
        match_count = sum(1 for rc, cc in zip(row_clean, cols_clean) if rc and cc and rc[:6] == cc[:6])
        return match_count >= min(2, len(columns))

    def _is_valid_header(self, row):
        """
        判断一行是否为有效的表头（非数据行）
        表头如：项目|期末余额|期初余额  或  项目|本期金额|上期金额
        数据行如：货币资金|734587608.57|628833804.17
        """
        if not row:
            return False
        
        cleaned = [self._clean_cell(c) for c in row]
        first_cell = cleaned[0] if cleaned else ''
        
        # 第一列必须是"项目"或类似的表头标记
        if first_cell not in ['项目', '项 目', '项目名称', '科目']:
            return False
        
        # 其余列不能全是空
        other_cells = [c for c in cleaned[1:] if c]
        if not other_cells:
            return False
        
        # 其余列应该包含中文（如"期末余额"、"本期金额"）
        has_chinese = any(re.search(r'[\u4e00-\u9fff]', c) for c in other_cells)
        return has_chinese

    def _normalize_columns(self, row, stmt_type):
        """
        标准化列名：始终使用统一的标准列名，不受原始PDF表头影响
        """
        defaults = {
            'balance_sheet': ['项目', '期末余额', '期初余额'],
            'income_statement': ['项目', '本期金额', '上期金额'],
            'cash_flow': ['项目', '本期金额', '上期金额'],
        }
        # 始终返回标准列名，避免数据值被误当列名
        return defaults.get(stmt_type, ['项目', '列1', '列2'])

    def _generate_default_columns(self, stmt_type, num_cols):
        """
        生成默认列名
        """
        defaults = {
            'balance_sheet': ['项目', '期末余额', '期初余额'],
            'income_statement': ['项目', '本期金额', '上期金额'],
            'cash_flow': ['项目', '本期金额', '上期金额'],
        }
        cols = defaults.get(stmt_type, [f'列{i}' for i in range(num_cols)])
        while len(cols) < num_cols:
            cols.append(f'列{len(cols)}')
        return cols[:num_cols]

    def _clean_table_rows(self, table, stmt_type, is_first_table):
        """
        清理表格行数据
        """
        cleaned = []
        for row in table:
            # 跳过全空行
            if not row or all(c is None or str(c).strip() == '' for c in row):
                continue
            
            # 清理每个单元格
            clean_row = [self._clean_cell(c) for c in row]
            
            # 跳过完全无意义的行
            if all(c == '' for c in clean_row):
                continue
            
            cleaned.append(clean_row)
        
        return cleaned

    def _clean_cell(self, cell):
        """
        清理单个单元格内容
        """
        if cell is None:
            return ''
        
        text = str(cell).strip()
        # 合并换行符
        text = text.replace('\n', '')
        return text

    def _rows_to_dataframe(self, rows, columns):
        """
        将行数据转为DataFrame，最多保留3列（项目+2个金额列）
        """
        # 对于财务报表，只需要3列：项目 + 2期金额
        max_cols = len(columns)
        padded_rows = []
        for row in rows:
            if len(row) < max_cols:
                row = row + [''] * (max_cols - len(row))
            elif len(row) > max_cols:
                row = row[:max_cols]
            # 截断到最多3列（财务报表标准格式）
            if len(row) > 3:
                row = row[:3]
            padded_rows.append(row)
        
        # 确保columns也截断到3列
        if len(columns) > 3:
            columns = columns[:3]
        
        df = pd.DataFrame(padded_rows, columns=columns)
        return df

    def _clean_dataframe(self, df):
        """
        清理DataFrame数据：解析金额、删除空列空行
        """
        # 确保第一列命名为"项目"
        if df.columns[0] != '项目':
            df = df.rename(columns={df.columns[0]: '项目'})
        
        # 删除完全为空的列（phantom columns from PDF lines）
        valid_cols = ['项目']
        for col in df.columns[1:]:
            non_empty = df[col].dropna()
            non_empty = non_empty[non_empty != '']
            if len(non_empty) > 0:
                valid_cols.append(col)
        df = df[valid_cols]
        
        # 处理金额列：去除逗号、空格、换行符
        for col in df.columns[1:]:
            df[col] = df[col].map(self._parse_number)
        
        # 删除全空行
        df = df[df['项目'].str.strip() != '']
        df = df.dropna(how='all')
        df = df.reset_index(drop=True)
        
        return df

    def _parse_number(self, value):
        """
        解析金额字符串为数字
        """
        if value is None or value == '':
            return None
        
        text = str(value).strip()
        # 处理括号负数：(123.45) -> -123.45
        is_negative = False
        if text.startswith('(') and text.endswith(')'):
            text = text[1:-1].strip()
            is_negative = True
        # 去除逗号、空格
        text = re.sub(r'[,，\s]', '', text)
        
        if not text:
            return None
        
        try:
            result = float(text)
            return -result if is_negative else result
        except ValueError:
            return text

    def _parse_with_pymupdf(self, pdf_path, stmt_type, start_page, end_page):
        """
        使用 pymupdf (MuPDF) 作为备用提取方案
        适用于 pdfplumber 无法解析的图片型表格PDF
        """
        column_names = {
            'balance_sheet': ['项目', '期末余额', '期初余额'],
            'income_statement': ['项目', '本期金额', '上期金额'],
            'cash_flow': ['项目', '本期金额', '上期金额'],
        }
        
        try:
            doc = fitz.open(pdf_path)
            all_items = []
            current_item = None  # (item_name, val1, val2)
            found_header = False
            collected_header = []
            header_detected = False
            
            for pn in range(start_page, end_page + 1):
                idx = pn - 1
                if idx >= doc.page_count:
                    break
                
                page = doc[idx]
                text = page.get_text()
                lines = [l.strip() for l in text.split('\n') if l.strip()]
                
                for line in lines:
                    # 跳过页面头和页码
                    if re.match(r'^[\d]+$', line):
                        continue
                    if re.match(r'^.+年年度报告全文$', line):
                        continue
                    
                    # 检测是否进入报表正文（表头行）
                    if not header_detected:
                        if line in ['项目', '项 目']:
                            collected_header = [line]
                        elif collected_header and line in ['期末余额', '期初余额', '本期金额', '上期金额']:
                            collected_header.append(line)
                            if len(collected_header) >= 2:
                                header_detected = True
                        elif collected_header and re.match(r'^[\d]{4}\s*年度?$', line):
                            collected_header.append(line)
                            if len(collected_header) >= 2:
                                header_detected = True
                        # 无"项目"列的情况：直接碰到两个年度列
                        elif re.match(r'^[\d]{4}\s*年度?$', line) and not collected_header:
                            collected_header = [line]
                        elif collected_header and re.match(r'^[\d]{4}\s*年度?$', line):
                            collected_header.append(line)
                            header_detected = True
                        continue
                    
                    # 判断行类型：纯数字行（含负数、括号负数、千分位）
                    is_pure_number = bool(re.match(r'^[(\d,\-.\s)]+$', line) and re.search(r'\d', line))
                    
                    if is_pure_number:
                        if current_item is not None:
                            num_val = self._parse_number(line)
                            if current_item[1] is None:
                                current_item = (current_item[0], num_val, None)
                            elif current_item[2] is None:
                                current_item = (current_item[0], current_item[1], num_val)
                                # 两个值都收集完毕，保存
                                all_items.append(current_item)
                                current_item = None
                    else:
                        # 文本行 = 新项目
                        # 先保存上一个未完成的项目
                        if current_item is not None:
                            all_items.append(current_item)
                        
                        # 跳过非数据行
                        if len(line) > 3 and not re.search(r'[\u4e00-\u9fff]', line[:10]):
                            continue
                        
                        # 检查是否为其他报表开始标记（不是本报表的结束标记）
                        if any(kw in line for kw in ['法定代表人', '主管会计', '会计机构']):
                            break
                        # 遇到其他报表类型时退出
                        if stmt_type == 'income_statement':
                            if any(kw in line for kw in ['合并资产负债表', '合并现金流量表']):
                                break
                        elif stmt_type == 'cash_flow':
                            if any(kw in line for kw in ['合并资产负债表', '合并利润表']):
                                break
                        elif stmt_type == 'balance_sheet':
                            if any(kw in line for kw in ['合并利润表', '合并现金流量表']):
                                break
                        
                        current_item = (line, None, None)
                
                # 跨页时保存最后一个未完成项目
                if current_item is not None and stmt_type in ('balance_sheet', 'income_statement'):
                    pass  # 保留到下页继续
            
            # 最后一页的残留项目
            if current_item is not None:
                all_items.append(current_item)
            
            doc.close()
            
            if len(all_items) < 3:
                return None
            
            cols = column_names.get(stmt_type, ['项目', '列1', '列2'])
            df = pd.DataFrame(all_items, columns=cols)
            df = self._clean_dataframe(df)
            
            return df
            
        except Exception as e:
            logger.warning(f'pymupdf解析失败: {e}')
            return None
