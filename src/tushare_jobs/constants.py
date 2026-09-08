"""Shared configuration for dataset defaults."""

from __future__ import annotations

# --- Listed company datasets (from tushare-general-data-downloader) ---
DATASET_STOCK_BASIC = "stock_basic"
DATASET_STOCK_COMPANY = "stock_company"
DATASET_STK_MANAGERS = "stk_managers"
DATASET_SHARE_FLOAT = "share_float"

ALL_LISTED_COMPANY_DATASETS = (
    DATASET_STOCK_BASIC,
    DATASET_STOCK_COMPANY,
    DATASET_STK_MANAGERS,
    DATASET_SHARE_FLOAT,
)

# --- Index / ST datasets (from tushare-email-fetch) ---
DATASET_STOCK_ST = "stock_st"
DATASET_INDEX_WEIGHT = "index_weight"
DATASET_INDEX_WEIGHT_DAILY = "index_weight_daily"

ALL_DATASETS = (
    DATASET_STOCK_BASIC,
    DATASET_STOCK_COMPANY,
    DATASET_STK_MANAGERS,
    DATASET_SHARE_FLOAT,
    DATASET_STOCK_ST,
    DATASET_INDEX_WEIGHT,
    DATASET_INDEX_WEIGHT_DAILY,
)

DEFAULT_FIELDS = {
    DATASET_STOCK_BASIC: (
        "ts_code,symbol,name,area,industry,market,exchange,list_status,list_date,is_hs"
    ),
    DATASET_STOCK_COMPANY: (
        "ts_code,exchange,chairman,manager,secretary,reg_capital,setup_date,"
        "province,city,website,employees,introduction,main_business,business_scope"
    ),
    DATASET_STK_MANAGERS: "ts_code,ann_date,name,title,begin_date,end_date",
    DATASET_SHARE_FLOAT: (
        "ts_code,ann_date,float_date,holder_name,share_type,float_share,float_ratio"
    ),
}

ENV_FIELD_OVERRIDES = {
    DATASET_STOCK_BASIC: "TUSHARE_FIELDS_STOCK_BASIC",
    DATASET_STOCK_COMPANY: "TUSHARE_FIELDS_STOCK_COMPANY",
    DATASET_STK_MANAGERS: "TUSHARE_FIELDS_STK_MANAGERS",
    DATASET_SHARE_FLOAT: "TUSHARE_FIELDS_SHARE_FLOAT",
}

DEDUP_KEYS = {
    DATASET_STOCK_BASIC: ["ts_code"],
    DATASET_STOCK_COMPANY: ["ts_code"],
    DATASET_STK_MANAGERS: [
        "ts_code",
        "ann_date",
        "name",
        "title",
        "begin_date",
        "end_date",
    ],
    DATASET_SHARE_FLOAT: [
        "ts_code",
        "float_date",
        "holder_name",
        "share_type",
        "ann_date",
    ],
}

DEFAULT_EXCHANGES = ("SSE", "SZSE", "BSE")
DEFAULT_SHARE_FLOAT_THRESHOLD = 5500
DEFAULT_MANAGERS_WINDOW = "month"
DEFAULT_SHARE_FLOAT_WINDOW = "week"
DEFAULT_YEARS = 5

# --- Index defaults (from tushare-email-fetch) ---
DEFAULT_INDEX_START_DATE = "20160101"
DEFAULT_INDEX_CODES = [
    "000300.SH",  # 沪深300
    "000905.SH",  # 中证500
    "000852.SH",  # 中证1000
    "399006.SZ",  # 创业板指
    "000016.SH",  # 上证50
]
