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

FIXES APPLIED (v3):
  FIX-14  Market-hours gate: skips live fetch when both NSE & NYSE are closed
           NSE  → Mon–Fri 09:15–15:30 IST  (Asia/Kolkata)
           NYSE → Mon–Fri 09:00–19:00 ET   (America/New_York, DST-aware)
  FIX-15  Per-exchange skip: only fetches NSE stocks when NSE is open,
           only fetches NYSE stocks when NYSE is open; uses synthetic
           fallback for the closed exchange instead of live network calls
  FIX-17  Timeframe data fix: each --timeframe now fetches the correct
           yfinance interval+period (15m/60d, 1h/60d, 4h resampled from
           1h/60d, 1d/6mo). Old config used '5d' for 15m (only ~100 bars)
           and '3mo' for 4h resample (broken condition). Now explicit.
  FIX-16  Output freshness check: skips full re-scan if existing report
           is younger than one candle period (15m/1h/4h/1d) — use
           --force flag to override
═══════════════════════════════════════════════════════════════
"""

import os
import sys
import time
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo          # Python 3.9+ — no extra install needed
import random
import math

import logging
import warnings
import json as _json_cfg
import urllib.request
import urllib.parse

# Suppress all yfinance / urllib3 / requests noise
logging.getLogger("yfinance").setLevel(logging.CRITICAL)
logging.getLogger("urllib3").setLevel(logging.CRITICAL)
logging.getLogger("requests").setLevel(logging.CRITICAL)
warnings.filterwarnings("ignore")

# ── Config loader ────────────────────────────────────────────────────────────
def load_config():
    """
    Load Telegram config with the following priority order:
      1. Environment variables  TELEGRAM_BOT_TOKEN  and  TELEGRAM_CHAT_ID
         (set via GitHub Actions Secrets — preferred for CI)
      2. config.json in the same directory as this script
         (used for local runs)
    """
    import os as _os2

    # ── Priority 1: GitHub Secrets / environment variables ────────────────────
    env_token = _os2.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    env_chat  = _os2.environ.get("TELEGRAM_CHAT_ID",  "").strip()

    if env_token and env_chat:
        print("  ✅  Telegram credentials loaded from environment variables.")
        return {
            "telegram": {
                "enabled":   True,
                "bot_token": env_token,
                "chat_id":   env_chat,
            }
        }

    # ── Priority 2: config.json (local development) ───────────────────────────
    cfg_path = _os2.path.join(_os2.path.dirname(_os2.path.abspath(__file__)), "config.json")
    if not _os2.path.exists(cfg_path):
        print(f"  ⚠️  config.json not found and no env vars set — Telegram alerts disabled.")
        return {}
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = _json_cfg.load(f)
        print("  ✅  Telegram credentials loaded from config.json.")
        return cfg
    except Exception as e:
        print(f"  ⚠️  Could not read config.json: {e} — Telegram alerts disabled.")
        return {}

CONFIG = load_config()

# ── Telegram Alert Module ────────────────────────────────────────────────────
def _tg_cfg():
    """Return telegram config dict or None if disabled/missing."""
    tg = CONFIG.get("telegram", {})
    if not tg.get("enabled", False):
        return None
    token = tg.get("bot_token", "")
    chat  = tg.get("chat_id", "")
    if not token or token == "YOUR_BOT_TOKEN_HERE":
        return None
    if not chat or str(chat) == "YOUR_CHAT_ID_HERE":
        return None
    return tg

def tg_send(text):
    """Send a plain-text message to Telegram. Silently returns False on failure."""
    tg = _tg_cfg()
    if not tg:
        return False
    try:
        url  = f"https://api.telegram.org/bot{tg['bot_token']}/sendMessage"
        data = urllib.parse.urlencode({
            "chat_id":    str(tg["chat_id"]),
            "text":       text,
            "parse_mode": "HTML",
        }).encode()
        req = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"  ⚠️  Telegram send failed: {e}")
        return False

def _tg_send_block(lines, split_size=4000):
    """Join lines into message and send, splitting if over Telegram limit."""
    msg = "\n".join(lines)
    if not msg.strip():
        return
    if len(msg) <= 4096:
        tg_send(msg)
    else:
        for i in range(0, len(msg), split_size):
            tg_send(msg[i:i+split_size])

# ── Currency symbol helper ────────────────────────────────────────────────────
def _ccy(exchange):
    return "\u20b9" if exchange == "NSE" else "$"   # ₹ or $

# ── Divider line used between header and stock rows ───────────────────────────
_DIVIDER = "\u2500" * 28   # ────────────────────────────────

def _fmt_breakout_row(r, arrow):
    """
    Format one trendline signal for Telegram using full visual legend:

    Legend:
      Bullish signal      \u25b2 (▲) per row  /  \U0001f7e2 (🟢) in header
      Bearish signal      \u25bc (▼) per row  /  \U0001f534 (🔴) in header
      Price % up          📈 bold +X.XX%
      Price % down        📉 bold -X.XX%
      RSI >= 70           🌡 bold RSI  (overbought)
      RSI <= 30           🧊 bold RSI  (oversold)
      Vol confirmed >=3x  🔥🔥 Vol ✅
      Vol confirmed <3x   🔥 Vol ✅
      Vol elevated >=1.5x ⚡ Vol X.Xx
    """
    exchange  = r.get("exchange", "")
    price     = r.get("price", 0)
    chg       = float(r.get("change", 0))
    rsi       = r.get("rsi", "")
    vol       = float(r.get("vol_ratio", 0))
    vol_ok    = r.get("vol_ok", False)
    ccy       = _ccy(exchange)
    exch_flag = "\U0001f1ee\U0001f1f3" if exchange == "NSE" else "\U0001f1fa\U0001f1f8"

    # ── Price change with directional emoji ───────────────────────────────────
    if chg >= 0:
        chg_s = "\U0001f4c8 <b>+{:.2f}%</b>".format(chg)   # 📈
    else:
        chg_s = "\U0001f4c9 <b>{:.2f}%</b>".format(chg)    # 📉

    # ── RSI badge ─────────────────────────────────────────────────────────────
    if rsi != "":
        rsi_val = float(rsi)
        if rsi_val >= 70:
            rsi_s = "  \U0001f321 <b>RSI:{}</b>".format(int(rsi_val))   # 🌡 overbought
        elif rsi_val <= 30:
            rsi_s = "  \U0001f9ca <b>RSI:{}</b>".format(int(rsi_val))   # 🧊 oversold
        else:
            rsi_s = "  RSI:{}".format(int(rsi_val))                       # plain
    else:
        rsi_s = ""

    # ── Volume badge ──────────────────────────────────────────────────────────
    if vol_ok and vol >= 3.0:
        vol_s = "  \U0001f525\U0001f525 Vol \u2705"       # 🔥🔥 Vol ✅  (>=3x confirmed)
    elif vol_ok:
        vol_s = "  \U0001f525 Vol \u2705"                  # 🔥 Vol ✅   (confirmed <3x)
    elif vol >= 1.5:
        vol_s = "  \u26a1 Vol {:.1f}x".format(vol)         # ⚡ Vol X.Xx (elevated)
    else:
        vol_s = "  Vol {:.1f}x".format(vol)                  # plain

    # ── Trendline type line ───────────────────────────────────────────────────
    tl_num  = r.get("num", "")
    tl_type = r.get("type", r.get("tl_type", ""))
    tl_line = "\U0001f4d0 #{} {}".format(tl_num, tl_type) if tl_num else "\U0001f4d0 {}".format(tl_type)

    return (
        "{arrow} <b>{ticker}</b>  {flag}".format(
            arrow=arrow, ticker=r["ticker"], flag=exch_flag) + "\n"
        "   <i>{name}</i>".format(name=r["name"]) + "\n"
        "   {ccy}{price}  {chg}{rsi}{vol}".format(
            ccy=ccy, price=price, chg=chg_s, rsi=rsi_s, vol=vol_s) + "\n"
        "   {tl}".format(tl=tl_line)
    )

def _fmt_spike_row(s):
    """
    Format one volume spike for Telegram using full visual legend:

    Legend:
      Vol spike >= 5x    🔥🔥 bold X.XXx
      Vol spike >= 2x    🔥 bold X.XXx
      Vol spike < 2x     ⚡ X.XXx
      Price % up         📈 bold +X.XX%
      Price % down       📉 bold -X.XX%
      Breakout tag       ⚡ Breakout (inline on first line)
    """
    ticker    = s.get("ticker", "")
    name      = s.get("name", "")
    exchange  = s.get("exchange", "")
    price     = s.get("price", 0)
    vol_ratio = s.get("vol_ratio", 0)
    chg       = s.get("candle_chg", 0)
    direction = "\u25b2" if s.get("direction") == "UP" else "\u25bc"
    ccy       = _ccy(exchange)

    # ── Price change with directional emoji ───────────────────────────────────
    if chg >= 0:
        chg_s = "\U0001f4c8 <b>+{:.2f}%</b>".format(chg)   # 📈
    else:
        chg_s = "\U0001f4c9 <b>{:.2f}%</b>".format(chg)    # 📉

    # ── Vol spike badge on first line ─────────────────────────────────────────
    if vol_ratio >= 5.0:
        vol_badge = "\U0001f525\U0001f525 <b>{:.2f}x</b>".format(vol_ratio)   # 🔥🔥 bold
    elif vol_ratio >= 2.0:
        vol_badge = "\U0001f525 <b>{:.2f}x</b>".format(vol_ratio)              # 🔥 bold
    else:
        vol_badge = "\u26a1 {:.2f}x".format(vol_ratio)                         # ⚡ plain

    # ── Breakout tag — inline on first line if present ────────────────────────
    breakout_tag = "  \u26a1 <b>Breakout</b>" if s.get("has_breakout") else ""

    # ── Shorten candle time to date only ──────────────────────────────────────
    raw_candle  = s.get("candle_time", "")
    candle_date = raw_candle.split("  ")[0].strip() if "  " in raw_candle else raw_candle

    return (
        "{dir} <b>{ticker}</b>   {vbadge}{bk}".format(
            dir=direction, ticker=ticker,
            vbadge=vol_badge, bk=breakout_tag) + "\n"
        "   <i>{name}</i>".format(name=name) + "\n"
        "   {ccy}{price}  {chg}  \U0001f4c5 {date}".format(
            ccy=ccy, price=price, chg=chg_s, date=candle_date)
    )

def tg_send_breakout_alerts(results, tf_label, scan_time):
    """
    Send 4 separate Telegram messages (one per exchange × direction bucket):
      1. NSE  Bullish breakouts
      2. NSE  Bearish breakouts
      3. NYSE Bullish breakouts
      4. NYSE Bearish breakouts

    Each message layout:
      ┌─────────────────────────────────┐
      │  🇮🇳 NSE 📈 BULLISH Breakouts   │  ← bold title
      │  🕐 28 May 2026  20:40:12        │  ← scan time
      │  ⏱ 1 Day  |  📊 6 signals       │  ← timeframe + count
      │  ────────────────────────────   │  ← divider
      │  ▲ TICKER  🇮🇳                   │
      │     Company Name                │
      │     ₹Price  +X.XX%  RSI  Vol    │
      │     📐 #N  TL Type              │
      │  ▲ ...                          │
      └─────────────────────────────────┘
    """
    tg = _tg_cfg()
    if not tg:
        return
    alerts_cfg = tg.get("alerts", {})
    if not alerts_cfg.get("trendline_breakouts", True):
        return

    vol_ok_only = alerts_cfg.get("only_confirmed_volume", False)
    filtered = [r for r in results if not (vol_ok_only and not r.get("vol_ok", False))]

    buckets = {
        ("NSE",  "BULLISH"): [],
        ("NSE",  "BEARISH"): [],
        ("NYSE", "BULLISH"): [],
        ("NYSE", "BEARISH"): [],
    }
    for r in filtered:
        key = (r.get("exchange", ""), r.get("signal", ""))
        if key in buckets:
            buckets[key].append(r)

    labels = {
        # 🟢 header for bullish, 🔴 header for bearish
        ("NSE",  "BULLISH"): ("\U0001f7e2 \U0001f1ee\U0001f1f3 NSE \U0001f4c8 BULLISH Breakouts",  "\u25b2"),
        ("NSE",  "BEARISH"): ("\U0001f534 \U0001f1ee\U0001f1f3 NSE \U0001f4c9 BEARISH Breakouts",  "\u25bc"),
        ("NYSE", "BULLISH"): ("\U0001f7e2 \U0001f1fa\U0001f1f8 NYSE \U0001f4c8 BULLISH Breakouts", "\u25b2"),
        ("NYSE", "BEARISH"): ("\U0001f534 \U0001f1fa\U0001f1f8 NYSE \U0001f4c9 BEARISH Breakouts", "\u25bc"),
    }

    for key, rows in buckets.items():
        if not rows:
            continue
        title, arrow = labels[key]
        n = len(rows)
        lines = [
            "<b>" + title + "</b>",
            "\U0001f550 " + scan_time,
            "\u23f1 " + tf_label + "  |  \U0001f4ca " + str(n) + " signal" + ("s" if n != 1 else ""),
            _DIVIDER,
        ]
        for r in rows[:20]:
            lines.append(_fmt_breakout_row(r, arrow))
            lines.append("")          # blank line between stocks for breathing room
        if n > 20:
            lines.append("\u2026 and {} more".format(n - 20))
        _tg_send_block(lines)

def tg_send_volume_spike_alerts(vol_spikes, tf_label, scan_time):
    """
    Send 2 separate Telegram messages (one per exchange):
      1. NSE  Volume Spikes
      2. NYSE Volume Spikes

    Each message layout:
      ┌─────────────────────────────────┐
      │  🇮🇳 NSE ⚡ Volume Spikes        │  ← bold title
      │  🕐 28 May 2026  20:40:12        │  ← scan time
      │  ⏱ 1 Day  |  🔍 15 stocks ≥ 1.5x│  ← timeframe + count
      │  ────────────────────────────   │  ← divider
      │  ▲ TICKER   11.51x  ⚡ Breakout  │
      │     Company Name                │
      │     ₹Price  +X.XX%  📅 27 May   │
      │  ▼ ...                          │
      └─────────────────────────────────┘
    """
    tg = _tg_cfg()
    if not tg:
        return
    alerts_cfg = tg.get("alerts", {})
    if not alerts_cfg.get("volume_spikes", True):
        return

    min_ratio = float(alerts_cfg.get("min_vol_ratio", 1.5))

    for exch, flag in [("NSE", "\U0001f1ee\U0001f1f3"), ("NYSE", "\U0001f1fa\U0001f1f8")]:
        rows = [s for s in vol_spikes
                if s.get("exchange") == exch and s.get("vol_ratio", 0) >= min_ratio]
        if not rows:
            continue
        n = len(rows)
        lines = [
            "<b>" + flag + " " + exch + " \u26a1 Volume Spikes</b>",
            "\U0001f550 " + scan_time,
            "\u23f1 " + tf_label + "  |  \U0001f50d " + str(n) + " stock" + ("s" if n != 1 else "")
                + " \u2265 " + "{:.1f}".format(min_ratio) + "x",
            _DIVIDER,
        ]
        for s in rows[:20]:
            lines.append(_fmt_spike_row(s))
            lines.append("")          # blank line between stocks
        if n > 20:
            lines.append("\u2026 and {} more".format(n - 20))
        _tg_send_block(lines)

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

# ── Timeframe Configuration ───────────────────────────────────────────────────
# Maps CLI timeframe arg → (yfinance interval, yfinance period, min_bars, label)
#
# yfinance intraday history hard limits:
#   15m  → max 60 days  →  use "60d"  (~390 bars on trading days)
#   1h   → max 730 days →  use "60d"  (~390 bars, more than enough)
#   4h   → no native 4h; fetch as 1h then resample → use "60d"
#   1d   → no limit     →  use "6mo"  (~126 daily bars)
#
TIMEFRAME_CONFIG = {
    "15m": ("15m", "60d",  60,  "15 Min"),
    "1h":  ("1h",  "60d",  40,  "1 Hour"),
    "4h":  ("1h",  "60d",  30,  "4 Hour"),   # fetched as 1h, resampled to 4h
    "1d":  ("1d",  "6mo",  30,  "1 Day"),
}
# Active timeframe — overridden by --timeframe CLI arg or env var SCAN_TIMEFRAME
ACTIVE_TIMEFRAME = "1d"

# ── Live Data via yfinance (with synthetic fallback) ─────────────────────────
_yf_cache = {}

def fetch_yf(yf_ticker, period="6mo", interval="1d", resample_4h=False):
    """
    Fetch OHLCV from yfinance with caching. Returns DataFrame or None.
    resample_4h=True: fetch 1h bars then resample to 4h (used for 4h timeframe).
    """
    cache_key = f"{yf_ticker}|{interval}|{period}|4h={resample_4h}"
    if cache_key in _yf_cache:
        return _yf_cache[cache_key]
    try:
        import io, sys
        _stderr = sys.stderr
        sys.stderr = io.StringIO()
        try:
            df = yf.Ticker(yf_ticker).history(period=period, interval=interval, auto_adjust=True)
        finally:
            sys.stderr = _stderr
        if df is None or len(df) < 10:
            _yf_cache[cache_key] = None
            return None
        df = df[["Open","High","Low","Close","Volume"]].copy()
        idx = pd.to_datetime(df.index)
        # Preserve tz-aware timestamps as IST before stripping (used for candle_time display)
        df["_ts"] = idx.tz_convert("Asia/Kolkata") if idx.tz is not None else idx
        df.index = idx.tz_convert(None) if idx.tz is not None else idx
        # Resample 1h → 4h bars when requested (4h timeframe)
        if resample_4h and interval == "1h":
            ts_col = df["_ts"].copy() if "_ts" in df.columns else None
            df = (df.resample("4h")
                    .agg({"Open":"first","High":"max","Low":"min",
                          "Close":"last","Volume":"sum"})
                    .dropna())
            # Re-attach _ts (first IST timestamp of each 4h bar)
            if ts_col is not None:
                df["_ts"] = ts_col.resample("4h").first().reindex(df.index)
        _yf_cache[cache_key] = df
        return df
    except Exception:
        _yf_cache[cache_key] = None
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

def fetch_data(ticker, base_price, idx, exchange="NSE", live=True):
    """
    Fetch real OHLCV via yfinance using ACTIVE_TIMEFRAME.
    - 15m  → fetches 15m bars  for last 60 days
    - 1h   → fetches 1h  bars  for last 60 days
    - 4h   → fetches 1h  bars  for last 60 days, then resamples to 4h
    - 1d   → fetches 1d  bars  for last 6 months
    NSE tickers get .NS suffix (.BO tried as fallback).
    live=False skips all network calls and uses synthetic data.
    """
    tf_interval, tf_period, tf_min_bars, _ = TIMEFRAME_CONFIG.get(ACTIVE_TIMEFRAME, TIMEFRAME_CONFIG["1d"])
    is_4h = (ACTIVE_TIMEFRAME == "4h")

    if YF_AVAILABLE and live:
        yf_ticker = (ticker + ".NS") if exchange == "NSE" else ticker
        df = fetch_yf(yf_ticker, period=tf_period, interval=tf_interval, resample_4h=is_4h)
        if df is not None and len(df) >= tf_min_bars:
            return df
        # If .NS failed, try .BO (BSE) for NSE stocks
        if exchange == "NSE":
            df = fetch_yf(ticker + ".BO", period=tf_period, interval=tf_interval, resample_4h=is_4h)
            if df is not None and len(df) >= tf_min_bars:
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
    """Return zone label and CSS class for RSI value.
    >70 = red (HOT/overbought), 55-70 = green (Bull), 45-55 = grey (Mid),
    30-45 = orange (Fade), <30 = blue (OS/oversold)
    """
    if rsi is None:    return "—",     "rz-na"
    if rsi > 70:       return "HOT",   "rz-hot"
    if rsi >= 55:      return "Bull",  "rz-bull"
    if rsi >= 45:      return "Mid",   "rz-mid"
    if rsi >= 30:      return "Fade",  "rz-fade"
    return "OS",   "rz-os"

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
        # Use matching period/interval for sector RSI
        tf_interval, tf_period, _, _ = TIMEFRAME_CONFIG.get(ACTIVE_TIMEFRAME, TIMEFRAME_CONFIG["1d"])
        df_s = fetch_yf(sector_code, period=tf_period, interval=tf_interval)
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


def scan_stock(ticker, name, base_price, idx, exchange, live=True):
    df = fetch_data(ticker, base_price, idx, exchange=exchange, live=live)
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
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#0d0f14;--surf:#13161d;--surf2:#1a1e27;
  --bdr:rgba(255,255,255,0.07);--bdr2:rgba(255,255,255,0.13);
  --txt:#e8eaf0;--mu:#8b909e;--dim:#555b6a;
  --bull:#00d17a;--bull-bg:rgba(0,209,122,0.09);--bull-br:rgba(0,209,122,0.28);
  --bear:#ff4c5b;--bear-bg:rgba(255,76,91,0.09);--bear-br:rgba(255,76,91,0.28);
  --acc:#4c9fff;--acc-bg:rgba(76,159,255,0.09);
  --gold:#f5c842;
  --mono:'IBM Plex Mono',monospace;
  --sans:'IBM Plex Sans',sans-serif
}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--txt);font-family:var(--sans);font-size:13px;min-height:100vh}

/* ── TOP BAR ── */
.topbar{background:var(--surf);border-bottom:1px solid var(--bdr2);padding:9px 20px;
  display:flex;align-items:center;gap:12px;flex-wrap:wrap;position:sticky;top:0;z-index:100}
.brand{display:flex;align-items:center;gap:9px}
.brand-icon{width:28px;height:28px;background:var(--acc);border-radius:6px;
  display:flex;align-items:center;justify-content:center;flex-shrink:0}
.brand-icon svg{width:14px;height:14px;fill:none;stroke:#fff;stroke-width:2.2;
  stroke-linecap:round;stroke-linejoin:round}
.brand-name{font-family:var(--mono);font-size:15px;font-weight:600;color:#fff}
.brand-sub{font-size:10px;color:var(--dim);font-family:var(--mono)}
.vsep{width:1px;height:22px;background:var(--bdr2);flex-shrink:0}
.tbadge{font-size:10px;font-family:var(--mono);background:var(--acc-bg);
  border:1px solid var(--bdr2);color:var(--acc);border-radius:4px;padding:2px 8px;white-space:nowrap}
.pulse{display:inline-block;width:5px;height:5px;background:var(--bull);border-radius:50%;
  margin-right:4px;vertical-align:middle;animation:pulse 1.8s ease-in-out infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.25}}
.clock-wrap{display:flex;gap:10px;align-items:center;font-family:var(--mono);margin-left:auto}
.clock-item{display:flex;flex-direction:column;align-items:center}
.clock-time{font-size:11px;font-weight:600;color:var(--acc);letter-spacing:.5px}
.clock-lbl{font-size:9px;color:var(--dim);text-transform:uppercase;letter-spacing:.6px}
.clock-sep{color:var(--bdr2)}

/* ── STATS STRIP ── */
.stats{display:flex;background:rgba(0,0,0,0.25);border-bottom:1px solid var(--bdr);overflow-x:auto}
.sc{flex:1;min-width:72px;padding:8px 10px;text-align:center;border-right:1px solid var(--bdr)}
.sc:last-child{border-right:none}
.sn{font-size:19px;font-weight:700;font-family:var(--mono);line-height:1.1}
.sl{font-size:9px;color:var(--dim);text-transform:uppercase;letter-spacing:.5px;margin-top:1px}

/* ── TOOLBAR ── */
.toolbar{display:flex;align-items:center;gap:8px;padding:10px 20px;
  border-bottom:1px solid var(--bdr);flex-wrap:wrap;background:var(--surf)}
.search-wrap{position:relative;flex:1;min-width:160px;max-width:260px}
.search-wrap svg{position:absolute;left:9px;top:50%;transform:translateY(-50%);
  width:13px;height:13px;stroke:var(--dim);fill:none;stroke-width:2;stroke-linecap:round}
.search{width:100%;background:var(--bg);border:1px solid var(--bdr2);border-radius:6px;
  padding:6px 10px 6px 30px;color:var(--txt);font-size:11px;font-family:var(--mono);outline:none}
.search:focus{border-color:var(--acc)}
.search::placeholder{color:var(--dim)}
.btn-grp{display:flex;gap:0;background:var(--bg);border:1px solid var(--bdr2);
  border-radius:6px;overflow:hidden}
.bg-btn{padding:5px 13px;font-size:11px;font-weight:600;font-family:var(--mono);
  cursor:pointer;border:none;background:transparent;color:var(--dim);transition:.12s}
.bg-btn:hover{color:var(--txt);background:var(--surf2)}
.bg-btn.active{color:var(--txt);background:var(--surf2)}
.bg-btn.bull-on{color:var(--bull);background:var(--bull-bg)}
.bg-btn.bear-on{color:var(--bear);background:var(--bear-bg)}
.bg-btn+.bg-btn{border-left:1px solid var(--bdr)}
/* NSE button active — Indian saffron */
.bg-btn.nse-btn.active{color:#ff9933;background:rgba(255,153,51,0.12);border-color:rgba(255,153,51,0.3)}
/* NYSE button active — American blue */
.bg-btn.nyse-btn.active{color:#5b8fff;background:rgba(60,100,200,0.12);border-color:rgba(60,100,200,0.3)}
select.flt{background:var(--bg);border:1px solid var(--bdr2);border-radius:6px;
  padding:5px 10px;color:var(--mu);font-size:11px;font-family:var(--mono);outline:none;cursor:pointer}
select.flt:focus{border-color:var(--acc)}
.vol-lbl{display:flex;align-items:center;gap:5px;font-size:11px;color:var(--dim);
  font-family:var(--mono);cursor:pointer}
.vol-lbl input{accent-color:var(--acc);cursor:pointer}
.rc{margin-left:auto;font-size:10px;color:var(--dim);font-family:var(--mono)}

/* ── LEGEND TOGGLE ── */
.lgnd-toggle{font-size:10px;color:var(--acc);font-family:var(--mono);cursor:pointer;
  padding:4px 10px;border:1px solid var(--bdr2);border-radius:6px;white-space:nowrap;
  background:transparent;transition:.12s}
.lgnd-toggle:hover{border-color:var(--acc)}

/* ── LEGEND PANEL ── */
.lgnd-panel{display:none;padding:10px 20px;border-bottom:1px solid var(--bdr);
  background:var(--surf);grid-template-columns:repeat(auto-fill,minmax(195px,1fr));gap:4px 14px}
.lgnd-panel.open{display:grid}
.lgnd-item{font-size:10px;font-family:var(--mono);color:var(--dim)}
.lgnd-item b{color:var(--mu);margin-right:4px}

/* ── TABLE ── */
.tbl-wrap{overflow-x:auto;padding:0 20px 32px}
table{width:100%;border-collapse:collapse;font-size:12px;min-width:1000px}
thead th{text-align:left;padding:9px 11px;color:var(--dim);font-family:var(--mono);
  font-size:10px;font-weight:500;letter-spacing:.07em;text-transform:uppercase;
  border-bottom:1px solid var(--bdr2);white-space:nowrap;cursor:pointer;user-select:none;
  transition:color .12s}
thead th:hover{color:var(--mu)}
thead th.sorted{color:var(--acc)}
thead th .sa{margin-left:3px;opacity:.35;font-size:9px}
thead th.sorted .sa{opacity:1}
tbody tr{border-bottom:1px solid var(--bdr);transition:background .1s;cursor:default}
tbody tr:hover{background:var(--surf)}
tbody td{padding:8px 11px;vertical-align:middle}

/* cell styles */
.ct{font-family:var(--mono);font-weight:600;font-size:12px;color:#fff;white-space:nowrap}
.cn{color:var(--mu);max-width:155px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
/* Sector badge — default grey */
.cs span{font-size:10px;padding:2px 7px;border-radius:3px;background:var(--surf2);
  border:1px solid var(--bdr2);color:var(--dim);font-family:var(--mono);white-space:nowrap;font-weight:600}
/* Sector badge — RSI zone colours matching the panel cards */
.cs span.sz-hot {background:rgba(255,76,91,0.12);  border-color:rgba(255,76,91,0.40);  color:#ff4c5b}
.cs span.sz-bull{background:rgba(0,209,122,0.10);  border-color:rgba(0,209,122,0.35);  color:#00d17a}
.cs span.sz-mid {background:var(--surf2);           border-color:var(--bdr2);           color:var(--mu)}
.cs span.sz-fade{background:rgba(255,140,66,0.10);  border-color:rgba(255,140,66,0.38); color:#ff8c42}
.cs span.sz-os  {background:rgba(76,159,255,0.10);  border-color:rgba(76,159,255,0.38); color:#4c9fff}
.cp{font-family:var(--mono);font-weight:500;text-align:right;white-space:nowrap}
.cc{font-family:var(--mono);font-weight:600;text-align:right;white-space:nowrap}
.cc.up{color:var(--bull)}.cc.dn{color:var(--bear)}
.sig-badge{display:inline-flex;align-items:center;gap:3px;font-size:10px;font-weight:700;
  font-family:var(--mono);padding:3px 8px;border-radius:4px;white-space:nowrap}
.sig-badge.bull{background:var(--bull-bg);color:var(--bull);border:1px solid var(--bull-br)}
.sig-badge.bear{background:var(--bear-bg);color:var(--bear);border:1px solid var(--bear-br)}
.crsi{font-family:var(--mono);text-align:right;white-space:nowrap}
.rv{font-size:12px;font-weight:600}
.rz{font-size:9px;margin-left:3px}
/* RSI zone colours: >70 red | 55-70 green | 45-55 grey | 30-45 orange | <30 blue */
.rz-hot {color:#ff4c5b}
.rz-bull{color:#00d17a}
.rz-mid {color:#8b909e}
.rz-fade{color:#ff8c42}
.rz-os  {color:#4c9fff}
.rz-na  {color:var(--dim)}
.cvol{font-family:var(--mono);text-align:right;white-space:nowrap}
.vok{color:var(--bull)}
.ctln{white-space:nowrap}
.tnum{display:inline-block;font-family:var(--mono);font-size:9px;font-weight:700;
  background:var(--surf2);border:1px solid var(--bdr2);color:var(--dim);
  border-radius:3px;padding:1px 5px;margin-right:5px}
.tname{color:var(--mu);font-size:11px}
.cdet{max-width:270px}
.dtxt{color:var(--dim);font-size:10px;white-space:nowrap;overflow:hidden;
  text-overflow:ellipsis;max-width:270px;display:block}
.dtxt:hover{white-space:normal;overflow:visible;color:var(--mu)}
.clvl{font-family:var(--mono);font-size:11px;color:var(--dim);text-align:right}

/* ── EXCHANGE BADGES — flag colours ── */
.exch-badge{display:inline-flex;align-items:center;gap:4px;font-size:10px;font-weight:700;
  font-family:var(--mono);padding:2px 8px;border-radius:4px;white-space:nowrap;letter-spacing:.04em}
/* NSE — Indian tricolour: saffron border/text, green underline accent */
.exch-nse{
  background:linear-gradient(135deg,rgba(255,153,51,0.13) 0%,rgba(19,100,52,0.10) 100%);
  border:1px solid rgba(255,153,51,0.55);
  color:#ff9933;
  box-shadow:0 1px 0 0 rgba(19,100,52,0.55)}
/* NYSE — American flag: red/blue */
.exch-nyse{
  background:linear-gradient(135deg,rgba(60,100,200,0.13) 0%,rgba(187,31,47,0.10) 100%);
  border:1px solid rgba(60,100,200,0.55);
  color:#5b8fff;
  box-shadow:0 1px 0 0 rgba(187,31,47,0.55)}

/* ── SECTOR RSI PANEL ── */
.srsi-panel{background:var(--surf);border-bottom:2px solid var(--bdr2);padding:10px 20px 12px;display:block}
.srsi-hdr{display:flex;align-items:center;gap:10px;margin-bottom:9px}
.srsi-title{font-family:var(--mono);font-size:11px;font-weight:600;color:var(--mu);
  text-transform:uppercase;letter-spacing:.08em}
.srsi-sub{font-size:9px;color:var(--dim);font-family:var(--mono)}
.srsi-exch-tabs{display:flex;gap:0;background:var(--bg);border:1px solid var(--bdr2);
  border-radius:5px;overflow:hidden;margin-left:auto}
.srsi-tab{padding:3px 11px;font-size:10px;font-weight:600;font-family:var(--mono);
  cursor:pointer;border:none;background:transparent;color:var(--dim);transition:.12s}
.srsi-tab:hover{color:var(--txt);background:var(--surf2)}
.srsi-tab.active{color:var(--txt);background:var(--surf2)}
.srsi-tab+.srsi-tab{border-left:1px solid var(--bdr)}
.srsi-grid{display:flex;flex-wrap:wrap;gap:7px}
.srsi-card{display:flex;flex-direction:column;align-items:center;justify-content:center;
  min-width:88px;padding:7px 10px 6px;border-radius:7px;border:1px solid var(--bdr2);
  background:var(--bg);gap:2px;cursor:default;transition:border-color .15s}
.srsi-card:hover{border-color:var(--bdr2);filter:brightness(1.12)}
.srsi-card.hot {border-color:rgba(255,76,91,0.40); background:rgba(255,76,91,0.07)}
.srsi-card.bull{border-color:rgba(0,209,122,0.35);  background:rgba(0,209,122,0.06)}
.srsi-card.mid {border-color:var(--bdr2)}
.srsi-card.fade{border-color:rgba(255,140,66,0.38); background:rgba(255,140,66,0.06)}
.srsi-card.os  {border-color:rgba(76,159,255,0.40); background:rgba(76,159,255,0.07)}
.srsi-card.na  {border-color:var(--bdr);opacity:.55}
.srsi-val{font-family:var(--mono);font-size:17px;font-weight:700;line-height:1.1}
.srsi-val.hot {color:#ff4c5b}
.srsi-val.bull{color:#00d17a}
.srsi-val.mid {color:var(--mu)}
.srsi-val.fade{color:#ff8c42}
.srsi-val.os  {color:#4c9fff}
.srsi-val.na  {color:var(--dim)}
.srsi-lbl{font-size:9px;color:var(--dim);font-family:var(--mono);text-align:center;
  white-space:nowrap;max-width:86px;overflow:hidden;text-overflow:ellipsis}
.srsi-zone-tag{font-size:8px;font-family:var(--mono);font-weight:600;
  padding:1px 5px;border-radius:3px;margin-top:1px}
.srsi-zone-tag.hot {background:rgba(255,76,91,0.15); color:#ff4c5b}
.srsi-zone-tag.bull{background:rgba(0,209,122,0.15); color:#00d17a}
.srsi-zone-tag.mid {background:var(--surf2);          color:var(--dim)}
.srsi-zone-tag.fade{background:rgba(255,140,66,0.15); color:#ff8c42}
.srsi-zone-tag.os  {background:rgba(76,159,255,0.15); color:#4c9fff}
.srsi-zone-tag.na  {background:var(--surf2);          color:var(--dim)}
.srsi-bar-wrap{width:100%;height:3px;background:var(--bdr2);border-radius:2px;margin-top:3px;overflow:hidden}
.srsi-bar{height:100%;border-radius:2px;transition:width .4s ease}

/* ── FOOTER ── */
footer{text-align:center;padding:12px 20px;border-top:1px solid var(--bdr);
  color:var(--dim);font-size:10px;font-family:var(--mono);line-height:2}
footer a{color:var(--acc);text-decoration:none}

/* ── VOL SPIKE ALERT PANEL ── */
.vs-alert-panel{background:linear-gradient(135deg,rgba(245,200,66,0.06),rgba(76,159,255,0.04));
  border-bottom:2px solid rgba(245,200,66,0.25);padding:10px 20px 14px;display:none}
.vs-alert-panel.has-data{display:block}
.vs-alert-hdr{display:flex;align-items:center;gap:10px;margin-bottom:10px;flex-wrap:wrap}
.vs-alert-title{font-family:var(--mono);font-size:11px;font-weight:600;
  color:var(--gold);text-transform:uppercase;letter-spacing:.08em}
.vs-alert-sub{font-size:9px;color:var(--dim);font-family:var(--mono)}
.vs-alert-count{font-family:var(--mono);font-size:10px;background:rgba(245,200,66,0.12);
  border:1px solid rgba(245,200,66,0.3);color:var(--gold);border-radius:4px;padding:2px 8px}
.vs-cards{display:flex;flex-wrap:wrap;gap:8px}
.vs-card{background:var(--surf);border:1px solid var(--bdr2);border-radius:8px;
  padding:9px 12px;min-width:148px;max-width:180px;cursor:default;
  transition:border-color .15s,filter .15s;position:relative}
.vs-card:hover{filter:brightness(1.12)}
.vs-card.has-signal{border-color:rgba(76,159,255,0.5);background:rgba(76,159,255,0.06)}
.vs-card.dir-up  {border-left:3px solid var(--bull)}
.vs-card.dir-down{border-left:3px solid var(--bear)}
.vs-card-ticker{font-family:var(--mono);font-size:13px;font-weight:700;color:#fff}
.vs-card-name{font-size:9px;color:var(--dim);white-space:nowrap;overflow:hidden;
  text-overflow:ellipsis;max-width:155px;margin-top:1px}
.vs-card-row{display:flex;align-items:center;justify-content:space-between;margin-top:5px}
.vs-vol-ratio{font-family:var(--mono);font-size:15px;font-weight:700;color:var(--gold)}
.vs-vol-label{font-size:8px;color:var(--dim);font-family:var(--mono)}
.vs-chg{font-family:var(--mono);font-size:11px;font-weight:600}
.vs-chg.up{color:var(--bull)}.vs-chg.down{color:var(--bear)}
.vs-signal-tag{font-size:8px;font-family:var(--mono);font-weight:700;
  background:rgba(76,159,255,0.15);border:1px solid rgba(76,159,255,0.4);
  color:#4c9fff;border-radius:3px;padding:1px 5px;margin-top:4px;display:inline-block}
.vs-exch-dot{width:5px;height:5px;border-radius:50%;display:inline-block;margin-right:3px}
.vs-exch-dot.nse{background:#ff9933}.vs-exch-dot.nyse{background:#5b8fff}

/* ── VOL SPIKE TAB ── */
.main-tabs{display:flex;gap:0;background:var(--surf);border-bottom:2px solid var(--bdr2);
  padding:0 20px}
.main-tab{padding:10px 18px;font-size:11px;font-weight:600;font-family:var(--mono);
  cursor:pointer;border:none;background:transparent;color:var(--dim);
  border-bottom:2px solid transparent;margin-bottom:-2px;transition:.12s;white-space:nowrap}
.main-tab:hover{color:var(--txt)}
.main-tab.active{color:var(--txt);border-bottom-color:var(--acc)}
.main-tab.vs-tab.active{color:var(--gold);border-bottom-color:var(--gold)}
.tab-panel{display:none}.tab-panel.active{display:block}

/* Vol spike table */
.vs-tbl-wrap{overflow-x:auto;padding:0 20px 32px}
.vs-filters{display:flex;gap:8px;padding:10px 20px;border-bottom:1px solid var(--bdr);
  background:var(--surf);flex-wrap:wrap;align-items:center}
.vs-filter-label{font-size:10px;color:var(--dim);font-family:var(--mono)}
#vs-ratio-slider{accent-color:var(--gold);cursor:pointer;width:120px}
#vs-ratio-val{font-family:var(--mono);font-size:11px;color:var(--gold);min-width:32px}
.vs-sort-note{font-size:10px;color:var(--dim);font-family:var(--mono);margin-left:auto}

/* ── SCROLLBAR ── */
::-webkit-scrollbar{height:4px;width:4px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:var(--bdr2);border-radius:2px}

@media(max-width:640px){
  .topbar{padding:7px 12px}.toolbar{padding:8px 12px}.tbl-wrap{padding:0 8px 24px}
  .clock-wrap{display:none}
}
</style></head><body>

<!-- TOP BAR -->
<div class="topbar">
  <div class="brand">
    <div class="brand-icon">
      <svg viewBox="0 0 14 14"><polyline points="1,11 4,6 7,8 10,3 13,5"/>
        <line x1="13" y1="1" x2="13" y2="5"/><line x1="13" y1="5" x2="9" y2="5"/></svg>
    </div>
    <div>
      <div class="brand-name">TrendBreak Pro</div>
      <div class="brand-sub">v2 &middot; 20 TL types &middot; 13 fixes applied</div>
    </div>
  </div>
  <div class="vsep"></div>
  <div class="tbadge"><span class="pulse"></span>%%SCAN_TIME%%</div>
  <div class="tbadge">%%SCANNED%% stocks scanned</div>
  <div class="tbadge" style="background:linear-gradient(135deg,rgba(255,153,51,0.1),rgba(60,100,200,0.1));border-color:rgba(255,153,51,0.35)">&#127470;&#127475; <span style="color:#ff9933">NSE</span> <span style="color:var(--dim)">+</span> &#127482;&#127480; <span style="color:#5b8fff">NYSE</span></div>
  <div class="tbadge" id="tf-badge" style="color:var(--gold);border-color:var(--gold);background:rgba(245,200,66,0.09)">&#9201; %%TF_LABEL%%</div>
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

<!-- STATS STRIP -->
<div class="stats">
  <div class="sc"><div class="sn" style="color:var(--acc)" id="stat-total">%%TOTAL%%</div><div class="sl">Signals</div></div>
  <div class="sc"><div class="sn" style="color:var(--bull)" id="stat-bull">%%BULL%%</div><div class="sl">Bullish</div></div>
  <div class="sc"><div class="sn" style="color:var(--bear)" id="stat-bear">%%BEAR%%</div><div class="sl">Bearish</div></div>
  <div class="sc"><div class="sn" style="color:#ff9933">%%NSE%%</div><div class="sl" style="color:#ff9933;opacity:.7">&#127470;&#127475; NSE</div></div>
  <div class="sc"><div class="sn" style="color:#5b8fff">%%NYSE%%</div><div class="sl" style="color:#5b8fff;opacity:.7">&#127482;&#127480; NYSE</div></div>
  <div class="sc"><div class="sn" style="color:var(--bull)" id="stat-vol">%%VOL%%</div><div class="sl">Vol &#10003;</div></div>
  <div class="sc"><div class="sn" style="color:var(--dim)">%%SCANNED%%</div><div class="sl">Scanned</div></div>
  <div class="sc"><div class="sn" style="color:var(--dim)">20</div><div class="sl">TL Types</div></div>
  <div class="sc"><div class="sn" style="color:var(--gold);font-size:13px">%%TF_LABEL%%</div><div class="sl">Timeframe</div></div>
</div>

<!-- SECTOR RSI PANEL -->
<div class="srsi-panel" id="srsi-panel">
  <div class="srsi-hdr">
    <div>
      <div class="srsi-title">&#128200; Sector RSI &mdash; Daily</div>
      <div class="srsi-sub">14-period RSI on daily candles &middot; updates on exchange filter</div>
    </div>
    <div class="srsi-exch-tabs" id="srsi-tabs">
      <button class="srsi-tab active" id="srsi-tab-nse"  onclick="setSrsiExch('NSE')">&#127470;&#127475; NSE</button>
      <button class="srsi-tab"        id="srsi-tab-nyse" onclick="setSrsiExch('NYSE')">&#127482;&#127480; NYSE</button>
    </div>
  </div>
  <div class="srsi-grid" id="srsi-grid"></div>
</div>

<!-- VOLUME SPIKE ALERT PANEL -->
<div class="vs-alert-panel" id="vs-alert-panel">
  <div class="vs-alert-hdr">
    <div>
      <div class="vs-alert-title">&#9889; Volume Spike Alert</div>
      <div class="vs-alert-sub">Top spikes this candle &middot; sorted by vol ratio &middot; click tab for full table</div>
    </div>
    <span class="vs-alert-count" id="vs-alert-count">0 spikes</span>
    <span class="vs-alert-sub" style="margin-left:4px">Showing top 12</span>
  </div>
  <div class="vs-cards" id="vs-alert-cards"></div>
</div>

<!-- MAIN TABS -->
<div class="main-tabs">
  <button class="main-tab active" id="tab-btn-signals" onclick="switchTab('signals')">&#128200; Trendline Signals</button>
  <button class="main-tab vs-tab"  id="tab-btn-volspike" onclick="switchTab('volspike')">&#9889; Volume Spikes <span id="vs-tab-count" style="font-size:9px;opacity:.7"></span></button>
</div>

<!-- TAB: TRENDLINE SIGNALS -->
<div class="tab-panel active" id="tab-signals">

<!-- TOOLBAR -->
<div class="toolbar">
  <div class="search-wrap">
    <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
    <input class="search" id="searchbox" type="text" placeholder="ticker or name&#8230;" oninput="render()">
  </div>

  <div class="btn-grp" id="exch-btns">
    <button class="bg-btn active" onclick="setExch('ALL')">All</button>
    <button class="bg-btn nse-btn" onclick="setExch('NSE')">&#127470;&#127475; NSE</button>
    <button class="bg-btn nyse-btn" onclick="setExch('NYSE')">&#127482;&#127480; NYSE</button>
  </div>

  <div class="btn-grp" id="dir-btns">
    <button class="bg-btn active" onclick="setDir('all')">All</button>
    <button class="bg-btn" onclick="setDir('bull')">&#9650; Bull</button>
    <button class="bg-btn" onclick="setDir('bear')">&#9660; Bear</button>
  </div>

  <select class="flt" id="sect-sel" onchange="render()"><option value="">All Sectors</option></select>

  <select class="flt" id="rsi-sel" onchange="render()">
    <option value="">All RSI Zones</option>
    <option value="HOT">🔴 HOT (&gt;70)</option>
    <option value="Bull">🟢 Bull (55&ndash;70)</option>
    <option value="Mid">⚪ Mid (45&ndash;55)</option>
    <option value="Fade">🟠 Fade (30&ndash;45)</option>
    <option value="OS">🔵 OS (&lt;30)</option>
  </select>

  <label class="vol-lbl"><input type="checkbox" id="vol-chk" onchange="render()"> Vol confirmed</label>

  <select class="flt" id="tf-sel" onchange="applyTimeframe(this.value)" title="Timeframe — re-run scanner with selected interval">
    <option value="1d" %%TF_SEL_1D%%>&#128198; 1 Day</option>
    <option value="4h" %%TF_SEL_4H%%>&#9202; 4 Hour</option>
    <option value="1h" %%TF_SEL_1H%%>&#9202; 1 Hour</option>
    <option value="15m" %%TF_SEL_15M%%>&#9202; 15 Min</option>
  </select>

  <select class="flt" id="topvol-sel" onchange="render()">
    <option value="0">All by Volume</option>
    <option value="5">Top 5 Vol</option>
    <option value="10">Top 10 Vol</option>
    <option value="20">Top 20 Vol</option>
  </select>

  <button class="lgnd-toggle" onclick="toggleLgnd()">&#9656; TL Types (20)</button>
  <span class="rc" id="rc-txt"></span>
</div>

<!-- LEGEND PANEL -->
<div class="lgnd-panel" id="lgnd-panel">
  <div class="lgnd-item"><b>#1</b>Uptrend Line</div>
  <div class="lgnd-item"><b>#2</b>Downtrend Line</div>
  <div class="lgnd-item"><b>#3</b>Horizontal Sup/Res</div>
  <div class="lgnd-item"><b>#4</b>Channel (Asc/Desc/Sideways)</div>
  <div class="lgnd-item"><b>#5</b>Triangle (Sym/Asc/Desc)</div>
  <div class="lgnd-item"><b>#6</b>Wedge (Rising/Falling)</div>
  <div class="lgnd-item"><b>#7</b>Flag &amp; Pennant</div>
  <div class="lgnd-item"><b>#8</b>Fan Lines (3-Fan System)</div>
  <div class="lgnd-item"><b>#9</b>Internal TL (Regression)</div>
  <div class="lgnd-item"><b>#10</b>Dynamic EMA (20/50/200)</div>
  <div class="lgnd-item"><b>#11</b>Neckline (H&amp;S / Inv H&amp;S)</div>
  <div class="lgnd-item"><b>#12</b>Fibonacci TL</div>
  <div class="lgnd-item"><b>#13</b>Pitchfork (Andrews)</div>
  <div class="lgnd-item"><b>#14</b>Regression Channel</div>
  <div class="lgnd-item"><b>#15</b>Acceleration / Parabolic</div>
  <div class="lgnd-item"><b>#16</b>Base TL (Accumulation)</div>
  <div class="lgnd-item"><b>#17</b>Role Reversal (Polarity)</div>
  <div class="lgnd-item"><b>#18</b>Speed Resistance Lines</div>
  <div class="lgnd-item"><b>#19</b>Body TL (No-Wick)</div>
  <div class="lgnd-item"><b>#20</b>Gann Angle (1&times;1 = 45&deg;)</div>
</div>

<!-- DATA TABLE -->
<div class="tbl-wrap">
<table id="main-tbl">
  <thead>
    <tr>
      <th onclick="sortBy('ticker')">Ticker <span class="sa">&#8597;</span></th>
      <th onclick="sortBy('name')">Company <span class="sa">&#8597;</span></th>
      <th onclick="sortBy('sector')">Sector <span class="sa">&#8597;</span></th>
      <th onclick="sortBy('exchange')">Exch <span class="sa">&#8597;</span></th>
      <th onclick="sortBy('price')" style="text-align:right">Price <span class="sa">&#8597;</span></th>
      <th onclick="sortBy('change')" style="text-align:right">Chg% <span class="sa">&#8597;</span></th>
      <th onclick="sortBy('signal')">Signal <span class="sa">&#8597;</span></th>
      <th onclick="sortBy('rsi')" style="text-align:right">RSI <span class="sa">&#8597;</span></th>
      <th onclick="sortBy('srsi')" style="text-align:right">Sect RSI <span class="sa">&#8597;</span></th>
      <th onclick="sortBy('vol_ratio')" style="text-align:right">Vol <span class="sa">&#8597;</span></th>
      <th onclick="sortBy('num')">TL Type <span class="sa">&#8597;</span></th>
      <th>Signal Detail</th>
      <th onclick="sortBy('tl')" style="text-align:right">TL Level <span class="sa">&#8597;</span></th>
    </tr>
  </thead>
  <tbody id="tbl-body"></tbody>
</table>
</div>

</div><!-- end tab-signals -->

<!-- TAB: VOLUME SPIKES -->
<div class="tab-panel" id="tab-volspike">
  <div class="vs-filters">
    <span class="vs-filter-label">Min Vol Ratio:</span>
    <input type="range" id="vs-ratio-slider" min="0.5" max="10" step="0.5" value="1" oninput="renderVsTab()">
    <span id="vs-ratio-val">1x</span>

    <div class="btn-grp" style="margin-left:8px">
      <button class="bg-btn active" id="vs-exch-all"  onclick="setVsExch('ALL')">All</button>
      <button class="bg-btn nse-btn"  id="vs-exch-nse"  onclick="setVsExch('NSE')">&#127470;&#127475; NSE</button>
      <button class="bg-btn nyse-btn" id="vs-exch-nyse" onclick="setVsExch('NYSE')">&#127482;&#127480; NYSE</button>
    </div>

    <div class="btn-grp" style="margin-left:4px">
      <button class="bg-btn active" id="vs-dir-all"  onclick="setVsDir('ALL')">All</button>
      <button class="bg-btn" id="vs-dir-up"   onclick="setVsDir('UP')"  style="color:var(--bull)">&#9650; Up</button>
      <button class="bg-btn" id="vs-dir-down" onclick="setVsDir('DOWN')" style="color:var(--bear)">&#9660; Down</button>
    </div>

    <label class="vol-lbl" style="margin-left:4px">
      <input type="checkbox" id="vs-sig-only" onchange="renderVsTab()"> Breakout signal only
    </label>

    <span class="vs-sort-note" id="vs-row-count"></span>
  </div>

  <div class="vs-tbl-wrap">
  <table id="vs-tbl" style="min-width:900px">
    <thead><tr>
      <th onclick="vsSort('candle_time')">Candle Time (IST) <span class="sa">&#8597;</span></th>
      <th onclick="vsSort('ticker')">Ticker <span class="sa">&#8597;</span></th>
      <th onclick="vsSort('name')">Company <span class="sa">&#8597;</span></th>
      <th onclick="vsSort('sector')">Sector <span class="sa">&#8597;</span></th>
      <th onclick="vsSort('exchange')">Exch <span class="sa">&#8597;</span></th>
      <th onclick="vsSort('price')" style="text-align:right">Price <span class="sa">&#8597;</span></th>
      <th onclick="vsSort('candle_chg')" style="text-align:right">Candle Chg% <span class="sa">&#8597;</span></th>
      <th onclick="vsSort('candle_body')" style="text-align:right">Body% <span class="sa">&#8597;</span></th>
      <th onclick="vsSort('candle_range')" style="text-align:right">Range% <span class="sa">&#8597;</span></th>
      <th onclick="vsSort('vol_ratio')" style="text-align:right">Vol Ratio <span class="sa">&#8597;</span></th>
      <th onclick="vsSort('cur_vol')" style="text-align:right">Cur Vol <span class="sa">&#8597;</span></th>
      <th onclick="vsSort('avg_vol')" style="text-align:right">Avg Vol <span class="sa">&#8597;</span></th>
      <th onclick="vsSort('has_breakout')">TL Breakout <span class="sa">&#8597;</span></th>
    </tr></thead>
    <tbody id="vs-tbl-body"></tbody>
  </table>
  </div>
</div><!-- end tab-volspike -->

<footer>
  &#9888; Educational &amp; research purposes only &middot; Not financial advice &middot; Not SEBI/SEC registered<br>
  Live data via <a href="https://pypi.org/project/yfinance/">yfinance</a> &middot;
  Install: <code>pip install yfinance</code> &middot;
  NSE tickers auto-appended with <code>.NS</code> suffix, BSE fallback <code>.BO</code><br>
  Generated: %%SCAN_TIME%%
</footer>

<script type="application/json" id="data-nse">%%NSE_DATA%%</script>
<script type="application/json" id="data-nyse">%%NYSE_DATA%%</script>
<script type="application/json" id="data-vol-spikes">%%VOL_SPIKE_DATA%%</script>
<script type="application/json" id="data-nse-srsi">%%NSE_SRSI%%</script>
<script type="application/json" id="data-nyse-srsi">%%NYSE_SRSI%%</script>

<script>
/* ── SECTOR RSI PANEL ──────────────────────────────────────────────────── */
var SRSI_DATA={NSE:[],NYSE:[]};
(function(){
  function loadSRSI(id){
    var el=document.getElementById(id);
    if(!el)return[];
    try{return JSON.parse(el.textContent);}catch(e){return[];}
  }
  SRSI_DATA.NSE =loadSRSI('data-nse-srsi');
  SRSI_DATA.NYSE=loadSRSI('data-nyse-srsi');
})();

var SRSI_EXCH='NSE'; // tracks which exchange the panel shows

// sector label → zone lookup map, rebuilt whenever panel switches exchange
var SECT_ZONE_MAP={};
function buildSectZoneMap(exch){
  SECT_ZONE_MAP={};
  var data=SRSI_DATA[exch]||[];
  data.forEach(function(s){
    if(s.label&&s.zone) SECT_ZONE_MAP[s.label]=s.zone;
  });
}
function sectZoneCls(label){
  var zone=SECT_ZONE_MAP[label]||'';
  if(zone==='HOT') return'sz-hot';
  if(zone==='Bull')return'sz-bull';
  if(zone==='Mid') return'sz-mid';
  if(zone==='Fade')return'sz-fade';
  if(zone==='OS')  return'sz-os';
  return'';
}
// initialise with NSE
buildSectZoneMap('NSE');

function zoneClass(zone){
  if(zone==='HOT') return'hot';
  if(zone==='Bull')return'bull';
  if(zone==='Mid') return'mid';
  if(zone==='Fade')return'fade';
  if(zone==='OS')  return'os';
  return'na';
}
function barColor(cls){
  if(cls==='hot') return'#ff4c5b';
  if(cls==='bull')return'#00d17a';
  if(cls==='fade')return'#ff8c42';
  if(cls==='os')  return'#4c9fff';
  return'var(--mu)';
}

function renderSrsiPanel(exch){
  var data=SRSI_DATA[exch]||[];
  var grid=document.getElementById('srsi-grid');
  if(!grid)return;
  if(!data.length){grid.innerHTML='<span style="font-size:11px;color:var(--dim);font-family:var(--mono)">No sector RSI data available</span>';return;}
  var html='';
  data.forEach(function(s){
    var rsi=s.rsi;
    var zone=s.zone||'—';
    var cls=zoneClass(zone);
    var val=rsi!==null&&rsi!==undefined?parseFloat(rsi).toFixed(1):'—';
    var barW=rsi!==null&&rsi!==undefined?Math.round(parseFloat(rsi))+'%':'0%';
    var bColor=barColor(cls);
    html+='<div class="srsi-card '+cls+'" title="'+s.label+': RSI '+val+' ('+zone+')">'
      +'<div class="srsi-val '+cls+'">'+val+'</div>'
      +'<div class="srsi-lbl">'+s.label+'</div>'
      +'<div class="srsi-zone-tag '+cls+'">'+zone+'</div>'
      +'<div class="srsi-bar-wrap"><div class="srsi-bar" style="width:'+barW+';background:'+bColor+'"></div></div>'
      +'</div>';
  });
  grid.innerHTML=html;
}

function setSrsiExch(exch){
  SRSI_EXCH=exch;
  var tabs=document.querySelectorAll('.srsi-tab');
  tabs.forEach(function(t){t.classList.remove('active');});
  var target=document.getElementById('srsi-tab-'+exch.toLowerCase());
  if(target)target.classList.add('active');
  buildSectZoneMap(exch);
  renderSrsiPanel(exch);
  render(); // re-render table rows so sector badges update colour
}

// Auto-sync panel when exchange filter button is clicked
function syncSrsiToExch(exch){
  if(exch==='NSE'||exch==='NYSE'){
    buildSectZoneMap(exch);
    setSrsiExch(exch);
  }
  // If "ALL" selected keep panel as-is
}

/* ── END SECTOR RSI PANEL ─────────────────────────────────────────────── */

var TL_NAMES={
  "1":"Uptrend Line","2":"Downtrend Line","3":"Horizontal",
  "4":"Channel","5":"Triangle","6":"Wedge",
  "7":"Flag & Pennant","8":"Fan Lines","9":"Internal TL",
  "10":"Dynamic EMA","11":"Neckline H&S","12":"Fibonacci TL",
  "13":"Pitchfork","14":"Regression Ch.","15":"Acceleration",
  "16":"Base TL","17":"Role Reversal","18":"Speed Resistance",
  "19":"Body TL","20":"Gann Angle"
};

var ALL_DATA=[];
function loadJSON(id){
  var el=document.getElementById(id);
  if(!el)return[];
  try{return JSON.parse(el.textContent);}catch(e){return[];}
}
(function(){
  var nse=loadJSON('data-nse');
  var nyse=loadJSON('data-nyse');
  ALL_DATA=nse.concat(nyse);
})();

var S={exch:'ALL',dir:'all',sortCol:'',sortAsc:true};

function rsiZone(v){
  if(v===''||v===null||v===undefined)return'';
  v=parseFloat(v);
  if(v>70) return'HOT';
  if(v>=55)return'Bull';
  if(v>=45)return'Mid';
  if(v>=30)return'Fade';
  return'OS';
}
function rsiCls(z){
  if(z==='HOT') return'rz-hot';
  if(z==='Bull')return'rz-bull';
  if(z==='Mid') return'rz-mid';
  if(z==='Fade')return'rz-fade';
  if(z==='OS')  return'rz-os';
  return'rz-na';
}
function fmtP(p,exch){
  var s=exch==='NSE'?'\u20b9':'$';
  return s+parseFloat(p).toLocaleString('en-IN',{minimumFractionDigits:2,maximumFractionDigits:2});
}

function populateSectors(){
  var sel=document.getElementById('sect-sel');
  var cur=sel.value;
  var data=ALL_DATA.filter(function(r){return S.exch==='ALL'||r.exchange===S.exch;});
  var seen={};var sects=[];
  data.forEach(function(r){if(r.sector&&r.sector!=='\u2014'&&!seen[r.sector]){seen[r.sector]=1;sects.push(r.sector);}});
  sects.sort();
  while(sel.options.length>1)sel.remove(1);
  sects.forEach(function(s){var o=document.createElement('option');o.value=s;o.textContent=s;if(s===cur)o.selected=true;sel.appendChild(o);});
}

function render(){
  var q=document.getElementById('searchbox').value.trim().toLowerCase();
  var sectF=document.getElementById('sect-sel').value;
  var rsiF=document.getElementById('rsi-sel').value;
  var volOnly=document.getElementById('vol-chk').checked;
  var topVol=parseInt(document.getElementById('topvol-sel').value||'0',10);

  var data=ALL_DATA.filter(function(r){
    if(S.exch!=='ALL'&&r.exchange!==S.exch)return false;
    if(S.dir==='bull'&&r.signal!=='BULLISH')return false;
    if(S.dir==='bear'&&r.signal!=='BEARISH')return false;
    if(sectF&&r.sector!==sectF)return false;
    if(rsiF&&rsiZone(r.rsi)!==rsiF)return false;
    if(volOnly&&!r.vol_ok)return false;
    if(q&&r.ticker.toLowerCase().indexOf(q)<0&&r.name.toLowerCase().indexOf(q)<0)return false;
    return true;
  });

  // Top-N by volume ratio
  if(topVol>0){
    var sorted=[].concat(data).sort(function(a,b){return parseFloat(b.vol_ratio)-parseFloat(a.vol_ratio);});
    var topTickers={};
    sorted.slice(0,topVol).forEach(function(r){topTickers[r.ticker]=1;});
    data=data.filter(function(r){return topTickers[r.ticker];});
  }

  if(S.sortCol){
    var col=S.sortCol,asc=S.sortAsc;
    data.sort(function(a,b){
      var va=a[col],vb=b[col];
      if(va===undefined||va===null)va='';
      if(vb===undefined||vb===null)vb='';
      if(typeof va==='string')va=va.toLowerCase(),vb=vb.toLowerCase();
      return asc?(va>vb?1:va<vb?-1:0):(va<vb?1:va>vb?-1:0);
    });
  }

  document.getElementById('rc-txt').textContent=data.length+' signal'+(data.length!==1?'s':'');
  document.getElementById('stat-total').textContent=ALL_DATA.length;
  document.getElementById('stat-bull').textContent=ALL_DATA.filter(function(r){return r.signal==='BULLISH';}).length;
  document.getElementById('stat-bear').textContent=ALL_DATA.filter(function(r){return r.signal==='BEARISH';}).length;
  document.getElementById('stat-vol').textContent=ALL_DATA.filter(function(r){return r.vol_ok;}).length;

  var tbody=document.getElementById('tbl-body');
  if(!data.length){
    tbody.innerHTML='<tr class="empty-row"><td colspan="13">No signals match the current filters.</td></tr>';
    return;
  }

  var html='';
  data.forEach(function(r){
    var isBull=r.signal==='BULLISH';
    var rsiV=r.rsi!==''?parseFloat(r.rsi).toFixed(1):'—';
    var rsiZ=r.rsi!==''?rsiZone(r.rsi):'';
    var srsiV=r.srsi!==''?parseFloat(r.srsi).toFixed(1):'—';
    var srsiZ=r.srsi!==''?rsiZone(r.srsi):'';
    var chgCls=parseFloat(r.change)>=0?'up':'dn';
    var chgSign=parseFloat(r.change)>=0?'+':'';
    var volOk=r.vol_ok;
    var exchCls=r.exchange==='NSE'?'exch-nse':'exch-nyse';
    var exchFlag=r.exchange==='NSE'?'&#127470;&#127475;':'&#127482;&#127480;';
    var sectCls=sectZoneCls(r.sector);
    html+='<tr>'
      +'<td class="ct">'+r.ticker+'</td>'
      +'<td class="cn" title="'+r.name+'">'+r.name+'</td>'
      +'<td class="cs"><span class="'+sectCls+'">'+r.sector+'</span></td>'
      +'<td><span class="exch-badge '+exchCls+'">'+exchFlag+' '+r.exchange+'</span></td>'
      +'<td class="cp">'+fmtP(r.price,r.exchange)+'</td>'
      +'<td class="cc '+chgCls+'">'+chgSign+parseFloat(r.change).toFixed(2)+'%</td>'
      +'<td><span class="sig-badge '+(isBull?'bull':'bear')+'">'+(isBull?'\u25b2':'\u25bc')+' '+r.signal+'</span></td>'
      +'<td class="crsi"><span class="rv '+rsiCls(rsiZ)+'">'+rsiV+'</span>'+(rsiZ?'<span class="rz '+rsiCls(rsiZ)+'">'+rsiZ+'</span>':'')+'</td>'
      +'<td class="crsi"><span class="rv '+rsiCls(srsiZ)+'">'+srsiV+'</span>'+(srsiZ?'<span class="rz '+rsiCls(srsiZ)+'">'+srsiZ+'</span>':'')+'</td>'
      +'<td class="cvol">'+(volOk?'<span class="vok">':'')
        +parseFloat(r.vol_ratio).toFixed(1)+'x'+(volOk?'<b>&nbsp;&#10003;</b></span>':'')
      +'</td>'
      +'<td class="ctln"><span class="tnum">#'+r.num+'</span><span class="tname">'+(TL_NAMES[r.num]||'')+'</span></td>'
      +'<td class="cdet"><span class="dtxt" title="'+r.type+' \u2014 '+r.detail+'">'+r.type+' \u2014 '+r.detail+'</span></td>'
      +'<td class="clvl">'+fmtP(r.tl,r.exchange)+'</td>'
      +'</tr>';
  });
  tbody.innerHTML=html;
}

function applyTimeframe(tf){
  var labels={'15m':'15 Min','1h':'1 Hour','4h':'4 Hour','1d':'1 Day'};
  var badge=document.getElementById('tf-badge');
  if(badge)badge.textContent='\u23f1 '+( labels[tf]||tf);
  // Show re-run notice banner
  var existing=document.getElementById('tf-notice');
  if(existing)existing.remove();
  var bar=document.createElement('div');
  bar.id='tf-notice';
  bar.style.cssText='background:#1a1e27;border-bottom:1px solid rgba(245,200,66,0.4);padding:8px 20px;font-size:11px;font-family:var(--mono);color:#f5c842;display:flex;align-items:center;gap:10px;';
  bar.innerHTML='&#9888;&nbsp;<b>Timeframe changed to '+(labels[tf]||tf)+'</b> &mdash; '
    +'Re-run the scanner with: &nbsp;<code style="background:rgba(255,255,255,0.08);padding:2px 7px;border-radius:3px;">python trendline_scanner.py --timeframe '+tf+'</code>'
    +'&nbsp;<button onclick="this.parentNode.remove()" style="margin-left:auto;background:transparent;border:1px solid rgba(245,200,66,0.4);color:#f5c842;padding:2px 10px;border-radius:4px;cursor:pointer;font-size:10px;font-family:var(--mono)">&#10005; Dismiss</button>';
  var toolbar=document.querySelector('.toolbar');
  toolbar.parentNode.insertBefore(bar,toolbar.nextSibling);
}

function setExch(ex){
  S.exch=ex;
  var btns=document.querySelectorAll('#exch-btns .bg-btn');
  btns.forEach(function(b){b.classList.remove('active');});
  var map={ALL:0,NSE:1,NYSE:2};
  if(map[ex]!==undefined)btns[map[ex]].classList.add('active');
  document.getElementById('sect-sel').value='';
  populateSectors();
  syncSrsiToExch(ex);
  render();
}

function setDir(d){
  S.dir=d;
  var btns=document.querySelectorAll('#dir-btns .bg-btn');
  btns.forEach(function(b){b.classList.remove('active','bull-on','bear-on');});
  var map={all:0,bull:1,bear:2};
  var btn=btns[map[d]];
  if(d==='bull')btn.classList.add('bull-on');
  else if(d==='bear')btn.classList.add('bear-on');
  else btn.classList.add('active');
  render();
}

function sortBy(col){
  if(S.sortCol===col)S.sortAsc=!S.sortAsc;
  else{S.sortCol=col;S.sortAsc=true;}
  document.querySelectorAll('thead th').forEach(function(th){
    th.classList.remove('sorted');
    var sa=th.querySelector('.sa');if(sa)sa.innerHTML='&#8597;';
  });
  var cols=['ticker','name','sector','exchange','price','change','signal','rsi','srsi','vol_ratio','num','','tl'];
  var idx=cols.indexOf(col);
  if(idx>=0){
    var th=document.querySelectorAll('thead th')[idx];
    th.classList.add('sorted');
    var sa=th.querySelector('.sa');
    if(sa)sa.innerHTML=S.sortAsc?'&#8593;':'&#8595;';
  }
  render();
}

function toggleLgnd(){
  var p=document.getElementById('lgnd-panel');
  var b=document.querySelector('.lgnd-toggle');
  p.classList.toggle('open');
  b.textContent=p.classList.contains('open')?'\u25be TL Types (20)':'\u25b6 TL Types (20)';
}

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

populateSectors();
renderSrsiPanel('NSE');
render();

/* ── VOLUME SPIKE TAB ──────────────────────────────────────────────── */
var VS_DATA = (function(){
  var el = document.getElementById('data-vol-spikes');
  if(!el) return [];
  try{ return JSON.parse(el.textContent); }catch(e){ return []; }
})();

var VS = { exch:'ALL', dir:'ALL', sortCol:'vol_ratio', sortAsc:false };

function fmtVol(v){
  if(v>=1e7) return (v/1e7).toFixed(1)+'Cr';
  if(v>=1e5) return (v/1e5).toFixed(1)+'L';
  if(v>=1000) return (v/1000).toFixed(0)+'K';
  return v;
}

function switchTab(tab){
  document.querySelectorAll('.tab-panel').forEach(function(p){ p.classList.remove('active'); });
  document.querySelectorAll('.main-tab').forEach(function(b){ b.classList.remove('active'); });
  document.getElementById('tab-'+tab).classList.add('active');
  document.getElementById('tab-btn-'+tab).classList.add('active');
}

function setVsExch(ex){
  VS.exch = ex;
  ['all','nse','nyse'].forEach(function(e){
    var btn = document.getElementById('vs-exch-'+e);
    if(btn) btn.classList.remove('active');
  });
  var map = {ALL:'all', NSE:'nse', NYSE:'nyse'};
  var btn = document.getElementById('vs-exch-'+(map[ex]||'all'));
  if(btn) btn.classList.add('active');
  renderVsTab();
}

function setVsDir(d){
  VS.dir = d;
  ['all','up','down'].forEach(function(e){
    var btn = document.getElementById('vs-dir-'+e);
    if(btn) btn.classList.remove('active');
  });
  var map = {ALL:'all', UP:'up', DOWN:'down'};
  var btn = document.getElementById('vs-dir-'+(map[d]||'all'));
  if(btn) btn.classList.add('active');
  renderVsTab();
}

function vsSort(col){
  if(VS.sortCol===col) VS.sortAsc=!VS.sortAsc;
  else { VS.sortCol=col; VS.sortAsc=(col==='ticker'||col==='name'); }
  // update header arrows
  document.querySelectorAll('#vs-tbl thead th').forEach(function(th){ th.classList.remove('sorted'); var sa=th.querySelector('.sa');if(sa)sa.innerHTML='&#8597;'; });
  var cols=['candle_time','ticker','name','sector','exchange','price','candle_chg','candle_body','candle_range','vol_ratio','cur_vol','avg_vol','has_breakout'];
  var idx=cols.indexOf(col);
  if(idx>=0){
    var th=document.querySelectorAll('#vs-tbl thead th')[idx];
    if(th){ th.classList.add('sorted'); var sa=th.querySelector('.sa'); if(sa)sa.innerHTML=VS.sortAsc?'&#8593;':'&#8595;'; }
  }
  renderVsTab();
}

function renderVsTab(){
  var slider = document.getElementById('vs-ratio-slider');
  var ratioMin = slider ? parseFloat(slider.value) : 1;
  document.getElementById('vs-ratio-val').textContent = ratioMin.toFixed(1)+'x';

  var sigOnly = document.getElementById('vs-sig-only').checked;

  var data = VS_DATA.filter(function(r){
    if(VS.exch !== 'ALL' && r.exchange !== VS.exch) return false;
    if(VS.dir  !== 'ALL' && r.direction !== VS.dir) return false;
    if(r.vol_ratio < ratioMin) return false;
    if(sigOnly && !r.has_breakout) return false;
    return true;
  });

  // sort
  data = [].concat(data).sort(function(a,b){
    var va=a[VS.sortCol], vb=b[VS.sortCol];
    if(va===undefined||va===null) va='';
    if(vb===undefined||vb===null) vb='';
    if(typeof va==='string') va=va.toLowerCase(), vb=vb.toLowerCase();
    return VS.sortAsc ? (va>vb?1:va<vb?-1:0) : (va<vb?1:va>vb?-1:0);
  });

  document.getElementById('vs-row-count').textContent = data.length+' stock'+(data.length!==1?'s':'');

  var tbody = document.getElementById('vs-tbl-body');
  if(!data.length){
    tbody.innerHTML='<tr><td colspan="13" style="padding:20px;color:var(--dim);font-family:var(--mono);text-align:center">No volume spikes match the current filters.</td></tr>';
    return;
  }

  var html='';
  data.forEach(function(r){
    var isUp   = r.direction === 'UP';
    var chgCls = r.candle_chg >= 0 ? 'up' : 'dn';
    var chgSign= r.candle_chg >= 0 ? '+' : '';
    var exchCls= r.exchange==='NSE'?'exch-nse':'exch-nyse';
    var exchFlag=r.exchange==='NSE'?'&#127470;&#127475;':'&#127482;&#127480;';
    var ratioColor = r.vol_ratio>=5 ? '#ff4c5b' : r.vol_ratio>=3 ? '#f5c842' : r.vol_ratio>=2 ? '#00d17a' : 'var(--mu)';
    var dirBadge = isUp
      ? '<span style="color:var(--bull);font-family:var(--mono);font-size:10px;font-weight:700">&#9650; UP</span>'
      : '<span style="color:var(--bear);font-family:var(--mono);font-size:10px;font-weight:700">&#9660; DOWN</span>';
    var brkCell = r.has_breakout
      ? '<span class="vs-signal-tag" title="'+r.breakout_signals.join(', ')+'">&#9889; '+r.breakout_signals.length+' breakout'+(r.breakout_signals.length>1?'s':'')+'</span>'
      : '<span style="color:var(--dim);font-size:10px;font-family:var(--mono)">—</span>';
    html += '<tr>'
      +'<td style="font-family:var(--mono);font-size:11px;color:var(--acc);white-space:nowrap">'+(r.candle_time||'—')+'</td>'
      +'<td class="ct">'+r.ticker+'</td>'
      +'<td class="cn" title="'+r.name+'">'+r.name+'</td>'
      +'<td class="cs"><span class="'+sectZoneCls(r.sector)+'">'+r.sector+'</span></td>'
      +'<td><span class="exch-badge '+exchCls+'">'+exchFlag+' '+r.exchange+'</span></td>'
      +'<td class="cp">'+fmtP(r.price, r.exchange)+'</td>'
      +'<td class="cc '+chgCls+'" style="text-align:right">'+chgSign+r.candle_chg.toFixed(2)+'%</td>'
      +'<td style="text-align:right;font-family:var(--mono);color:var(--mu)">'+r.candle_body.toFixed(2)+'%</td>'
      +'<td style="text-align:right;font-family:var(--mono);color:var(--dim)">'+r.candle_range.toFixed(2)+'%</td>'
      +'<td style="text-align:right;font-family:var(--mono);font-weight:700;font-size:14px;color:'+ratioColor+'">'+r.vol_ratio.toFixed(2)+'x</td>'
      +'<td style="text-align:right;font-family:var(--mono);color:var(--mu)">'+fmtVol(r.cur_vol)+'</td>'
      +'<td style="text-align:right;font-family:var(--mono);color:var(--dim)">'+fmtVol(r.avg_vol)+'</td>'
      +'<td>'+brkCell+'</td>'
      +'</tr>';
  });
  tbody.innerHTML = html;
}

// ── Build top-12 alert cards ──────────────────────────────────────────────
function buildAlertCards(){
  var panel = document.getElementById('vs-alert-panel');
  var cards = document.getElementById('vs-alert-cards');
  var countEl = document.getElementById('vs-alert-count');
  var tabCount = document.getElementById('vs-tab-count');
  if(!panel||!cards) return;

  var top = VS_DATA.slice(0,12);   // already sorted by vol_ratio desc from Python
  if(!top.length){ panel.classList.remove('has-data'); return; }

  panel.classList.add('has-data');
  if(countEl) countEl.textContent = VS_DATA.length+' spike'+(VS_DATA.length!==1?'s':'');
  if(tabCount) tabCount.textContent = '('+VS_DATA.length+')';

  var html='';
  top.forEach(function(r){
    var isUp = r.direction==='UP';
    var dirCls = isUp ? 'dir-up' : 'dir-down';
    var sigCls = r.has_breakout ? 'has-signal' : '';
    var dotCls = r.exchange==='NSE' ? 'nse' : 'nyse';
    var chgSign = r.candle_chg>=0?'+':'';
    var chgCls  = r.candle_chg>=0?'up':'down';
    var ratioColor = r.vol_ratio>=5?'#ff4c5b':r.vol_ratio>=3?'#f5c842':'#00d17a';
    html += '<div class="vs-card '+dirCls+' '+sigCls+'" onclick="switchTab(&apos;volspike&apos;)" title="'+r.name+' — Vol: '+r.vol_ratio.toFixed(2)+'x avg | Chg: '+r.candle_chg.toFixed(2)+'%">'
      +'<div style="display:flex;align-items:center;gap:5px">'
      +'<span class="vs-exch-dot '+dotCls+'"></span>'
      +'<span class="vs-card-ticker">'+r.ticker+'</span>'
      +'</div>'
      +'<div class="vs-card-name">'+r.name+'</div>'
      +'<div class="vs-card-row">'
      +'<div><div class="vs-vol-ratio" style="color:'+ratioColor+'">'+r.vol_ratio.toFixed(1)+'x</div>'
      +'<div class="vs-vol-label">vol ratio</div></div>'
      +'<div class="vs-chg '+chgCls+'">'+chgSign+r.candle_chg.toFixed(2)+'%</div>'
      +'</div>'
      +(r.has_breakout?'<div class="vs-signal-tag">&#9889; breakout</div>':'')
      +'</div>';
  });
  cards.innerHTML = html;
}

buildAlertCards();
renderVsTab();
// mark vol_ratio col header as default sorted
(function(){
  var th=document.querySelectorAll('#vs-tbl thead th')[8];
  if(th){th.classList.add('sorted');var sa=th.querySelector('.sa');if(sa)sa.innerHTML='&#8595;';}
})();
</script>
</body></html>"""



# ── Collect all sector RSIs for the panel ────────────────────────────────────
NSE_SECTOR_CODES = [
    ("^NSEBANK",            "Banking"),
    ("NIFTY_FIN_SERVICE.NS","Fin. Services"),
    ("^CNXIT",              "IT"),
    ("^CNXENERGY",          "Energy"),
    ("^CNXAUTO",            "Auto"),
    ("^CNXPHARMA",          "Pharma"),
    ("^CNXMETAL",           "Metals"),
    ("^CNXFMCG",            "FMCG"),
    ("^CNXINFRA",           "Infra/Defence"),
    ("^CNXCONSUM",          "Cons. Goods"),
]
NYSE_SECTOR_CODES = [
    ("XLK",  "Technology"),
    ("XLF",  "Financials"),
    ("XLV",  "Healthcare"),
    ("XLP",  "Cons. Staples"),
    ("XLY",  "Cons. Discret."),
    ("XLE",  "Energy"),
    ("XLI",  "Industrials"),
    ("XLC",  "Comm. Services"),
    ("XLB",  "Materials"),
]

def collect_sector_rsi_panel():
    """
    Fetch daily RSI for every NSE and NYSE sector index.
    Always uses 1d/6mo regardless of the active scan timeframe,
    so the sector health panel is always on the daily chart.
    Returns two lists of dicts: nse_panel, nyse_panel.
    """
    def _fetch_rsi_daily(code):
        if YF_AVAILABLE:
            df = fetch_yf(code, period="6mo", interval="1d")
            if df is not None and len(df) >= 15:
                return calc_rsi(df)
        return get_sector_rsi(code)   # synthetic fallback

    nse_panel, nyse_panel = [], []

    for code, label in NSE_SECTOR_CODES:
        rsi_val = _fetch_rsi_daily(code)
        zone, _ = rsi_zone(rsi_val)
        nse_panel.append({"code": code, "label": label,
                          "rsi": round(rsi_val, 1) if rsi_val is not None else None,
                          "zone": zone})

    for code, label in NYSE_SECTOR_CODES:
        rsi_val = _fetch_rsi_daily(code)
        zone, _ = rsi_zone(rsi_val)
        nyse_panel.append({"code": code, "label": label,
                           "rsi": round(rsi_val, 1) if rsi_val is not None else None,
                           "zone": zone})

    return nse_panel, nyse_panel


# ── Volume Spike Detector ─────────────────────────────────────────────────────
def detect_volume_spikes(all_stocks_data):
    """
    For every stock in all_stocks_data (list of (ticker,name,price,idx,exchange)),
    fetch OHLCV using ACTIVE_TIMEFRAME and compute volume spike metrics on the
    latest candle. Returns list of dicts sorted by vol_ratio descending.
    all_stocks_data: list of (ticker, name, base_price, idx, exchange, live)
    """
    spikes = []
    for (ticker, name, base_price, idx, exchange, live) in all_stocks_data:
        try:
            df = fetch_data(ticker, base_price, idx, exchange=exchange, live=live)
            if df is None or len(df) < 5:
                continue

            cur_candle  = df.iloc[-1]
            prev_close  = float(df["Close"].iloc[-2])
            cur_close   = float(cur_candle["Close"])
            cur_open    = float(cur_candle["Open"])
            cur_high    = float(cur_candle["High"])
            cur_low     = float(cur_candle["Low"])
            cur_vol     = float(cur_candle["Volume"])

            # Capture the candle's own timestamp (date + time of bar open)
            # _ts column holds IST-converted timestamps preserved in fetch_yf
            try:
                import pandas as _pd
                if "_ts" in df.columns and df["_ts"].iloc[-1] is not None:
                    ts_ist = _pd.Timestamp(df["_ts"].iloc[-1])
                    # For daily timeframe, yfinance gives date-only (midnight) — show date only
                    if ACTIVE_TIMEFRAME == "1d":
                        candle_time_str = ts_ist.strftime("%d %b %Y")
                    else:
                        candle_time_str = ts_ist.strftime("%d %b %Y  %H:%M IST")
                else:
                    # Fallback: use stripped index, treat as UTC for intraday
                    raw_ts = df.index[-1]
                    ts = _pd.Timestamp(raw_ts)
                    if ACTIVE_TIMEFRAME == "1d":
                        candle_time_str = ts.strftime("%d %b %Y")
                    else:
                        ts_ist = ts.tz_localize("UTC").tz_convert("Asia/Kolkata")
                        candle_time_str = ts_ist.strftime("%d %b %Y  %H:%M IST")
            except Exception:
                candle_time_str = str(df.index[-1])[:16]

            # Average volume over last 20 candles (excluding current)
            avg_vol = float(df["Volume"].iloc[-21:-1].mean()) if len(df) >= 21 else float(df["Volume"].iloc[:-1].mean())
            if avg_vol <= 0:
                continue

            vol_ratio   = round(cur_vol / avg_vol, 2)
            candle_chg  = round((cur_close - prev_close) / prev_close * 100, 2) if prev_close else 0
            candle_body = round(abs(cur_close - cur_open) / prev_close * 100, 2) if prev_close else 0
            candle_range= round((cur_high - cur_low) / prev_close * 100, 2) if prev_close else 0
            direction   = "UP" if cur_close >= cur_open else "DOWN"

            # Check if this ticker has any trendline breakout signal in all_results
            tl_signals  = []  # will be filled in generate_html

            spikes.append({
                "ticker":       ticker,
                "name":         name,
                "exchange":     exchange,
                "sector":       get_sector(ticker, exchange),
                "price":        round(cur_close, 2),
                "candle_chg":   candle_chg,
                "candle_body":  candle_body,
                "candle_range": candle_range,
                "direction":    direction,
                "cur_vol":      int(cur_vol),
                "avg_vol":      int(avg_vol),
                "vol_ratio":    vol_ratio,
                "candle_time":  candle_time_str,   # date+time of the spike candle
                "has_breakout": False,   # patched in generate_html
                "breakout_signals": [],  # patched in generate_html
            })
        except Exception as e:
            logging.debug(f"[{ticker}] vol spike calc failed: {e}")

    spikes.sort(key=lambda x: x["vol_ratio"], reverse=True)
    return spikes


def generate_html(results, scan_time, tf_label="1 Day", vol_spikes=None):
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

    # ── Volume Spike tab data ──────────────────────────────────────────────────
    if vol_spikes is None:
        vol_spikes = []
    # Patch breakout signals: match by ticker
    breakout_map = {}
    for r in results:
        t = r["ticker"]
        if t not in breakout_map:
            breakout_map[t] = []
        breakout_map[t].append(r["type"] + " (" + r["signal"] + ")")
    for s in vol_spikes:
        sigs = breakout_map.get(s["ticker"], [])
        s["has_breakout"]       = len(sigs) > 0
        s["breakout_signals"]   = sigs[:3]   # max 3 labels in panel
    vol_spike_json = _json.dumps(vol_spikes, ensure_ascii=False)

    # Sector RSI panel data (always daily)
    nse_panel, nyse_panel = collect_sector_rsi_panel()
    nse_srsi_json  = _json.dumps(nse_panel,  ensure_ascii=False)
    nyse_srsi_json = _json.dumps(nyse_panel, ensure_ascii=False)

    html = _HTML_TEMPLATE
    html = html.replace("%%SCAN_TIME%%",     scan_time)
    html = html.replace("%%TF_LABEL%%",      tf_label)
    # Mark the selected option in the timeframe dropdown
    tf_key = ACTIVE_TIMEFRAME
    for k in ["1d","4h","1h","15m"]:
        placeholder = f"%%TF_SEL_{k.upper().replace('M','M')}%%"
        html = html.replace(placeholder, 'selected' if k == tf_key else '')
    html = html.replace("%%NSE_DATA%%",      nse_json)
    html = html.replace("%%NYSE_DATA%%",     nyse_json)
    html = html.replace("%%VOL_SPIKE_DATA%%", vol_spike_json)
    html = html.replace("%%NSE_SRSI%%",      nse_srsi_json)
    html = html.replace("%%NYSE_SRSI%%",     nyse_srsi_json)
    html = html.replace("%%TOTAL%%",         str(len(results)))
    html = html.replace("%%BULL%%",          str(len(bull)))
    html = html.replace("%%BEAR%%",          str(len(bear)))
    html = html.replace("%%NSE%%",           str(len(nse)))
    html = html.replace("%%NYSE%%",          str(len(nyse)))
    html = html.replace("%%VOL%%",           str(len(vol_c)))
    html = html.replace("%%SCANNED%%",       str(len(NSE_STOCKS) + len(NYSE_STOCKS)))
    return html


# ── Market Hours (FIX-14 / FIX-15) ───────────────────────────────────────────
def market_status() -> tuple[bool, bool]:
    """
    Returns (nse_open, nyse_open).
      NSE  : Mon–Fri  09:15–15:30  IST  (Asia/Kolkata)
      NYSE : Mon–Fri  09:30–16:00  ET   (America/New_York, DST-aware)
    Note: public holidays are NOT checked — only clock & weekday.
    """
    now_ist = datetime.now(ZoneInfo("Asia/Kolkata"))
    now_et  = datetime.now(ZoneInfo("America/New_York"))

    def _in_session(now, open_hm, close_hm):
        if now.weekday() >= 5:          # Saturday=5, Sunday=6
            return False
        t = (now.hour, now.minute)
        return open_hm <= t <= close_hm

    nse_open  = _in_session(now_ist, (9, 15),  (15, 30))   # 09:15–15:30 IST
    nyse_open = _in_session(now_et,  (9,  0),  (19,  0))   # 09:00–19:00 ET
    return nse_open, nyse_open


# ── Report Freshness Check (FIX-16) ───────────────────────────────────────────
# How many minutes a report stays "fresh" for each timeframe
_FRESH_MINUTES = {"15m": 15, "1h": 60, "4h": 240, "1d": 1440}

def report_is_fresh(out_path: str, timeframe: str) -> bool:
    """Return True if the existing report is younger than one candle period."""
    if not os.path.exists(out_path):
        return False
    age_min = (time.time() - os.path.getmtime(out_path)) / 60
    return age_min < _FRESH_MINUTES.get(timeframe, 0)


# ── Single-timeframe scan (shared by main() and multi-TF loop) ───────────────
def run_single_timeframe(tf, nse_to_scan, nyse_to_scan, scan_time, force=False):
    """
    Run a full scan for one timeframe (tf = '15m'|'1h'|'4h'|'1d').
    Returns (all_results, vol_spikes, out_path, tf_label).
    Clears caches before running so each TF gets fresh yfinance data.
    """
    global ACTIVE_TIMEFRAME, _yf_cache, _sector_rsi_cache
    ACTIVE_TIMEFRAME = tf
    _yf_cache.clear()
    _sector_rsi_cache.clear()

    tf_label    = TIMEFRAME_CONFIG[tf][3]
    total_stocks = len(nse_to_scan) + len(nyse_to_scan)
    out_path    = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               f"trendline_breakout_{tf}_report.html")

    print(f"\n  ── Timeframe: {tf_label} ({'--force' if force else 'normal'}) ─────────────────")

    all_results = []
    done = 0

    for idx, (ticker, name, price) in enumerate(nse_to_scan):
        res = scan_stock(ticker, name, price, idx, "NSE", live=True)
        all_results.extend(res)
        done += 1
        pct = int(done / max(total_stocks, 1) * 40)
        print(f"\r    [{tf_label}] Scanning [{'█'*pct}{'.'*(40-pct)}] {done}/{total_stocks}", end="", flush=True)

    for idx, (ticker, name, price) in enumerate(nyse_to_scan):
        res = scan_stock(ticker, name, price, idx, "NYSE", live=True)
        all_results.extend(res)
        done += 1
        pct = int(done / max(total_stocks, 1) * 40)
        print(f"\r    [{tf_label}] Scanning [{'█'*pct}{'.'*(40-pct)}] {done}/{total_stocks}", end="", flush=True)

    bull = [r for r in all_results if r["signal"] == "BULLISH"]
    bear = [r for r in all_results if r["signal"] == "BEARISH"]
    print(f"\r    [{tf_label}] Scanning [{'█'*40}] {total_stocks}/{total_stocks}  ✅ Done")
    print(f"    Signals: {len(all_results)} total  |  🟢 {len(bull)} Bullish  |  🔴 {len(bear)} Bearish")

    # Volume spikes
    print(f"    Building volume spike tracker…", end="", flush=True)
    all_stocks_live = (
        [(t, n, p, i, "NSE",  True) for i,(t,n,p) in enumerate(nse_to_scan)] +
        [(t, n, p, i, "NYSE", True) for i,(t,n,p) in enumerate(nyse_to_scan)]
    )
    vol_spikes = detect_volume_spikes(all_stocks_live)
    print(f" {len(vol_spikes)} stocks tracked")

    html = generate_html(all_results, scan_time, tf_label, vol_spikes=vol_spikes)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"    Report  → {out_path}")

    return all_results, vol_spikes, out_path, tf_label


# ── Multi-timeframe combined HTML index page ──────────────────────────────────
def generate_combined_index(tf_reports, scan_time):
    """
    Generate a simple HTML index page that links to each individual TF report
    and shows a quick summary table.
    tf_reports: list of (tf, tf_label, out_path, n_bull, n_bear, n_vol, n_total)
    """
    rows = ""
    for (tf, tf_label, out_path, n_bull, n_bear, n_vol, n_total) in tf_reports:
        fname = os.path.basename(out_path)
        rows += f"""
        <tr>
          <td style="font-family:var(--mono);color:var(--gold);font-weight:700">{tf_label}</td>
          <td style="font-family:var(--mono);color:var(--acc)">{n_total}</td>
          <td style="font-family:var(--mono);color:#00d17a">▲ {n_bull}</td>
          <td style="font-family:var(--mono);color:#ff4c5b">▼ {n_bear}</td>
          <td style="font-family:var(--mono);color:#00d17a">{n_vol} ✓</td>
          <td><a href="{fname}" style="color:var(--acc);font-family:var(--mono);font-size:11px"
              target="_blank">Open {tf_label} Report →</a></td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>TrendBreak Pro · All Timeframes</title>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@400;600&display=swap" rel="stylesheet">
<style>
:root{{--bg:#0d0f14;--surf:#13161d;--surf2:#1a1e27;--bdr:rgba(255,255,255,0.07);
  --bdr2:rgba(255,255,255,0.13);--txt:#e8eaf0;--mu:#8b909e;--dim:#555b6a;
  --acc:#4c9fff;--gold:#f5c842;--mono:'IBM Plex Mono',monospace;--sans:'IBM Plex Sans',sans-serif}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--txt);font-family:var(--sans);min-height:100vh;padding:40px 24px}}
h1{{font-family:var(--mono);font-size:22px;color:#fff;margin-bottom:4px}}
.sub{{font-family:var(--mono);font-size:11px;color:var(--dim);margin-bottom:32px}}
.card{{background:var(--surf);border:1px solid var(--bdr2);border-radius:10px;overflow:hidden;max-width:780px}}
.card-hdr{{padding:14px 20px;border-bottom:1px solid var(--bdr2);display:flex;align-items:center;gap:10px}}
.card-title{{font-family:var(--mono);font-size:12px;font-weight:600;color:var(--mu);
  text-transform:uppercase;letter-spacing:.08em}}
table{{width:100%;border-collapse:collapse}}
thead th{{text-align:left;padding:9px 16px;color:var(--dim);font-family:var(--mono);
  font-size:10px;font-weight:500;text-transform:uppercase;letter-spacing:.07em;
  border-bottom:1px solid var(--bdr2)}}
tbody tr{{border-bottom:1px solid var(--bdr);transition:background .1s}}
tbody tr:hover{{background:var(--surf2)}}
tbody td{{padding:12px 16px;vertical-align:middle}}
.tf-links{{display:flex;flex-wrap:wrap;gap:10px;margin-top:24px;max-width:780px}}
.tf-btn{{display:inline-flex;align-items:center;gap:6px;padding:10px 20px;
  border-radius:8px;text-decoration:none;font-family:var(--mono);font-size:12px;
  font-weight:600;border:1px solid var(--bdr2);background:var(--surf);
  color:var(--acc);transition:.15s}}
.tf-btn:hover{{border-color:var(--acc);background:rgba(76,159,255,0.08)}}
footer{{margin-top:32px;font-family:var(--mono);font-size:10px;color:var(--dim)}}
</style></head><body>
<h1>⚡ TrendBreak Pro — All Timeframes</h1>
<div class="sub">Scanned: {scan_time} &nbsp;·&nbsp; 20 trendline types &nbsp;·&nbsp; NSE + NYSE</div>

<div class="card">
  <div class="card-hdr"><span class="card-title">📊 Summary by Timeframe</span></div>
  <table>
    <thead><tr>
      <th>Timeframe</th><th>Total Signals</th><th>Bullish</th><th>Bearish</th>
      <th>Vol Confirmed</th><th>Report</th>
    </tr></thead>
    <tbody>{rows}</tbody>
  </table>
</div>

<div class="tf-links">
  {''.join(f'<a class="tf-btn" href="{os.path.basename(p)}" target="_blank">⏱ {lbl}</a>'
           for (_, lbl, p, *_) in tf_reports)}
</div>

<footer>
  ⚠ Educational &amp; research purposes only · Not financial advice<br>
  Generated: {scan_time}
</footer>
</body></html>"""


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    import argparse, os as _os
    global ACTIVE_TIMEFRAME, _yf_cache, _sector_rsi_cache

    ALL_TF = ["15m", "1h", "4h", "1d"]

    parser = argparse.ArgumentParser(description="TrendBreak Pro — Trendline Breakout Scanner")
    parser.add_argument(
        "--timeframe", "-tf",
        choices=["15m", "1h", "4h", "1d", "all"],
        default=_os.environ.get("SCAN_TIMEFRAME", "1d"),
        help=(
            "Candle timeframe: 15m | 1h | 4h | 1d | all\n"
            "  all → runs all 4 timeframes in one go, generates one report per TF\n"
            "        plus a combined index.html linking them all  (default: 1d)"
        )
    )
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Skip freshness check and market-hours gate — always run a full scan"
    )
    args = parser.parse_args()

    scan_time = datetime.now().strftime("%d %b %Y  %H:%M:%S")

    print(f"\nTrendBreak Pro v3  ·  {len(NSE_STOCKS)+len(NYSE_STOCKS)} stocks  ·  20 trendline types  ·  {scan_time}")
    print(f"  16 fixes applied — see file header for changelog")

    # ── Market-hours gate: decide which exchanges to scan ──────────────────────
    nse_open, nyse_open = market_status()

    if args.force:
        nse_open = nyse_open = True
        print("  ⚡  --force flag set — scanning both NSE + NYSE regardless of market hours\n")
    else:
        if not nse_open and not nyse_open:
            print("  ⏸  Both NSE and NYSE are currently closed — nothing to scan.")
            print("     NSE  : Mon–Fri  09:15–15:30 IST")
            print("     NYSE : Mon–Fri  09:00–19:00 ET")
            print("     Run with --force to scan anyway.\n")
            sys.exit(0)
        if nse_open:
            print(f"  ✅  NSE is OPEN  (09:15–15:30 IST) → scanning {len(NSE_STOCKS)} NSE stocks")
        else:
            print(f"  🔒  NSE is CLOSED → skipping NSE stocks entirely")
        if nyse_open:
            print(f"  ✅  NYSE is OPEN (09:00–19:00 ET)  → scanning {len(NYSE_STOCKS)} NYSE stocks")
        else:
            print(f"  🔒  NYSE is CLOSED → skipping NYSE stocks entirely")
        print()

    nse_to_scan  = NSE_STOCKS  if nse_open  else []
    nyse_to_scan = NYSE_STOCKS if nyse_open else []

    # ── Decide which timeframes to run ────────────────────────────────────────
    if args.timeframe == "all":
        timeframes_to_run = ALL_TF
        print(f"  ⏱  Running ALL 4 timeframes: {' | '.join(TIMEFRAME_CONFIG[t][3] for t in timeframes_to_run)}")
        print(f"     Each TF fetches its own data — 15m volume ≠ 1d volume ✓\n")
    else:
        timeframes_to_run = [args.timeframe]
        print(f"  ⏱  Timeframe: {TIMEFRAME_CONFIG[args.timeframe][3]}\n")

    # ── Run each timeframe ────────────────────────────────────────────────────
    tf_reports = []   # (tf, tf_label, out_path, n_bull, n_bear, n_vol, n_total)

    for tf in timeframes_to_run:
        all_results, vol_spikes, out_path, tf_label = run_single_timeframe(
            tf, nse_to_scan, nyse_to_scan, scan_time, force=args.force
        )
        bull  = [r for r in all_results if r["signal"] == "BULLISH"]
        bear  = [r for r in all_results if r["signal"] == "BEARISH"]
        vol_c = [r for r in all_results if r.get("vol_confirmed")]
        tf_reports.append((tf, tf_label, out_path, len(bull), len(bear), len(vol_c), len(all_results)))

        # Telegram alerts per timeframe
        tg = _tg_cfg()
        if tg:
            print(f"    Sending Telegram alerts [{tf_label}]…", end="", flush=True)
            tg_send_breakout_alerts(all_results, tf_label, scan_time)
            tg_send_volume_spike_alerts(vol_spikes, tf_label, scan_time)
            print(" ✅ Sent")

    # ── If multi-TF, write a combined index page ───────────────────────────────
    if len(timeframes_to_run) > 1:
        idx_path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)),
                                 "trendline_breakout_ALL_index.html")
        idx_html = generate_combined_index(tf_reports, scan_time)
        with open(idx_path, "w", encoding="utf-8") as f:
            f.write(idx_html)
        print(f"\n  ✅  All {len(timeframes_to_run)} timeframes complete.")
        print(f"  📄  Combined index → {idx_path}")
        for tf, tf_label, out_path, *_ in tf_reports:
            print(f"      [{tf_label:>6}]  {out_path}")
    else:
        tf, tf_label, out_path, *_ = tf_reports[0]
        # Telegram status for single-TF run
        tg = _tg_cfg()
        if not tg:
            cfg_tg = CONFIG.get("telegram", {})
            if not cfg_tg.get("enabled", False):
                print("  ℹ️  Telegram alerts disabled in config.json")
            elif cfg_tg.get("bot_token","") in ("","YOUR_BOT_TOKEN_HERE") or \
                 str(cfg_tg.get("chat_id","")) in ("","YOUR_CHAT_ID_HERE"):
                print("  ⚠️  Telegram not configured — fill bot_token & chat_id in config.json")

    print()

if __name__ == "__main__":
    main()
