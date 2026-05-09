"""
╔══════════════════════════════════════════════════════════════╗
║   TRENDLINE BREAKOUT SCANNER — NSE & NYSE                   ║
║   ALL 20 Price Action Trendline Types Applied               ║
║   Output: Beautiful HTML Report                             ║
╚══════════════════════════════════════════════════════════════╝

20 TRENDLINE TYPES:
 1.  Uptrend Line (Higher Lows Support)
 2.  Downtrend Line (Lower Highs Resistance)
 3.  Horizontal Support / Resistance
 4.  Channel (Ascending / Descending / Sideways)
 5.  Triangle (Symmetrical / Ascending / Descending)
 6.  Wedge (Rising / Falling)
 7.  Flag & Pennant (Continuation)
 8.  Fan Lines (3-Fan Trendline System)
 9.  Internal Trendline (Mid-body regression)
10.  Dynamic EMA (20 / 50 / 200)
11.  Neckline — Head & Shoulders / Inverse H&S
12.  Fibonacci Trendline (Key Fib levels)
13.  Pitchfork / Andrews Pitchfork (Median line)
14.  Regression Trendline (Linear Regression Channel)
15.  Acceleration / Parabolic Trendline
16.  Base Trendline (Accumulation Floor)
17.  Role Reversal (Polarity Flip — broken support → resistance)
18.  Speed Resistance Lines (1/3 and 2/3 lines)
19.  Candlestick Body Trendline (No-wick trendline)
20.  Gann Angle (1x1 = 45° rule)

═══════════════════════════════════════════════════════════════
FIXES APPLIED (v2):
  FIX-01  NSE tickers corrected: LTM→LTIM, TATACAP→JIOFIN
  FIX-02  Gann unit: origin_v/100 → origin_v*0.001 (was 100× too large)
  FIX-03  Regression channel: description corrected (lower breakdown = BEARISH momentum)
  FIX-04  Base trendline: added missing BEARISH breakdown signal
  FIX-05  Pitchfork: pivots sorted by bar-index before A/B/C assignment
  FIX-06  Internal trendline: regression limited to last 50 bars (was all 130)
  FIX-07  Acceleration: correlation threshold 0.90→0.80; residual relaxed to 2-of-3
  FIX-08  Speed resistance: 2/3 level checked before 1/3 (stronger signal first)
  FIX-09  Fibonacci: EMA-slope direction filter added (no counter-trend Fib signals)
  FIX-10  scan_stock: deduplication — max 2 signals per direction per stock
  FIX-11  Role reversal: proximity band widened 2%→3%
  FIX-12  Base range threshold: exchange-aware (0.20 NSE, 0.15 NYSE)
  FIX-13  Flag pole threshold: exchange-aware (7% NSE, 4% NYSE)
═══════════════════════════════════════════════════════════════
"""

import os
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import random
import math

import logging
import warnings

# Suppress all yfinance / urllib3 / requests noise
logging.getLogger("yfinance").setLevel(logging.CRITICAL)
logging.getLogger("urllib3").setLevel(logging.CRITICAL)
logging.getLogger("requests").setLevel(logging.CRITICAL)
warnings.filterwarnings("ignore")

try:
    import yfinance as yf
    logging.getLogger("peewee").setLevel(logging.CRITICAL)
    YF_AVAILABLE = True
except ImportError:
    YF_AVAILABLE = False

random.seed(int(datetime.now().strftime("%Y%m%d")))

# ── Stock Universe ─────────────────────────────────────────────────────────────
NSE_STOCKS = [
    # ── Banking & Finance (^NSEBANK) ──────────────────────────────
    ("HDFCBANK",    "HDFC Bank",               1785.40),
    ("ICICIBANK",   "ICICI Bank",              1268.30),
    ("SBIN",        "State Bank of India",      813.60),
    ("KOTAKBANK",   "Kotak Mahindra Bank",     1932.75),
    ("AXISBANK",    "Axis Bank",               1189.60),
    ("CANBK",       "Canara Bank",              102.85),
    ("BANKBARODA",  "Bank of Baroda",           248.30),
    ("UNIONBANK",   "Union Bank of India",      133.20),
    ("PNB",         "Punjab National Bank",     105.60),
    # ── Financial Services (NIFTY_FIN_SERVICE) ────────────────────
    ("BAJFINANCE",  "Bajaj Finance",           7124.50),
    ("BAJAJFINSV",  "Bajaj Finserv",           1672.80),
    ("MUTHOOTFIN",  "Muthoot Finance",         1938.45),
    ("CHOLAFIN",    "Cholamandalam Finance",   1312.60),
    ("SBILIFE",     "SBI Life Insurance",      1512.30),
    ("HDFCLIFE",    "HDFC Life Insurance",      624.75),
    ("SHRIRAMFIN",  "Shriram Finance",         2814.90),
    # FIX-01: TATACAP removed (Tata Capital not separately listed on NSE)
    #         Replaced with JIOFIN (Jio Financial Services — listed Aug 2023)
    ("JIOFIN",      "Jio Financial Services",   312.50),
    ("IRFC",        "Indian Railway Fin Corp",  192.40),
    ("PFC",         "Power Finance Corp",       452.30),
    ("RECLTD",      "REC Limited",              512.80),
    ("HDFCAMC",     "HDFC AMC",               4012.60),
    ("BAJAJHLDNG",  "Bajaj Holdings",          9824.50),
    # ── IT & Technology (^CNXIT) ──────────────────────────────────
    ("TCS",         "Tata Consultancy",        3421.20),
    ("INFY",        "Infosys",                 1181.80),
    ("WIPRO",       "Wipro",                    538.90),
    ("TECHM",       "Tech Mahindra",           1473.50),
    ("HCLTECH",     "HCL Technologies",        1612.45),
    # FIX-01: LTM → LTIM (correct NSE symbol for LTIMindtree)
    ("LTIM",        "LTIMindtree",             5234.80),
    # ── Oil, Gas & Energy (^CNXENERGY) ────────────────────────────
    ("RELIANCE",    "Reliance Industries",     2890.50),
    ("ONGC",        "ONGC",                     268.50),
    ("BPCL",        "BPCL",                     312.40),
    ("GAIL",        "GAIL India",               212.75),
    ("IOC",         "Indian Oil Corp",          164.30),
    ("TATAPOWER",   "Tata Power",               412.60),
    ("ADANIGREEN",  "Adani Green Energy",      1724.85),
    ("ADANIENSOL",  "Adani Energy Solutions",   812.40),
    ("ADANIPOWER",  "Adani Power",              221.85),
    ("NTPC",        "NTPC",                     362.80),
    ("POWERGRID",   "Power Grid Corp",          316.45),
    ("SOLARINDS",   "Solar Industries",        9124.50),
    # ── Auto & Auto Ancillary (^CNXAUTO) ──────────────────────────
    ("MARUTI",      "Maruti Suzuki",          12340.00),
    ("BAJAJ-AUTO",  "Bajaj Auto",              9994.00),
    ("M&M",         "Mahindra & Mahindra",     2812.30),
    ("EICHERMOT",   "Eicher Motors",           4612.80),
    ("TVSMOTOR",    "TVS Motor",              2314.60),
    ("MOTHERSON",   "Samvardhana Motherson",    142.35),
    ("BOSCHLTD",    "Bosch",                 34812.00),
    ("CUMMINSIND",  "Cummins India",           3412.50),
    # ── Pharma & Healthcare (^CNXPHARMA) ──────────────────────────
    ("SUNPHARMA",   "Sun Pharma",             1808.30),
    ("DRREDDY",     "Dr Reddy's Labs",         1284.60),
    ("CIPLA",       "Cipla",                   1512.80),
    ("DIVISLAB",    "Divi's Laboratories",     5124.30),
    ("TORNTPHARM",  "Torrent Pharma",          3214.70),
    ("APOLLOHOSP",  "Apollo Hospitals",        6912.40),
    ("ZYDUSLIFE",   "Zydus Lifesciences",      1124.80),
    ("MAXHEALTH",   "Max Healthcare",          1012.60),
    # ── Metals & Mining (^CNXMETAL) ───────────────────────────────
    ("JSWSTEEL",    "JSW Steel",              1012.40),
    ("TATASTEEL",   "Tata Steel",              168.75),
    ("HINDALCO",    "Hindalco Industries",      682.30),
    ("VEDL",        "Vedanta",                  462.80),
    ("COALINDIA",   "Coal India",               412.60),
    ("HINDZINC",    "Hindustan Zinc",           312.45),
    ("JINDALSTEL",  "Jindal Steel & Power",     924.80),
    # ── FMCG & Retail (^CNXFMCG) ─────────────────────────────────
    ("HINDUNILVR",  "Hindustan Unilever",      2512.40),
    ("ITC",         "ITC",                      462.30),
    ("NESTLEIND",   "Nestle India",            2412.80),
    ("BRITANNIA",   "Britannia Industries",    5312.60),
    ("TATACONSUM",  "Tata Consumer Products",  1012.40),
    ("GODREJCP",    "Godrej Consumer Products",1212.80),
    ("VBL",         "Varun Beverages",         1612.30),
    ("UNITDSPR",    "United Spirits",          1124.60),
    # ── Infra, Capital Goods & Defence (^CNXINFRA) ────────────────
    ("LT",          "Larsen & Toubro",         3512.80),
    ("ADANIENT",    "Adani Enterprises",       2812.40),
    ("ADANIPORTS",  "Adani Ports",             1312.60),
    ("BEL",         "Bharat Electronics",       312.45),
    ("HAL",         "Hindustan Aeronautics",   4512.80),
    ("SIEMENS",     "Siemens India",           7124.30),
    ("ABB",         "ABB India",               8012.60),
    ("CGPOWER",     "CG Power & Ind Solutions", 712.40),
    ("MAZDOCK",     "Mazagon Dock",            4812.30),
    ("DLF",         "DLF",                      812.60),
    ("LODHA",       "Macrotech Developers",    1312.40),
    ("BHARTIARTL",  "Bharti Airtel",           1880.90),
    # ── Cement & Consumer Discretionary (^CNXCONSUM) ──────────────
    ("ULTRACEMCO",  "UltraTech Cement",       11812.40),
    ("GRASIM",      "Grasim Industries",       2612.80),
    ("AMBUJACEM",   "Ambuja Cements",           612.30),
    ("SHREECEM",    "Shree Cement",           26812.00),
    ("ASIANPAINT",  "Asian Paints",            2412.60),
    ("PIDILITIND",  "Pidilite Industries",     3012.80),
    ("TITAN",       "Titan Company",           3612.40),
    ("TRENT",       "Trent",                   6812.30),
    ("DMART",       "Avenue Supermarts",       4812.60),
    ("INDHOTEL",    "Indian Hotels",            612.80),
    ("INDIGO",      "IndiGo (InterGlobe)",     4412.30),
    ("ETERNAL",     "Eternal (Zomato)",         312.45),
    # ── Others ───────────────────────────────────────────────────
    ("RBLBANK",     "RBL Bank",                 391.75),
    ("TATAMOTORS",  "Tata Motors",              778.25),
]

NYSE_STOCKS = [
    # ── Technology (XLK) ──────────────────────────────────────────
    ("NVDA",  "NVIDIA",                  950.02),
    ("AAPL",  "Apple Inc",               213.49),
    ("MSFT",  "Microsoft",               421.90),
    ("GOOGL", "Alphabet (Class A)",      176.30),
    ("GOOG",  "Alphabet (Class C)",      178.10),
    ("META",  "Meta Platforms",          578.15),
    ("AVGO",  "Broadcom",              1742.80),
    ("MU",    "Micron Technology",        98.42),
    ("ORCL",  "Oracle",                  128.74),
    ("AMD",   "AMD",                     148.20),
    ("CSCO",  "Cisco Systems",            49.82),
    ("IBM",   "IBM",                     188.34),
    ("INTC",  "Intel",                    21.48),
    ("LRCX",  "Lam Research",            812.60),
    ("AMAT",  "Applied Materials",       192.34),
    ("PLTR",  "Palantir Technologies",    24.82),
    ("AMZN",  "Amazon",                  202.40),
    ("TSLA",  "Tesla",                   177.58),
    # ── Financials (XLF) ──────────────────────────────────────────
    ("BRK-B", "Berkshire Hathaway B",    412.30),
    ("JPM",   "JPMorgan Chase",          244.82),
    ("V",     "Visa",                    276.93),
    ("MA",    "Mastercard",              489.25),
    ("BAC",   "Bank of America",          44.21),
    ("MS",    "Morgan Stanley",          108.42),
    ("WFC",   "Wells Fargo",              62.18),
    ("GS",    "Goldman Sachs",           482.60),
    ("AXP",   "American Express",        242.80),
    # ── Healthcare (XLV) ──────────────────────────────────────────
    ("LLY",   "Eli Lilly",              812.40),
    ("JNJ",   "Johnson & Johnson",       157.42),
    ("ABBV",  "AbbVie",                 182.60),
    ("MRK",   "Merck",                  128.34),
    ("UNH",   "UnitedHealth Group",      512.80),
    # ── Consumer Staples (XLP) ────────────────────────────────────
    ("WMT",   "Walmart",                 100.12),
    ("COST",  "Costco Wholesale",        892.40),
    ("PG",    "Procter & Gamble",        171.08),
    ("KO",    "Coca-Cola",               62.34),
    ("PM",    "Philip Morris",           112.48),
    ("PEP",   "PepsiCo",                172.60),
    # ── Consumer Discretionary (XLY) ─────────────────────────────
    ("HD",    "Home Depot",              342.50),
    ("NFLX",  "Netflix",                 698.90),
    ("MCD",   "McDonald's",              312.40),
    # ── Energy (XLE) ──────────────────────────────────────────────
    ("XOM",   "ExxonMobil",              111.56),
    ("CVX",   "Chevron",                 152.34),
    # ── Industrials (XLI) ─────────────────────────────────────────
    ("CAT",   "Caterpillar",             382.60),
    ("GE",    "GE Aerospace",            182.40),
    ("RTX",   "RTX Corporation",         112.80),
    ("GEV",   "GE Vernova",              312.60),
    # ── Communication Services (XLC) ─────────────────────────────
    ("TMUS",  "T-Mobile US",             212.40),
    ("VZ",    "Verizon",                  42.18),
    # ── Materials (XLB) ───────────────────────────────────────────
    ("LIN",   "Linde",                   482.60),
    # ── Others ───────────────────────────────────────────────────
    ("DIS",   "Walt Disney",              96.40),
    ("PYPL",  "PayPal",                   77.65),
]

# ── Sector Maps ───────────────────────────────────────────────────────────────
USA_SECTOR_MAP = {
    **{s: "XLK" for s in [
        "NVDA","AAPL","MSFT","GOOGL","GOOG","META","AVGO","MU","ORCL",
        "AMD","CSCO","IBM","INTC","LRCX","AMAT","PLTR","AMZN","TSLA",
    ]},
    **{s: "XLF" for s in [
        "BRK-B","JPM","V","MA","BAC","MS","WFC","GS","AXP",
    ]},
    **{s: "XLV" for s in [
        "LLY","JNJ","ABBV","MRK","UNH",
    ]},
    **{s: "XLP" for s in [
        "WMT","COST","PG","KO","PM","PEP",
    ]},
    **{s: "XLY" for s in [
        "HD","NFLX","MCD",
    ]},
    **{s: "XLE" for s in [
        "XOM","CVX",
    ]},
    **{s: "XLI" for s in [
        "CAT","GE","RTX","GEV",
    ]},
    **{s: "XLC" for s in [
        "TMUS","VZ",
    ]},
    **{s: "XLB" for s in [
        "LIN",
    ]},
}

INDIA_SECTOR_MAP = {
    **{s: "^NSEBANK" for s in [
        "HDFCBANK.NS","ICICIBANK.NS","SBIN.NS","KOTAKBANK.NS","AXISBANK.NS",
        "CANBK.NS","BANKBARODA.NS","UNIONBANK.NS","PNB.NS",
    ]},
    **{s: "NIFTY_FIN_SERVICE.NS" for s in [
        "BAJFINANCE.NS","BAJAJFINSV.NS","MUTHOOTFIN.NS","CHOLAFIN.NS",
        "SBILIFE.NS","HDFCLIFE.NS","SHRIRAMFIN.NS","JIOFIN.NS",
        "IRFC.NS","PFC.NS","RECLTD.NS","HDFCAMC.NS","BAJAJHLDNG.NS",
    ]},
    **{s: "^CNXIT" for s in [
        # FIX-01: updated LTIM.NS (was LTM.NS)
        "TCS.NS","INFY.NS","WIPRO.NS","TECHM.NS","HCLTECH.NS","LTIM.NS",
    ]},
    **{s: "^CNXENERGY" for s in [
        "RELIANCE.NS","ONGC.NS","BPCL.NS","GAIL.NS","IOC.NS",
        "TATAPOWER.NS","ADANIGREEN.NS","ADANIENSOL.NS","ADANIPOWER.NS",
        "NTPC.NS","POWERGRID.NS","SOLARINDS.NS",
    ]},
    **{s: "^CNXAUTO" for s in [
        "MARUTI.NS","BAJAJ-AUTO.NS","M&M.NS","EICHERMOT.NS",
        "TVSMOTOR.NS","MOTHERSON.NS","BOSCHLTD.NS","CUMMINSIND.NS",
    ]},
    **{s: "^CNXPHARMA" for s in [
        "SUNPHARMA.NS","DRREDDY.NS","CIPLA.NS","DIVISLAB.NS",
        "TORNTPHARM.NS","APOLLOHOSP.NS","ZYDUSLIFE.NS","MAXHEALTH.NS",
    ]},
    **{s: "^CNXMETAL" for s in [
        "JSWSTEEL.NS","TATASTEEL.NS","HINDALCO.NS","VEDL.NS",
        "COALINDIA.NS","HINDZINC.NS","JINDALSTEL.NS",
    ]},
    **{s: "^CNXFMCG" for s in [
        "HINDUNILVR.NS","ITC.NS","NESTLEIND.NS","BRITANNIA.NS",
        "TATACONSUM.NS","GODREJCP.NS","VBL.NS","UNITDSPR.NS",
    ]},
    **{s: "^CNXINFRA" for s in [
        "LT.NS","ADANIENT.NS","ADANIPORTS.NS","BEL.NS","HAL.NS",
        "SIEMENS.NS","ABB.NS","CGPOWER.NS","MAZDOCK.NS",
        "DLF.NS","LODHA.NS","BHARTIARTL.NS",
    ]},
    **{s: "^CNXCONSUM" for s in [
        "ULTRACEMCO.NS","GRASIM.NS","AMBUJACEM.NS","SHREECEM.NS",
        "ASIANPAINT.NS","PIDILITIND.NS",
        "TITAN.NS","TRENT.NS","DMART.NS","INDHOTEL.NS","INDIGO.NS",
        "ETERNAL.NS",
    ]},
}

SECTOR_LABEL_MAP = {
    "XLK": "Technology",
    "XLF": "Financials",
    "XLV": "Healthcare",
    "XLP": "Cons. Staples",
    "XLY": "Cons. Discret.",
    "XLE": "Energy",
    "XLI": "Industrials",
    "XLC": "Comm. Services",
    "XLB": "Materials",
    "^NSEBANK": "Banking",
    "NIFTY_FIN_SERVICE.NS": "Fin. Services",
    "^CNXIT": "IT",
    "^CNXENERGY": "Energy",
    "^CNXAUTO": "Auto",
    "^CNXPHARMA": "Pharma",
    "^CNXMETAL": "Metals",
    "^CNXFMCG": "FMCG",
    "^CNXINFRA": "Infra/Defence",
    "^CNXCONSUM": "Cons. Goods",
}

def get_sector(ticker, exchange):
    """Return a friendly sector label for a given ticker."""
    if exchange == "NYSE":
        code = USA_SECTOR_MAP.get(ticker)
    else:
        code = INDIA_SECTOR_MAP.get(ticker + ".NS") or INDIA_SECTOR_MAP.get(ticker)
    if code:
        return SECTOR_LABEL_MAP.get(code, code)
    return "—"

# ── Synthetic pattern pool ────────────────────────────────────────────────────
PATTERNS = [
    "downtrend","uptrend","channel_up","channel_down","triangle_sym",
    "triangle_asc","triangle_desc","wedge_rise","wedge_fall","consolidation",
    "parabolic","hs_pattern","inv_hs","double_top","double_bottom","flag",
    "downtrend","channel_up","triangle_asc","uptrend","wedge_fall","parabolic",
    "consolidation","channel_down","triangle_sym","inv_hs","flag","uptrend",
    "hs_pattern","double_bottom",
]
DIRS = [
    "up","down","up","down","up","up","down","down","up","up",
    "up","down","up","down","up","up","up","up","up","down",
    "down","up","up","down","up","up","up","down","down","up",
]

# ── Live Data via yfinance (with synthetic fallback) ─────────────────────────
_yf_cache = {}

def fetch_yf(yf_ticker, period="6mo"):
    """Fetch OHLCV from yfinance with caching. Returns DataFrame or None."""
    if yf_ticker in _yf_cache:
        return _yf_cache[yf_ticker]
    try:
        import io, sys
        _stderr = sys.stderr
        sys.stderr = io.StringIO()
        try:
            df = yf.Ticker(yf_ticker).history(period=period, auto_adjust=True)
        finally:
            sys.stderr = _stderr
        if df is None or len(df) < 30:
            _yf_cache[yf_ticker] = None
            return None
        df = df[["Open","High","Low","Close","Volume"]].copy()
        idx = pd.to_datetime(df.index)
        df.index = idx.tz_convert(None) if idx.tz is not None else idx
        _yf_cache[yf_ticker] = df
        return df
    except Exception:
        _yf_cache[yf_ticker] = None
        return None

def generate_ohlcv(base_price, pattern="random", days=130):
    """Synthetic OHLCV fallback — used only when yfinance is unavailable."""
    prices = [base_price]
    vol = base_price * 0.015
    for i in range(1, days):
        p = prices[-1]
        phase = i / days
        d = {
            "uptrend":       vol * 0.30,
            "downtrend":    -vol * 0.30,
            "channel_up":    vol * 0.20,
            "channel_down": -vol * 0.20,
            "wedge_rise":    vol * 0.10 * (1 - phase * 0.5),
            "wedge_fall":   -vol * 0.10 * (1 - phase * 0.5),
            "consolidation": 0,
            "parabolic":     vol * phase * 0.5,
            "flag":          vol * 0.10 if phase < 0.6 else -vol * 0.05,
        }.get(pattern, 0)
        if pattern == "triangle_sym":
            d = vol * (1 - phase) * math.sin(i * 0.5) * 0.1
        elif pattern == "triangle_asc":
            d = vol * 0.15 if i % 4 < 2 else -vol * 0.05
        elif pattern == "triangle_desc":
            d = -vol * 0.15 if i % 4 < 2 else vol * 0.05
        elif pattern in ("hs_pattern", "double_top"):
            if phase < 0.4:   d = vol * 0.25
            elif phase < 0.7: d = vol * math.sin(i * 0.8) * 0.15
            else:              d = -vol * 0.20
        elif pattern in ("inv_hs", "double_bottom"):
            if phase < 0.4:   d = -vol * 0.25
            elif phase < 0.7: d = vol * math.sin(i * 0.8) * 0.15
            else:              d = vol * 0.20
        noise = np.random.normal(0, vol)
        prices.append(max(p + d + noise, p * 0.5))
    dates = [datetime.today() - timedelta(days=days - i - 1) for i in range(days)]
    rows = []
    for i, p in enumerate(prices):
        sp = abs(np.random.normal(0, p * 0.008))
        vol_v = int(abs(np.random.normal(1e6, 3e5)) * (base_price / 100))
        rows.append({"Date": dates[i], "Open": p + np.random.normal(0, p*0.003),
                     "High": p+sp, "Low": p-sp, "Close": p, "Volume": max(vol_v,100)})
    return pd.DataFrame(rows).set_index("Date")

def inject_breakout(df, direction="up"):
    """Synthetic fallback only — injects artificial breakout into fake data."""
    ar = (df["High"] - df["Low"]).mean()
    df["Volume"] = df["Volume"].astype(float)
    for i in range(-3, 0):
        orig_close = float(df["Close"].iloc[i])
        orig_vol   = float(df["Volume"].iloc[i])
        if direction == "up":
            df.iloc[i, df.columns.get_loc("Close")]  = orig_close + ar * 1.8
            df.iloc[i, df.columns.get_loc("High")]   = orig_close + ar * 2.2
            df.iloc[i, df.columns.get_loc("Volume")] = orig_vol   * 2.5
        else:
            df.iloc[i, df.columns.get_loc("Close")]  = orig_close - ar * 1.8
            df.iloc[i, df.columns.get_loc("Low")]    = orig_close - ar * 2.2
            df.iloc[i, df.columns.get_loc("Volume")] = orig_vol   * 2.5
    return df

def fetch_data(ticker, base_price, idx, exchange="NSE"):
    """
    Fetch real OHLCV via yfinance.
    NSE tickers get .NS suffix. Falls back to synthetic data if yfinance
    is unavailable or returns insufficient data.
    """
    if YF_AVAILABLE:
        yf_ticker = (ticker + ".NS") if exchange == "NSE" else ticker
        df = fetch_yf(yf_ticker)
        if df is not None and len(df) >= 30:
            return df
        # If .NS failed, try .BO (BSE) for NSE stocks
        if exchange == "NSE":
            df = fetch_yf(ticker + ".BO")
            if df is not None and len(df) >= 30:
                return df
    # Synthetic fallback
    df = generate_ohlcv(base_price, pattern=PATTERNS[idx % len(PATTERNS)])
    return inject_breakout(df, direction=DIRS[idx % len(DIRS)])

# ── Pivot Detection ───────────────────────────────────────────────────────────
def find_pivots(series, order=5):
    highs, lows, arr = [], [], series.values
    for i in range(order, len(arr) - order):
        w = arr[i - order:i + order + 1]
        if arr[i] == w.max(): highs.append((i, float(arr[i])))
        if arr[i] == w.min(): lows.append((i, float(arr[i])))
    return highs, lows


# ═══════════════════════════════════════════════════════════════════════════════
#  ALL 20 TRENDLINE DETECTORS
# ═══════════════════════════════════════════════════════════════════════════════

def mk(type_, signal, num, detail, tl):
    return {"type": type_, "signal": signal, "num": num, "detail": detail, "tl": round(float(tl), 2)}


# ── 1. Uptrend Line ───────────────────────────────────────────────────────────
def check_uptrend_line(df):
    _, lows = find_pivots(df["Low"])
    if len(lows) < 2: return None
    (i1, p1), (i2, p2) = lows[-2], lows[-1]
    if p2 <= p1: return None
    proj = p2 + (p2 - p1) / max(i2 - i1, 1) * (len(df) - 1 - i2)
    cur, prev = float(df["Close"].iloc[-1]), float(df["Close"].iloc[-2])
    if prev >= proj * 0.99 and cur < proj * 0.985:
        return mk("Uptrend Line Break", "BEARISH", "1",
                  "Price broke below ascending higher-lows trendline → downside risk", proj)
    if cur > proj * 1.01 and prev <= proj:
        return mk("Uptrend Line Bounce", "BULLISH", "1",
                  "Rebounded from uptrend support trendline → continuation expected", proj)

# ── 2. Downtrend Line ─────────────────────────────────────────────────────────
def check_downtrend_line(df):
    highs, _ = find_pivots(df["High"])
    if len(highs) < 2: return None
    (i1, p1), (i2, p2) = highs[-2], highs[-1]
    if p2 >= p1: return None
    proj = p2 + (p2 - p1) / max(i2 - i1, 1) * (len(df) - 1 - i2)
    cur, prev = float(df["Close"].iloc[-1]), float(df["Close"].iloc[-2])
    if prev <= proj * 1.01 and cur > proj * 1.015:
        return mk("Downtrend Line Breakout", "BULLISH", "2",
                  "Broke above descending lower-highs trendline → bullish reversal", proj)

# ── 3. Horizontal Support / Resistance ────────────────────────────────────────
def check_horizontal(df):
    r = df.tail(60)
    res = float(r["High"].quantile(0.92))
    sup = float(r["Low"].quantile(0.08))
    cur, prev = float(df["Close"].iloc[-1]), float(df["Close"].iloc[-2])
    if prev < res * 1.005 and cur > res * 1.012:
        return mk("Horizontal Resistance Breakout", "BULLISH", "3",
                  f"Broke above flat multi-week resistance at {res:.2f}", res)
    if prev > sup * 0.995 and cur < sup * 0.988:
        return mk("Horizontal Support Breakdown", "BEARISH", "3",
                  f"Broke below key flat support floor at {sup:.2f}", sup)

# ── 4. Channel ────────────────────────────────────────────────────────────────
def check_channel(df):
    ph, pl = find_pivots(df["High"]), find_pivots(df["Low"])
    ph, pl = ph[0], pl[1]
    if len(ph) < 2 or len(pl) < 2: return None
    (hi1, hv1), (hi2, hv2) = ph[-2], ph[-1]
    (li1, lv1), (li2, lv2) = pl[-2], pl[-1]
    us = (hv2 - hv1) / max(hi2 - hi1, 1)
    ls = (lv2 - lv1) / max(li2 - li1, 1)
    n = len(df) - 1
    upper = hv2 + us * (n - hi2)
    lower = lv2 + ls * (n - li2)
    cur, prev = float(df["Close"].iloc[-1]), float(df["Close"].iloc[-2])
    ch = "Ascending" if ls > 0.001 else "Descending" if ls < -0.001 else "Sideways"
    if prev < upper and cur > upper * 1.01:
        return mk(f"{ch} Channel Breakout", "BULLISH", "4",
                  f"Broke above upper {ch.lower()} channel resistance", upper)
    if prev > lower and cur < lower * 0.99:
        return mk(f"{ch} Channel Breakdown", "BEARISH", "4",
                  f"Broke below lower {ch.lower()} channel support", lower)

# ── 5. Triangle ───────────────────────────────────────────────────────────────
def check_triangle(df):
    ph, pl = find_pivots(df["High"]), find_pivots(df["Low"])
    ph, pl = ph[0], pl[1]
    if len(ph) < 2 or len(pl) < 2: return None
    (hi1, hv1), (hi2, hv2) = ph[-2], ph[-1]
    (li1, lv1), (li2, lv2) = pl[-2], pl[-1]
    us = (hv2 - hv1) / max(hi2 - hi1, 1)
    ls = (lv2 - lv1) / max(li2 - li1, 1)
    # Filter out pure channels (both slopes same direction)
    if (us > 0 and ls > 0) or (us < 0 and ls < 0): return None
    n = len(df) - 1
    upper = hv2 + us * (n - hi2)
    lower = lv2 + ls * (n - li2)
    cur, prev = float(df["Close"].iloc[-1]), float(df["Close"].iloc[-2])
    tri = ("Ascending Triangle" if abs(us) < 0.003 and ls > 0
           else "Descending Triangle" if us < 0 and abs(ls) < 0.003
           else "Symmetrical Triangle")
    if prev < upper and cur > upper * 1.01:
        return mk(f"{tri} Breakout", "BULLISH", "5",
                  f"Explosive breakout from compressed {tri.lower()}", upper)
    if prev > lower and cur < lower * 0.99:
        return mk(f"{tri} Breakdown", "BEARISH", "5",
                  f"Broke down from {tri.lower()} pattern", lower)

# ── 6. Wedge ─────────────────────────────────────────────────────────────────
def check_wedge(df):
    ph, pl = find_pivots(df["High"]), find_pivots(df["Low"])
    ph, pl = ph[0], pl[1]
    if len(ph) < 2 or len(pl) < 2: return None
    (hi1, hv1), (hi2, hv2) = ph[-2], ph[-1]
    (li1, lv1), (li2, lv2) = pl[-2], pl[-1]
    us = (hv2 - hv1) / max(hi2 - hi1, 1)
    ls = (lv2 - lv1) / max(li2 - li1, 1)
    n = len(df) - 1
    upper = hv2 + us * (n - hi2)
    lower = lv2 + ls * (n - li2)
    cur, prev = float(df["Close"].iloc[-1]), float(df["Close"].iloc[-2])
    if us < -0.001 and ls < -0.001 and cur > upper * 1.01 and prev <= upper:
        return mk("Falling Wedge Breakout", "BULLISH", "6",
                  "Classic falling wedge breakout — both lines slope down, price breaks up", upper)
    if us > 0.001 and ls > 0.001 and cur < lower * 0.99 and prev >= lower:
        return mk("Rising Wedge Breakdown", "BEARISH", "6",
                  "Rising wedge breakdown — overbought reversal, both lines slope up", lower)

# ── 7. Flag & Pennant ─────────────────────────────────────────────────────────
# FIX-13: pole_move threshold is now exchange-aware (7% NSE, 4% NYSE)
def check_flag_pennant(df, exchange="NSE"):
    n = len(df)
    if n < 30: return None
    pole = df.iloc[-30:-15]
    flag = df.iloc[-15:]
    pole_move = (float(pole["Close"].iloc[-1]) - float(pole["Close"].iloc[0])) / max(float(pole["Close"].iloc[0]), 0.001)
    flag_high = float(flag["High"].max())
    flag_low  = float(flag["Low"].min())
    flag_range = (flag_high - flag_low) / max(float(flag["Close"].mean()), 0.001)
    cur  = float(df["Close"].iloc[-1])
    prev = float(df["Close"].iloc[-2])
    # FIX-13: NSE stocks are high-beta; require a stronger pole move
    min_pole = 0.07 if exchange == "NSE" else 0.04
    if pole_move > min_pole and flag_range < 0.06 and cur > flag_high * 1.005 and prev <= flag_high:
        return mk("Bull Flag / Pennant Breakout", "BULLISH", "7",
                  f"Flag breakout after +{pole_move*100:.1f}% pole — tight consolidation broken upward", flag_high)
    if pole_move < -min_pole and flag_range < 0.06 and cur < flag_low * 0.995 and prev >= flag_low:
        return mk("Bear Flag Breakdown", "BEARISH", "7",
                  f"Bear flag breakdown after {pole_move*100:.1f}% pole — continuation lower", flag_low)

# ── 8. Fan Lines ──────────────────────────────────────────────────────────────
def check_fan_lines(df):
    _, lows = find_pivots(df["Low"], order=8)
    if len(lows) < 4: return None
    # FIX: Use most significant swing low (largest drop to it) as origin, not oldest
    # Find the lowest pivot in the list as the fan origin
    oi, ov = min(lows, key=lambda x: x[1])
    n = len(df) - 1
    # Only use lows that come AFTER the origin
    subsequent = [(i, v) for i, v in lows if i > oi]
    if len(subsequent) < 3: return None
    slopes = [(v - ov) / max(i - oi, 1) for i, v in subsequent[:3]]
    fan1 = ov + slopes[0] * (n - oi)
    fan2 = ov + slopes[1] * (n - oi)
    fan3 = ov + slopes[2] * (n - oi)
    cur, prev = float(df["Close"].iloc[-1]), float(df["Close"].iloc[-2])
    if prev >= fan3 * 0.99 and cur < fan3 * 0.985:
        return mk("Fan Line 3rd Break (Major)", "BEARISH", "8",
                  "All 3 fan lines broken — major trend exhaustion and reversal confirmed", fan3)
    if prev <= fan1 * 1.01 and cur > fan1 * 1.015:
        return mk("Fan Line 1st Break (Bounce)", "BULLISH", "8",
                  "Price broke above first fan line — early trend recovery signal", fan1)

# ── 9. Internal Trendline ─────────────────────────────────────────────────────
# FIX-06: regression limited to last 50 bars (was entire dataset ~130 bars)
def check_internal_trendline(df):
    lookback = min(50, len(df))
    bodies = ((df["Open"] + df["Close"]) / 2).values[-lookback:]
    x = np.arange(lookback)
    sl, ic = np.polyfit(x, bodies, 1)
    n = lookback - 1
    proj      = sl * n + ic
    prev_proj = sl * (n - 1) + ic
    cur, prev = float(df["Close"].iloc[-1]), float(df["Close"].iloc[-2])
    if prev <= prev_proj * 1.005 and cur > proj * 1.012:
        return mk("Internal Trendline Breakout (Up)", "BULLISH", "9",
                  "Broke above internal mid-body regression line — momentum shift up", proj)
    if prev >= prev_proj * 0.995 and cur < proj * 0.988:
        return mk("Internal Trendline Breakdown (Down)", "BEARISH", "9",
                  "Broke below internal mid-body regression line — momentum shift down", proj)

# ── 10. Dynamic EMA Trendlines ────────────────────────────────────────────────
def check_ema_dynamic(df):
    c = df["Close"]
    results = []
    for period, label in [(20, "EMA20"), (50, "EMA50"), (200, "EMA200")]:
        if len(c) < period + 2: continue
        ema = c.ewm(span=period, adjust=False).mean()
        cc, pc = float(c.iloc[-1]), float(c.iloc[-2])
        ce, pe = float(ema.iloc[-1]), float(ema.iloc[-2])
        if pc < pe * 1.002 and cc > ce * 1.008:
            results.append(mk(f"{label} Dynamic Breakout", "BULLISH", "10",
                              f"Price crossed above {label} dynamic trendline — bullish momentum", ce))
        elif pc > pe * 0.998 and cc < ce * 0.992:
            results.append(mk(f"{label} Dynamic Breakdown", "BEARISH", "10",
                              f"Price fell below {label} dynamic trendline — bearish momentum", ce))
    return results

# ── 11. Neckline — Head & Shoulders / Inverse H&S ────────────────────────────
def check_neckline(df):
    highs, lows = find_pivots(df["High"], order=8), find_pivots(df["Low"], order=8)
    highs, lows = highs[0], lows[1]
    cur, prev = float(df["Close"].iloc[-1]), float(df["Close"].iloc[-2])

    # Inverse H&S
    if len(lows) >= 3:
        ls_i, ls_v = lows[-3]
        h_i,  h_v  = lows[-2]
        rs_i, rs_v = lows[-1]
        if h_v < ls_v and h_v < rs_v and abs(ls_v - rs_v) / max(ls_v, 0.001) < 0.05:
            mid_highs = [v for i, v in highs if ls_i < i < rs_i]
            if mid_highs:
                neckline = sum(mid_highs) / len(mid_highs)
                if prev <= neckline * 1.005 and cur > neckline * 1.01:
                    return mk("Inverse H&S Neckline Breakout", "BULLISH", "11",
                              f"Classic Inverse Head & Shoulders — neckline at {neckline:.2f} broken upward", neckline)

    # H&S
    if len(highs) >= 3:
        ls_i, ls_v = highs[-3]
        h_i,  h_v  = highs[-2]
        rs_i, rs_v = highs[-1]
        if h_v > ls_v and h_v > rs_v and abs(ls_v - rs_v) / max(ls_v, 0.001) < 0.05:
            mid_lows = [v for i, v in lows if ls_i < i < rs_i]
            if mid_lows:
                neckline = sum(mid_lows) / len(mid_lows)
                if prev >= neckline * 0.995 and cur < neckline * 0.99:
                    return mk("H&S Neckline Breakdown", "BEARISH", "11",
                              f"Classic Head & Shoulders — neckline at {neckline:.2f} broken downward", neckline)

# ── 12. Fibonacci Trendline ───────────────────────────────────────────────────
# FIX-09: EMA slope filter added — only fire Fib signals aligned with EMA trend direction
def check_fibonacci_trendline(df):
    recent = df.tail(60)
    swing_high = float(recent["High"].max())
    swing_low  = float(recent["Low"].min())
    diff = swing_high - swing_low
    fib_levels = {
        "23.6%": swing_high - diff * 0.236,
        "38.2%": swing_high - diff * 0.382,
        "50.0%": swing_high - diff * 0.500,
        "61.8%": swing_high - diff * 0.618,
        "78.6%": swing_high - diff * 0.786,
    }
    cur, prev = float(df["Close"].iloc[-1]), float(df["Close"].iloc[-2])

    # FIX-09: Determine trend direction via EMA50 slope
    ema50 = df["Close"].ewm(span=50, adjust=False).mean()
    ema_slope_up = float(ema50.iloc[-1]) > float(ema50.iloc[-5])  # rising over last 5 bars

    for label, level in fib_levels.items():
        # Bullish Fib bounce: only fire when trend is up (EMA rising)
        if ema_slope_up and prev < level * 0.998 and cur > level * 1.005:
            return mk(f"Fibonacci {label} Breakout", "BULLISH", "12",
                      f"Price broke above Fib {label} retracement level at {level:.2f} — uptrend aligned", level)
        # Bearish Fib rejection: only fire when trend is down (EMA falling)
        if not ema_slope_up and prev > level * 1.002 and cur < level * 0.995:
            return mk(f"Fibonacci {label} Breakdown", "BEARISH", "12",
                      f"Price broke below Fib {label} support level at {level:.2f} — downtrend aligned", level)

# ── 13. Pitchfork / Andrews Pitchfork ────────────────────────────────────────
# FIX-05: All pivot candidates are sorted by bar-index before A/B/C assignment
def check_pitchfork(df):
    highs, lows = find_pivots(df["High"], order=10), find_pivots(df["Low"], order=10)
    highs, lows = highs[0], lows[1]
    if len(highs) < 2 or len(lows) < 2: return None
    try:
        # Merge all pivots, tag type, sort chronologically
        all_pivots = [("H", i, v) for i, v in highs] + [("L", i, v) for i, v in lows]
        all_pivots.sort(key=lambda x: x[1])
        # Need at least 3 alternating pivots: H-L-H or L-H-L pattern
        # Andrews Pitchfork: A=first pivot, B=second pivot, C=third pivot
        # Best is: A=high, B=low, C=high (bullish pitchfork)
        # Find last H-L-H sequence
        A_t = A_i = A_v = B_t = B_i = B_v = C_t = C_i = C_v = None
        for k in range(len(all_pivots) - 2):
            t1, i1, v1 = all_pivots[k]
            t2, i2, v2 = all_pivots[k+1]
            t3, i3, v3 = all_pivots[k+2]
            if t1 == "H" and t2 == "L" and t3 == "H":
                A_t, A_i, A_v = t1, i1, v1
                B_t, B_i, B_v = t2, i2, v2
                C_t, C_i, C_v = t3, i3, v3
        if A_i is None: return None
        if not (A_i < B_i < C_i): return None
    except Exception as e:
        logging.debug(f"check_pitchfork pivot unpacking failed: {e}")
        return None
    mid_bc_v = (B_v + C_v) / 2
    mid_bc_i = (B_i + C_i) / 2
    ml_slope = (mid_bc_v - A_v) / max(mid_bc_i - A_i, 1)
    n = len(df) - 1
    median_val  = A_v + ml_slope * (n - A_i)
    prev_median = A_v + ml_slope * (n - 1 - A_i)
    cur, prev = float(df["Close"].iloc[-1]), float(df["Close"].iloc[-2])
    if prev <= prev_median * 1.005 and cur > median_val * 1.01:
        return mk("Pitchfork Median Line Breakout", "BULLISH", "13",
                  f"Price broke above Andrews Pitchfork median line — bullish acceleration", median_val)
    if prev >= prev_median * 0.995 and cur < median_val * 0.99:
        return mk("Pitchfork Median Line Breakdown", "BEARISH", "13",
                  f"Price broke below Andrews Pitchfork median line — bearish shift", median_val)

# ── 14. Linear Regression Channel ────────────────────────────────────────────
# FIX-03: Description corrected — kept momentum breakout interpretation (upper=BULL, lower=BEAR)
#         and fixed misleading "mean reversion exhausted" wording on lower breakdown
def check_regression_channel(df):
    n = min(50, len(df))
    closes = df["Close"].values[-n:]
    x = np.arange(n)
    sl, ic = np.polyfit(x, closes, 1)
    residuals = closes - (sl * x + ic)
    std = residuals.std()
    upper_band = sl * (n - 1) + ic + 2 * std
    lower_band = sl * (n - 1) + ic - 2 * std
    cur, prev  = float(df["Close"].iloc[-1]), float(df["Close"].iloc[-2])
    prev_upper = sl * (n - 2) + ic + 2 * std
    prev_lower = sl * (n - 2) + ic - 2 * std
    if prev <= prev_upper * 1.005 and cur > upper_band * 1.01:
        return mk("Regression Channel Upper Breakout", "BULLISH", "14",
                  f"Broke above 2σ upper regression band — strong momentum, parabolic extension possible", upper_band)
    # FIX-03: Description corrected — "breakdown below lower band" not "mean reversion exhausted"
    if prev >= prev_lower * 0.995 and cur < lower_band * 0.99:
        return mk("Regression Channel Lower Breakdown", "BEARISH", "14",
                  f"Broke below 2σ lower regression band — accelerating sell-off below lower channel", lower_band)

# ── 15. Acceleration / Parabolic Trendline ───────────────────────────────────
# FIX-07: Correlation threshold lowered 0.90→0.80; residual relaxed to 2-of-3
def check_acceleration(df):
    n = 20
    if len(df) < n: return None
    closes = df["Close"].values[-n:]
    x = np.arange(n)
    sl, ic = np.polyfit(x, closes, 1)
    residuals = closes - (sl * x + ic)
    r_corr = np.corrcoef(x, closes)[0, 1]
    recent_resid = residuals[-5:]
    projected = sl * (n - 1) + ic
    # FIX-07: threshold 0.90→0.80, and 2-of-3 last residuals (not all 3)
    if r_corr > 0.80 and sl > 0 and sum(1 for r in recent_resid[-3:] if r > 0) >= 2:
        return mk("Parabolic Acceleration Breakout", "BULLISH", "15",
                  f"Price accelerating above regression — parabolic up-move (R={r_corr:.2f}, slope={sl:.2f}/day)", projected)
    if r_corr < -0.80 and sl < 0 and sum(1 for r in recent_resid[-3:] if r < 0) >= 2:
        return mk("Parabolic Deceleration Breakdown", "BEARISH", "15",
                  f"Price accelerating below regression — parabolic downmove (R={r_corr:.2f})", projected)

# ── 16. Base Trendline (Accumulation Floor) ───────────────────────────────────
# FIX-04: Added missing BEARISH base failure signal
# FIX-12: base_range threshold is exchange-aware (0.20 NSE, 0.15 NYSE)
def check_base_trendline(df, exchange="NSE"):
    if len(df) < 40: return None
    base_zone  = df.tail(40)
    low_floor  = float(base_zone["Low"].quantile(0.10))
    high_roof  = float(base_zone["High"].quantile(0.90))
    base_range = (high_roof - low_floor) / max(float(base_zone["Close"].mean()), 0.001)
    cur, prev  = float(df["Close"].iloc[-1]), float(df["Close"].iloc[-2])
    # FIX-12: NSE high-beta stocks have wider natural ranges
    max_range = 0.20 if exchange == "NSE" else 0.15
    if base_range < max_range:
        if prev <= high_roof * 1.005 and cur > high_roof * 1.015:
            return mk("Base Trendline Breakout (Accumulation)", "BULLISH", "16",
                      f"Price broke out of 40-bar accumulation base — strong institutional buying", high_roof)
        # FIX-04: Bearish base failure — breakdown below base floor
        if prev >= low_floor * 0.995 and cur < low_floor * 0.985:
            return mk("Base Trendline Failure (Distribution)", "BEARISH", "16",
                      f"Price broke below 40-bar base floor at {low_floor:.2f} — distribution/panic selling", low_floor)

# ── 17. Role Reversal / Polarity Flip ────────────────────────────────────────
# FIX-11: Proximity band widened from 2% to 3%
def check_role_reversal(df):
    highs, lows = find_pivots(df["High"], order=8), find_pivots(df["Low"], order=8)
    highs, lows = highs[0], lows[1]
    cur, prev = float(df["Close"].iloc[-1]), float(df["Close"].iloc[-2])
    # Old resistance becoming support
    if len(highs) >= 2:
        old_res_i, old_res_v = highs[-2]
        recent_min = float(df["Close"].tail(10).min())
        # FIX-11: band widened 2%→3%
        if (recent_min >= old_res_v * 0.97 and recent_min <= old_res_v * 1.03
                and cur > old_res_v * 1.01 and prev <= old_res_v * 1.01):
            return mk("Role Reversal — Old Resistance Now Support", "BULLISH", "17",
                      f"Polarity flip: old resistance {old_res_v:.2f} held as support → bullish continuation", old_res_v)
    # Old support becoming resistance
    if len(lows) >= 2:
        old_sup_i, old_sup_v = lows[-2]
        recent_max = float(df["Close"].tail(10).max())
        # FIX-11: band widened 2%→3%
        if (recent_max >= old_sup_v * 0.97 and recent_max <= old_sup_v * 1.03
                and cur < old_sup_v * 0.99 and prev >= old_sup_v * 0.99):
            return mk("Role Reversal — Old Support Now Resistance", "BEARISH", "17",
                      f"Polarity flip: old support {old_sup_v:.2f} now acting as resistance → bearish continuation", old_sup_v)

# ── 18. Speed Resistance Lines ────────────────────────────────────────────────
# FIX-08: 2/3 level checked before 1/3 — stronger breakdown/recovery checked first
def check_speed_resistance(df):
    recent = df.tail(60)
    swing_high = float(recent["High"].max())
    swing_low  = float(recent["Low"].min())
    diff = swing_high - swing_low
    srl_33 = swing_high - diff * (1 / 3)  # 1/3 line (higher)
    srl_67 = swing_high - diff * (2 / 3)  # 2/3 line (lower, stronger signal)
    cur, prev = float(df["Close"].iloc[-1]), float(df["Close"].iloc[-2])
    # FIX-08: Check stronger 2/3 first
    if prev > srl_67 * 0.998 and cur < srl_67 * 0.992:
        return mk("Speed Resistance 2/3 Line Break", "BEARISH", "18",
                  f"Broke below 2/3 Speed Resistance Line at {srl_67:.2f} — major support lost", srl_67)
    if prev > srl_33 * 0.998 and cur < srl_33 * 0.992:
        return mk("Speed Resistance 1/3 Line Break", "BEARISH", "18",
                  f"Broke below 1/3 Speed Resistance Line at {srl_33:.2f} — correction deepening", srl_33)
    if prev < srl_33 * 1.002 and cur > srl_33 * 1.008:
        return mk("Speed Resistance 1/3 Line Recovery", "BULLISH", "18",
                  f"Recovered above 1/3 Speed Resistance Line at {srl_33:.2f} — trend resuming", srl_33)
    if prev < srl_67 * 1.002 and cur > srl_67 * 1.008:
        return mk("Speed Resistance 2/3 Line Recovery", "BULLISH", "18",
                  f"Recovered above 2/3 Speed Resistance Line at {srl_67:.2f} — major support reclaimed", srl_67)

# ── 19. Candlestick Body Trendline (No-Wick) ─────────────────────────────────
def check_body_trendline(df):
    body_highs = df[["Open", "Close"]].max(axis=1)
    body_lows  = df[["Open", "Close"]].min(axis=1)
    bh_pivots, bl_pivots = find_pivots(body_highs, order=5), find_pivots(body_lows, order=5)
    bh_pivots, bl_pivots = bh_pivots[0], bl_pivots[1]
    cur, prev = float(df["Close"].iloc[-1]), float(df["Close"].iloc[-2])

    if len(bh_pivots) >= 2:
        (i1, v1), (i2, v2) = bh_pivots[-2], bh_pivots[-1]
        if v2 < v1:
            proj = v2 + (v2 - v1) / max(i2 - i1, 1) * (len(df) - 1 - i2)
            if prev <= proj * 1.005 and cur > proj * 1.012:
                return mk("Body Trendline Breakout (No-Wick)", "BULLISH", "19",
                          f"Broke above candle-body downtrend line (wick-filtered) at {proj:.2f}", proj)

    if len(bl_pivots) >= 2:
        (i1, v1), (i2, v2) = bl_pivots[-2], bl_pivots[-1]
        if v2 > v1:
            proj = v2 + (v2 - v1) / max(i2 - i1, 1) * (len(df) - 1 - i2)
            if prev >= proj * 0.995 and cur < proj * 0.988:
                return mk("Body Trendline Breakdown (No-Wick)", "BEARISH", "19",
                          f"Broke below candle-body uptrend line (wick-filtered) at {proj:.2f}", proj)

# ── 20. Gann Angle (1×1 = 45°) ───────────────────────────────────────────────
# FIX-02: unit = origin_v * 0.001 (was /100 = 1% per bar — 100× too aggressive)
def check_gann_angle(df):
    if len(df) < 30: return None
    _, lows = find_pivots(df["Low"], order=10)
    if not lows: return None
    origin_i, origin_v = lows[-1]
    n = len(df) - 1
    # FIX-02: Gann 1×1 unit = 0.1% of origin per bar (realistic for daily charts)
    unit = origin_v * 0.001
    gann_1x1  = origin_v + unit * (n - origin_i)
    prev_gann = origin_v + unit * (n - 1 - origin_i)
    cur, prev = float(df["Close"].iloc[-1]), float(df["Close"].iloc[-2])
    if prev <= prev_gann * 1.005 and cur > gann_1x1 * 1.01:
        return mk("Gann 1×1 Angle Breakout (45°)", "BULLISH", "20",
                  f"Price broke above Gann 1×1 angle from origin {origin_v:.2f} — trend acceleration", gann_1x1)
    if prev >= prev_gann * 0.995 and cur < gann_1x1 * 0.99:
        return mk("Gann 1×1 Angle Breakdown (45°)", "BEARISH", "20",
                  f"Price fell below Gann 1×1 angle from origin {origin_v:.2f} — trend weakening", gann_1x1)

# ── Category mapper ───────────────────────────────────────────────────────────
TL_CATEGORIES = {
    "1": "Uptrend Line",     "2": "Downtrend Line",  "3": "Horizontal",
    "4": "Channel",          "5": "Triangle",          "6": "Wedge",
    "7": "Flag & Pennant",   "8": "Fan Lines",         "9": "Internal TL",
    "10": "Dynamic EMA",     "11": "Neckline (H&S)",  "12": "Fibonacci TL",
    "13": "Pitchfork",       "14": "Regression Ch.",  "15": "Acceleration",
    "16": "Base TL",         "17": "Role Reversal",   "18": "Speed Resistance",
    "19": "Body TL",         "20": "Gann Angle",
}

# Single-result detectors (return one result or None)
# Note: check_flag_pennant and check_base_trendline need exchange arg — handled in scan_stock
SINGLE_CHECKERS = [
    check_uptrend_line, check_downtrend_line, check_horizontal,
    check_channel, check_triangle, check_wedge,
    check_fan_lines, check_internal_trendline, check_neckline,
    check_fibonacci_trendline, check_pitchfork, check_regression_channel,
    check_acceleration, check_role_reversal,
    check_speed_resistance, check_body_trendline, check_gann_angle,
]

# ── RSI (14-period, Wilder smoothing) ─────────────────────────────────────────
def calc_rsi(df, period=14):
    delta = df["Close"].diff()
    gain  = delta.clip(lower=0)
    loss  = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    rs  = avg_gain / avg_loss.replace(0, float("nan"))
    rsi = 100 - (100 / (1 + rs))
    val = float(rsi.iloc[-1])
    return round(val, 1) if not np.isnan(val) else None

def rsi_zone(rsi):
    """Return zone label and CSS class for RSI value."""
    if rsi is None:   return "—",       "rz-na"
    if rsi >= 70:     return "OB",      "rz-ob"
    if rsi <= 30:     return "OS",      "rz-os"
    if rsi >= 60:     return "Strong",  "rz-str"
    if rsi <= 40:     return "Weak",    "rz-wk"
    return "Neutral", "rz-neu"

# ── Sector RSI ───────────────────────────────────────────────────────────────
SECTOR_BASE_PRICES = {
    "XLK": 225.40, "XLF": 42.80,  "XLV": 138.60, "XLP": 74.20,
    "XLY": 192.50, "XLE": 88.30,  "XLI": 128.40, "XLC": 82.10,
    "XLB": 88.60,
    "^NSEBANK":           48200.0, "NIFTY_FIN_SERVICE.NS": 21800.0,
    "^CNXIT":             38400.0, "^CNXENERGY":           32100.0,
    "^CNXAUTO":           24800.0, "^CNXPHARMA":           18900.0,
    "^CNXMETAL":          9800.0,  "^CNXFMCG":             56200.0,
    "^CNXINFRA":          8200.0,  "^CNXCONSUM":           10400.0,
}

_sector_rsi_cache = {}

def get_sector_rsi(sector_code):
    if sector_code in _sector_rsi_cache:
        return _sector_rsi_cache[sector_code]
    if YF_AVAILABLE:
        df_s = fetch_yf(sector_code, period="3mo")
        if df_s is not None and len(df_s) >= 15:
            rsi_val = calc_rsi(df_s)
            _sector_rsi_cache[sector_code] = rsi_val
            return rsi_val
    # Synthetic fallback
    base = SECTOR_BASE_PRICES.get(sector_code)
    if base is None:
        _sector_rsi_cache[sector_code] = None
        return None
    extra = sum(ord(c) for c in sector_code)
    rng = random.Random(int(datetime.now().strftime("%Y%m%d")) + extra)
    prices = [base]
    for _ in range(60):
        drift = rng.gauss(0, base * 0.012)
        prices.append(max(prices[-1] + drift, base * 0.3))
    df_s = pd.DataFrame({"Close": prices})
    delta = df_s["Close"].diff()
    gain  = delta.clip(lower=0)
    loss  = (-delta).clip(lower=0)
    ag = gain.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
    al = loss.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
    rs = ag / al.replace(0, float("nan"))
    rsi_s = 100 - (100 / (1 + rs))
    val = float(rsi_s.iloc[-1])
    result = round(val, 1) if not np.isnan(val) else None
    _sector_rsi_cache[sector_code] = result
    return result

def get_sector_rsi_for_ticker(ticker, exchange):
    if exchange == "NYSE":
        code = USA_SECTOR_MAP.get(ticker)
    else:
        code = INDIA_SECTOR_MAP.get(ticker + ".NS") or INDIA_SECTOR_MAP.get(ticker)
    if not code:
        return None, None
    rsi_val = get_sector_rsi(code)
    return rsi_val, code


# ── Deduplication helper ──────────────────────────────────────────────────────
# FIX-10: Keep at most MAX_PER_DIRECTION signals per direction per stock.
#         Within each direction bucket, prefer lower-numbered (more classical) detectors.
MAX_PER_DIRECTION = 2

def deduplicate_signals(results):
    """
    From a list of signals for a single stock, keep at most MAX_PER_DIRECTION
    bullish and MAX_PER_DIRECTION bearish signals.
    Priority: lower trendline number = more classical = higher priority.
    Within the same number, keep only 1 (e.g. one EMA crossover direction).
    """
    bull = [r for r in results if r["signal"] == "BULLISH"]
    bear = [r for r in results if r["signal"] == "BEARISH"]

    def _pick(signals, max_keep):
        # Sort by num (string "1"..."20" — sort numerically)
        signals.sort(key=lambda r: int(r["num"]))
        # De-dup by num: keep first occurrence of each num
        seen_nums = set()
        unique = []
        for s in signals:
            if s["num"] not in seen_nums:
                seen_nums.add(s["num"])
                unique.append(s)
        return unique[:max_keep]

    return _pick(bull, MAX_PER_DIRECTION) + _pick(bear, MAX_PER_DIRECTION)


def scan_stock(ticker, name, base_price, idx, exchange):
    df = fetch_data(ticker, base_price, idx, exchange=exchange)
    cur  = float(df["Close"].iloc[-1])
    prev = float(df["Close"].iloc[-2])
    pct  = round((cur - prev) / prev * 100, 2)
    vol  = int(df["Volume"].iloc[-1])
    avg_vol = int(df["Volume"].tail(20).mean())
    vol_ratio = round(vol / max(avg_vol, 1), 1)
    vol_confirmed = vol > avg_vol * 1.5
    rsi = calc_rsi(df)
    sector_rsi_val, sector_code = get_sector_rsi_for_ticker(ticker, exchange)

    base_info = {
        "ticker": ticker, "name": name, "exchange": exchange,
        "price": round(cur, 2), "change": pct,
        "volume": vol, "vol_ratio": vol_ratio,
        "vol_confirmed": vol_confirmed,
        "sector": get_sector(ticker, exchange),
        "sector_code": sector_code or "—",
        "rsi": rsi,
        "sector_rsi": sector_rsi_val,
    }

    results = []

    # Run all single-result checkers
    for fn in SINGLE_CHECKERS:
        try:
            r = fn(df)
            if r:
                r.update({**base_info, "category": TL_CATEGORIES.get(r["num"], "Other")})
                results.append(r)
        except Exception as e:
            logging.debug(f"[{ticker}] {fn.__name__} failed: {e}")

    # Exchange-aware checkers (need exchange argument)
    for fn, kwargs in [
        (check_flag_pennant,   {"exchange": exchange}),
        (check_base_trendline, {"exchange": exchange}),
    ]:
        try:
            r = fn(df, **kwargs)
            if r:
                r.update({**base_info, "category": TL_CATEGORIES.get(r["num"], "Other")})
                results.append(r)
        except Exception as e:
            logging.debug(f"[{ticker}] {fn.__name__} failed: {e}")

    # Multi-result: EMA dynamic (returns list)
    try:
        for r in (check_ema_dynamic(df) or []):
            r.update({**base_info, "category": TL_CATEGORIES.get(r["num"], "Other")})
            results.append(r)
    except Exception as e:
        logging.debug(f"[{ticker}] check_ema_dynamic failed: {e}")

    # FIX-10: Deduplicate — max MAX_PER_DIRECTION signals per direction
    results = deduplicate_signals(results)

    return results


# ── HTML Builder ──────────────────────────────────────────────────────────────
_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>TrendBreak Pro &middot; NSE &amp; NYSE</title>
<style>
:root{
  --nb:#0a1628;--nb2:#0d1f3c;--nb3:#132550;
  --acc:#2e8fe4;--acc2:#60b8ff;--acc3:#a8dfff;
  --bdr:rgba(56,163,245,0.25);--bdr2:rgba(56,163,245,0.45);
  --txt:#e8f2ff;--mu:#8dafc8;--wh:#ffffff;
  --bu:#34d97b;--be:#f87171;--mx:#fbbf24;
  --nse:#fbbf24;--nyse:#60b8ff;
  --mono:'Courier New',Courier,monospace
}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--nb);color:var(--txt);font-family:system-ui,sans-serif;font-size:13px;min-height:100vh}

/* ── TOPBAR ── */
.topbar{background:var(--nb2);border-bottom:1px solid var(--bdr2);padding:7px 16px;
  display:flex;align-items:center;gap:10px;flex-wrap:wrap;position:sticky;top:0;z-index:100}
.logo{display:flex;align-items:center;gap:8px}
.logo-icon{width:26px;height:26px;background:var(--acc);border-radius:5px;
  display:flex;align-items:center;justify-content:center}
.logo-icon svg{width:14px;height:14px;fill:none;stroke:#fff;stroke-width:2.2;stroke-linecap:round;stroke-linejoin:round}
.logo-name{font-weight:700;font-size:14px;color:#fff;letter-spacing:-.2px}
.logo-sub{font-size:10px;color:var(--acc3);font-family:var(--mono)}
.vsep{width:1px;height:24px;background:var(--bdr2);flex-shrink:0}
.tbadge{font-size:10px;font-family:var(--mono);background:rgba(46,143,228,0.1);
  border:1px solid var(--bdr);color:var(--acc2);border-radius:4px;padding:2px 7px;white-space:nowrap}
.pulse{display:inline-block;width:5px;height:5px;background:var(--bu);border-radius:50%;
  margin-right:3px;vertical-align:middle;animation:pulse 1.8s ease-in-out infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
.topbadges{display:flex;gap:5px;flex-wrap:wrap;margin-left:auto}

/* ── STATS STRIP ── */
.stats{display:flex;background:rgba(0,0,0,0.3);border-bottom:1px solid var(--bdr);overflow-x:auto}
.sc{flex:1;min-width:72px;padding:7px 10px;text-align:center;border-right:1px solid var(--bdr)}
.sc:last-child{border-right:none}
.sn{font-size:20px;font-weight:700;font-family:var(--mono);line-height:1.1}
.sl{font-size:9px;color:var(--acc3);text-transform:uppercase;letter-spacing:.5px;margin-top:1px}

/* ── FILTER BAR ── */
.filterbar{display:flex;align-items:center;gap:6px;padding:8px 14px;
  background:rgba(0,0,0,0.18);border-bottom:1px solid var(--bdr);flex-wrap:wrap}
.fb-sep{width:1px;height:20px;background:var(--bdr2);flex-shrink:0;margin:0 2px}
.btn{padding:4px 13px;border-radius:18px;font-size:11px;font-weight:700;
  border:1px solid var(--bdr);color:var(--mu);background:transparent;
  cursor:pointer;font-family:var(--mono);transition:all .15s}
.btn:hover{border-color:var(--acc2);color:var(--acc2)}
.btn.on{background:rgba(46,143,228,0.15);color:var(--acc2);border-color:var(--bdr2)}
.btn.bull-on{background:rgba(52,217,123,0.12);color:var(--bu);border-color:rgba(52,217,123,0.4)}
.btn.bear-on{background:rgba(248,113,113,0.12);color:var(--be);border-color:rgba(248,113,113,0.4)}
.tb-sect{background:#0d1f3c;color:var(--mu);border:1px solid var(--bdr);border-radius:4px;
  padding:3px 8px;font-size:11px;font-family:var(--mono);cursor:pointer;outline:none}
.tb-sect:focus{border-color:var(--acc2)}
.result-count{font-size:10px;color:var(--mu);font-family:var(--mono);margin-left:auto}

/* ── SECTOR RSI PANEL ── */
.srp{background:rgba(0,0,0,0.2);border-bottom:1px solid var(--bdr);padding:8px 14px}
.srp-title{font-size:9px;color:var(--acc3);text-transform:uppercase;letter-spacing:.5px;
  margin-bottom:6px;font-family:var(--mono)}
.srp-tiles{display:flex;flex-wrap:wrap;gap:6px}
.srp-tile{display:flex;align-items:center;gap:8px;background:rgba(13,31,60,0.7);
  border:1px solid var(--bdr);border-left:3px solid transparent;
  border-radius:5px;padding:5px 10px;
  cursor:pointer;transition:all .18s;white-space:nowrap}
.srp-tile:hover{background:rgba(46,143,228,0.08);border-color:var(--bdr2)}
.srp-tile.active{background:rgba(46,143,228,0.14);border-color:var(--acc2)}
.srp-sname{font-size:10px;font-family:var(--mono);font-weight:700}
.srp-val{font-size:13px;font-weight:700;font-family:var(--mono)}

/* ── EXCHANGE PANELS ── */
.panel{display:none;padding:12px 14px 20px}
.panel.active{display:block}

/* ── CARD GRID ── */
.card-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(305px,1fr));gap:10px}

/* ── STOCK CARDS ── */
.card{background:var(--nb2);border:1px solid var(--bdr);border-left:3px solid transparent;
  border-radius:8px;padding:12px 13px;overflow:hidden;transition:border-color .15s}
.card:hover{border-color:var(--bdr2)}
.card.bull{border-left-color:var(--bu)}
.card.bear{border-left-color:var(--be)}
.card.mix {border-left-color:var(--mx)}

.c-head{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px}
.c-left{min-width:0}
.c-ticker{font-family:var(--mono);font-size:15px;font-weight:700;color:#fff;letter-spacing:.3px}
.c-name{font-size:11px;color:var(--mu);margin-top:2px;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:165px}
.c-right{display:flex;flex-direction:column;align-items:flex-end;gap:4px;flex-shrink:0;margin-left:8px}
.c-sect{font-size:10px;color:var(--mu);background:rgba(255,255,255,0.05);
  border:1px solid var(--bdr);padding:1px 7px;border-radius:3px;
  font-family:var(--mono);white-space:nowrap}
.c-badge{font-size:11px;font-weight:700;padding:2px 9px;border-radius:10px;
  font-family:var(--mono);white-space:nowrap}
.c-badge.bull{background:rgba(52,217,123,0.15);color:var(--bu);border:1px solid rgba(52,217,123,0.35)}
.c-badge.bear{background:rgba(248,113,113,0.15);color:var(--be);border:1px solid rgba(248,113,113,0.35)}
.c-badge.mix {background:rgba(251,191,36,0.15);color:var(--mx);border:1px solid rgba(251,191,36,0.35)}

.c-prow{display:flex;gap:8px;align-items:center;flex-wrap:wrap;
  padding:7px 0;border-top:1px solid rgba(56,163,245,0.12);
  border-bottom:1px solid rgba(56,163,245,0.12);margin-bottom:7px}
.c-price{font-family:var(--mono);font-size:13px;font-weight:700;color:#fff}
.c-chg{font-family:var(--mono);font-size:12px;font-weight:700}
.c-chg.up{color:var(--bu)}.c-chg.dn{color:var(--be)}
.c-rsi{font-size:10px;padding:2px 6px;border-radius:3px;font-family:var(--mono);
  background:rgba(240,246,255,0.08);color:#e8f2ff;font-weight:500}
.c-rsi.bull{background:rgba(52,217,123,0.18);color:var(--bu)}
.c-rsi.bear{background:rgba(248,113,113,0.18);color:var(--be)}
.c-rsi.mix{background:rgba(240,246,255,0.1);color:#e8f2ff}
.c-vol{font-size:10px;color:var(--mu);font-family:var(--mono)}
.c-vol.vok{color:var(--bu)}
.c-tl{font-size:10px;color:var(--acc3);font-family:var(--mono)}

.sig-block{max-height:0;overflow:hidden;opacity:0;
  transition:max-height .28s ease, opacity .2s ease}
.card.expanded .sig-block{max-height:1000px;opacity:1}

.sig{display:flex;align-items:baseline;gap:5px;padding:3px 0;
  border-bottom:1px solid rgba(56,163,245,0.08);font-size:11px}
.sig:last-child{border-bottom:none}
.sig-n{font-family:var(--mono);font-size:10px;background:rgba(255,255,255,0.06);
  color:var(--acc3);padding:1px 5px;border-radius:3px;
  flex-shrink:0;min-width:24px;text-align:center}
.sig-t{color:var(--txt);flex:1;line-height:1.35}
.sig-d{flex-shrink:0;font-size:10px;font-weight:700}
.sig-d.up{color:var(--bu)}.sig-d.dn{color:var(--be)}

.sig-detail{font-size:10px;color:var(--mu);font-style:italic;
  padding:0 0 0 29px;line-height:1.3;max-height:0;overflow:hidden;
  opacity:0;transition:max-height .22s ease, opacity .18s ease, padding .18s ease}
.card.expanded .sig-detail{max-height:60px;opacity:1;padding:1px 0 4px 29px}

.c-toggle{display:flex;align-items:center;gap:4px;margin-top:7px;
  padding:3px 9px;border-radius:10px;font-size:10px;font-family:var(--mono);
  font-weight:700;cursor:pointer;border:1px solid var(--bdr);
  background:rgba(255,255,255,0.04);color:var(--mu);
  width:fit-content;transition:all .15s;user-select:none}
.c-toggle:hover{border-color:var(--acc2);color:var(--acc2)}
.card.expanded .c-toggle{background:rgba(46,143,228,0.1);
  border-color:var(--bdr2);color:var(--acc2)}
.c-toggle-arrow{display:inline-block;transition:transform .2s ease;font-size:9px}
.card.expanded .c-toggle-arrow{transform:rotate(180deg)}

.lgnd{margin:14px 0 0;background:rgba(0,0,0,0.2);border:1px solid var(--bdr);
  border-radius:7px;padding:10px 12px}
.lgt{font-size:9px;letter-spacing:.5px;color:var(--acc3);text-transform:uppercase;
  font-family:var(--mono);margin-bottom:8px}
.lgg{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:3px}
.lgi{font-size:10px;display:flex;align-items:center;gap:5px;padding:1px 0}
.ln{display:inline-flex;align-items:center;justify-content:center;width:18px;height:18px;
  background:rgba(96,184,255,0.15);border:1px solid rgba(96,184,255,0.35);border-radius:3px;
  font-size:9px;font-family:var(--mono);color:var(--acc3);flex-shrink:0;font-weight:700}
.lhit{background:rgba(52,217,123,0.15);color:var(--bu);
  border:1px solid rgba(52,217,123,0.35);border-radius:3px;
  padding:0 5px;font-family:var(--mono);font-size:9px;margin-left:auto}

.empty{text-align:center;color:var(--mu);padding:40px 20px;font-family:var(--mono);font-size:12px}

footer{text-align:center;padding:12px;border-top:1px solid var(--bdr);
  color:var(--mu);font-size:10px;font-family:var(--mono);line-height:2}
footer a{color:var(--acc2);text-decoration:none}

.clock-wrap{display:flex;align-items:center;gap:10px;font-family:var(--mono)}
.clock-item{display:flex;flex-direction:column;align-items:center;gap:1px}
.clock-time{font-size:12px;font-weight:700;color:var(--acc2);letter-spacing:.5px;white-space:nowrap}
.clock-lbl{font-size:9px;color:var(--acc3);letter-spacing:.6px;text-transform:uppercase}
.clock-sep{color:var(--bdr2);font-size:14px;line-height:1}

@media(max-width:600px){
  .topbar{padding:6px 10px}
  .panel{padding:8px 8px 14px}
  .card-grid{grid-template-columns:1fr}
  .stats .sl{display:none}
}
</style></head><body>

<div class="topbar">
  <div class="logo">
    <div class="logo-icon">
      <svg viewBox="0 0 14 14"><polyline points="1,11 4,6 7,8 10,3 13,5"/><line x1="13" y1="1" x2="13" y2="5"/><line x1="13" y1="5" x2="9" y2="5"/></svg>
    </div>
    <div>
      <div class="logo-name">TrendBreak Pro</div>
      <div class="logo-sub">20 Trendline Types &middot; NSE + NYSE</div>
    </div>
  </div>
  <div class="vsep"></div>
  <div class="topbadges">
    <div class="tbadge"><span class="pulse"></span>%%SCAN_TIME%%</div>
    <div class="tbadge">&#128208; 20 Detectors</div>
    <div class="tbadge">&#127470;&#127475; NSE &middot; &#127482;&#127480; NYSE</div>
  </div>
  <div class="vsep"></div>
  <div class="clock-wrap">
    <div class="clock-item">
      <span id="clk-ist" class="clock-time">--:--:--</span>
      <span class="clock-lbl">IST</span>
    </div>
    <span class="clock-sep">/</span>
    <div class="clock-item">
      <span id="clk-est" class="clock-time">--:--:--</span>
      <span id="clk-est-lbl" class="clock-lbl">EST</span>
    </div>
  </div>
</div>

<div class="stats">
  <div class="sc"><div class="sn" id="stat-total" style="color:var(--acc2)">%%TOTAL%%</div><div class="sl">Signals</div></div>
  <div class="sc"><div class="sn" id="stat-bull"  style="color:var(--bu)">%%BULL%%</div><div class="sl">Bullish</div></div>
  <div class="sc"><div class="sn" id="stat-bear"  style="color:var(--be)">%%BEAR%%</div><div class="sl">Bearish</div></div>
  <div class="sc"><div class="sn" style="color:var(--nse)">%%NSE%%</div><div class="sl">NSE</div></div>
  <div class="sc"><div class="sn" style="color:var(--nyse)">%%NYSE%%</div><div class="sl">NYSE</div></div>
  <div class="sc"><div class="sn" id="stat-vol"   style="color:var(--acc3)">%%VOL%%</div><div class="sl">Vol &#10003;</div></div>
  <div class="sc"><div class="sn" style="color:var(--mu)">%%SCANNED%%</div><div class="sl">Scanned</div></div>
  <div class="sc"><div class="sn" style="color:var(--mu)">20</div><div class="sl">TL Types</div></div>
</div>

<div class="filterbar" id="filterbar">
  <button class="btn on" id="btn-nse" onclick="switchExch('nse')">&#127470;&#127475; NSE India</button>
  <button class="btn" id="btn-nyse" onclick="switchExch('nyse')">&#127482;&#127480; NYSE</button>
  <span class="fb-sep"></span>
  <button class="btn on" id="btn-all"  onclick="setDir('all')">All</button>
  <button class="btn" id="btn-bull" onclick="setDir('bull')">&#9650; Bullish</button>
  <button class="btn" id="btn-bear" onclick="setDir('bear')">&#9660; Bearish</button>
  <span class="fb-sep"></span>
  <select class="tb-sect" id="sect-select" onchange="setSect(this.value)">
    <option value="">All sectors</option>
  </select>
  <span class="result-count" id="result-count"></span>
</div>

<div id="srp-nse"  class="srp"></div>
<div id="srp-nyse" class="srp" style="display:none"></div>

<div id="panel-nse" class="panel active">
  <div class="card-grid" id="grid-nse"></div>
  <div class="lgnd">
    <div class="lgt">&#128218; Trendline coverage &mdash; NSE</div>
    <div class="lgg" id="lgnd-nse"></div>
  </div>
</div>
<div id="panel-nyse" class="panel">
  <div class="card-grid" id="grid-nyse"></div>
  <div class="lgnd">
    <div class="lgt">&#128218; Trendline coverage &mdash; NYSE</div>
    <div class="lgg" id="lgnd-nyse"></div>
  </div>
</div>

<footer>
  &#9888; Educational &amp; research purposes only &middot; Not financial advice &middot; Not SEBI/SEC registered<br>
  Live data via <a href="https://pypi.org/project/yfinance/">yfinance</a> &middot;
  Install: <code>pip install yfinance</code> &middot;
  NSE tickers auto-appended with <code>.NS</code> suffix, BSE fallback <code>.BO</code><br>
  Generated: %%SCAN_TIME%%
</footer>

<script type="application/json" id="data-nse">%%NSE_DATA%%</script>
<script type="application/json" id="data-nyse">%%NYSE_DATA%%</script>

<script>
var S={exch:'nse',dir:'all',sect:''};
var DATA={};

var TL_CAT={
  "1":"Uptrend Line","2":"Downtrend Line","3":"Horizontal",
  "4":"Channel","5":"Triangle","6":"Wedge",
  "7":"Flag & Pennant","8":"Fan Lines","9":"Internal TL",
  "10":"Dynamic EMA","11":"Neckline (H&S)","12":"Fibonacci TL",
  "13":"Pitchfork","14":"Regression Ch.","15":"Acceleration",
  "16":"Base TL","17":"Role Reversal","18":"Speed Resistance",
  "19":"Body TL","20":"Gann Angle"
};

function loadData(eid){
  var el=document.getElementById('data-'+eid);
  if(!el)return[];
  try{return JSON.parse(el.textContent);}catch(e){return[];}
}

function groupByTicker(rows){
  var m={};
  for(var i=0;i<rows.length;i++){
    var r=rows[i];
    if(S.dir!=='all'){
      var want=S.dir==='bull'?'BULLISH':'BEARISH';
      if(r.signal!==want)continue;
    }
    if(S.sect&&r.sector!==S.sect)continue;
    var k=r.ticker;
    if(!m[k])m[k]={ticker:r.ticker,name:r.name,sector:r.sector,exchange:r.exchange,
                    price:r.price,change:r.change,vol_ratio:r.vol_ratio,vol_ok:r.vol_ok,
                    rsi:r.rsi,rsi_zone:r.rsi_zone,srsi:r.srsi,srsi_zone:r.srsi_zone,sigs:[]};
    m[k].sigs.push({num:r.num,type:r.type,signal:r.signal,detail:r.detail,tl:r.tl});
  }
  var arr=Object.values(m);
  arr.sort(function(a,b){return b.sigs.length-a.sigs.length;});
  return arr;
}

function cardDir(sigs){
  var b=0;
  for(var i=0;i<sigs.length;i++){if(sigs[i].signal==='BULLISH')b++;}
  return b===sigs.length?'bull':b===0?'bear':'mix';
}

function fmtPrice(p,exch){
  var sym=exch==='NSE'?'\u20b9':'$';
  return sym+p.toLocaleString('en-IN',{minimumFractionDigits:2,maximumFractionDigits:2});
}

function buildCard(s){
  var d=cardDir(s.sigs);
  var bc=s.sigs.filter(function(x){return x.signal==='BULLISH';}).length;
  var rc=s.sigs.length-bc;
  var badgeLabel=d==='bull'?s.sigs.length+' \u25b2 bull'
                :d==='bear'?s.sigs.length+' \u25bc bear'
                :bc+'\u25b2 '+rc+'\u25bc';
  var rsiHtml=s.rsi!==''?'<span class="c-rsi '+d+'">RSI '+s.rsi+' &middot; '+s.rsi_zone+'</span>':'';
  var volCls=s.vol_ok?'vok':'';
  var volCheck=s.vol_ok?' \u2713':'';
  var chgCls=s.change>=0?'up':'dn';
  var chgSign=s.change>=0?'+':'';

  var sigRows=s.sigs.map(function(sg){
    var up=sg.signal==='BULLISH';
    return '<div class="sig">'
      +'<span class="sig-n">#'+sg.num+'</span>'
      +'<span class="sig-t">'+sg.type+'</span>'
      +'<span class="sig-d '+(up?'up':'dn')+'">'+(up?'\u25b2':'\u25bc')+'</span>'
      +'</div>'
      +'<div class="sig-detail">'+sg.detail+'</div>';
  }).join('');

  var uid='c'+Math.random().toString(36).substr(2,7);
  return '<div class="card '+d+'" id="'+uid+'">'
    +'<div class="c-head">'
      +'<div class="c-left">'
        +'<div class="c-ticker">'+s.ticker+'</div>'
        +'<div class="c-name">'+s.name+'</div>'
      +'</div>'
      +'<div class="c-right">'
        +'<span class="c-sect">'+s.sector+'</span>'
        +'<span class="c-badge '+d+'">'+badgeLabel+'</span>'
      +'</div>'
    +'</div>'
    +'<div class="c-prow">'
      +'<span class="c-price">'+fmtPrice(s.price,s.exchange)+'</span>'
      +'<span class="c-chg '+chgCls+'">'+chgSign+s.change+'%</span>'
      +rsiHtml
      +'<span class="c-vol '+volCls+'">'+s.vol_ratio+'x'+volCheck+'</span>'
    +'</div>'
    +'<div class="sig-block"><div>'+sigRows+'</div></div>'
    +'<div class="c-toggle" onclick="toggleCard(\''+uid+'\')">'
      +'<span class="c-toggle-arrow">&#9660;</span>'
      +'<span class="c-toggle-lbl">details</span>'
    +'</div>'
    +'</div>';
}

function toggleCard(uid){
  var el=document.getElementById(uid);
  if(!el)return;
  var expanded=el.classList.toggle('expanded');
  var lbl=el.querySelector('.c-toggle-lbl');
  if(lbl)lbl.textContent=expanded?'hide details':'details';
}

var SECT_COL={
  'Banking':       '#3b82f6',
  'Fin. Services': '#8b5cf6',
  'IT':            '#22d3ee',
  'Auto':          '#f97316',
  'Cons. Goods':   '#ec4899',
  'FMCG':          '#10b981',
  'Infra/Defence': '#6366f1',
  'Metals':        '#94a3b8',
  'Pharma':        '#14b8a6',
  'Energy':        '#f59e0b',
  'Technology':    '#22d3ee',
  'Financials':    '#3b82f6',
  'Healthcare':    '#14b8a6',
  'Cons. Staples': '#a78bfa',
  'Cons. Discret.':'#ec4899',
  'Industrials':   '#84cc16',
  'Comm. Services':'#f43f5e',
  'Materials':     '#94a3b8',
};
function sectCol(s){return SECT_COL[s]||'#60b8ff';}
function rsiColor(v){
  if(v<30)  return '#34d97b';
  if(v<45)  return '#86efac';
  if(v<=55) return '#e8f2ff';
  if(v<=70) return '#fbbf24';
  return '#f87171';
}

function buildSectorRsi(rows,eid){
  var seen={};
  rows.forEach(function(r){
    if(r.sector&&r.sector!=='\u2014'&&!(r.sector in seen)&&r.srsi!==''){
      seen[r.sector]=r.srsi;
    }
  });
  var entries=Object.entries(seen).sort(function(a,b){return a[1]-b[1];});
  if(!entries.length)return;
  var tiles=entries.map(function(e){
    var s=e[0],v=e[1];
    var sc=sectCol(s);
    var rc=rsiColor(v);
    var act=S.sect===s?' active':'';
    return '<div class="srp-tile'+act+'" onclick="toggleSect(\''+s+'\')" style="border-left-color:'+sc+'">'
      +'<span class="srp-sname" style="color:'+sc+'">'+s+'</span>'
      +'<span class="srp-val" style="color:'+rc+'">'+v+'</span>'
      +'</div>';
  }).join('');
  var el=document.getElementById('srp-'+eid);
  if(el)el.innerHTML='<div class="srp-title">&#128200; Sector RSI &mdash; click a tile to filter</div>'
    +'<div class="srp-tiles">'+tiles+'</div>';
}

function populateSectors(){
  var rows=DATA[S.exch]||[];
  var seen={};var sects=[];
  rows.forEach(function(r){
    if(r.sector&&r.sector!=='\u2014'&&!seen[r.sector]){seen[r.sector]=1;sects.push(r.sector);}
  });
  sects.sort();
  var sel=document.getElementById('sect-select');
  if(!sel)return;
  sel.innerHTML='<option value="">All sectors</option>';
  sects.forEach(function(s){
    var o=document.createElement('option');
    o.value=s;o.textContent=s;
    if(S.sect===s)o.selected=true;
    sel.appendChild(o);
  });
}

function renderCards(eid){
  var rows=DATA[eid]||[];
  var stocks=groupByTicker(rows);
  var grid=document.getElementById('grid-'+eid);
  if(!grid)return;
  if(!stocks.length){
    grid.innerHTML='<div class="empty">No signals match current filters.</div>';
  } else {
    grid.innerHTML=stocks.map(buildCard).join('');
  }
  var sigTotal=stocks.reduce(function(n,s){return n+s.sigs.length;},0);
  var rc=document.getElementById('result-count');
  if(eid===S.exch&&rc)rc.textContent=stocks.length+' tickers \u00b7 '+sigTotal+' signals';
}

function buildLegend(eid){
  var rows=DATA[eid]||[];
  var cnt={};
  rows.forEach(function(r){cnt[r.num]=(cnt[r.num]||0)+1;});
  var parts=[];
  for(var i=1;i<=20;i++){
    var n=String(i);
    var hit=cnt[n]?'<span class="lhit">'+cnt[n]+'</span>':'';
    parts.push('<div class="lgi"><span class="ln">'+n+'</span>'
      +'<span style="color:var(--txt)">'+TL_CAT[n]+'</span>'+hit+'</div>');
  }
  var el=document.getElementById('lgnd-'+eid);
  if(el)el.innerHTML=parts.join('');
}

function updateStats(){
  var rows=DATA[S.exch]||[];
  if(S.sect)rows=rows.filter(function(r){return r.sector===S.sect;});
  var shown=S.dir==='all'?rows:rows.filter(function(r){
    return r.signal===(S.dir==='bull'?'BULLISH':'BEARISH');
  });
  var b=shown.filter(function(r){return r.signal==='BULLISH';}).length;
  var r=shown.filter(function(r){return r.signal==='BEARISH';}).length;
  var v=shown.filter(function(r){return r.vol_ok;}).length;
  var el;
  if(el=document.getElementById('stat-total'))el.textContent=shown.length;
  if(el=document.getElementById('stat-bull')) el.textContent=b;
  if(el=document.getElementById('stat-bear')) el.textContent=r;
  if(el=document.getElementById('stat-vol'))  el.textContent=v;
}

function switchExch(ex){
  S.exch=ex;S.sect='';
  document.getElementById('panel-nse').classList.toggle('active',ex==='nse');
  document.getElementById('panel-nyse').classList.toggle('active',ex==='nyse');
  document.getElementById('srp-nse').style.display=ex==='nse'?'':'none';
  document.getElementById('srp-nyse').style.display=ex==='nyse'?'':'none';
  var bns=document.getElementById('btn-nse');
  var bny=document.getElementById('btn-nyse');
  if(bns)bns.className='btn'+(ex==='nse'?' on':'');
  if(bny)bny.className='btn'+(ex==='nyse'?' on':'');
  var ss=document.getElementById('sect-select');
  if(ss)ss.value='';
  populateSectors();
  renderCards(ex);
  updateStats();
}

function setDir(d){
  S.dir=d;
  ['all','bull','bear'].forEach(function(x){
    var b=document.getElementById('btn-'+x);
    if(!b)return;
    if(x===d){
      b.className='btn'+(x==='bull'?' bull-on':x==='bear'?' bear-on':' on');
    } else {
      b.className='btn';
    }
  });
  renderCards(S.exch);
  updateStats();
}

function setSect(s){
  S.sect=s;
  document.querySelectorAll('.srp-tile').forEach(function(t){
    var nm=t.querySelector('.srp-sname');
    if(nm)t.classList.toggle('active',nm.textContent===s);
  });
  renderCards(S.exch);
  updateStats();
}

function toggleSect(s){
  S.sect=(S.sect===s?'':s);
  var ss=document.getElementById('sect-select');
  if(ss)ss.value=S.sect;
  setSect(S.sect);
}

document.addEventListener('DOMContentLoaded',function(){
  DATA.nse=loadData('nse');
  DATA.nyse=loadData('nyse');
  buildSectorRsi(DATA.nse,'nse');
  buildSectorRsi(DATA.nyse,'nyse');
  populateSectors();
  renderCards('nse');
  renderCards('nyse');
  buildLegend('nse');
  buildLegend('nyse');
  updateStats();
});

function isDST(d){
  var j=new Date(d.getFullYear(),0,1).getTimezoneOffset();
  var u=new Date(d.getFullYear(),6,1).getTimezoneOffset();
  return d.getTimezoneOffset()<Math.max(j,u);
}
function updateClock(){
  var n=new Date();
  var istMs=n.getTime()+330*60000;
  var estMs=n.getTime()+(isDST(n)?-240:-300)*60000;
  function t(ms){return new Date(ms).toISOString().substr(11,8);}
  var ei=document.getElementById('clk-ist');
  var ee=document.getElementById('clk-est');
  var el=document.getElementById('clk-est-lbl');
  if(ei)ei.textContent=t(istMs);
  if(ee)ee.textContent=t(estMs);
  if(el)el.textContent=isDST(n)?'EDT':'EST';
}
setInterval(updateClock,1000);
updateClock();
</script>
</body></html>"""


def generate_html(results, scan_time):
    import json as _json

    bull  = [r for r in results if r["signal"] == "BULLISH"]
    bear  = [r for r in results if r["signal"] == "BEARISH"]
    nse   = [r for r in results if r["exchange"] == "NSE"]
    nyse  = [r for r in results if r["exchange"] == "NYSE"]
    vol_c = [r for r in results if r.get("vol_confirmed")]

    def row_to_dict(r):
        rsi_raw  = r.get("rsi")
        zone_lbl, _ = rsi_zone(rsi_raw)
        srsi_raw = r.get("sector_rsi")
        srsi_lbl, _ = rsi_zone(srsi_raw)
        return {
            "ticker":    r["ticker"],
            "name":      r["name"],
            "sector":    r.get("sector", "—"),
            "exchange":  r["exchange"],
            "num":       r.get("num", "?"),
            "type":      r["type"],
            "signal":    r["signal"],
            "price":     r["price"],
            "change":    r["change"],
            "vol_ratio": r.get("vol_ratio", 0),
            "vol_ok":    bool(r.get("vol_confirmed")),
            "rsi":       rsi_raw if rsi_raw is not None else "",
            "rsi_zone":  zone_lbl,
            "srsi":      srsi_raw if srsi_raw is not None else "",
            "srsi_zone": srsi_lbl,
            "tl":        r["tl"],
            "detail":    r["detail"],
        }

    nse_json  = _json.dumps([row_to_dict(r) for r in nse],  ensure_ascii=False)
    nyse_json = _json.dumps([row_to_dict(r) for r in nyse], ensure_ascii=False)

    html = _HTML_TEMPLATE
    html = html.replace("%%SCAN_TIME%%",  scan_time)
    html = html.replace("%%NSE_DATA%%",   nse_json)
    html = html.replace("%%NYSE_DATA%%",  nyse_json)
    html = html.replace("%%TOTAL%%",      str(len(results)))
    html = html.replace("%%BULL%%",       str(len(bull)))
    html = html.replace("%%BEAR%%",       str(len(bear)))
    html = html.replace("%%NSE%%",        str(len(nse)))
    html = html.replace("%%NYSE%%",       str(len(nyse)))
    html = html.replace("%%VOL%%",        str(len(vol_c)))
    html = html.replace("%%SCANNED%%",    str(len(NSE_STOCKS) + len(NYSE_STOCKS)))
    return html


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    scan_time = datetime.now().strftime("%d %b %Y  %H:%M:%S")
    total_stocks = len(NSE_STOCKS) + len(NYSE_STOCKS)
    print(f"\nTrendBreak Pro v2  ·  {total_stocks} stocks  ·  20 trendline types  ·  {scan_time}")
    print(f"  13 fixes applied — see file header for changelog\n")

    all_results = []
    done = 0

    for idx, (ticker, name, price) in enumerate(NSE_STOCKS):
        res = scan_stock(ticker, name, price, idx, "NSE")
        all_results.extend(res)
        done += 1
        pct = int(done / total_stocks * 40)
        print(f"\r  Scanning [{'█'*pct}{'.'*(40-pct)}] {done}/{total_stocks}", end="", flush=True)

    for idx, (ticker, name, price) in enumerate(NYSE_STOCKS):
        res = scan_stock(ticker, name, price, idx, "NYSE")
        all_results.extend(res)
        done += 1
        pct = int(done / total_stocks * 40)
        print(f"\r  Scanning [{'█'*pct}{'.'*(40-pct)}] {done}/{total_stocks}", end="", flush=True)

    bull = [r for r in all_results if r["signal"] == "BULLISH"]
    bear = [r for r in all_results if r["signal"] == "BEARISH"]

    print(f"\r  Scanning [{'█'*40}] {total_stocks}/{total_stocks}  ✅ Done")
    print(f"  Signals: {len(all_results)} total  |  🟢 {len(bull)} Bullish  |  🔴 {len(bear)} Bearish")

    html = generate_html(all_results, scan_time)
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trendline_breakout_report.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  Report  → {out}\n")

if __name__ == "__main__":
    main()
