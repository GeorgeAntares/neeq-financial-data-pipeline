# 公司级指标数据字典 / Company Metrics Data Dictionary

生成：`python company_metrics.py --csv-dir output/analysis/_csv_255`  
产物：`output/analysis/company_metrics.csv`（一家一年一行）

样本默认是新解析器导出的约 255 家 CSV。只读每个文件的**第一张表**（合并报表）；同一 CSV 后半段的母公司表或其它年份表不参与计算。科目缺失记为 NaN，不用后一张表补。

金额单位：人民币元。比率与同比均为小数（`0.218` = 21.8%），流动比率、权益乘数、总资产周转率为倍数。

## 清洗

| 规则 | 说明 |
|------|------|
| 营收门槛 | `revenue >= 100_000`。更小的数多半是附注编号进了金额列。 |
| 成本口径 | 优先「营业成本」（含标准格式里的「其中：营业成本」）；没有时才用「营业总成本」（含期间费用）。`cost_source` 标明口径。 |
| 主表行 | 跳过「其中：营业收入」；净利润不用持续经营 / 终止经营 / 少数股东 / 归属于母公司分项。 |
| 权益 | 优先「所有者权益合计」；没有时才用「归属于母公司所有者权益」。不用「负债和所有者权益」。 |
| 比率截尾 | `*_w` 列为样本 1% / 99% 分位截尾（winsorize）。主列保留原始值。 |

## 标识

| 列 | 含义 | 来源 |
|----|------|------|
| `stock_code` | 证券代码 | 文件名 `{code}_{name}_{year}_合并*.csv` |
| `company_name` | 公司简称 | 文件名 |
| `year` | 报告年度 | 文件名 |
| `revenue_item` | 实际命中的营收科目 | 利润表 |
| `cost_source` | `营业成本` 或 `营业总成本` | 利润表 |
| `equity_source` | `total` 或 `parent` | 资产负债表 |

## 水平项（期末 / 本期）

| 列 | 公式 / 口径 | 科目 |
|----|-------------|------|
| `revenue` | 本期营收 | 优先「营业总收入」，否则「一、营业收入」 |
| `revenue_prior` | 上期营收 | 同上，上期金额列 |
| `cogs` | 营业成本 | 「其中：营业成本」/「减：营业成本」/「营业成本」；否则「营业总成本」 |
| `net_profit` | 本期净利润 | 「四、/五、净利润（净亏损以…）」 |
| `net_profit_prior` | 上期净利润 | 同上，上期金额列 |
| `total_assets` | 期末资产 | 「资产总计」 |
| `total_assets_begin` | 期初资产 | 「资产总计」期初余额 |
| `current_assets` | 期末流动资产 | 「流动资产合计」 |
| `current_liabilities` | 期末流动负债 | 「流动负债合计」 |
| `total_liabilities` | 期末负债 | 「负债合计」 |
| `equity` | 期末所有者权益 | 「所有者权益（或股东权益）合计」 |
| `equity_begin` | 期初所有者权益 | 同上，期初余额 |
| `accounts_receivable` | 期末应收账款 | 「应收账款」（不含票据、应收款项融资） |
| `inventory` | 期末存货 | 「存货」 |
| `ocf` | 本期经营现金流净额 | 「经营活动产生的现金流量净额」 |
| `ocf_prior` | 上期经营现金流净额 | 同上，上期金额列 |
| `avg_assets` | 平均资产 | 期初、期末都有则取平均，否则用期末 |
| `avg_equity` | 平均权益 | 同上 |

## 比率与同比（原始列）

| 列 | 公式 | 备注 |
|----|------|------|
| `gross_margin` | `(revenue - cogs) / revenue` | 成本若为营业总成本，则不是会计毛利率 |
| `net_margin` | `net_profit / revenue` | 杜邦净利率 |
| `roe` | `net_profit / avg_equity` | 权益为负时符号随权益 |
| `asset_turnover` | `revenue / avg_assets` | 杜邦周转 |
| `equity_multiplier` | `avg_assets / avg_equity` | 杜邦杠杆 |
| `dupont_product` | `net_margin × asset_turnover × equity_multiplier` | 应与 `roe` 接近；分母一致时相等 |
| `current_ratio` | `current_assets / current_liabilities` | |
| `debt_ratio` | `total_liabilities / total_assets` | 资产负债率 |
| `ar_to_revenue` | `accounts_receivable / revenue` | 应收占收入 |
| `inventory_to_revenue` | `inventory / revenue` | 存货占收入；软件企业可为 0 |
| `ocf_to_revenue` | `ocf / revenue` | |
| `ocf_minus_np` | `ocf - net_profit` | 单位：元 |
| `revenue_yoy` | `(revenue - revenue_prior) / \|revenue_prior\|` | 上期为 0 则缺失 |
| `net_profit_yoy` | `(net_profit - net_profit_prior) / \|net_profit_prior\|` | 用绝对值做分母，亏损翻正记为改善 |
| `ocf_yoy` | `(ocf - ocf_prior) / \|ocf_prior\|` | |

`*_w` 是对应列在有效营收样本上的 1% / 99% 分位截尾，供画像和建模用。核对单家公司请看无 `_w` 的原始列。

## 已知缺口

- 不少利润表第一张表在「净利润」行之前被截断，`net_profit` 覆盖会低于营收覆盖。不把母公司净利润拼到合并营收上。
- 现金流量表同样可能缺「经营活动产生的现金流量净额」。
- 单期年报：同比来自表内上期列，不是多年面板。
- PDF 集合里可能混入非新三板代码；本表不按板块过滤。
