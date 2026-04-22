#!/usr/bin/env python3
"""
NSE Sector Rotation & Outlook Report Generator
================================================
Generates a daily HTML sector report with:
  - Relative Rotation Graph (RRG) scatter plot
  - Sector rotation trail plot (weekly movement)
  - Sector outlook table with detailed analysis

Usage:
    python sector_report_generator.py
    python sector_report_generator.py -o ./sector_reports/

Requirements:
    pip install yfinance pandas numpy
"""

import os
import sys
import math
import argparse
import shutil
from datetime import datetime, timedelta

try:
    import yfinance as yf
except ImportError:
    os.system(f"{sys.executable} -m pip install yfinance")
    import yfinance as yf

try:
    import pandas as pd
except ImportError:
    os.system(f"{sys.executable} -m pip install pandas")
    import pandas as pd

try:
    import numpy as np
except ImportError:
    os.system(f"{sys.executable} -m pip install numpy")
    import numpy as np


# ─────────────────────────────────────────────────────────────────────────────
# NSE SECTOR INDICES — All tradable sectors on NSE
# ─────────────────────────────────────────────────────────────────────────────

BENCHMARK_SYMBOL = "^NSEI"  # Nifty 50
BENCHMARK_NAME = "NIFTY 50"

NSE_SECTORS = {
    "Nifty Bank":             {"symbol": "^NSEBANK",              "desc": "Banking sector — SBI, HDFC Bank, ICICI Bank, Kotak, Axis etc."},
    "Nifty IT":               {"symbol": "^CNXIT",                "desc": "Information Technology — TCS, Infosys, Wipro, HCL Tech, Tech Mahindra etc."},
    "Nifty Auto":             {"symbol": "^CNXAUTO",              "desc": "Automobile & ancillaries — M&M, Tata Motors, Maruti, Bajaj Auto etc."},
    "Nifty FMCG":             {"symbol": "^CNXFMCG",             "desc": "Fast Moving Consumer Goods — HUL, ITC, Nestlé, Dabur, Britannia etc."},
    "Nifty Metal":            {"symbol": "^CNXMETAL",             "desc": "Metals & Mining — Tata Steel, JSW Steel, Hindalco, Vedanta etc."},
    "Nifty Pharma":           {"symbol": "^CNXPHARMA",            "desc": "Pharmaceuticals — Sun Pharma, Dr. Reddy's, Cipla, Lupin, Divis Labs etc."},
    "Nifty PSU Bank":         {"symbol": "^CNXPSUBANK",           "desc": "Public Sector Banks — SBI, PNB, Bank of Baroda, Canara Bank etc."},
    "Nifty Realty":           {"symbol": "^CNXREALTY",             "desc": "Real Estate — DLF, Godrej Properties, Oberoi Realty, Brigade etc."},
    "Nifty Media":            {"symbol": "^CNXMEDIA",             "desc": "Media & Entertainment — Zee, Sun TV, PVR INOX, Saregama etc."},
    "Nifty Energy":           {"symbol": "^CNXENERGY",            "desc": "Energy — Reliance, ONGC, NTPC, Power Grid, BPCL, IOC etc."},
    "Nifty Infra":            {"symbol": "^CNXINFRA",             "desc": "Infrastructure — L&T, Adani Ports, UltraTech, Bharti Airtel etc."},
    "Nifty Commodities":      {"symbol": "^CNXCMDT",              "desc": "Commodities — ONGC, Coal India, Tata Steel, UPL, Hindalco etc."},
    "Nifty MNC":              {"symbol": "^CNXMNC",               "desc": "Multinational Corporations — Maruti, HUL, Siemens, ABB, Honeywell etc."},
    "Nifty PSE":              {"symbol": "^CNXPSE",               "desc": "Public Sector Enterprises — NTPC, Coal India, BEL, HAL, ONGC etc."},
    "Nifty Fin Services":     {"symbol": "NIFTY_FIN_SERVICE.NS",  "desc": "Financial Services — Banks, NBFCs, Insurance, AMCs etc."},
    "Nifty Services":         {"symbol": "^CNXSERVICE",           "desc": "Services Sector — IT, Financial Services, Telecom, Hospitality etc."},
}


MARKET_CAP_INDICES = {
    "Nifty 50":         {"symbol": "^NSEI",     "desc": "Large Cap — Top 50 companies by market cap"},
    "Nifty 100":        {"symbol": "^CNX100",   "desc": "Large Cap — Top 100 companies"},
    "Nifty 200":        {"symbol": "^CNX200",   "desc": "Large + Mid Cap — Top 200 companies"},
    "Nifty Midcap 100": {"symbol": "^NSMIDCP",  "desc": "Mid Cap — Ranks 101-200 by market cap"},
    "Nifty Midcap 150": {"symbol": "^CRSMID",   "desc": "Mid Cap — 150 mid-sized companies"},
}

# Top 3 leaders per sector (by market cap weight) — NSE symbols
SECTOR_LEADERS = {
    "Nifty Bank":             ["HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS"],
    "Nifty IT":               ["TCS.NS", "INFY.NS", "HCLTECH.NS"],
    "Nifty Auto":             ["M&M.NS", "BAJAJ-AUTO.NS", "MARUTI.NS"],
    "Nifty FMCG":             ["HINDUNILVR.NS", "ITC.NS", "NESTLEIND.NS"],
    "Nifty Metal":            ["TATASTEEL.NS", "JSWSTEEL.NS", "HINDALCO.NS"],
    "Nifty Pharma":           ["SUNPHARMA.NS", "DRREDDY.NS", "CIPLA.NS"],
    "Nifty PSU Bank":         ["SBIN.NS", "PNB.NS", "BANKBARODA.NS"],
    "Nifty Realty":           ["DLF.NS", "GODREJPROP.NS", "OBEROIRLTY.NS"],
    "Nifty Media":            ["ZEEL.NS", "SUNTV.NS", "PVRINOX.NS"],
    "Nifty Energy":           ["RELIANCE.NS", "ONGC.NS", "NTPC.NS"],
    "Nifty Infra":            ["LT.NS", "ADANIPORTS.NS", "ULTRACEMCO.NS"],
    "Nifty Commodities":      ["ONGC.NS", "COALINDIA.NS", "TATASTEEL.NS"],
    "Nifty MNC":              ["MARUTI.NS", "HINDUNILVR.NS", "SIEMENS.NS"],
    "Nifty PSE":              ["NTPC.NS", "COALINDIA.NS", "BEL.NS"],
    "Nifty Fin Services":     ["HDFCBANK.NS", "ICICIBANK.NS", "BAJFINANCE.NS"],
    "Nifty Services":         ["TCS.NS", "HDFCBANK.NS", "BHARTIARTL.NS"],
}


# ─────────────────────────────────────────────────────────────────────────────
# DATA FETCHING
# ─────────────────────────────────────────────────────────────────────────────

def fetch_index_history(symbol, period="1y", interval="1d"):
    """Fetch historical data for an index from yfinance."""
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=period, interval=interval)
        if hist is not None and not hist.empty:
            return hist
    except Exception as e:
        print(f"    ⚠ Error fetching {symbol}: {e}")
    return None


def fetch_stock_returns(symbol):
    """Fetch 1W, 1M, 1Y returns for a single stock."""
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="13mo")
        if hist is None or hist.empty or len(hist) < 2:
            return None
        close = hist["Close"]
        current = close.iloc[-1]
        info = ticker.info or {}
        name = info.get("shortName", symbol.replace(".NS", ""))

        returns = {}
        for label, days in [("1W", 5), ("1M", 21), ("1Y", 252)]:
            if len(close) > days:
                returns[label] = ((current / close.iloc[-(days + 1)]) - 1) * 100
            else:
                returns[label] = None

        return {"symbol": symbol, "name": name, "price": current, "returns": returns}
    except Exception:
        return None


def compute_rs_ratio_momentum(sector_hist, benchmark_hist, window=10):
    """
    Compute Relative Strength (RS) Ratio and RS Momentum for RRG.
    RS-Ratio = rolling ratio of sector to benchmark, normalized to 100
    RS-Momentum = rate of change of RS-Ratio
    """
    if sector_hist is None or benchmark_hist is None:
        return None, None, None, None

    sector_close = sector_hist["Close"].dropna()
    bench_close = benchmark_hist["Close"].dropna()

    common_idx = sector_close.index.intersection(bench_close.index)
    if len(common_idx) < window * 4:
        return None, None, None, None

    sector_close = sector_close.loc[common_idx]
    bench_close = bench_close.loc[common_idx]

    rs_raw = (sector_close / bench_close) * 100

    rs_sma = rs_raw.rolling(window=window).mean()
    rs_ratio = (rs_raw / rs_sma) * 100

    rs_momentum = rs_ratio - rs_ratio.shift(window)
    rs_momentum = rs_momentum + 100

    rs_ratio_current = rs_ratio.iloc[-1] if not rs_ratio.empty else None
    rs_momentum_current = rs_momentum.iloc[-1] if not rs_momentum.empty else None

    rs_ratio_prev = rs_ratio.iloc[-6] if len(rs_ratio) >= 6 else (rs_ratio.iloc[-2] if len(rs_ratio) >= 2 else None)
    rs_momentum_prev = rs_momentum.iloc[-6] if len(rs_momentum) >= 6 else (rs_momentum.iloc[-2] if len(rs_momentum) >= 2 else None)

    return rs_ratio_current, rs_momentum_current, rs_ratio_prev, rs_momentum_prev


def compute_sector_metrics(sector_hist, benchmark_hist):
    """Compute comprehensive metrics for a sector."""
    if sector_hist is None or sector_hist.empty:
        return {}

    close = sector_hist["Close"]
    current_price = close.iloc[-1]

    returns = {}
    for label, days in [("1D", 1), ("1W", 5), ("1M", 21), ("3M", 63), ("6M", 126), ("1Y", 252)]:
        if len(close) > days:
            ret = ((current_price / close.iloc[-days - 1]) - 1) * 100
            returns[label] = ret
        else:
            returns[label] = None

    high_52w = close.tail(252).max() if len(close) >= 252 else close.max()
    low_52w = close.tail(252).min() if len(close) >= 252 else close.min()
    pct_from_high = ((current_price / high_52w) - 1) * 100 if high_52w else 0
    pct_from_low = ((current_price / low_52w) - 1) * 100 if low_52w else 0

    sma_20 = close.rolling(20).mean().iloc[-1] if len(close) >= 20 else None
    sma_50 = close.rolling(50).mean().iloc[-1] if len(close) >= 50 else None
    sma_200 = close.rolling(200).mean().iloc[-1] if len(close) >= 200 else None

    above_20 = current_price > sma_20 if sma_20 else None
    above_50 = current_price > sma_50 if sma_50 else None
    above_200 = current_price > sma_200 if sma_200 else None

    daily_returns = close.pct_change().dropna()
    volatility_30d = daily_returns.tail(30).std() * (252 ** 0.5) * 100 if len(daily_returns) >= 30 else None

    rs_vs_bench = None
    if benchmark_hist is not None and not benchmark_hist.empty:
        bench_close = benchmark_hist["Close"]
        common = close.index.intersection(bench_close.index)
        if len(common) > 21:
            s_ret = (close.loc[common].iloc[-1] / close.loc[common].iloc[-22] - 1) * 100
            b_ret = (bench_close.loc[common].iloc[-1] / bench_close.loc[common].iloc[-22] - 1) * 100
            rs_vs_bench = s_ret - b_ret

    return {
        "current_price": current_price,
        "returns": returns,
        "high_52w": high_52w,
        "low_52w": low_52w,
        "pct_from_high": pct_from_high,
        "pct_from_low": pct_from_low,
        "sma_20": sma_20,
        "sma_50": sma_50,
        "sma_200": sma_200,
        "above_20": above_20,
        "above_50": above_50,
        "above_200": above_200,
        "volatility_30d": volatility_30d,
        "rs_vs_benchmark": rs_vs_bench,
    }


def get_rrg_trail(sector_hist, benchmark_hist, window=14, trail_length=5):
    """
    Get the trail of RS-Ratio and RS-Momentum points for rotation plot.
    Uses weekly (5-day) smoothed samples spaced 2 weeks apart for clean trails.
    """
    if sector_hist is None or benchmark_hist is None:
        return []

    sector_close = sector_hist["Close"].dropna()
    bench_close = benchmark_hist["Close"].dropna()
    common_idx = sector_close.index.intersection(bench_close.index)
    if len(common_idx) < window * 6:
        return []

    sector_close = sector_close.loc[common_idx]
    bench_close = bench_close.loc[common_idx]

    rs_raw = (sector_close / bench_close) * 100
    rs_sma = rs_raw.rolling(window=window).mean()
    rs_ratio = (rs_raw / rs_sma) * 100
    rs_momentum = (rs_ratio - rs_ratio.shift(window)) + 100

    # Smooth with a 5-day average to reduce daily noise
    rs_ratio_smooth = rs_ratio.rolling(window=5, min_periods=3).mean()
    rs_momentum_smooth = rs_momentum.rolling(window=5, min_periods=3).mean()

    combined = pd.DataFrame({"ratio": rs_ratio_smooth, "momentum": rs_momentum_smooth}).dropna()
    if len(combined) < trail_length * 10:
        return []

    step = 10  # ~2 weeks between trail points
    trail = []
    for i in range(trail_length, 0, -1):
        idx = -1 - (i - 1) * step
        if abs(idx) <= len(combined):
            row = combined.iloc[idx]
            trail.append((row["ratio"], row["momentum"]))

    return trail


def classify_quadrant(rs_ratio, rs_momentum):
    """Classify sector into RRG quadrant."""
    if rs_ratio is None or rs_momentum is None:
        return "Unknown"
    if rs_ratio >= 100 and rs_momentum >= 100:
        return "Leading"
    elif rs_ratio < 100 and rs_momentum >= 100:
        return "Improving"
    elif rs_ratio < 100 and rs_momentum < 100:
        return "Lagging"
    else:
        return "Weakening"


def get_trend_signal(metrics):
    """Determine trend signal from moving averages."""
    above_20 = metrics.get("above_20")
    above_50 = metrics.get("above_50")
    above_200 = metrics.get("above_200")

    score = sum(1 for x in [above_20, above_50, above_200] if x is True)

    if score == 3:
        return "Strong Uptrend", "green"
    elif score == 2:
        return "Uptrend", "green"
    elif score == 1:
        return "Neutral", "amber"
    else:
        return "Downtrend", "red"


def generate_sector_outlook(name, sector_info, metrics, quadrant, rs_ratio, rs_momentum):
    """Generate detailed textual outlook for a sector."""
    trend, _ = get_trend_signal(metrics)
    returns = metrics.get("returns", {})
    r1m = returns.get("1M")
    r3m = returns.get("3M")
    r6m = returns.get("6M")
    pct_high = metrics.get("pct_from_high", 0)
    vol = metrics.get("volatility_30d")
    rs = metrics.get("rs_vs_benchmark")

    reasons = []

    if quadrant == "Leading":
        reasons.append(f"Sector is in the <b>Leading</b> quadrant — both relative strength and momentum vs {BENCHMARK_NAME} are above average.")
    elif quadrant == "Improving":
        reasons.append(f"Sector is in the <b>Improving</b> quadrant — momentum is picking up though relative strength is still below {BENCHMARK_NAME}.")
    elif quadrant == "Weakening":
        reasons.append(f"Sector is in the <b>Weakening</b> quadrant — while relative strength is still above average, momentum is fading.")
    elif quadrant == "Lagging":
        reasons.append(f"Sector is in the <b>Lagging</b> quadrant — both relative strength and momentum are below {BENCHMARK_NAME}.")

    if trend == "Strong Uptrend":
        reasons.append("Price is above all key moving averages (20/50/200 DMA) — strongly bullish structure.")
    elif trend == "Uptrend":
        reasons.append("Price is above most moving averages — bullish structure intact.")
    elif trend == "Neutral":
        reasons.append("Mixed moving average signals — trend is indecisive.")
    else:
        reasons.append("Price is below key moving averages — bearish structure.")

    if r1m is not None:
        if r1m > 5:
            reasons.append(f"Strong 1-month return of <b>{r1m:+.1f}%</b> shows near-term strength.")
        elif r1m < -5:
            reasons.append(f"Weak 1-month return of <b>{r1m:+.1f}%</b> indicates near-term pressure.")

    if r3m is not None and r1m is not None:
        if r3m > 0 and r1m > 0:
            reasons.append("Positive returns across both 1M and 3M timeframes show sustained momentum.")
        elif r3m < 0 and r1m < 0:
            reasons.append("Negative returns across both 1M and 3M periods — persistent weakness.")

    if pct_high is not None:
        if pct_high > -3:
            reasons.append(f"Trading near 52-week high ({pct_high:+.1f}% from peak) — strong relative positioning.")
        elif pct_high < -20:
            reasons.append(f"Significantly off 52-week high ({pct_high:+.1f}%) — potential value zone or structural weakness.")

    if rs is not None:
        if rs > 2:
            reasons.append(f"Outperforming {BENCHMARK_NAME} by <b>{rs:+.1f}%</b> over the past month.")
        elif rs < -2:
            reasons.append(f"Underperforming {BENCHMARK_NAME} by <b>{rs:.1f}%</b> over the past month.")

    if vol is not None:
        if vol > 30:
            reasons.append(f"Elevated 30-day annualized volatility of {vol:.0f}% — higher risk.")
        elif vol < 15:
            reasons.append(f"Low volatility ({vol:.0f}% annualized) — stable price action.")

    # Overall verdict
    bullish_score = 0
    if quadrant in ("Leading", "Improving"):
        bullish_score += 2
    if trend in ("Strong Uptrend", "Uptrend"):
        bullish_score += 2
    if r1m and r1m > 0:
        bullish_score += 1
    if r3m and r3m > 0:
        bullish_score += 1
    if rs and rs > 0:
        bullish_score += 1

    if bullish_score >= 5:
        verdict = "Bullish"
        verdict_color = "green"
    elif bullish_score >= 3:
        verdict = "Moderately Bullish"
        verdict_color = "green"
    elif bullish_score >= 2:
        verdict = "Neutral"
        verdict_color = "amber"
    elif bullish_score >= 1:
        verdict = "Moderately Bearish"
        verdict_color = "amber"
    else:
        verdict = "Bearish"
        verdict_color = "red"

    return {
        "verdict": verdict,
        "verdict_color": verdict_color,
        "reasons": reasons,
        "trend": trend,
        "quadrant": quadrant,
    }


# ─────────────────────────────────────────────────────────────────────────────
# SVG CHART GENERATION
# ─────────────────────────────────────────────────────────────────────────────

QUADRANT_COLORS = {
    "Leading": "#00e5a0",
    "Improving": "#3d9cf5",
    "Lagging": "#ff4d6d",
    "Weakening": "#f5a623",
}

SECTOR_DOT_COLORS = [
    "#00e5a0", "#3d9cf5", "#ff4d6d", "#f5a623", "#9b7fff",
    "#e879f9", "#22d3ee", "#fb923c", "#a3e635", "#f472b6",
    "#818cf8", "#34d399", "#fbbf24", "#ef4444", "#06b6d4",
    "#8b5cf6", "#10b981", "#f97316", "#ec4899",
]


def compute_shared_spread(sectors_data):
    """Compute a shared axis spread for both RRG scatter and trail plots."""
    all_vals = []

    for s in sectors_data:
        if s.get("rs_ratio") is not None:
            all_vals.append(abs(s["rs_ratio"] - 100))
        if s.get("rs_momentum") is not None:
            all_vals.append(abs(s["rs_momentum"] - 100))
        for r, m in (s.get("trail") or []):
            if not (math.isnan(r) or math.isnan(m)):
                all_vals.append(abs(r - 100))
                all_vals.append(abs(m - 100))

    return max(max(all_vals) if all_vals else 2, 2) * 1.15


def generate_rrg_scatter_svg(sectors_data, spread=None, width=1200, height=660):
    """
    Generate Relative Rotation Graph (RRG) scatter plot as inline SVG.
    X-axis: RS-Ratio, Y-axis: RS-Momentum, center at (100,100).
    """
    pad = 80
    chart_w = width - 2 * pad
    chart_h = height - 2 * pad

    all_ratios = [s["rs_ratio"] for s in sectors_data if s["rs_ratio"] is not None]
    all_momenta = [s["rs_momentum"] for s in sectors_data if s["rs_momentum"] is not None]

    if not all_ratios or not all_momenta:
        return f'<svg viewBox="0 0 {width} {height}"><text x="{width//2}" y="{height//2}" text-anchor="middle" fill="#5c5d6e" font-family="Fira Code,monospace" font-size="14">Insufficient data for RRG</text></svg>'

    if spread is None:
        spread = compute_shared_spread(sectors_data)

    x_min, x_max = 100 - spread, 100 + spread
    y_min, y_max = 100 - spread, 100 + spread

    def sx(v):
        return pad + ((v - x_min) / (x_max - x_min)) * chart_w

    def sy(v):
        return pad + ((y_max - v) / (y_max - y_min)) * chart_h

    cx, cy = sx(100), sy(100)

    svg = f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" style="width:100%;">\n'

    # Quadrant fills
    svg += f'  <rect x="{cx}" y="{pad}" width="{sx(x_max) - cx}" height="{cy - pad}" fill="rgba(0,229,160,0.04)" />\n'
    svg += f'  <rect x="{pad}" y="{pad}" width="{cx - pad}" height="{cy - pad}" fill="rgba(61,156,245,0.04)" />\n'
    svg += f'  <rect x="{pad}" y="{cy}" width="{cx - pad}" height="{sy(y_min) - cy}" fill="rgba(255,77,109,0.04)" />\n'
    svg += f'  <rect x="{cx}" y="{cy}" width="{sx(x_max) - cx}" height="{sy(y_min) - cy}" fill="rgba(245,166,35,0.04)" />\n'

    # Quadrant labels
    svg += f'  <text x="{cx + (sx(x_max) - cx)/2}" y="{pad + 22}" text-anchor="middle" font-family="Fira Code,monospace" font-size="11" fill="rgba(0,229,160,0.5)" font-weight="600">LEADING</text>\n'
    svg += f'  <text x="{pad + (cx - pad)/2}" y="{pad + 22}" text-anchor="middle" font-family="Fira Code,monospace" font-size="11" fill="rgba(61,156,245,0.5)" font-weight="600">IMPROVING</text>\n'
    svg += f'  <text x="{pad + (cx - pad)/2}" y="{sy(y_min) - 10}" text-anchor="middle" font-family="Fira Code,monospace" font-size="11" fill="rgba(255,77,109,0.5)" font-weight="600">LAGGING</text>\n'
    svg += f'  <text x="{cx + (sx(x_max) - cx)/2}" y="{sy(y_min) - 10}" text-anchor="middle" font-family="Fira Code,monospace" font-size="11" fill="rgba(245,166,35,0.5)" font-weight="600">WEAKENING</text>\n'

    # Grid lines
    for v in np.arange(math.floor(x_min), math.ceil(x_max) + 1, max(1, round(spread / 4))):
        x = sx(v)
        if pad < x < width - pad:
            opacity = "0.12" if v == 100 else "0.04"
            sw = "1.5" if v == 100 else "0.5"
            svg += f'  <line x1="{x:.1f}" y1="{pad}" x2="{x:.1f}" y2="{height - pad}" stroke="rgba(255,255,255,{opacity})" stroke-width="{sw}"/>\n'
            if v != 100:
                svg += f'  <text x="{x:.1f}" y="{height - pad + 18}" text-anchor="middle" font-family="Fira Code,monospace" font-size="9" fill="#5c5d6e">{v:.0f}</text>\n'

    for v in np.arange(math.floor(y_min), math.ceil(y_max) + 1, max(1, round(spread / 4))):
        y = sy(v)
        if pad < y < height - pad:
            opacity = "0.12" if v == 100 else "0.04"
            sw = "1.5" if v == 100 else "0.5"
            svg += f'  <line x1="{pad}" y1="{y:.1f}" x2="{width - pad}" y2="{y:.1f}" stroke="rgba(255,255,255,{opacity})" stroke-width="{sw}"/>\n'
            if v != 100:
                svg += f'  <text x="{pad - 8}" y="{y + 3:.1f}" text-anchor="end" font-family="Fira Code,monospace" font-size="9" fill="#5c5d6e">{v:.0f}</text>\n'

    # Axis labels
    svg += f'  <text x="{width // 2}" y="{height - 10}" text-anchor="middle" font-family="Fira Code,monospace" font-size="10" fill="#9899a8" font-weight="600">RS-RATIO →</text>\n'
    svg += f'  <text x="14" y="{height // 2}" text-anchor="middle" font-family="Fira Code,monospace" font-size="10" fill="#9899a8" font-weight="600" transform="rotate(-90 14 {height // 2})">RS-MOMENTUM →</text>\n'

    # Sector dots
    for i, s in enumerate(sectors_data):
        if s["rs_ratio"] is None or s["rs_momentum"] is None:
            continue
        x = sx(s["rs_ratio"])
        y = sy(s["rs_momentum"])
        color = SECTOR_DOT_COLORS[i % len(SECTOR_DOT_COLORS)]
        svg += f'  <circle cx="{x:.1f}" cy="{y:.1f}" r="7" fill="{color}" stroke="#08090d" stroke-width="2" opacity="0.9"/>\n'
        svg += f'  <circle cx="{x:.1f}" cy="{y:.1f}" r="7" fill="none" stroke="{color}" stroke-width="0.5" opacity="0.4">\n'
        svg += f'    <animate attributeName="r" from="7" to="16" dur="2s" repeatCount="indefinite" />\n'
        svg += f'    <animate attributeName="opacity" from="0.4" to="0" dur="2s" repeatCount="indefinite" />\n'
        svg += f'  </circle>\n'

        label = s["name"].replace("Nifty ", "")
        label_x = x + 12
        label_y = y - 10
        if label_x + len(label) * 5.5 > width - pad:
            label_x = x - 12
            svg += f'  <text x="{label_x:.1f}" y="{label_y:.1f}" text-anchor="end" font-family="Fira Code,monospace" font-size="8" fill="{color}" font-weight="500">{label}</text>\n'
        else:
            svg += f'  <text x="{label_x:.1f}" y="{label_y:.1f}" text-anchor="start" font-family="Fira Code,monospace" font-size="8" fill="{color}" font-weight="500">{label}</text>\n'

    svg += '</svg>'
    return svg


def generate_rotation_trail_svg(sectors_data, spread=None, width=1200, height=660):
    """
    Generate a clean sector rotation trail plot.
    Each sector shows a smooth dotted path from its oldest trail point to the current
    position, with an arrowhead at the end and a single label — no intermediate dots.
    """
    pad = 80
    chart_w = width - 2 * pad
    chart_h = height - 2 * pad

    valid = [s for s in sectors_data if s.get("trail") and len(s["trail"]) >= 2]
    if not valid:
        return f'<svg viewBox="0 0 {width} {height}"><text x="{width//2}" y="{height//2}" text-anchor="middle" fill="#5c5d6e" font-family="Fira Code,monospace" font-size="14">Insufficient trail data</text></svg>'

    if spread is None:
        spread = compute_shared_spread(sectors_data)

    x_min, x_max = 100 - spread, 100 + spread
    y_min, y_max = 100 - spread, 100 + spread

    def sx(v):
        return pad + ((v - x_min) / (x_max - x_min)) * chart_w

    def sy(v):
        return pad + ((y_max - v) / (y_max - y_min)) * chart_h

    cx, cy = sx(100), sy(100)

    svg = f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" style="width:100%;">\n'
    svg += '  <defs>\n'
    for idx_s, s in enumerate(valid):
        i = sectors_data.index(s)
        color = SECTOR_DOT_COLORS[i % len(SECTOR_DOT_COLORS)]
        svg += f'    <marker id="trailArrow{idx_s}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto"><path d="M 0 1 L 8 5 L 0 9 z" fill="{color}" opacity="0.5"/></marker>\n'
    svg += '  </defs>\n'

    # Quadrant fills
    svg += f'  <rect x="{cx}" y="{pad}" width="{sx(x_max) - cx}" height="{cy - pad}" fill="rgba(0,229,160,0.04)" />\n'
    svg += f'  <rect x="{pad}" y="{pad}" width="{cx - pad}" height="{cy - pad}" fill="rgba(61,156,245,0.04)" />\n'
    svg += f'  <rect x="{pad}" y="{cy}" width="{cx - pad}" height="{sy(y_min) - cy}" fill="rgba(255,77,109,0.04)" />\n'
    svg += f'  <rect x="{cx}" y="{cy}" width="{sx(x_max) - cx}" height="{sy(y_min) - cy}" fill="rgba(245,166,35,0.04)" />\n'

    # Quadrant labels
    svg += f'  <text x="{cx + (sx(x_max) - cx)/2}" y="{pad + 22}" text-anchor="middle" font-family="Fira Code,monospace" font-size="11" fill="rgba(0,229,160,0.5)" font-weight="600">LEADING</text>\n'
    svg += f'  <text x="{pad + (cx - pad)/2}" y="{pad + 22}" text-anchor="middle" font-family="Fira Code,monospace" font-size="11" fill="rgba(61,156,245,0.5)" font-weight="600">IMPROVING</text>\n'
    svg += f'  <text x="{pad + (cx - pad)/2}" y="{sy(y_min) - 10}" text-anchor="middle" font-family="Fira Code,monospace" font-size="11" fill="rgba(255,77,109,0.5)" font-weight="600">LAGGING</text>\n'
    svg += f'  <text x="{cx + (sx(x_max) - cx)/2}" y="{sy(y_min) - 10}" text-anchor="middle" font-family="Fira Code,monospace" font-size="11" fill="rgba(245,166,35,0.5)" font-weight="600">WEAKENING</text>\n'

    # Grid
    for v in np.arange(math.floor(x_min), math.ceil(x_max) + 1, max(1, round(spread / 4))):
        x = sx(v)
        if pad < x < width - pad:
            opacity = "0.12" if v == 100 else "0.04"
            sw = "1.5" if v == 100 else "0.5"
            svg += f'  <line x1="{x:.1f}" y1="{pad}" x2="{x:.1f}" y2="{height - pad}" stroke="rgba(255,255,255,{opacity})" stroke-width="{sw}"/>\n'

    for v in np.arange(math.floor(y_min), math.ceil(y_max) + 1, max(1, round(spread / 4))):
        y = sy(v)
        if pad < y < height - pad:
            opacity = "0.12" if v == 100 else "0.04"
            sw = "1.5" if v == 100 else "0.5"
            svg += f'  <line x1="{pad}" y1="{y:.1f}" x2="{width - pad}" y2="{y:.1f}" stroke="rgba(255,255,255,{opacity})" stroke-width="{sw}"/>\n'

    svg += f'  <text x="{width // 2}" y="{height - 10}" text-anchor="middle" font-family="Fira Code,monospace" font-size="10" fill="#9899a8" font-weight="600">RS-RATIO →</text>\n'
    svg += f'  <text x="14" y="{height // 2}" text-anchor="middle" font-family="Fira Code,monospace" font-size="10" fill="#9899a8" font-weight="600" transform="rotate(-90 14 {height // 2})">RS-MOMENTUM →</text>\n'

    # Collect final positions for label collision avoidance
    final_positions = []

    # Draw trails — one smooth dotted polyline + start dot + end dot per sector
    for idx_s, s in enumerate(valid):
        i = sectors_data.index(s)
        color = SECTOR_DOT_COLORS[i % len(SECTOR_DOT_COLORS)]
        trail = [(r, m) for r, m in s["trail"] if not (math.isnan(r) or math.isnan(m))]
        if len(trail) < 2:
            continue

        pts = [(sx(r), sy(m)) for r, m in trail]

        # Faint start dot (oldest position)
        svg += f'  <circle cx="{pts[0][0]:.1f}" cy="{pts[0][1]:.1f}" r="2.5" fill="{color}" opacity="0.15"/>\n'

        # Smooth dotted polyline for the trail
        points_str = " ".join(f"{px:.1f},{py:.1f}" for px, py in pts)
        svg += f'  <polyline points="{points_str}" fill="none" stroke="{color}" stroke-width="1" stroke-dasharray="4,4" opacity="0.35" stroke-linejoin="round" stroke-linecap="round" marker-end="url(#trailArrow{idx_s})"/>\n'

        # Solid end dot (current position)
        ex, ey = pts[-1]
        svg += f'  <circle cx="{ex:.1f}" cy="{ey:.1f}" r="5" fill="{color}" stroke="#08090d" stroke-width="1.5"/>\n'

        final_positions.append((ex, ey, i, s["name"].replace("Nifty ", ""), color))

    # Labels with basic collision nudging
    placed = []
    for ex, ey, i, label, color in final_positions:
        lx = ex + 10
        ly = ey - 6
        if lx + len(label) * 5.5 > width - pad:
            lx = ex - 10
            anchor = "end"
        else:
            anchor = "start"

        # Nudge vertically if too close to an already-placed label
        for plx, ply in placed:
            if abs(lx - plx) < 60 and abs(ly - ply) < 12:
                ly = ply + 13 if ly >= ply else ply - 13

        placed.append((lx, ly))
        svg += f'  <text x="{lx:.1f}" y="{ly:.1f}" text-anchor="{anchor}" font-family="Fira Code,monospace" font-size="8.5" fill="{color}" font-weight="500">{label}</text>\n'

    svg += '</svg>'
    return svg


def generate_performance_bar_svg(sectors_data, period="1M", width=720, height=None):
    """Generate horizontal bar chart of sector performance for a given period."""
    valid = [(s["name"], s["metrics"]["returns"].get(period)) for s in sectors_data if s["metrics"].get("returns", {}).get(period) is not None]
    valid.sort(key=lambda x: x[1], reverse=True)

    if not valid:
        return f'<svg viewBox="0 0 {width} 100"><text x="{width//2}" y="50" text-anchor="middle" fill="#5c5d6e" font-family="Fira Code,monospace" font-size="14">No performance data</text></svg>'

    bar_h = 28
    gap = 4
    pad_left = 170
    pad_right = 70
    pad_top = 10
    bar_area = width - pad_left - pad_right
    if height is None:
        height = pad_top + len(valid) * (bar_h + gap) + 10

    max_abs = max(abs(v) for _, v in valid) if valid else 1
    if max_abs == 0:
        max_abs = 1

    svg = f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" style="width:100%;">\n'

    zero_x = pad_left + bar_area * (max_abs / (2 * max_abs))
    svg += f'  <line x1="{zero_x:.1f}" y1="0" x2="{zero_x:.1f}" y2="{height}" stroke="rgba(255,255,255,0.08)" stroke-width="1" stroke-dasharray="3,3"/>\n'

    for i, (name, val) in enumerate(valid):
        y = pad_top + i * (bar_h + gap)
        bar_width = (abs(val) / max_abs) * (bar_area / 2)

        if val >= 0:
            bx = zero_x
            color = "#00e5a0"
            fill_opacity = "0.7"
        else:
            bx = zero_x - bar_width
            color = "#ff4d6d"
            fill_opacity = "0.7"

        svg += f'  <rect x="{bx:.1f}" y="{y:.1f}" width="{bar_width:.1f}" height="{bar_h}" rx="4" fill="{color}" opacity="{fill_opacity}"/>\n'

        label = name.replace("Nifty ", "")
        svg += f'  <text x="{pad_left - 8}" y="{y + bar_h/2 + 4:.1f}" text-anchor="end" font-family="Fira Code,monospace" font-size="10" fill="#9899a8">{label}</text>\n'

        val_x = (bx + bar_width + 8) if val >= 0 else (bx - 8)
        anchor = "start" if val >= 0 else "end"
        svg += f'  <text x="{val_x:.1f}" y="{y + bar_h/2 + 4:.1f}" text-anchor="{anchor}" font-family="Fira Code,monospace" font-size="10" fill="{color}" font-weight="600">{val:+.1f}%</text>\n'

    svg += '</svg>'
    return svg


# ─────────────────────────────────────────────────────────────────────────────
# HTML REPORT GENERATION
# ─────────────────────────────────────────────────────────────────────────────

def generate_html_report(sectors_data, benchmark_metrics, today_str, mktcap_data=None, leaders_data=None):
    """Generate the complete sector report HTML page."""

    if mktcap_data is None:
        mktcap_data = []
    if leaders_data is None:
        leaders_data = {}

    # Prepare summary counts
    quadrant_counts = {"Leading": 0, "Improving": 0, "Lagging": 0, "Weakening": 0}
    for s in sectors_data:
        q = s.get("quadrant", "Unknown")
        if q in quadrant_counts:
            quadrant_counts[q] += 1

    # Compute shared axis scale so both plots align
    shared_spread = compute_shared_spread(sectors_data)

    # Generate charts
    rrg_svg = generate_rrg_scatter_svg(sectors_data, spread=shared_spread)
    trail_svg = generate_rotation_trail_svg(sectors_data, spread=shared_spread)
    perf_1m_svg = generate_performance_bar_svg(sectors_data, "1M")
    perf_3m_svg = generate_performance_bar_svg(sectors_data, "3M")

    # Benchmark info
    bench_ret = benchmark_metrics.get("returns", {})
    bench_price = benchmark_metrics.get("current_price", 0)

    # Sector table rows
    table_rows = ""
    sorted_sectors = sorted(sectors_data, key=lambda s: (
        {"Leading": 0, "Improving": 1, "Weakening": 2, "Lagging": 3}.get(s.get("quadrant", ""), 4),
        -(s.get("metrics", {}).get("returns", {}).get("1M") or 0)
    ))

    for s in sorted_sectors:
        m = s.get("metrics", {})
        ret = m.get("returns", {})
        outlook = s.get("outlook", {})
        q = s.get("quadrant", "—")
        q_color = QUADRANT_COLORS.get(q, "#5c5d6e")
        trend = outlook.get("trend", "—")
        trend_color_name = get_trend_signal(m)[1] if m else "text3"
        trend_css = {"green": "var(--green)", "amber": "var(--amber)", "red": "var(--red)"}.get(trend_color_name, "var(--text2)")
        verdict = outlook.get("verdict", "—")
        v_color_name = outlook.get("verdict_color", "text2")
        v_css = {"green": "var(--green)", "amber": "var(--amber)", "red": "var(--red)"}.get(v_color_name, "var(--text2)")

        def fmt_ret(v):
            if v is None:
                return '<span style="color:var(--text3)">—</span>'
            color = "var(--green)" if v >= 0 else "var(--red)"
            return f'<span style="color:{color}">{v:+.1f}%</span>'

        r1d = fmt_ret(ret.get("1D"))
        r1w = fmt_ret(ret.get("1W"))
        r1m = fmt_ret(ret.get("1M"))
        r3m = fmt_ret(ret.get("3M"))
        r6m = fmt_ret(ret.get("6M"))

        pct_high = m.get("pct_from_high")
        pct_high_str = f'{pct_high:+.1f}%' if pct_high is not None else "—"

        vol = m.get("volatility_30d")
        vol_str = f'{vol:.0f}%' if vol is not None else "—"

        table_rows += f'''
        <tr>
          <td style="text-align:left;color:#fff;font-weight:600;">{s["name"].replace("Nifty ", "")}</td>
          <td><span style="color:{q_color};font-weight:600;">{q}</span></td>
          <td style="color:{trend_css}">{trend}</td>
          <td>{r1d}</td>
          <td>{r1w}</td>
          <td>{r1m}</td>
          <td>{r3m}</td>
          <td>{r6m}</td>
          <td style="color:var(--text2)">{pct_high_str}</td>
          <td style="color:var(--text2)">{vol_str}</td>
          <td style="color:{v_css};font-weight:600;">{verdict}</td>
        </tr>'''

    # Quadrant detail sections
    quadrant_detail_html = ""
    for quadrant_name in ["Leading", "Improving", "Weakening", "Lagging"]:
        q_sectors = [s for s in sectors_data if s.get("quadrant") == quadrant_name]
        if not q_sectors:
            continue

        q_color = QUADRANT_COLORS[quadrant_name]
        quadrant_descriptions = {
            "Leading": "These sectors have <b>strong relative strength AND rising momentum</b> vs Nifty 50. They are outperforming the benchmark and the outperformance is accelerating. These are the strongest sectors in the market — ideal for trend-following strategies. Sectors typically enter this quadrant from 'Improving' after sustained relative outperformance.",
            "Improving": "These sectors have <b>rising momentum but relative strength is still below average</b>. They were previously underperforming but are now gaining ground. This is where <b>early opportunities</b> emerge — sectors moving from Lagging to Improving are showing signs of a turnaround. If momentum sustains, they will rotate into the Leading quadrant.",
            "Weakening": "These sectors still have <b>above-average relative strength but momentum is declining</b>. They were previously leading but are starting to lose steam. This is a <b>caution zone</b> — while still relatively strong, the deceleration suggests the best of the move may be over. Without a momentum reversal, they will rotate into Lagging.",
            "Lagging": "These sectors have <b>weak relative strength AND declining momentum</b>. They are underperforming the benchmark and the underperformance is worsening. These are the weakest sectors — best avoided for fresh longs. However, when momentum starts improving (rotation toward Improving), it can signal a bottoming process.",
        }

        sector_cards = ""
        for s in q_sectors:
            outlook = s.get("outlook", {})
            reasons_html = "".join([f'<li>{r}</li>' for r in outlook.get("reasons", [])])
            rs_r = s.get("rs_ratio")
            rs_m = s.get("rs_momentum")
            rs_str = f'RS-Ratio: {rs_r:.2f} | RS-Momentum: {rs_m:.2f}' if rs_r and rs_m else ""
            v_color = outlook.get("verdict_color", "")
            v_css = {"green": "var(--green)", "amber": "var(--amber)", "red": "var(--red)"}.get(v_color, "var(--text2)")

            sector_cards += f'''
            <div class="sector-detail-card">
              <div class="sdc-header">
                <span class="sdc-name">{s["name"]}</span>
                <span class="sdc-verdict" style="color:{v_css}">{outlook.get("verdict", "—")}</span>
              </div>
              <div class="sdc-rs">{rs_str}</div>
              <div class="sdc-desc">{NSE_SECTORS.get(s["name"], {}).get("desc", "")}</div>
              <ul class="sdc-reasons">{reasons_html}</ul>
            </div>'''

        quadrant_detail_html += f'''
        <div class="quadrant-block" style="border-left:3px solid {q_color};">
          <h3 class="qb-title" style="color:{q_color};">
            <span class="qb-dot" style="background:{q_color};"></span>
            {quadrant_name} Quadrant
            <span class="qb-count">{len(q_sectors)} sector{"s" if len(q_sectors) != 1 else ""}</span>
          </h3>
          <p class="qb-desc">{quadrant_descriptions[quadrant_name]}</p>
          {sector_cards}
        </div>'''

    # Legend for the scatter plot
    legend_items = ""
    for i, s in enumerate(sectors_data):
        color = SECTOR_DOT_COLORS[i % len(SECTOR_DOT_COLORS)]
        label = s["name"].replace("Nifty ", "")
        q = s.get("quadrant", "—")
        legend_items += f'<span class="legend-item"><span class="legend-dot" style="background:{color};"></span>{label} <span class="legend-q" style="color:{QUADRANT_COLORS.get(q, "#5c5d6e")}">[{q}]</span></span>\n'

    perf_bar_height = 10 + len(sectors_data) * 32 + 10

    # Market cap indices table
    mktcap_rows = ""
    for mc in mktcap_data:
        m = mc.get("metrics", {})
        ret = m.get("returns", {})
        price = m.get("current_price", 0)

        def fmt_mc(v):
            if v is None:
                return '<span style="color:var(--text3)">—</span>'
            c = "var(--green)" if v >= 0 else "var(--red)"
            return f'<span style="color:{c}">{v:+.1f}%</span>'

        pct_high = m.get("pct_from_high")
        pct_high_str = f'{pct_high:+.1f}%' if pct_high is not None else "—"
        trend, trend_clr = get_trend_signal(m)
        trend_css = {"green": "var(--green)", "amber": "var(--amber)", "red": "var(--red)"}.get(trend_clr, "var(--text2)")

        mktcap_rows += f'''
        <tr>
          <td style="text-align:left;color:#fff;font-weight:600;">{mc["name"]}</td>
          <td style="color:var(--text2)">{price:,.0f}</td>
          <td>{fmt_mc(ret.get("1D"))}</td>
          <td>{fmt_mc(ret.get("1W"))}</td>
          <td>{fmt_mc(ret.get("1M"))}</td>
          <td>{fmt_mc(ret.get("3M"))}</td>
          <td>{fmt_mc(ret.get("6M"))}</td>
          <td>{fmt_mc(ret.get("1Y"))}</td>
          <td style="color:var(--text2)">{pct_high_str}</td>
          <td style="color:{trend_css}">{trend}</td>
        </tr>'''

    # Sector leaders HTML
    leaders_html = ""
    for s in sorted_sectors:
        sname = s["name"]
        stocks = leaders_data.get(sname, [])
        if not stocks:
            continue
        q = s.get("quadrant", "—")
        q_color = QUADRANT_COLORS.get(q, "#5c5d6e")

        stock_rows = ""
        for st in stocks:
            ret = st.get("returns", {})
            def fmt_sr(v):
                if v is None:
                    return '<span style="color:var(--text3)">—</span>'
                c = "var(--green)" if v >= 0 else "var(--red)"
                return f'<span style="color:{c}">{v:+.1f}%</span>'
            stock_rows += f'''
              <tr>
                <td style="text-align:left;color:#fff;">{st["name"]}</td>
                <td style="color:var(--text2)">₹{st["price"]:,.0f}</td>
                <td>{fmt_sr(ret.get("1W"))}</td>
                <td>{fmt_sr(ret.get("1M"))}</td>
                <td>{fmt_sr(ret.get("1Y"))}</td>
              </tr>'''

        leaders_html += f'''
        <div class="leader-block">
          <div class="lb-header">
            <span class="lb-name">{sname.replace("Nifty ", "")}</span>
            <span class="lb-quad" style="color:{q_color}">{q}</span>
          </div>
          <table class="leader-table">
            <thead><tr>
              <th style="text-align:left;">Stock</th>
              <th>Price</th><th>1W</th><th>1M</th><th>1Y</th>
            </tr></thead>
            <tbody>{stock_rows}</tbody>
          </table>
        </div>'''

    # ── Build Overview tab: S&P-style heatmap sector cards ─────────────────
    overview_cards_html = ""
    for s in sorted_sectors:
        m = s.get("metrics", {})
        ret = m.get("returns", {})
        outlook = s.get("outlook", {})
        r1m = ret.get("1M", 0) or 0
        q = s.get("quadrant", "—")
        q_color = QUADRANT_COLORS.get(q, "#5c5d6e")

        if r1m >= 10:
            card_bg, accent = "rgba(0,229,160,0.18)", "#00e5a0"
        elif r1m >= 3:
            card_bg, accent = "rgba(0,229,160,0.10)", "#00e5a0"
        elif r1m >= 0:
            card_bg, accent = "rgba(0,229,160,0.05)", "#4ade80"
        elif r1m >= -3:
            card_bg, accent = "rgba(245,166,35,0.08)", "#f5a623"
        elif r1m >= -10:
            card_bg, accent = "rgba(245,166,35,0.15)", "#f59e0b"
        else:
            card_bg, accent = "rgba(255,77,109,0.14)", "#ff4d6d"

        sname = s["name"]
        leaders = leaders_data.get(sname, [])
        leader_rows_ov = ""
        for st in leaders:
            st_ret = st.get("returns", {})
            def _fl(v):
                if v is None:
                    return '<span style="color:var(--text3)">—</span>'
                c = "var(--green)" if v >= 0 else "var(--red)"
                return f'<span style="color:{c}">{v:+.1f}%</span>'
            st_price = st.get("price", 0) or 0
            leader_rows_ov += f'''<tr>
              <td class="h-sym">{(st.get("name") or st["symbol"])[:22]}</td>
              <td class="h-mcap">\u20b9{st_price:,.0f}</td>
              <td class="h-ytd">{_fl(st_ret.get("1W"))}</td>
              <td class="h-ytd">{_fl(st_ret.get("1M"))}</td>
              <td class="h-ytd">{_fl(st_ret.get("1Y"))}</td>
            </tr>'''

        low = m.get("low_52w", 0) or 0
        high = m.get("high_52w", 0) or 0
        cur = m.get("current_price", 0) or 0
        range_pct = ((cur - low) / (high - low)) * 100 if high > low else 50

        r1d = ret.get("1D")
        r1w = ret.get("1W")
        r3m = ret.get("3M")
        vol = m.get("volatility_30d")
        verdict = outlook.get("verdict", "—")
        v_clr = outlook.get("verdict_color", "")
        _color_map = {"green": "#00e5a0", "amber": "#f5a623", "red": "#ff4d6d"}
        _css_map = {"green": "var(--green)", "amber": "var(--amber)", "red": "var(--red)"}
        v_css_ov = _color_map.get(v_clr, "#9899a8")
        trend_ov = outlook.get("trend", "—")
        trend_clr_ov = get_trend_signal(m)[1] if m else "text3"
        trend_css_ov = _css_map.get(trend_clr_ov, "var(--text2)")

        def _pc(v):
            return "positive" if v is not None and v >= 0 else ("negative" if v is not None else "neutral")
        def _sg(v):
            return "+" if v is not None and v >= 0 else ""

        rs_r = s.get("rs_ratio")
        rs_m = s.get("rs_momentum")
        rs_str = f"RS-Ratio: <b>{rs_r:.2f}</b> | RS-Momentum: <b>{rs_m:.2f}</b>" if rs_r and rs_m else "—"

        r1d_str = f"{_sg(r1d)}{r1d:.1f}%" if r1d is not None else "N/A"
        r1w_str = f"{_sg(r1w)}{r1w:.1f}%" if r1w is not None else "N/A"
        r3m_str = f"{_sg(r3m)}{r3m:.1f}%" if r3m is not None else "N/A"
        vol_str = f"{vol:.0f}%" if vol is not None else "N/A"
        sym_str = NSE_SECTORS.get(sname, {}).get("symbol", "")
        desc_str = NSE_SECTORS.get(sname, {}).get("desc", "")

        rs_r_val = rs_r if rs_r is not None else 0
        rs_m_val = rs_m if rs_m is not None else 0

        overview_cards_html += f"""
    <div class="sector-card fade-in" data-ret1m="{r1m:.2f}" data-vol="{vol if vol else 0}" data-rsratio="{rs_r_val:.2f}" data-rsmom="{rs_m_val:.2f}"
         style="--card-bg:{card_bg};--card-accent:{accent}" onclick="toggleExpand(this)">
      <div class="card-top">
        <div class="card-header">
          <div class="sector-name">{sname}</div>
          <div class="etf-ticker">{sym_str}</div>
        </div>
        <div class="ytd-badge {_pc(r1m)}">
          {_sg(r1m)}{r1m:.1f}%
        </div>
      </div>
      <div class="card-desc">{desc_str}</div>
      <div class="card-metrics">
        <div class="metric">
          <span class="metric-label">Quadrant</span>
          <span class="metric-value" style="color:{q_color}">{q}</span>
        </div>
        <div class="metric">
          <span class="metric-label">1D</span>
          <span class="metric-value {_pc(r1d)}">{r1d_str}</span>
        </div>
        <div class="metric">
          <span class="metric-label">1W</span>
          <span class="metric-value {_pc(r1w)}">{r1w_str}</span>
        </div>
        <div class="metric">
          <span class="metric-label">3M</span>
          <span class="metric-value {_pc(r3m)}">{r3m_str}</span>
        </div>
        <div class="metric">
          <span class="metric-label">Volatility</span>
          <span class="metric-value">{vol_str}</span>
        </div>
        <div class="metric rating" style="--r-color:{v_css_ov}">
          <span class="metric-label">Outlook</span>
          <span class="metric-value">{verdict}</span>
        </div>
      </div>
      <div class="expand-section">
        <div class="expand-block">
          <div class="expand-title">Top Leader Stocks</div>
          <table class="holdings-table">
            <thead><tr><th>Stock</th><th>Price</th><th>1W</th><th>1M</th><th>1Y</th></tr></thead>
            <tbody>{leader_rows_ov}</tbody>
          </table>
        </div>
        <div class="expand-block">
          <div class="expand-title">52-Week Price Range</div>
          <div class="range-track">
            <div class="range-fill" style="width:100%"></div>
            <div class="range-marker" style="left:{range_pct:.1f}%">
              <div class="marker-label">\u20b9{cur:,.0f}</div>
            </div>
          </div>
          <div class="range-labels">
            <span>\u20b9{low:,.0f}</span>
            <span>\u20b9{high:,.0f}</span>
          </div>
        </div>
        <div class="expand-block">
          <div class="expand-title">Relative Strength</div>
          <div style="font-family:var(--mono);font-size:10px;color:var(--text2);line-height:1.8;">
            {rs_str} | Trend: <b style="color:{trend_css_ov}">{trend_ov}</b>
          </div>
        </div>
      </div>
    </div>"""

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>NSE Sector Rotation Report · {today_str}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Fira+Code:wght@300;400;500;600;700&family=DM+Sans:ital,opsz,wght@0,9..40,100..1000;1,9..40,100..1000&display=swap" rel="stylesheet">
<style>
  :root {{
    --bg: #08090d; --bg2: #0d0e14; --bg3: #12131a; --bg4: #181922;
    --border: rgba(255,255,255,0.07); --border2: rgba(255,255,255,0.12);
    --green: #00e5a0; --green-dim: rgba(0,229,160,0.12);
    --red: #ff4d6d; --red-dim: rgba(255,77,109,0.12);
    --amber: #f5a623; --amber-dim: rgba(245,166,35,0.12);
    --blue: #3d9cf5; --blue-dim: rgba(61,156,245,0.12);
    --purple: #9b7fff;
    --text: #e8e9f0; --text2: #9899a8; --text3: #5c5d6e;
    --mono: 'Fira Code', monospace; --sans: 'DM Sans', sans-serif;
  }}
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  html {{ scroll-behavior:smooth; }}
  body {{ background: var(--bg); color: var(--text); font-family: var(--sans); font-size: 13px; line-height: 1.6; -webkit-font-smoothing: antialiased; }}
  ::-webkit-scrollbar {{ width: 4px; }} ::-webkit-scrollbar-track {{ background: var(--bg); }} ::-webkit-scrollbar-thumb {{ background: var(--border2); border-radius: 2px; }}
  .page {{ max-width: 1280px; margin: 0 auto; padding: 32px 24px; }}

  /* ── Header ────────────────────────────────────── */
  .report-header {{ padding:28px 32px; background:linear-gradient(135deg,#0f1018,#131420 60%,#0d1020); border:1px solid var(--border2); border-radius:16px; position:relative; overflow:hidden; margin-bottom:0; }}
  .report-header::before {{ content:''; position:absolute; top:0; left:0; right:0; height:1px; background:linear-gradient(90deg,transparent,var(--blue),transparent); opacity:0.4; }}
  .rh-badge {{ display:inline-flex; align-items:center; gap:6px; font-family:var(--mono); font-size:10px; font-weight:600; color:var(--blue); letter-spacing:2px; margin-bottom:8px; }}
  .rh-badge span {{ background:var(--blue-dim); color:var(--blue); border:1px solid rgba(61,156,245,0.2); border-radius:4px; padding:1px 6px; font-size:9px; }}
  .rh-title {{ font-family:var(--mono); font-size:28px; font-weight:700; color:#fff; letter-spacing:-0.5px; margin-bottom:4px; }}
  .rh-sub {{ font-family:var(--mono); font-size:11px; color:var(--text2); }}
  .rh-right {{ position:absolute; right:32px; top:28px; text-align:right; }}
  .rh-nifty {{ font-family:var(--mono); font-size:28px; font-weight:700; color:#fff; }}
  .rh-nifty-label {{ font-family:var(--mono); font-size:9px; color:var(--text3); letter-spacing:1px; }}
  .rh-date {{ font-family:var(--mono); font-size:9px; color:var(--text3); margin-top:6px; }}

  /* ── Tab Bar ────────────────────────────────────── */
  .tab-bar {{ display:flex; gap:0; background:var(--bg2); border:1px solid var(--border); border-radius:0 0 14px 14px; border-top:none; padding:0 16px; position:sticky; top:0; z-index:100; margin-bottom:20px; }}
  .tab-btn {{ font-family:var(--mono); font-size:10px; font-weight:600; color:var(--text3); background:none; border:none; border-bottom:2px solid transparent; padding:12px 18px; cursor:pointer; transition:all .15s; white-space:nowrap; letter-spacing:0.5px; }}
  .tab-btn:hover {{ color:var(--text); }}
  .tab-btn.active {{ color:#fff; border-bottom-color:var(--blue); }}
  .tab-pane {{ display:none; }}
  .tab-pane.active {{ display:block; }}

  /* ── KPI strip ─────────────────────────────────── */
  .kpi-row {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin-bottom:20px; }}
  .kpi-card {{ background:var(--bg2); border:1px solid var(--border); border-radius:12px; padding:16px 18px; }}
  .kpi-label {{ font-family:var(--mono); font-size:9px; letter-spacing:1.5px; text-transform:uppercase; color:var(--text3); margin-bottom:6px; }}
  .kpi-value {{ font-family:var(--mono); font-size:24px; font-weight:700; }}
  .kpi-sub {{ font-size:10px; color:var(--text2); margin-top:2px; }}

  /* ── Sort & Controls ───────────────────────────── */
  .controls {{ display:flex; align-items:center; gap:8px; flex-wrap:wrap; margin-bottom:18px; }}
  .controls-label {{ font-family:var(--mono); font-size:10px; color:var(--text3); text-transform:uppercase; letter-spacing:1px; margin-right:4px; }}
  .sort-btn {{ font-family:var(--mono); font-size:10px; font-weight:600; padding:6px 14px; border-radius:6px; border:1px solid var(--border); background:var(--bg3); color:var(--text3); cursor:pointer; transition:all .18s; }}
  .sort-btn:hover {{ color:var(--text); border-color:var(--border2); }}
  .sort-btn.active {{ color:#fff; background:var(--bg4); border-color:var(--blue); box-shadow:0 0 8px rgba(61,156,245,0.15); }}

  /* ── Legend bar ─────────────────────────────────── */
  .perf-legend {{ display:flex; align-items:center; gap:12px; margin-bottom:20px; background:var(--bg2); border:1px solid var(--border); border-radius:10px; padding:12px 18px; }}
  .perf-legend-label {{ font-family:var(--mono); font-size:9px; color:var(--text3); text-transform:uppercase; letter-spacing:0.8px; white-space:nowrap; }}
  .perf-legend-bar {{ flex:1; height:10px; border-radius:5px; background:linear-gradient(90deg,#ff4d6d,#f5a623 40%,#4ade80 60%,#00e5a0); }}
  .perf-legend-range {{ display:flex; justify-content:space-between; font-family:var(--mono); font-size:9px; color:var(--text3); flex:1; }}

  /* ── Sector Grid (S&P-style cards) ─────────────── */
  .sector-grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(320px,1fr)); gap:14px; }}
  @media(max-width:700px) {{ .sector-grid {{ grid-template-columns:1fr; }} }}
  .sector-card {{ background:var(--card-bg, var(--bg2)); border:1px solid var(--border); border-radius:14px; padding:18px 20px; cursor:pointer; transition:all .22s ease; position:relative; overflow:hidden; }}
  .sector-card::before {{ content:''; position:absolute; top:0; left:0; right:0; height:2px; background:linear-gradient(90deg,transparent,var(--card-accent,var(--blue)),transparent); opacity:.35; }}
  .sector-card:hover {{ border-color:var(--card-accent,var(--border2)); transform:translateY(-2px); box-shadow:0 8px 24px rgba(0,0,0,0.35); }}
  .card-top {{ display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:6px; }}
  .card-header {{ }}
  .sector-name {{ font-family:var(--mono); font-size:14px; font-weight:700; color:#fff; }}
  .etf-ticker {{ font-family:var(--mono); font-size:10px; color:var(--text3); margin-top:2px; }}
  .card-desc {{ font-size:11px; color:var(--text3); margin-bottom:10px; line-height:1.4; }}
  .ytd-badge {{ font-family:var(--mono); font-size:16px; font-weight:700; padding:4px 12px; border-radius:8px; white-space:nowrap; }}
  .ytd-badge.positive {{ color:var(--green); background:var(--green-dim); }}
  .ytd-badge.negative {{ color:var(--red); background:var(--red-dim); }}
  .ytd-badge.neutral {{ color:var(--text3); background:var(--bg4); }}
  .card-metrics {{ display:grid; grid-template-columns:repeat(3,1fr); gap:6px; }}
  .metric {{ background:var(--bg3); border:1px solid var(--border); border-radius:8px; padding:8px 10px; text-align:center; }}
  .metric-label {{ display:block; font-family:var(--mono); font-size:8px; color:var(--text3); text-transform:uppercase; letter-spacing:0.8px; margin-bottom:2px; }}
  .metric-value {{ font-family:var(--mono); font-size:12px; font-weight:600; color:var(--text); }}
  .metric-value.positive {{ color:var(--green); }}
  .metric-value.negative {{ color:var(--red); }}
  .metric.rating {{ border-color:var(--r-color,var(--border)); }}
  .metric.rating .metric-value {{ color:var(--r-color,var(--text)); font-size:10px; }}
  .expand-section {{ max-height:0; overflow:hidden; transition:max-height .4s cubic-bezier(0.4,0,0.2,1), opacity .3s ease; opacity:0; margin-top:0; }}
  .sector-card.expanded .expand-section {{ max-height:600px; opacity:1; margin-top:14px; }}
  .expand-block {{ margin-bottom:14px; }}
  .expand-title {{ font-family:var(--mono); font-size:10px; font-weight:600; color:var(--text2); text-transform:uppercase; letter-spacing:1px; margin-bottom:8px; padding-bottom:4px; border-bottom:1px solid var(--border); }}
  .holdings-table {{ width:100%; border-collapse:collapse; font-family:var(--mono); font-size:10px; }}
  .holdings-table th {{ text-align:left; color:var(--text3); font-size:8px; text-transform:uppercase; letter-spacing:0.8px; padding:4px 6px; border-bottom:1px solid var(--border); }}
  .holdings-table td {{ padding:5px 6px; border-bottom:1px solid rgba(255,255,255,0.03); }}
  .h-sym {{ color:#fff; font-weight:600; }}
  .h-mcap {{ color:var(--text2); text-align:right; }}
  .h-ytd {{ text-align:right; font-weight:600; }}
  .range-track {{ position:relative; height:8px; background:linear-gradient(90deg,var(--red),var(--amber),var(--green)); border-radius:4px; margin:12px 0 4px; }}
  .range-fill {{ height:100%; border-radius:4px; }}
  .range-marker {{ position:absolute; top:-6px; width:3px; height:20px; background:#fff; border-radius:2px; transform:translateX(-50%); box-shadow:0 0 8px rgba(255,255,255,0.4); }}
  .marker-label {{ position:absolute; top:-20px; left:50%; transform:translateX(-50%); font-family:var(--mono); font-size:9px; font-weight:700; color:#fff; white-space:nowrap; background:var(--bg4); padding:1px 6px; border-radius:3px; }}
  .range-labels {{ display:flex; justify-content:space-between; font-family:var(--mono); font-size:9px; color:var(--text3); }}

  /* ── Section ───────────────────────────────────── */
  .section {{ background:var(--bg2); border:1px solid var(--border); border-radius:14px; padding:22px; margin-bottom:24px; }}
  .section-title {{ font-family:var(--mono); font-size:10px; color:var(--text3); letter-spacing:2px; text-transform:uppercase; margin-bottom:16px; display:flex; align-items:center; gap:8px; }}
  .section-title::after {{ content:''; flex:1; height:1px; background:var(--border); }}

  /* ── Charts ────────────────────────────────────── */
  .chart-grid {{ display:grid; grid-template-columns:1fr; gap:20px; margin-bottom:24px; }}
  .chart-card {{ background:var(--bg2); border:1px solid var(--border); border-radius:14px; padding:22px; }}
  .chart-label {{ font-family:var(--mono); font-size:10px; color:var(--text3); letter-spacing:2px; text-transform:uppercase; margin-bottom:12px; display:flex; align-items:center; gap:8px; }}
  .chart-label::after {{ content:''; flex:1; height:1px; background:var(--border); }}
  .legend {{ display:flex; flex-wrap:wrap; gap:10px 16px; padding:12px 16px; background:var(--bg3); border:1px solid var(--border); border-radius:10px; margin-top:12px; }}
  .legend-item {{ display:inline-flex; align-items:center; gap:5px; font-family:var(--mono); font-size:9px; color:var(--text2); }}
  .legend-dot {{ width:8px; height:8px; border-radius:50%; flex-shrink:0; }}
  .legend-q {{ font-size:8px; font-weight:600; }}

  /* ── Table ──────────────────────────────────────── */
  .table-wrap {{ overflow-x:auto; }}
  table {{ width:100%; border-collapse:collapse; font-family:var(--mono); font-size:11px; }}
  thead th {{ padding:10px 10px; text-align:right; color:var(--text3); font-weight:500; font-size:9px; letter-spacing:1px; text-transform:uppercase; border-bottom:2px solid var(--border2); white-space:nowrap; }}
  thead th:first-child {{ text-align:left; }}
  tbody tr {{ border-bottom:1px solid var(--border); transition:background 0.2s; }}
  tbody tr:hover {{ background:rgba(255,255,255,0.02); }}
  tbody td {{ padding:10px 10px; text-align:right; white-space:nowrap; }}
  tbody td:first-child {{ text-align:left; }}

  /* ── Quadrant detail blocks ────────────────────── */
  .quadrant-block {{ background:var(--bg3); border:1px solid var(--border); border-radius:12px; padding:20px 22px; margin-bottom:16px; }}
  .qb-title {{ font-family:var(--mono); font-size:14px; font-weight:700; display:flex; align-items:center; gap:8px; margin-bottom:10px; }}
  .qb-dot {{ width:10px; height:10px; border-radius:50%; flex-shrink:0; }}
  .qb-count {{ font-size:10px; font-weight:400; color:var(--text3); margin-left:auto; }}
  .qb-desc {{ font-size:12px; color:var(--text2); line-height:1.7; margin-bottom:16px; padding-bottom:12px; border-bottom:1px solid var(--border); }}
  .sector-detail-card {{ background:var(--bg2); border:1px solid var(--border); border-radius:10px; padding:14px 16px; margin-bottom:10px; }}
  .sector-detail-card:last-child {{ margin-bottom:0; }}
  .sdc-header {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:6px; }}
  .sdc-name {{ font-family:var(--mono); font-size:12px; font-weight:700; color:#fff; }}
  .sdc-verdict {{ font-family:var(--mono); font-size:10px; font-weight:600; }}
  .sdc-rs {{ font-family:var(--mono); font-size:9px; color:var(--text3); margin-bottom:6px; }}
  .sdc-desc {{ font-size:11px; color:var(--text3); margin-bottom:8px; font-style:italic; }}
  .sdc-reasons {{ list-style:none; }}
  .sdc-reasons li {{ display:flex; align-items:flex-start; gap:6px; font-size:11px; color:var(--text2); padding:3px 0; line-height:1.5; }}
  .sdc-reasons li::before {{ content:'›'; color:var(--text3); font-weight:700; flex-shrink:0; }}

  /* ── Performance, RRG, Leaders ─────────────────── */
  .perf-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; }}
  .rrg-explainer {{ display:grid; grid-template-columns:1fr 1fr; gap:14px; margin-bottom:16px; }}
  .rrg-quad-card {{ background:var(--bg3); border:1px solid var(--border); border-radius:10px; padding:14px 16px; }}
  .rrg-quad-card h4 {{ font-family:var(--mono); font-size:11px; font-weight:700; margin-bottom:6px; display:flex; align-items:center; gap:6px; }}
  .rrg-quad-card p {{ font-size:11px; color:var(--text2); line-height:1.6; }}
  .leaders-grid {{ display:grid; grid-template-columns:repeat(2,1fr); gap:14px; }}
  .leader-block {{ background:var(--bg3); border:1px solid var(--border); border-radius:10px; padding:14px 16px; }}
  .lb-header {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:10px; }}
  .lb-name {{ font-family:var(--mono); font-size:12px; font-weight:700; color:#fff; }}
  .lb-quad {{ font-family:var(--mono); font-size:9px; font-weight:600; }}
  .leader-table {{ width:100%; border-collapse:collapse; font-family:var(--mono); font-size:10px; }}
  .leader-table thead th {{ padding:6px 8px; text-align:right; color:var(--text3); font-weight:500; font-size:8px; letter-spacing:0.5px; text-transform:uppercase; border-bottom:1px solid var(--border); }}
  .leader-table thead th:first-child {{ text-align:left; }}
  .leader-table tbody td {{ padding:6px 8px; text-align:right; }}
  .leader-table tbody td:first-child {{ text-align:left; }}
  .leader-table tbody tr {{ border-bottom:1px solid var(--border); }}

  /* ── Animations ────────────────────────────────── */
  .fade-in {{ opacity:0; transform:translateY(20px); transition:opacity .5s ease, transform .5s ease; }}
  .fade-in.visible {{ opacity:1; transform:translateY(0); }}

  /* ── Back link ─────────────────────────────────── */
  .back-link {{ display:inline-block; font-family:var(--mono); font-size:10px; color:var(--text3); text-decoration:none; margin-bottom:16px; padding:5px 12px; border:1px solid var(--border); border-radius:6px; transition:all .15s; }}
  .back-link:hover {{ color:var(--text); border-color:var(--border2); }}

  /* ── Footer ────────────────────────────────────── */
  .report-footer {{ text-align:center; padding:24px 0; font-family:var(--mono); font-size:9px; color:var(--text3); }}

  @media (max-width: 900px) {{
    .perf-grid, .rrg-explainer, .leaders-grid {{ grid-template-columns: 1fr; }}
    .kpi-row {{ grid-template-columns: repeat(2, 1fr); }}
    .sector-grid {{ grid-template-columns: 1fr; }}
    table {{ font-size: 10px; }}
  }}
  @media print {{ .tab-pane {{ display:block !important; }} .tab-bar {{ display:none; }} }}
</style>
</head>
<body>
<div class="page">

  <a href="../index.html" class="back-link">\u2190 Dashboard</a>

  <!-- HEADER -->
  <div class="report-header">
    <div class="rh-badge">SECTOR ROTATION REPORT <span>NSE</span></div>
    <div class="rh-title">NSE Sector Outlook</div>
    <div class="rh-sub">Relative Rotation Analysis \u00b7 All NSE Tradable Sectors \u00b7 Benchmark: {BENCHMARK_NAME}</div>
    <div class="rh-right">
      <div class="rh-nifty-label">{BENCHMARK_NAME}</div>
      <div class="rh-nifty">{bench_price:,.0f}</div>
      <div class="rh-date">{today_str} \u00b7 Auto-generated</div>
    </div>
  </div>

  <!-- TAB BAR -->
  <div class="tab-bar" id="main-tabs">
    <button class="tab-btn active" onclick="switchTab('overview',this)">Overview</button>
    <button class="tab-btn" onclick="switchTab('rrg',this)">RRG &amp; Rotation</button>
    <button class="tab-btn" onclick="switchTab('performance',this)">Performance</button>
    <button class="tab-btn" onclick="switchTab('leaders',this)">Leaders</button>
    <button class="tab-btn" onclick="switchTab('analysis',this)">Analysis</button>
  </div>

  <!-- ═══════════ TAB: OVERVIEW ═══════════ -->
  <div class="tab-pane active" id="tab-overview">

    <div class="kpi-row">
      <div class="kpi-card">
        <div class="kpi-label">Leading Sectors</div>
        <div class="kpi-value" style="color:var(--green)">{quadrant_counts["Leading"]}</div>
        <div class="kpi-sub">Strong RS + Rising Momentum</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Improving Sectors</div>
        <div class="kpi-value" style="color:var(--blue)">{quadrant_counts["Improving"]}</div>
        <div class="kpi-sub">Weak RS + Rising Momentum</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Weakening Sectors</div>
        <div class="kpi-value" style="color:var(--amber)">{quadrant_counts["Weakening"]}</div>
        <div class="kpi-sub">Strong RS + Falling Momentum</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Lagging Sectors</div>
        <div class="kpi-value" style="color:var(--red)">{quadrant_counts["Lagging"]}</div>
        <div class="kpi-sub">Weak RS + Falling Momentum</div>
      </div>
    </div>

    <div class="controls fade-in">
      <span class="controls-label">Sort by</span>
      <button class="sort-btn active" data-sort="ret1m" onclick="sortCards('ret1m',this)">1M Return</button>
      <button class="sort-btn" data-sort="rsratio" onclick="sortCards('rsratio',this)">RS-Ratio</button>
      <button class="sort-btn" data-sort="rsmom" onclick="sortCards('rsmom',this)">RS-Momentum</button>
      <button class="sort-btn" data-sort="vol" onclick="sortCards('vol',this)">Volatility</button>
    </div>

    <div class="perf-legend fade-in">
      <span class="perf-legend-label">1M Performance</span>
      <div style="flex:1">
        <div class="perf-legend-bar"></div>
        <div class="perf-legend-range">
          <span>\u221220%</span>
          <span>0%</span>
          <span>+20%</span>
        </div>
      </div>
    </div>

    <div class="sector-grid" id="sector-grid">
      {overview_cards_html}
    </div>

  </div>

  <!-- ═══════════ TAB: RRG & ROTATION ═══════════ -->
  <div class="tab-pane" id="tab-rrg">

    <div class="section">
      <div class="section-title">How to Read the Relative Rotation Graph</div>
      <p style="font-size:12px;color:var(--text2);margin-bottom:14px;line-height:1.7;">
        The RRG plots each sector's <b style="color:#fff">relative strength</b> (RS-Ratio, X-axis) against its <b style="color:#fff">momentum</b> (RS-Momentum, Y-axis) compared to the {BENCHMARK_NAME} benchmark. The center (100,100) represents parity. Sectors rotate clockwise through the four quadrants — this rotation reflects the natural cycle of sector leadership.
      </p>
      <div class="rrg-explainer">
        <div class="rrg-quad-card">
          <h4 style="color:var(--blue)"><span class="qb-dot" style="background:var(--blue);width:8px;height:8px;border-radius:50%;display:inline-block;"></span> Improving (Top-Left)</h4>
          <p>RS-Ratio &lt; 100, RS-Momentum &gt; 100 — Sector still underperforms but momentum is turning up. Early rotation signal.</p>
        </div>
        <div class="rrg-quad-card">
          <h4 style="color:var(--green)"><span class="qb-dot" style="background:var(--green);width:8px;height:8px;border-radius:50%;display:inline-block;"></span> Leading (Top-Right)</h4>
          <p>RS-Ratio &gt; 100, RS-Momentum &gt; 100 — Sector is outperforming and acceleration is positive. Strongest position.</p>
        </div>
        <div class="rrg-quad-card">
          <h4 style="color:var(--red)"><span class="qb-dot" style="background:var(--red);width:8px;height:8px;border-radius:50%;display:inline-block;"></span> Lagging (Bottom-Left)</h4>
          <p>RS-Ratio &lt; 100, RS-Momentum &lt; 100 — Sector underperforms with declining momentum. Weakest position.</p>
        </div>
        <div class="rrg-quad-card">
          <h4 style="color:var(--amber)"><span class="qb-dot" style="background:var(--amber);width:8px;height:8px;border-radius:50%;display:inline-block;"></span> Weakening (Bottom-Right)</h4>
          <p>RS-Ratio &gt; 100, RS-Momentum &lt; 100 — Sector still outperforms but momentum is fading. Consider booking profits.</p>
        </div>
      </div>
    </div>

    <div class="chart-grid">
      <div class="chart-card">
        <div class="chart-label">RRG Scatter Plot \u2014 Current Positioning</div>
        {rrg_svg}
      </div>
      <div class="chart-card">
        <div class="chart-label">Sector Rotation Trail \u2014 Weekly Movement</div>
        {trail_svg}
      </div>
    </div>

    <div class="section" style="padding:14px 22px;">
      <div class="legend">
        {legend_items}
      </div>
    </div>

  </div>

  <!-- ═══════════ TAB: PERFORMANCE ═══════════ -->
  <div class="tab-pane" id="tab-performance">

    <div class="perf-grid" style="margin-bottom:24px;">
      <div class="chart-card">
        <div class="chart-label">1-Month Sector Performance</div>
        {perf_1m_svg}
      </div>
      <div class="chart-card">
        <div class="chart-label">3-Month Sector Performance</div>
        {perf_3m_svg}
      </div>
    </div>

    <div class="section">
      <div class="section-title">Market Breadth \u2014 Cap-wise Index Performance</div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th style="text-align:left;">Index</th>
              <th>Level</th>
              <th>1D</th><th>1W</th><th>1M</th><th>3M</th><th>6M</th><th>1Y</th>
              <th>From High</th>
              <th>Trend</th>
            </tr>
          </thead>
          <tbody>
            {mktcap_rows}
          </tbody>
        </table>
      </div>
    </div>

    <div class="section">
      <div class="section-title">Sector Outlook Summary</div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th style="text-align:left;">Sector</th>
              <th>Quadrant</th>
              <th>Trend</th>
              <th>1D</th><th>1W</th><th>1M</th><th>3M</th><th>6M</th>
              <th>From High</th>
              <th>Vol (30d)</th>
              <th>Outlook</th>
            </tr>
          </thead>
          <tbody>
            {table_rows}
          </tbody>
        </table>
      </div>
    </div>

  </div>

  <!-- ═══════════ TAB: LEADERS ═══════════ -->
  <div class="tab-pane" id="tab-leaders">

    <div class="section">
      <div class="section-title">Sector Leaders \u2014 Top 3 Stocks per Sector</div>
      <div class="leaders-grid">
        {leaders_html}
      </div>
    </div>

  </div>

  <!-- ═══════════ TAB: ANALYSIS ═══════════ -->
  <div class="tab-pane" id="tab-analysis">

    <div class="section">
      <div class="section-title">Detailed Sector Analysis by Quadrant</div>
      {quadrant_detail_html}
    </div>

  </div>

  <!-- FOOTER -->
  <div class="report-footer">
    Generated on {today_str} \u00b7 Data via Yahoo Finance \u00b7 Benchmark: {BENCHMARK_NAME}<br>
    Relative Rotation Graph methodology based on Julius de Kempenaer's RRG framework<br>
    Not investment advice \u00b7 For informational purposes only
  </div>

</div>

<script>
function switchTab(id, btn) {{
  document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('tab-'+id).classList.add('active');
  btn.classList.add('active');
  window.scrollTo({{top: document.querySelector('.tab-bar').offsetTop - 10, behavior:'smooth'}});
}}

function toggleExpand(card) {{
  card.classList.toggle('expanded');
}}

function sortCards(key, btn) {{
  document.querySelectorAll('.sort-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  const grid = document.getElementById('sector-grid');
  const cards = Array.from(grid.querySelectorAll('.sector-card'));
  cards.sort((a, b) => {{
    const av = parseFloat(a.dataset[key]) || 0;
    const bv = parseFloat(b.dataset[key]) || 0;
    if (key === 'vol') return av - bv;  // lower volatility first
    return bv - av;  // higher values first for returns, RS-Ratio, RS-Momentum
  }});
  cards.forEach(c => grid.appendChild(c));
}}

const observer = new IntersectionObserver((entries) => {{
  entries.forEach(e => {{
    if (e.isIntersecting) {{
      e.target.classList.add('visible');
      observer.unobserve(e.target);
    }}
  }});
}}, {{ threshold: 0.08, rootMargin: '0px 0px -40px 0px' }});
document.querySelectorAll('.fade-in').forEach(el => observer.observe(el));
</script>
</body>
</html>'''

    return html


# ─────────────────────────────────────────────────────────────────────────────
# CLEANUP
# ─────────────────────────────────────────────────────────────────────────────

def cleanup_old_reports(reports_root, keep_days=15):
    """Remove report date-directories older than keep_days."""
    removed = 0
    if not os.path.isdir(reports_root):
        return 0
    cutoff = datetime.now() - timedelta(days=keep_days)
    for name in os.listdir(reports_root):
        path = os.path.join(reports_root, name)
        if not os.path.isdir(path):
            continue
        try:
            d = datetime.strptime(name, "%Y-%m-%d")
            if d < cutoff:
                shutil.rmtree(path)
                removed += 1
        except ValueError:
            pass
    return removed


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="NSE Sector Rotation & Outlook Report Generator")
    parser.add_argument("-o", "--output-dir", default="./sector_reports", help="Output directory (default: ./sector_reports)")
    args = parser.parse_args()

    reports_root = args.output_dir
    today_str = datetime.now().strftime("%Y-%m-%d")
    output_dir = os.path.join(reports_root, today_str)
    os.makedirs(output_dir, exist_ok=True)

    removed = cleanup_old_reports(reports_root, keep_days=15)
    if removed:
        print(f"  🧹 Cleaned up {removed} report folder(s) older than 15 days")

    print("=" * 62)
    print("  NSE Sector Rotation & Outlook Report Generator")
    print("  Powered by yfinance · No API Key Required")
    print(f"  Sectors: {len(NSE_SECTORS)}")
    print(f"  Date:    {today_str}")
    print(f"  Output:  {os.path.abspath(output_dir)}/")
    print("=" * 62)
    print()

    # Fetch benchmark
    print(f"  📊 Fetching benchmark: {BENCHMARK_NAME} ({BENCHMARK_SYMBOL})...")
    benchmark_hist = fetch_index_history(BENCHMARK_SYMBOL, period="1y")
    if benchmark_hist is None or benchmark_hist.empty:
        print("  ❌ Failed to fetch benchmark data. Aborting.")
        sys.exit(1)
    benchmark_metrics = compute_sector_metrics(benchmark_hist, None)
    print(f"  ✅ Benchmark loaded: {len(benchmark_hist)} days of data\n")

    sectors_data = []

    for i, (name, info) in enumerate(NSE_SECTORS.items(), 1):
        symbol = info["symbol"]
        print(f"  [{i}/{len(NSE_SECTORS)}] Fetching {name} ({symbol})...")

        hist = fetch_index_history(symbol, period="1y")
        if hist is None or hist.empty:
            print(f"    ⚠ No data for {name}, skipping")
            continue

        metrics = compute_sector_metrics(hist, benchmark_hist)

        rs_ratio, rs_momentum, rs_ratio_prev, rs_momentum_prev = compute_rs_ratio_momentum(hist, benchmark_hist)
        quadrant = classify_quadrant(rs_ratio, rs_momentum)
        trail = get_rrg_trail(hist, benchmark_hist)

        outlook = generate_sector_outlook(name, info, metrics, quadrant, rs_ratio, rs_momentum)

        sectors_data.append({
            "name": name,
            "symbol": symbol,
            "metrics": metrics,
            "rs_ratio": rs_ratio,
            "rs_momentum": rs_momentum,
            "rs_ratio_prev": rs_ratio_prev,
            "rs_momentum_prev": rs_momentum_prev,
            "quadrant": quadrant,
            "trail": trail,
            "outlook": outlook,
        })

        q_color = QUADRANT_COLORS.get(quadrant, "")
        ret_1m = metrics.get("returns", {}).get("1M")
        ret_str = f'{ret_1m:+.1f}%' if ret_1m is not None else "N/A"
        print(f"    ✅ {quadrant:12s} | 1M: {ret_str:>7s} | RS-Ratio: {rs_ratio:.2f} | RS-Mom: {rs_momentum:.2f}" if rs_ratio and rs_momentum else f"    ✅ {quadrant}")

    # Fetch market cap indices
    print(f"\n  📊 Fetching market cap indices...")
    mktcap_data = []
    for mc_name, mc_info in MARKET_CAP_INDICES.items():
        mc_sym = mc_info["symbol"]
        print(f"    {mc_name} ({mc_sym})...")
        mc_hist = fetch_index_history(mc_sym, period="1y")
        if mc_hist is not None and not mc_hist.empty:
            mc_metrics = compute_sector_metrics(mc_hist, benchmark_hist)
            mktcap_data.append({"name": mc_name, "symbol": mc_sym, "metrics": mc_metrics})
            print(f"      ✅ {len(mc_hist)} days")
        else:
            print(f"      ⚠ No data")

    # Fetch sector leader stocks
    print(f"\n  📊 Fetching sector leader stocks...")
    leaders_data = {}
    seen_symbols = set()
    for sname in [s["name"] for s in sectors_data]:
        symbols = SECTOR_LEADERS.get(sname, [])
        leader_list = []
        for sym in symbols:
            if sym in seen_symbols:
                cached = None
                for prev_name, prev_list in leaders_data.items():
                    for prev_st in prev_list:
                        if prev_st["symbol"] == sym:
                            cached = prev_st
                            break
                    if cached:
                        break
                if cached:
                    leader_list.append(cached)
                    continue
            seen_symbols.add(sym)
            print(f"    {sym}...")
            st = fetch_stock_returns(sym)
            if st:
                leader_list.append(st)
        leaders_data[sname] = leader_list
    print(f"  ✅ Fetched {len(seen_symbols)} unique leader stocks")

    print(f"\n  📄 Generating HTML report...")

    html = generate_html_report(sectors_data, benchmark_metrics, today_str, mktcap_data, leaders_data)
    output_file = os.path.join(output_dir, "SectorRotation_Report.html")
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html)

    # Also copy to root for easy access
    root_report = os.path.join(reports_root, "SectorRotation_Report.html")
    shutil.copy2(output_file, root_report)

    file_size = os.path.getsize(output_file) / 1024
    print(f"  ✅ Saved: {output_file} ({file_size:.1f} KB)")
    print(f"  📋 Also at: {root_report}")

    # Summary
    q_summary = {}
    for s in sectors_data:
        q = s.get("quadrant", "Unknown")
        q_summary.setdefault(q, []).append(s["name"].replace("Nifty ", ""))

    print(f"\n{'=' * 62}")
    print("  SECTOR ROTATION SUMMARY")
    print(f"{'=' * 62}")
    for q in ["Leading", "Improving", "Weakening", "Lagging"]:
        if q in q_summary:
            print(f"  {q:12s}: {', '.join(q_summary[q])}")
    print(f"{'=' * 62}\n")


if __name__ == "__main__":
    main()
