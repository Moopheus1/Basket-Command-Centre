TICKERS = {
    "1211.HK": "HK Stock",
    "9618.HK": "HK Stock",
    "3067.HK": "HK/SGX ETF",
    "HST.SI":  "HK/SGX ETF",
    "O5RU.SI": "SGX REIT",
    "MXNU.SI": "SGX REIT",
    "A17U.SI": "SGX REIT",
    "HMN.SI":  "SGX REIT",
    "9CI.SI":  "SGX Real Estate",
    "C38U.SI": "SGX REIT",
    "J85.SI":  "SGX REIT",
    "C70.SI":  "SGX Pref Share",
    "Q5T.SI":  "SGX REIT",
    "J69U.SI": "SGX REIT",
    "BUOU.SI": "SGX REIT",
    "AJBU.SI": "SGX REIT",
    "K71U.SI": "SGX REIT",
    "CMOU.SI": "SGX REIT",
    "JYEU.SI": "SGX REIT",
    "ME8U.SI": "SGX REIT",
    "N2IU.SI": "SGX REIT",
    "M44U.SI": "SGX REIT",
    "TS0U.SI": "SGX REIT",
    "SEB.SI":  "SGX REIT",
    "T82U.SI": "SGX REIT",
}

# Benchmarks used for relative-strength comparison and the top-of-dashboard
# index strip. Direct index tickers preferred over ETF proxies (avoids NAV
# tracking error / dividend drag). No working ^HSTECH ticker on Yahoo, so
# the HSTECH ETF already in TICKERS (3067.HK) is reused as the Tech proxy.
BENCHMARKS = {
    "^STI":   {"label": "SG Index (STI)",        "applies_to": "SGX"},
    "^HSI":   {"label": "HK Index (HSI)",         "applies_to": "HK"},
    "3067.HK":{"label": "Tech Index (HSTECH ETF)","applies_to": "TECH"},
}

# Which benchmark each category is compared against for relative strength.
CATEGORY_BENCHMARK = {
    "HK Stock": "^HSI",
    "HK/SGX ETF": "^HSI",       # 3067.HK itself is skipped as its own benchmark
    "SGX REIT": "^STI",
    "SGX Real Estate": "^STI",
    "SGX Pref Share": "^STI",
}
