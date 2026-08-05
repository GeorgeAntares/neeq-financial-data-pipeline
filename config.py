import os

# 巨潮资讯网API配置
CNINFO_API = {
    'search_url': 'https://www.cninfo.com.cn/new/hisAnnouncement/query',
    'pdf_base_url': 'https://static.cninfo.com.cn/',
    'headers': {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': '*/*',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'Origin': 'https://www.cninfo.com.cn',
        'Referer': 'https://www.cninfo.com.cn/new/commonUrl/pageOfSearch?url=disclosure/list/search&checkedCategory=category_ndbg_szsh',
        'X-Requested-With': 'XMLHttpRequest',
    }
}

# 板块代码映射
PLATE_CODES = {
    '创业板': 'szcy',
    '科创板': 'shkcp',
    '北交所': 'bj',
    '新三板': 'neeq',
    '深市': 'sz',
    '沪市': 'sh',
    '深主板': 'szmb',
    '沪主板': 'shmb',
}

# 板块对应的 column 参数
PLATE_COLUMN = {
    'neeq': 'third',  # 新三板用 third
    # 其他板块默认用 szse
}

# 公告类型代码
CATEGORY_CODES = {
    '年报': 'category_ndbg_szsh',
    '半年报': 'category_bndbg_szsh',
    '一季报': 'category_yjdbg_szsh',
    '三季报': 'category_sjdbg_szsh',
    '定期公告': 'category_dqgg',  # 新三板用定期公告
}

# 请求间隔（秒）- 巨潮网反爬较严格
REQUEST_INTERVAL = 2.0

# 重试次数
MAX_RETRIES = 3

# 输出目录配置
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = {
    'pdf': os.path.join(BASE_DIR, 'output', 'pdf'),
    'csv': os.path.join(BASE_DIR, 'output', 'csv'),
    'log': os.path.join(BASE_DIR, 'output', 'log'),
}

# 优雅停止标记文件
STOP_FILE = os.path.join(BASE_DIR, 'STOP.txt')

# 创建输出目录
for dir_path in OUTPUT_DIR.values():
    os.makedirs(dir_path, exist_ok=True)