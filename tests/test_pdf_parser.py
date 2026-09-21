import unittest

from pdf_parser import PDFParser


class PdfParserTableShapeTest(unittest.TestCase):
    def setUp(self):
        self.parser = PDFParser()

    def test_drops_empty_and_note_columns(self):
        rows = [
            ['', '项目', '', '', '附注', ''],
            ['', '一、营业总收入', '', '', '', ''],
            ['', '其中：营业收入', '', '五、32', '', ''],
            ['', '二、营业总成本', '', '', '184,337,957.32', '233,062,952.73'],
            ['', '其中：营业成本', '', '注释31', '95,404,953.93', '132,273,384.81'],
        ]
        cleaned = [[self.parser._clean_cell(c) for c in row] for row in rows]
        shaped = self.parser._normalize_table_shape(cleaned)
        self.assertEqual(shaped[0][0], '项目')
        cost = next(r for r in shaped if '营业成本' in r[0] and not r[0].startswith('二'))
        self.assertEqual(cost[1], '95,404,953.93')
        self.assertEqual(cost[2], '132,273,384.81')
        revenue_detail = next(r for r in shaped if r[0].startswith('其中：营业收入'))
        self.assertNotIn('五、32', revenue_detail)

    def test_three_column_table_without_notes_is_unchanged(self):
        rows = [
            ['项目', '本期金额', '上期金额'],
            ['销售商品、提供劳务收到的现金', '124961531.00', '165565846.25'],
            ['经营活动产生的现金流量净额', '-12253571.25', '-1083447.54'],
        ]
        shaped = self.parser._normalize_table_shape(rows)
        self.assertEqual(shaped[1][1], '124961531.00')
        self.assertEqual(shaped[2][2], '-1083447.54')

    def test_income_table_is_accepted_and_balance_tail_is_rejected(self):
        income = [
            ['', '项目', '', '', '附注', ''],
            ['', '一、营业总收入', '', '', '', ''],
            ['', '其中：营业收入', '', '五、32', '19879209.86', '86220689.31'],
            ['', '二、营业总成本', '', '', '171190639.52', '197697121.68'],
            ['', '其中：营业成本', '', '五、32', '136265338.74', '155798551.20'],
        ]
        balance_tail = [
            ['', '合同负债', '', '', '100', '90'],
            ['', '持有待售负债', '', '', '', ''],
            ['', '一年内到期的非流动负债', '', '', '20', '10'],
            ['', '其他流动负债', '', '', '5', '4'],
            ['', '流动负债合计', '', '', '125', '104'],
        ]
        self.assertTrue(
            self.parser._is_main_financial_table(income, 'income_statement')
        )
        self.assertFalse(
            self.parser._is_main_financial_table(balance_tail, 'income_statement')
        )
        self.assertTrue(
            self.parser._is_main_financial_table(balance_tail, 'balance_sheet')
        )
        short_income_start = [
            ['', '项目', '', '', '附注', ''],
            ['', '一、营业总收入', '', '', '200550607.08', '217390251.77'],
            ['', '其中：营业收入', '', '五、32', '19879209.86', '86220689.31'],
        ]
        self.assertTrue(
            self.parser._is_main_financial_table(short_income_start, 'income_statement')
        )

    def test_statement_page_span_is_capped(self):
        self.assertEqual(
            self.parser._cap_statement_end('cash_flow', 39, 89),
            46,
        )
        self.assertEqual(
            self.parser._cap_statement_end('income_statement', 35, 38),
            38,
        )

    def test_notes_heading_is_detected(self):
        self.assertTrue(
            self.parser._is_notes_heading_page(
                '北京华环电子股份有限公司 2025 年度财务报表附注 （除特别说明外）'
            )
        )
        self.assertFalse(
            self.parser._is_notes_heading_page(
                '详见财务报表附注。产品收入的确认通常仅包括转让商品。'
            )
        )
        self.assertFalse(
            self.parser._is_notes_heading_page(
                '山东星科智能科技股份有限公司 2025年年度报告\n'
                '为 1,168.11 万元，占销售收入比重提升至 14.41%。'
            )
        )

    def test_page_start_rejects_mda_and_audit_cover(self):
        mda = (
            '8、应付职工薪酬本期期末余额较上年期末余额增加 31.60%，'
            '系本期现金流不充足。资产负债表项目变动分析如下。'
        )
        audit = (
            '第七节 财务会计报告\n一、 审计报告\n是否审计 是\n'
            '审计意见 无保留意见\n资产负债表 利润表 现金流量表'
        )
        real_bs = (
            '二、 财务报表 (一) 合并资产负债表 单位：元\n'
            '项目 附注 2025年12月31日 2024年12月31日\n'
            '流动资产：\n货币资金 五、1 704,347.95'
        )
        is_title_only = (
            '合同负债 4,390,946.30\n(二) 合并利润表 单位：元\n项目 附注'
        )
        real_cf = (
            '(五) 合并现金流量表 单位：元\n'
            '一、经营活动产生的现金流量：\n'
            '销售商品、提供劳务收到的现金 122,566,267.57'
        )
        self.assertFalse(self.parser._page_starts_statement(mda, 'balance_sheet'))
        self.assertFalse(self.parser._page_starts_statement(audit, 'balance_sheet'))
        self.assertTrue(self.parser._page_starts_statement(real_bs, 'balance_sheet'))
        self.assertTrue(self.parser._page_starts_statement(is_title_only, 'income_statement'))
        self.assertTrue(self.parser._page_starts_statement(real_cf, 'cash_flow'))
        audit_mentions_is = (
            '三、关键审计事项\n我们确定下列事项是需要在审计报告中沟通的关键审计事项。\n'
            '合并利润表中营业收入的确认'
        )
        self.assertFalse(
            self.parser._page_starts_statement(audit_mentions_is, 'income_statement')
        )

    def test_same_page_types_keep_both_ranges(self):
        ranges = self.parser._ranges_from_starts(
            {'balance_sheet': 30, 'income_statement': 30, 'cash_flow': 34},
            total_pages=80,
        )
        self.assertEqual(ranges['balance_sheet'][0], 30)
        self.assertGreaterEqual(ranges['balance_sheet'][1], 30)
        self.assertEqual(ranges['income_statement'], (30, 33))


if __name__ == '__main__':
    unittest.main()
