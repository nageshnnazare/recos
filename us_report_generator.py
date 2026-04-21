#!/usr/bin/env python3
"""
US Stock Risk Score Report Generator (No API Key Required)
============================================================
Generates 2-page dark HTML risk score reports for any US stock
using yfinance for live data. No prompting or API keys needed.

Usage:
    # Single stock
    python us_report_generator.py AAPL
    python us_report_generator.py MSFT

    # Multiple stocks
    python us_report_generator.py AAPL MSFT NVDA

    # From watchlist file
    python us_report_generator.py --watchlist us_watchlist.txt

    # Generate alerts summary (for GitHub Actions)
    python us_report_generator.py --watchlist us_watchlist.txt --alerts

    # Custom output directory
    python us_report_generator.py AAPL -o ./us_reports/

Requirements:
    pip install yfinance
"""

import os
import sys
import json
import math
import argparse
import shutil
from datetime import datetime, timedelta

try:
    import yfinance as yf
except ImportError:
    print("Installing yfinance...")
    os.system(f"{sys.executable} -m pip install yfinance")
    import yfinance as yf


# ─────────────────────────────────────────────────────────────────────────────
# SECTOR-SPECIFIC BENCHMARKS
# ─────────────────────────────────────────────────────────────────────────────
# pe: (cheap, fair, expensive)   pb: (cheap, fair, expensive)
# roe: (moderate, good) as decimal   margin: (moderate, good) as decimal
# de: (comfortable, high)

_DEFAULT_BENCH = {"pe": (15, 25, 50), "pb": (2, 5, 12), "roe": (0.10, 0.18), "margin": (0.08, 0.18), "de": (40, 100)}

SECTOR_BENCHMARKS = {
    "Financial Services": {"pe": (12, 22, 35), "pb": (1.5, 3, 5),  "roe": (0.12, 0.18), "margin": (0.15, 0.30), "de": (200, 500)},
    "Technology":         {"pe": (20, 35, 60), "pb": (3, 8, 15),   "roe": (0.15, 0.25), "margin": (0.15, 0.25), "de": (20, 60)},
    "Energy":             {"pe": (8, 15, 25),  "pb": (1, 2, 4),    "roe": (0.10, 0.18), "margin": (0.05, 0.12), "de": (40, 100)},
    "Industrials":        {"pe": (15, 30, 50), "pb": (2, 5, 10),   "roe": (0.12, 0.20), "margin": (0.10, 0.20), "de": (30, 80)},
    "Healthcare":         {"pe": (18, 30, 50), "pb": (2, 5, 10),   "roe": (0.12, 0.20), "margin": (0.12, 0.22), "de": (20, 60)},
    "Consumer Cyclical":  {"pe": (15, 25, 45), "pb": (2, 5, 12),   "roe": (0.12, 0.20), "margin": (0.08, 0.18), "de": (30, 80)},
    "Consumer Defensive": {"pe": (18, 30, 50), "pb": (3, 8, 15),   "roe": (0.15, 0.25), "margin": (0.10, 0.20), "de": (30, 80)},
    "Basic Materials":    {"pe": (8, 15, 30),  "pb": (1, 2.5, 6),  "roe": (0.10, 0.18), "margin": (0.08, 0.15), "de": (40, 100)},
    "Communication Services": {"pe": (12, 25, 45), "pb": (1.5, 4, 10), "roe": (0.08, 0.15), "margin": (0.10, 0.20), "de": (50, 120)},
    "Real Estate":        {"pe": (10, 20, 40), "pb": (1, 2.5, 6),  "roe": (0.08, 0.15), "margin": (0.10, 0.25), "de": (50, 120)},
    "Utilities":          {"pe": (10, 18, 30), "pb": (1, 2, 4),    "roe": (0.10, 0.15), "margin": (0.10, 0.20), "de": (80, 200)},
}

def get_sector_bench(sector):
    return SECTOR_BENCHMARKS.get(sector, _DEFAULT_BENCH)


# ─────────────────────────────────────────────────────────────────────────────
# DATA FETCHING
# ─────────────────────────────────────────────────────────────────────────────

def fetch_stock_data(ticker_symbol):
    """Fetch all required data for any US stock from yfinance."""
    yf_symbol = ticker_symbol.upper()
    print(f"  📊 Fetching live data for {yf_symbol}...")

    ticker = yf.Ticker(yf_symbol)
    result = {"ticker_symbol": ticker_symbol, "yf_symbol": yf_symbol}

    try:
        result["info"] = ticker.info or {}
    except Exception as e:
        print(f"    ⚠ Could not fetch info: {e}")
        result["info"] = {}

    try:
        result["hist_1y"] = ticker.history(period="1y")
    except Exception as e:
        print(f"    ⚠ Could not fetch 1Y history: {e}")
        result["hist_1y"] = None

    try:
        result["hist_6m"] = ticker.history(period="6mo")
    except Exception as e:
        print(f"    ⚠ Could not fetch 6M history: {e}")
        result["hist_6m"] = None

    try:
        result["quarterly_income"] = ticker.quarterly_income_stmt
    except Exception as e:
        print(f"    ⚠ Could not fetch quarterly income: {e}")
        result["quarterly_income"] = None

    try:
        result["balance_sheet"] = ticker.quarterly_balance_sheet
    except Exception as e:
        print(f"    ⚠ Could not fetch quarterly balance sheet: {e}")
        result["balance_sheet"] = None

    try:
        result["financials"] = ticker.financials
    except Exception as e:
        print(f"    ⚠ Could not fetch annual financials: {e}")
        result["financials"] = None

    try:
        result["annual_balance_sheet"] = ticker.balance_sheet
    except Exception as e:
        print(f"    ⚠ Could not fetch annual balance sheet: {e}")
        result["annual_balance_sheet"] = None

    try:
        result["quarterly_cash_flow"] = ticker.quarterly_cash_flow
    except Exception as e:
        print(f"    ⚠ Could not fetch quarterly cash flow: {e}")
        result["quarterly_cash_flow"] = None

    try:
        result["annual_cash_flow"] = ticker.cash_flow
    except Exception as e:
        print(f"    ⚠ Could not fetch annual cash flow: {e}")
        result["annual_cash_flow"] = None

    for period_key, period_val in [("hist_5d", "5d"), ("hist_1mo", "1mo"), ("hist_3y", "3y"), ("hist_5y", "5y")]:
        try:
            result[period_key] = ticker.history(period=period_val)
        except Exception:
            result[period_key] = None

    try:
        result["major_holders"] = ticker.major_holders
    except Exception:
        result["major_holders"] = None
    try:
        result["institutional_holders"] = ticker.institutional_holders
    except Exception:
        result["institutional_holders"] = None
    try:
        result["mutualfund_holders"] = ticker.mutualfund_holders
    except Exception:
        result["mutualfund_holders"] = None

    try:
        result["news"] = ticker.get_news(count=8)
    except Exception:
        result["news"] = None

    result["ticker_obj"] = ticker

    # Peer data: not available for US without Screener.in, use empty defaults
    result["peers"] = []
    result["peers_page_url"] = ""
    result["industry_name"] = safe_get(result.get("info", {}), "industry", "")
    result["screener"] = {}

    return result


def calculate_roe_manual(data):
    """Calculate Return on Equity manually if info['returnOnEquity'] is missing."""
    info = data.get("info", {})
    roe = safe_get(info, "returnOnEquity")

    if roe is not None and roe != 0:
        return roe

    try:
        f = data.get("financials")
        b = data.get("annual_balance_sheet")

        if f is not None and not f.empty and b is not None and not b.empty:
            ni = None
            for key in ["Net Income", "Net Income Common Stockholders", "Diluted NI Availto Com Stockholders"]:
                if key in f.index:
                    ni = f.loc[key].iloc[0]
                    if ni is not None and not math.isnan(ni):
                        break

            equity = None
            for key in ["Common Stock Equity", "Stockholders Equity", "Total Equity Gross Minority Interest"]:
                if key in b.index:
                    equity = b.loc[key].iloc[0]
                    if equity is not None and not math.isnan(equity) and equity != 0:
                        break

            if ni is not None and equity is not None:
                return ni / equity
    except:
        pass

    return roe or 0


def safe_get(d, key, default=None):
    try:
        val = d.get(key, default)
        return default if val is None else val
    except:
        return default


def fmt_val(val):
    """Format value in USD (B/M/K)."""
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return "N/A"
    abs_val = abs(val)
    if abs_val >= 1e12:
        return f"${val/1e12:,.1f}T"
    elif abs_val >= 1e9:
        return f"${val/1e9:,.1f}B"
    elif abs_val >= 1e6:
        return f"${val/1e6:,.1f}M"
    elif abs_val >= 1e3:
        return f"${val/1e3:,.1f}K"
    return f"${val:,.2f}"


# ─────────────────────────────────────────────────────────────────────────────
# RISK SCORE CALCULATION (Sector-calibrated)
# ─────────────────────────────────────────────────────────────────────────────

def calculate_risk_scores(data):
    """Calculate risk scores based on 35/35/30 weighting with sector-specific thresholds."""
    info = data["info"]
    sector = safe_get(info, "sector", "")
    bench = get_sector_bench(sector)
    pe_cheap, pe_fair, pe_exp = bench["pe"]
    pb_cheap, pb_fair, pb_exp = bench["pb"]
    roe_mod, roe_good = bench["roe"]
    margin_mod, margin_good = bench["margin"]
    de_ok, de_high = bench["de"]

    val_score = 17
    pe = safe_get(info, "trailingPE", safe_get(info, "forwardPE"))
    pb = safe_get(info, "priceToBook")

    if pe:
        if pe < pe_cheap:
            val_score += 10
        elif pe < pe_fair:
            val_score += 7
        elif pe < pe_exp:
            val_score += 4
        elif pe < pe_exp * 1.5:
            val_score += 0
        elif pe < pe_exp * 2.5:
            val_score -= 3
        else:
            val_score -= 7

    if pb:
        if pb < pb_cheap:
            val_score += 5
        elif pb < pb_fair:
            val_score += 3
        elif pb < pb_exp:
            val_score += 1
        elif pb < pb_exp * 2:
            val_score -= 2
        else:
            val_score -= 5

    target = safe_get(info, "targetMeanPrice")
    current = safe_get(info, "currentPrice", safe_get(info, "regularMarketPrice"))
    if target and current and current > 0:
        upside = (target - current) / current * 100
        if upside > 30: val_score += 5
        elif upside > 15: val_score += 4
        elif upside > 5: val_score += 2
        elif upside > 0: val_score += 1
        elif upside > -10: val_score -= 1
        else: val_score -= 4

    val_score = max(0, min(35, val_score))

    fin_score = 17
    roe = calculate_roe_manual(data)
    if roe:
        if roe > roe_good * 1.4: fin_score += 7
        elif roe > roe_good: fin_score += 5
        elif roe > roe_mod: fin_score += 2
        elif roe > 0: fin_score += 0
        else: fin_score -= 5

    profit_margin = safe_get(info, "profitMargins")
    if profit_margin:
        if profit_margin > margin_good * 1.3: fin_score += 6
        elif profit_margin > margin_mod: fin_score += 3
        elif profit_margin > 0: fin_score += 1
        else: fin_score -= 5

    rev_growth = safe_get(info, "revenueGrowth")
    if rev_growth:
        if rev_growth > 0.3: fin_score += 5
        elif rev_growth > 0.15: fin_score += 3
        elif rev_growth > 0.05: fin_score += 1
        elif rev_growth > 0: fin_score += 0
        else: fin_score -= 4

    debt_equity = safe_get(info, "debtToEquity")
    if debt_equity is not None:
        if debt_equity < de_ok: fin_score += 3
        elif debt_equity < de_high: fin_score += 1
        elif debt_equity < de_high * 1.5: fin_score -= 1
        else: fin_score -= 3

    fin_score = max(0, min(35, fin_score))

    growth_score = 15
    if rev_growth:
        if rev_growth > 0.4: growth_score += 8
        elif rev_growth > 0.25: growth_score += 5
        elif rev_growth > 0.1: growth_score += 3
        elif rev_growth > 0: growth_score += 1
        else: growth_score -= 4

    earnings_growth = safe_get(info, "earningsGrowth")
    if earnings_growth:
        if earnings_growth > 0.3: growth_score += 5
        elif earnings_growth > 0.1: growth_score += 3
        elif earnings_growth > 0: growth_score += 1
        else: growth_score -= 3

    beta = safe_get(info, "beta")
    if beta:
        if beta < 0.8: growth_score += 2
        elif beta < 1.2: growth_score += 1
        else: growth_score -= 1

    growth_score = max(0, min(30, growth_score))
    composite = val_score + fin_score + growth_score

    return {"valuation": val_score, "financial": fin_score, "growth": growth_score, "composite": composite}


def get_signal(scores, info):
    """Determine buy/sell/hold signal and whether it's a value buy."""
    composite = scores["composite"]
    current = safe_get(info, "currentPrice", safe_get(info, "regularMarketPrice"))
    target = safe_get(info, "targetMeanPrice")
    sector = safe_get(info, "sector", "")
    sector_tag = f" for {sector}" if sector else ""

    upside = 0
    if target and current and current > 0:
        upside = (target - current) / current * 100

    if composite >= 75 and upside > 15:
        return "🟢 STRONG BUY", True, f"Strong score with significant upside{sector_tag}"
    elif composite >= 65 and upside > 5:
        return "🟢 BUY", True, f"Attractive risk/reward{sector_tag} at current levels"
    elif composite >= 55:
        return "🟡 SPECULATIVE BUY", False, f"Positive{sector_tag} but monitor closely"
    elif composite >= 40:
        return "🟡 HOLD", False, f"Neutral{sector_tag} — wait for better entry or catalyst"
    elif composite >= 25:
        return "🔴 SELL", False, f"Elevated risk{sector_tag} — consider exiting"
    else:
        return "🔴 STRONG SELL", False, f"High risk{sector_tag} — exit recommended"


# ─────────────────────────────────────────────────────────────────────────────
# SVG CHART GENERATORS
# ─────────────────────────────────────────────────────────────────────────────

def generate_risk_gauge_svg(score):
    """Generate an SVG risk gauge (0-100)."""
    cx, cy = 130, 130
    r = 100
    start_angle = 225
    end_angle = -45
    total_angle = start_angle - end_angle

    score_angle = start_angle - (score / 100) * total_angle
    score_rad = math.radians(score_angle)

    needle_len = 75
    nx = cx + needle_len * math.cos(score_rad)
    ny = cy - needle_len * math.sin(score_rad)

    if score >= 70: color, label = "#00e5a0", "LOW RISK"
    elif score >= 40: color, label = "#f5a623", "MODERATE"
    else: color, label = "#ff4d6d", "HIGH RISK"

    def arc_point(angle_deg, radius):
        rad = math.radians(angle_deg)
        return (cx + radius * math.cos(rad), cy - radius * math.sin(rad))

    svg = f'''<svg viewBox="0 0 260 170" xmlns="http://www.w3.org/2000/svg" style="width:100%;max-width:260px;">
  <defs>
    <filter id="glow"><feGaussianBlur stdDeviation="3" result="blur"/><feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
    <linearGradient id="arcGrad" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="#ff4d6d"/><stop offset="50%" stop-color="#f5a623"/><stop offset="100%" stop-color="#00e5a0"/>
    </linearGradient>
  </defs>'''

    for pct_start, pct_end, seg_color in [(0, 33, "#ff4d6d22"), (33, 66, "#f5a62322"), (66, 100, "#00e5a022")]:
        a1 = start_angle - (pct_start / 100) * total_angle
        a2 = start_angle - (pct_end / 100) * total_angle
        p1, p2 = arc_point(a1, r), arc_point(a2, r)
        large = 1 if abs(a1 - a2) > 180 else 0
        svg += f'\n  <path d="M {p1[0]:.1f} {p1[1]:.1f} A {r} {r} 0 {large} 1 {p2[0]:.1f} {p2[1]:.1f}" fill="none" stroke="{seg_color}" stroke-width="16" stroke-linecap="round"/>'

    score_end_angle = start_angle - (score / 100) * total_angle
    p_start, p_end = arc_point(start_angle, r), arc_point(score_end_angle, r)
    large = 1 if abs(start_angle - score_end_angle) > 180 else 0
    svg += f'\n  <path d="M {p_start[0]:.1f} {p_start[1]:.1f} A {r} {r} 0 {large} 1 {p_end[0]:.1f} {p_end[1]:.1f}" fill="none" stroke="url(#arcGrad)" stroke-width="8" stroke-linecap="round" filter="url(#glow)"/>'

    for i in range(0, 101, 10):
        angle = start_angle - (i / 100) * total_angle
        p_out, p_in = arc_point(angle, r + 12), arc_point(angle, r + 6)
        svg += f'\n  <line x1="{p_in[0]:.1f}" y1="{p_in[1]:.1f}" x2="{p_out[0]:.1f}" y2="{p_out[1]:.1f}" stroke="#5c5d6e" stroke-width="1"/>'

    svg += f'''
  <line x1="{cx}" y1="{cy}" x2="{nx:.1f}" y2="{ny:.1f}" stroke="{color}" stroke-width="2.5" stroke-linecap="round" filter="url(#glow)"/>
  <circle cx="{cx}" cy="{cy}" r="6" fill="{color}" filter="url(#glow)"/>
  <circle cx="{cx}" cy="{cy}" r="3" fill="#08090d"/>
  <text x="{cx}" y="{cy + 35}" text-anchor="middle" font-family="'Fira Code',monospace" font-size="32" font-weight="700" fill="#fff">{score}</text>
  <text x="{cx}" y="{cy + 52}" text-anchor="middle" font-family="'Fira Code',monospace" font-size="9" fill="{color}" letter-spacing="2">{label}</text>
</svg>'''
    return svg


def generate_price_chart_svg(hist_data, width=1040, height=280):
    """Generate a 12-month price chart with annotations."""
    if hist_data is None or hist_data.empty:
        return '<svg viewBox="0 0 1040 280"><text x="520" y="140" text-anchor="middle" fill="#5c5d6e" font-family="Fira Code,monospace" font-size="14">Price data unavailable</text></svg>'

    prices = hist_data["Close"].values.tolist()
    dates = hist_data.index.tolist()
    highs = hist_data["High"].values.tolist()
    lows = hist_data["Low"].values.tolist()
    if len(prices) < 2:
        return '<svg viewBox="0 0 1040 280"><text x="520" y="140" text-anchor="middle" fill="#5c5d6e">Insufficient data</text></svg>'

    pad_left, pad_right, pad_top, pad_bottom = 60, 20, 30, 40
    chart_w = width - pad_left - pad_right
    chart_h = height - pad_top - pad_bottom
    min_p = min(lows) * 0.97
    max_p = max(highs) * 1.03
    p_range = max_p - min_p if max_p != min_p else 1

    def x_pos(i): return pad_left + (i / (len(prices) - 1)) * chart_w
    def y_pos(p): return pad_top + (1 - (p - min_p) / p_range) * chart_h

    svg = f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" style="width:100%;">\n'
    svg += '  <defs>\n    <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">\n      <stop offset="0%" stop-color="#00e5a0" stop-opacity="0.25"/>\n      <stop offset="100%" stop-color="#00e5a0" stop-opacity="0.01"/>\n    </linearGradient>\n    <filter id="lineGlow"><feGaussianBlur stdDeviation="2" result="blur"/><feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter>\n  </defs>\n'

    for i in range(6):
        y = pad_top + (i / 5) * chart_h
        p_val = max_p - (i / 5) * p_range
        svg += f'  <line x1="{pad_left}" y1="{y:.1f}" x2="{width - pad_right}" y2="{y:.1f}" stroke="rgba(255,255,255,0.04)" stroke-width="1"/>\n'
        svg += f'  <text x="{pad_left - 8}" y="{y + 4:.1f}" text-anchor="end" font-family="Fira Code,monospace" font-size="9" fill="#5c5d6e">${p_val:.0f}</text>\n'

    shown_months = set()
    for i, d in enumerate(dates):
        try:
            dt = d.to_pydatetime() if hasattr(d, 'to_pydatetime') else d
            month_key = f"{dt.year}-{dt.month}"
            if month_key not in shown_months and dt.day <= 7:
                shown_months.add(month_key)
                date_str = dt.strftime("%b'%y")
                svg += f'  <text x="{x_pos(i):.1f}" y="{height - 8}" text-anchor="middle" font-family="Fira Code,monospace" font-size="8" fill="#5c5d6e">{date_str}</text>\n'
        except: pass

    area_points = f"M {x_pos(0):.1f} {y_pos(prices[0]):.1f} "
    for i in range(1, len(prices)):
        area_points += f"L {x_pos(i):.1f} {y_pos(prices[i]):.1f} "
    area_points += f"L {x_pos(len(prices)-1):.1f} {pad_top + chart_h:.1f} L {x_pos(0):.1f} {pad_top + chart_h:.1f} Z"
    svg += f'  <path d="{area_points}" fill="url(#areaGrad)"/>\n'

    line_points = " ".join([f"{x_pos(i):.1f},{y_pos(prices[i]):.1f}" for i in range(len(prices))])
    svg += f'  <polyline points="{line_points}" fill="none" stroke="#00e5a0" stroke-width="2" stroke-linejoin="round" filter="url(#lineGlow)"/>\n'

    # Annotate 52W high, 52W low, CMP
    max_idx = highs.index(max(highs))
    min_idx = lows.index(min(lows))
    events = [
        (max_idx, f"52W High: ${max(highs):.0f}", "#f5a623"),
        (min_idx, f"52W Low: ${min(lows):.0f}", "#ff4d6d"),
        (len(prices) - 1, f"CMP: ${prices[-1]:.0f}", "#3d9cf5"),
    ]
    for idx, label, color in events:
        if 0 <= idx < len(prices):
            ex, ey = x_pos(idx), y_pos(prices[idx])
            svg += f'  <line x1="{ex:.1f}" y1="{ey:.1f}" x2="{ex:.1f}" y2="{pad_top + chart_h:.1f}" stroke="{color}" stroke-width="0.5" stroke-dasharray="3,3" opacity="0.5"/>\n'
            svg += f'  <circle cx="{ex:.1f}" cy="{ey:.1f}" r="4" fill="{color}" stroke="#08090d" stroke-width="2"/>\n'
            label_y = ey - 12 if ey > pad_top + 30 else ey + 20
            svg += f'  <text x="{ex:.1f}" y="{label_y:.1f}" text-anchor="middle" font-family="Fira Code,monospace" font-size="8" fill="{color}">{label}</text>\n'

    svg += '</svg>'
    return svg


def generate_candle_chart_svg(hist_data, width=1040, height=280):
    """Generate a daily candlestick chart with 50 EMA and 200 DMA overlays + value labels."""
    if hist_data is None or hist_data.empty:
        return '<svg viewBox="0 0 1040 280"><text x="520" y="140" text-anchor="middle" fill="#5c5d6e" font-family="Fira Code,monospace" font-size="14">Candle data unavailable</text></svg>'

    daily = hist_data.tail(90).copy()
    opens = daily["Open"].values.tolist()
    highs = daily["High"].values.tolist()
    lows = daily["Low"].values.tolist()
    closes = daily["Close"].values.tolist()
    n = len(opens)
    if n < 5:
        return '<svg viewBox="0 0 1040 280"><text x="520" y="140" text-anchor="middle" fill="#5c5d6e">Insufficient candle data</text></svg>'

    all_closes = hist_data["Close"].values.tolist()
    total = len(all_closes)
    display_start = total - n

    ema50_all = [all_closes[0]]
    mult_50 = 2 / 51
    for i in range(1, total):
        ema50_all.append(all_closes[i] * mult_50 + ema50_all[-1] * (1 - mult_50))

    dma200_all = []
    for i in range(total):
        if i >= 199:
            dma200_all.append(sum(all_closes[i-199:i+1]) / 200)
        else:
            dma200_all.append(None)

    ema50_display = ema50_all[display_start:]
    dma200_display = dma200_all[display_start:]

    pad_left, pad_right, pad_top, pad_bottom = 60, 70, 20, 40
    chart_w = width - pad_left - pad_right
    chart_h = height - pad_top - pad_bottom

    all_prices = lows + highs
    for v in ema50_display:
        if v is not None: all_prices.append(v)
    for v in dma200_display:
        if v is not None: all_prices.append(v)
    min_p = min(all_prices) * 0.97
    max_p = max(all_prices) * 1.03
    p_range = max_p - min_p if max_p != min_p else 1

    candle_w = max(1.5, min(8, (chart_w / n) * 0.65))
    gap = chart_w / n

    def y_pos(p): return pad_top + (1 - (p - min_p) / p_range) * chart_h

    svg = f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" style="width:100%;">\n'

    for i in range(6):
        y = pad_top + (i / 5) * chart_h
        p_val = max_p - (i / 5) * p_range
        svg += f'  <line x1="{pad_left}" y1="{y:.1f}" x2="{width - pad_right}" y2="{y:.1f}" stroke="rgba(255,255,255,0.04)" stroke-width="1"/>\n'
        svg += f'  <text x="{pad_left - 8}" y="{y + 4:.1f}" text-anchor="end" font-family="Fira Code,monospace" font-size="8" fill="#5c5d6e">${p_val:.0f}</text>\n'

    dates = daily.index.tolist()
    shown_months = set()
    for i, d in enumerate(dates):
        try:
            dt = d.to_pydatetime() if hasattr(d, 'to_pydatetime') else d
            month_key = f"{dt.year}-{dt.month}"
            if month_key not in shown_months and dt.day <= 7:
                shown_months.add(month_key)
                date_str = dt.strftime("%b'%y")
                svg += f'  <text x="{pad_left + (i + 0.5) * gap:.1f}" y="{height - 8}" text-anchor="middle" font-family="Fira Code,monospace" font-size="8" fill="#5c5d6e">{date_str}</text>\n'
        except: pass

    dma_points = []
    dma_last_val = None
    for i in range(n):
        if dma200_display[i] is not None:
            x = pad_left + (i + 0.5) * gap
            dma_points.append(f"{x:.1f},{y_pos(dma200_display[i]):.1f}")
            dma_last_val = dma200_display[i]
    if dma_points:
        svg += f'  <polyline points="{" ".join(dma_points)}" fill="none" stroke="#f5a623" stroke-width="1.5" opacity="0.5" stroke-dasharray="6,3"/>\n'
        if dma_last_val is not None:
            lx = pad_left + (n - 0.5) * gap + 4
            svg += f'  <text x="{lx:.1f}" y="{y_pos(dma_last_val) + 3:.1f}" font-family="Fira Code,monospace" font-size="8" font-weight="600" fill="#f5a623">${dma_last_val:,.0f}</text>\n'

    ema_points = []
    ema_last_val = None
    for i in range(n):
        if ema50_display[i] is not None:
            x = pad_left + (i + 0.5) * gap
            ema_points.append(f"{x:.1f},{y_pos(ema50_display[i]):.1f}")
            ema_last_val = ema50_display[i]
    if ema_points:
        svg += f'  <polyline points="{" ".join(ema_points)}" fill="none" stroke="#9b7fff" stroke-width="1.5" opacity="0.7"/>\n'
        if ema_last_val is not None:
            lx = pad_left + (n - 0.5) * gap + 4
            svg += f'  <text x="{lx:.1f}" y="{y_pos(ema_last_val) + 3:.1f}" font-family="Fira Code,monospace" font-size="8" font-weight="600" fill="#9b7fff">${ema_last_val:,.0f}</text>\n'

    for i in range(n):
        x_center = pad_left + (i + 0.5) * gap
        o, h, l, c = opens[i], highs[i], lows[i], closes[i]
        bullish = c >= o
        color = "#00e5a0" if bullish else "#ff4d6d"
        body_top = y_pos(max(o, c))
        body_bottom = y_pos(min(o, c))
        body_h = max(1, body_bottom - body_top)
        svg += f'  <line x1="{x_center:.1f}" y1="{y_pos(h):.1f}" x2="{x_center:.1f}" y2="{y_pos(l):.1f}" stroke="{color}" stroke-width="1" opacity="0.7"/>\n'
        fill = color if not bullish else "none"
        svg += f'  <rect x="{x_center - candle_w/2:.1f}" y="{body_top:.1f}" width="{candle_w:.1f}" height="{body_h:.1f}" fill="{fill}" stroke="{color}" stroke-width="1" rx="1"/>\n'

    ema_legend = f"── 50 EMA (${ema_last_val:,.0f})" if ema_last_val else "── 50 EMA"
    dma_legend = f"╌╌ 200 DMA (${dma_last_val:,.0f})" if dma_last_val else "╌╌ 200 DMA"
    svg += f'''
  <text x="{pad_left + 4}" y="{pad_top + 12}" font-family="Fira Code,monospace" font-size="8" fill="#9b7fff">{ema_legend}</text>
  <text x="{pad_left + 4}" y="{pad_top + 24}" font-family="Fira Code,monospace" font-size="8" fill="#f5a623">{dma_legend}</text>
'''
    svg += '</svg>'
    return svg


def generate_fair_value_svg(current_price, fair_value_low, fair_value_mid, fair_value_high, width=480, height=90):
    """Generate a fair value comparison bar chart."""
    all_vals = [current_price, fair_value_low, fair_value_mid, fair_value_high]
    min_v = min(all_vals) * 0.8
    max_v = max(all_vals) * 1.2
    v_range = max_v - min_v if max_v != min_v else 1

    def x_pos(v): return 60 + ((v - min_v) / v_range) * (width - 100)

    svg = f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" style="width:100%;">\n'
    x1, x2 = x_pos(fair_value_low), x_pos(fair_value_high)
    svg += f'  <rect x="{x1:.1f}" y="25" width="{x2 - x1:.1f}" height="30" rx="4" fill="rgba(0,229,160,0.08)" stroke="rgba(0,229,160,0.2)" stroke-width="1" stroke-dasharray="4,2"/>\n'
    svg += f'  <text x="{(x1+x2)/2:.1f}" y="20" text-anchor="middle" font-family="Fira Code,monospace" font-size="8" fill="#00e5a0">FAIR VALUE ZONE</text>\n'
    xm = x_pos(fair_value_mid)
    svg += f'  <line x1="{xm:.1f}" y1="22" x2="{xm:.1f}" y2="58" stroke="#00e5a0" stroke-width="2"/>\n'
    svg += f'  <text x="{xm:.1f}" y="72" text-anchor="middle" font-family="Fira Code,monospace" font-size="9" fill="#00e5a0">${fair_value_mid:,.0f}</text>\n'
    svg += f'  <text x="{xm:.1f}" y="82" text-anchor="middle" font-family="Fira Code,monospace" font-size="7" fill="#5c5d6e">FAIR VALUE</text>\n'
    svg += f'  <text x="{x1:.1f}" y="72" text-anchor="middle" font-family="Fira Code,monospace" font-size="8" fill="#5c5d6e">${fair_value_low:,.0f}</text>\n'
    svg += f'  <text x="{x2:.1f}" y="72" text-anchor="middle" font-family="Fira Code,monospace" font-size="8" fill="#5c5d6e">${fair_value_high:,.0f}</text>\n'
    xc = x_pos(current_price)
    color = "#00e5a0" if current_price <= fair_value_mid * 1.1 else "#f5a623" if current_price <= fair_value_high else "#ff4d6d"
    svg += f'  <line x1="{xc:.1f}" y1="22" x2="{xc:.1f}" y2="58" stroke="{color}" stroke-width="3"/>\n'
    svg += f'  <polygon points="{xc:.1f},20 {xc-5:.1f},12 {xc+5:.1f},12" fill="{color}"/>\n'
    svg += f'  <text x="{xc:.1f}" y="8" text-anchor="middle" font-family="Fira Code,monospace" font-size="10" font-weight="700" fill="{color}">${current_price:,.0f} CMP</text>\n'
    svg += '</svg>'
    return svg


# ─────────────────────────────────────────────────────────────────────────────
# DATA EXTRACTION HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _pct_change(current, previous):
    if current is not None and previous is not None and previous != 0:
        return ((current - previous) / abs(previous)) * 100
    return None


def _safe_df_value(df, col, key_list):
    for key in key_list:
        if key in df.index:
            val = df.loc[key, col]
            if val is not None and not (isinstance(val, float) and math.isnan(val)):
                return val
    return None


def extract_quarterly_data(data):
    """Extract quarterly financial data with QoQ % changes and operating cash flow."""
    qi = data.get("quarterly_income")
    qcf = data.get("quarterly_cash_flow")
    rows = []

    if qi is not None and not qi.empty:
        for col in qi.columns[:8]:
            try:
                dt = col.to_pydatetime() if hasattr(col, 'to_pydatetime') else col
                q_label = f"Q{(dt.month-1)//3 + 1} '{dt.year % 100}"

                rev = _safe_df_value(qi, col, ["Total Revenue", "Operating Revenue", "Revenue"])
                profit = _safe_df_value(qi, col, ["Net Income", "Net Income Common Stockholders", "Net Income From Continuing Operations"])
                ebitda = _safe_df_value(qi, col, ["EBITDA", "Normalized EBITDA"])
                ebitda_margin = (ebitda / rev) * 100 if ebitda and rev and rev > 0 else None

                op_cf = None
                if qcf is not None and not qcf.empty and col in qcf.columns:
                    op_cf = _safe_df_value(qcf, col, ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"])

                rows.append({"quarter": q_label, "date": dt, "revenue": rev, "profit": profit,
                             "ebitda_margin": ebitda_margin, "op_cash_flow": op_cf})
            except:
                continue

    rows.sort(key=lambda x: x.get("date", datetime.min))

    for i in range(1, len(rows)):
        rows[i]["rev_qoq_pct"] = _pct_change(rows[i]["revenue"], rows[i-1]["revenue"])
        rows[i]["profit_qoq_pct"] = _pct_change(rows[i]["profit"], rows[i-1]["profit"])
    if rows:
        rows[0]["rev_qoq_pct"] = None
        rows[0]["profit_qoq_pct"] = None

    return rows


def extract_annual_data(data):
    """Extract annual revenue, net profit, and operating cash flow with YoY %."""
    fi = data.get("financials")
    acf = data.get("annual_cash_flow")
    rows = []

    if fi is not None and not fi.empty:
        for col in fi.columns[:5]:
            try:
                dt = col.to_pydatetime() if hasattr(col, 'to_pydatetime') else col
                rev = _safe_df_value(fi, col, ["Total Revenue", "Operating Revenue", "Revenue"])
                profit = _safe_df_value(fi, col, ["Net Income", "Net Income Common Stockholders"])

                op_cf = None
                if acf is not None and not acf.empty and col in acf.columns:
                    op_cf = _safe_df_value(acf, col, ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"])

                rows.append({"year": str(dt.year), "date": dt, "revenue": rev, "profit": profit, "op_cash_flow": op_cf})
            except:
                continue

    rows.sort(key=lambda x: x.get("date", datetime.min))

    for i in range(1, len(rows)):
        rows[i]["rev_yoy_pct"] = _pct_change(rows[i]["revenue"], rows[i-1]["revenue"])
        rows[i]["profit_yoy_pct"] = _pct_change(rows[i]["profit"], rows[i-1]["profit"])
        rows[i]["cf_yoy_pct"] = _pct_change(rows[i]["op_cash_flow"], rows[i-1]["op_cash_flow"])
    if rows:
        rows[0]["rev_yoy_pct"] = None
        rows[0]["profit_yoy_pct"] = None
        rows[0]["cf_yoy_pct"] = None

    return rows


def extract_holder_data(data):
    """Parse major_holders, institutional_holders, mutualfund_holders."""
    mh = data.get("major_holders")
    ih = data.get("institutional_holders")
    mfh = data.get("mutualfund_holders")

    holder_summary = {}
    if mh is not None and not mh.empty:
        for idx in mh.index:
            try:
                label = str(mh.loc[idx, 0] if 0 in mh.columns else mh.iloc[idx, 0] if mh.shape[1] > 0 else "")
                val_raw = str(mh.loc[idx, 1] if 1 in mh.columns else mh.iloc[idx, 1] if mh.shape[1] > 1 else "")
                label_lower = label.lower()
                val_clean = val_raw.replace("%", "").strip()
                try:
                    val_num = float(val_clean)
                except:
                    val_num = None

                if "insider" in label_lower and val_num is not None:
                    holder_summary["insiders"] = val_num
                elif "institution" in label_lower and "count" not in label_lower and val_num is not None and val_num < 100:
                    holder_summary["institutions"] = val_num
            except:
                continue

    top_holders = []
    for source, htype in [(ih, "Institutional"), (mfh, "Mutual Fund")]:
        if source is not None and not source.empty:
            for _, row in source.head(5).iterrows():
                name = str(row.get("Holder", row.get("holder", "Unknown")))
                shares = row.get("Shares", row.get("shares", 0))
                pct = row.get("pctHeld", row.get("% Out", 0))
                top_holders.append({"name": name, "type": htype, "shares": shares, "pct": pct})

    return holder_summary, top_holders[:8]


def extract_news(data):
    """Parse news items from yfinance."""
    raw_news = data.get("news")
    items = []
    if not raw_news:
        return items

    for entry in raw_news:
        try:
            content = entry.get("content", entry) if isinstance(entry, dict) else entry
            if isinstance(content, dict):
                title = content.get("title", "")
                publisher = content.get("provider", {}).get("displayName", "") if isinstance(content.get("provider"), dict) else str(content.get("provider", ""))
                pub_date = content.get("pubDate", "")
                link = content.get("canonicalUrl", {}).get("url", "") if isinstance(content.get("canonicalUrl"), dict) else content.get("url", content.get("link", ""))
            else:
                continue

            if title:
                items.append({"title": title[:120], "publisher": publisher, "date_str": pub_date[:16] if pub_date else "", "link": link})
        except:
            continue

    return items[:6]


def calculate_returns(data, current_price):
    """Calculate multi-period returns."""
    returns = {}
    periods = {"1D": "hist_5d", "1W": "hist_5d", "1M": "hist_1mo", "6M": "hist_6m", "1Y": "hist_1y", "3Y": "hist_3y", "5Y": "hist_5y"}
    offsets = {"1D": -2, "1W": -6}

    for label, key in periods.items():
        hist = data.get(key)
        if hist is not None and not hist.empty and len(hist) > 1:
            idx = offsets.get(label, 0)
            try:
                base_price = hist["Close"].iloc[idx]
                if base_price and base_price > 0:
                    returns[label] = ((current_price - base_price) / base_price) * 100
            except:
                pass

    return returns


def calculate_factor_scores(data, scores, returns):
    """Calculate 5 factor scores (0-10 each) with reasoning."""
    info = data.get("info", {})
    reasons = {}

    momentum = 5
    mom_parts = []
    r1m, r6m = returns.get("1M"), returns.get("6M")
    if r1m is not None:
        mom_parts.append(f"1M return {r1m:+.1f}%")
        if r1m > 10: momentum += 2
        elif r1m > 3: momentum += 1
        elif r1m < -10: momentum -= 2
        elif r1m < -3: momentum -= 1
    if r6m is not None:
        mom_parts.append(f"6M return {r6m:+.1f}%")
        if r6m > 20: momentum += 2
        elif r6m > 5: momentum += 1
        elif r6m < -20: momentum -= 2
        elif r6m < -5: momentum -= 1
    reasons["Momentum"] = ", ".join(mom_parts) if mom_parts else "No return data"

    sentiment = 5
    sent_parts = []
    target = safe_get(info, "targetMeanPrice")
    current = safe_get(info, "currentPrice", safe_get(info, "regularMarketPrice"))
    if target and current and current > 0:
        upside = (target - current) / current * 100
        sent_parts.append(f"Analyst upside {upside:+.1f}%")
        if upside > 30: sentiment += 3
        elif upside > 15: sentiment += 2
        elif upside > 5: sentiment += 1
        elif upside < -10: sentiment -= 2
        elif upside < 0: sentiment -= 1
    rec_key = safe_get(info, "recommendationKey", "")
    if rec_key:
        sent_parts.append(f"Rec: {rec_key.replace('_', ' ')}")
    if rec_key in ("strong_buy", "buy"): sentiment += 1
    elif rec_key in ("sell", "strong_sell"): sentiment -= 1
    reasons["Sentiment"] = ", ".join(sent_parts) if sent_parts else "No analyst data"

    value = 5
    val_parts = []
    pe = safe_get(info, "trailingPE")
    pb = safe_get(info, "priceToBook")
    peg = safe_get(info, "trailingPegRatio", safe_get(info, "pegRatio"))
    ev_ebitda = safe_get(info, "enterpriseToEbitda")
    if pe:
        val_parts.append(f"P/E {pe:.1f}")
        if pe < 15: value += 2
        elif pe < 25: value += 1
        elif pe > 60: value -= 2
        elif pe > 40: value -= 1
    if pb:
        val_parts.append(f"P/B {pb:.1f}")
        if pb < 2: value += 1
        elif pb > 10: value -= 1
    if peg:
        val_parts.append(f"PEG {peg:.2f}")
        if peg < 1: value += 1
        elif peg > 2: value -= 1
    if ev_ebitda:
        val_parts.append(f"EV/EBITDA {ev_ebitda:.1f}")
        if ev_ebitda < 12: value += 1
        elif ev_ebitda > 25: value -= 1
    reasons["Value"] = ", ".join(val_parts) if val_parts else "No valuation data"

    quality = 5
    qual_parts = []
    roe = safe_get(info, "returnOnEquity")
    pm = safe_get(info, "profitMargins")
    de = safe_get(info, "debtToEquity")
    cr = safe_get(info, "currentRatio")
    if roe:
        qual_parts.append(f"ROE {roe*100:.1f}%")
        if roe > 0.25: quality += 2
        elif roe > 0.15: quality += 1
        elif roe < 0: quality -= 2
    if pm:
        qual_parts.append(f"Margin {pm*100:.1f}%")
        if pm > 0.2: quality += 1
        elif pm < 0: quality -= 2
        elif pm < 0.05: quality -= 1
    if de is not None:
        qual_parts.append(f"D/E {de:.0f}")
        if de < 30: quality += 1
        elif de > 150: quality -= 1
    if cr:
        qual_parts.append(f"CR {cr:.2f}")
        if cr > 1.5: quality += 1
        elif cr < 1.0: quality -= 1
    reasons["Quality"] = ", ".join(qual_parts) if qual_parts else "No quality data"

    low_vol = 5
    lv_parts = []
    beta = safe_get(info, "beta")
    if beta:
        lv_parts.append(f"Beta {beta:.2f}")
        if beta < 0.6: low_vol += 3
        elif beta < 0.8: low_vol += 2
        elif beta < 1.0: low_vol += 1
        elif beta > 1.5: low_vol -= 3
        elif beta > 1.3: low_vol -= 2
        elif beta > 1.1: low_vol -= 1
    hist = data.get("hist_1y")
    if hist is not None and not hist.empty and len(hist) > 20:
        daily_returns = hist["Close"].pct_change().dropna()
        if len(daily_returns) > 0:
            vol = daily_returns.std() * (252 ** 0.5)
            lv_parts.append(f"Ann. vol {vol*100:.0f}%")
            if vol < 0.25: low_vol += 2
            elif vol < 0.35: low_vol += 1
            elif vol > 0.6: low_vol -= 2
            elif vol > 0.45: low_vol -= 1
    reasons["Low Volatility"] = ", ".join(lv_parts) if lv_parts else "No volatility data"

    factor_scores = {
        "Momentum": max(0, min(10, momentum)),
        "Sentiment": max(0, min(10, sentiment)),
        "Value": max(0, min(10, value)),
        "Quality": max(0, min(10, quality)),
        "Low Volatility": max(0, min(10, low_vol)),
    }
    return factor_scores, reasons


def generate_spider_chart_svg(factors, reasons=None, width=480, height=440):
    """Generate a radar/spider chart SVG with hover tooltips."""
    short_labels = {"Low Volatility": "Low Vol"}
    labels = list(factors.keys())
    values = list(factors.values())
    n = len(labels)
    cx, cy = width / 2, height / 2
    max_r = 130
    if reasons is None: reasons = {}

    angle_offset = -math.pi / 2
    def polar(i, r):
        angle = angle_offset + (2 * math.pi * i / n)
        return (cx + r * math.cos(angle), cy + r * math.sin(angle))

    svg = f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" style="width:100%;max-width:{width}px;">\n'
    svg += '  <defs><filter id="spiderGlow"><feGaussianBlur stdDeviation="3" result="blur"/><feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>\n'

    for ring in [2, 4, 6, 8, 10]:
        r = max_r * ring / 10
        points = " ".join([f"{polar(i, r)[0]:.1f},{polar(i, r)[1]:.1f}" for i in range(n)])
        opacity = "0.08" if ring < 10 else "0.15"
        svg += f'  <polygon points="{points}" fill="none" stroke="rgba(255,255,255,{opacity})" stroke-width="1"/>\n'

    for i in range(n):
        px, py = polar(i, max_r)
        svg += f'  <line x1="{cx:.1f}" y1="{cy:.1f}" x2="{px:.1f}" y2="{py:.1f}" stroke="rgba(255,255,255,0.06)" stroke-width="1"/>\n'

    data_points = []
    for i, v in enumerate(values):
        data_points.append(polar(i, max_r * v / 10))

    points_str = " ".join([f"{p[0]:.1f},{p[1]:.1f}" for p in data_points])
    svg += f'  <polygon points="{points_str}" fill="rgba(0,229,160,0.12)" stroke="#00e5a0" stroke-width="2" filter="url(#spiderGlow)"/>\n'

    for i, (px, py) in enumerate(data_points):
        tip = reasons.get(labels[i], "")
        svg += f'  <circle cx="{px:.1f}" cy="{py:.1f}" r="6" fill="#00e5a0" stroke="#08090d" stroke-width="2" style="cursor:pointer;"><title>{labels[i]} {values[i]}/10: {tip}</title></circle>\n'

    for i, label in enumerate(labels):
        display_label = short_labels.get(label, label)
        lx, ly = polar(i, max_r + 24)
        anchor = "middle"
        dy = 0
        if lx < cx - 10: anchor = "end"; lx -= 4
        elif lx > cx + 10: anchor = "start"; lx += 4
        if ly < cy: dy = -4
        elif ly > cy: dy = 8
        svg += f'  <text x="{lx:.1f}" y="{ly + dy:.1f}" text-anchor="{anchor}" font-family="Fira Code,monospace" font-size="10" fill="#9899a8">{display_label}</text>\n'
        sx, sy = polar(i, max_r + 38)
        if sx < cx - 10: sx -= 4
        elif sx > cx + 10: sx += 4
        svg += f'  <text x="{sx:.1f}" y="{sy + dy:.1f}" text-anchor="{anchor}" font-family="Fira Code,monospace" font-size="12" font-weight="700" fill="#00e5a0">{values[i]}</text>\n'

    svg += '</svg>'
    return svg


# ─────────────────────────────────────────────────────────────────────────────
# HTML REPORT GENERATOR (US)
# ─────────────────────────────────────────────────────────────────────────────

def generate_html_report(data, scores):
    """Generate the complete 2-page HTML report for any US stock."""
    info = data["info"]
    hist_1y = data["hist_1y"]
    hist_6m = data["hist_6m"]
    ticker_symbol = data["ticker_symbol"]
    ticker_u = ticker_symbol.upper()

    # Extract values with fallbacks
    current_price = safe_get(info, "currentPrice", safe_get(info, "regularMarketPrice", 0))
    prev_close = safe_get(info, "previousClose", safe_get(info, "regularMarketPreviousClose", current_price))
    change = current_price - prev_close if current_price and prev_close else 0
    change_pct = (change / prev_close * 100) if prev_close and prev_close > 0 else 0
    high_52w = safe_get(info, "fiftyTwoWeekHigh", 0)
    low_52w = safe_get(info, "fiftyTwoWeekLow", 0)
    day_high = safe_get(info, "dayHigh", safe_get(info, "regularMarketDayHigh", 0))
    day_low = safe_get(info, "dayLow", safe_get(info, "regularMarketDayLow", 0))
    market_cap = safe_get(info, "marketCap", 0)
    pe_ratio = safe_get(info, "trailingPE", safe_get(info, "forwardPE", 0))
    pb_ratio = safe_get(info, "priceToBook", 0)
    eps = safe_get(info, "trailingEps", 0)
    roe = safe_get(info, "returnOnEquity", 0)
    rev_growth = safe_get(info, "revenueGrowth", 0)
    profit_margin = safe_get(info, "profitMargins", 0)
    target_mean = safe_get(info, "targetMeanPrice", 0)
    target_high = safe_get(info, "targetHighPrice", 0)
    target_low = safe_get(info, "targetLowPrice", 0)
    dividend_yield = safe_get(info, "dividendYield")
    if dividend_yield is not None and 0 <= dividend_yield <= 1:
        dy_pct = float(dividend_yield) * 100.0
    else:
        dy_pct = dividend_yield
    beta = safe_get(info, "beta", 0)
    volume = safe_get(info, "volume", safe_get(info, "regularMarketVolume", 0))
    avg_volume = safe_get(info, "averageVolume", 0)
    sector = safe_get(info, "sector", "N/A")
    industry = safe_get(info, "industry", "N/A")
    company_name = safe_get(info, "longName", safe_get(info, "shortName", ticker_symbol))
    total_revenue = safe_get(info, "totalRevenue", 0)
    debt_equity = safe_get(info, "debtToEquity", 0)
    gross_margin = safe_get(info, "grossMargins")
    operating_margin = safe_get(info, "operatingMargins")
    earnings_growth = safe_get(info, "earningsGrowth", 0)
    peg_ratio = safe_get(info, "trailingPegRatio", safe_get(info, "pegRatio"))
    ev_ebitda = safe_get(info, "enterpriseToEbitda")
    current_ratio = safe_get(info, "currentRatio")
    roa = safe_get(info, "returnOnAssets")

    _mcap = market_cap or 0
    mcap_cap_label = "Large" if _mcap > 10e9 else ("Mid" if _mcap > 2e9 else "Small")
    change_color = "#00e5a0" if change >= 0 else "#ff4d6d"
    change_icon = "▲" if change >= 0 else "▼"

    day_range = day_high - day_low if day_high and day_low and day_high > day_low else 0
    day_pct = max(0, min(100, ((current_price - day_low) / day_range * 100))) if day_range > 0 else 50
    w52_range = high_52w - low_52w if high_52w and low_52w and high_52w > low_52w else 0
    w52_pct = max(0, min(100, ((current_price - low_52w) / w52_range * 100))) if w52_range > 0 else 50

    def score_color(score, max_score):
        pct = score / max_score * 100 if max_score > 0 else 0
        if pct >= 70:
            return "#00e5a0"
        elif pct >= 40:
            return "#f5a623"
        else:
            return "#ff4d6d"

    gauge_svg = generate_risk_gauge_svg(scores["composite"])
    price_chart_svg = generate_price_chart_svg(hist_1y)
    candle_chart_svg = generate_candle_chart_svg(hist_1y)

    fair_value_low = target_low if target_low else current_price * 0.75
    fair_value_mid = target_mean if target_mean else current_price
    fair_value_high = target_high if target_high else current_price * 1.25
    fair_value_svg = generate_fair_value_svg(current_price, fair_value_low, fair_value_mid, fair_value_high)

    if hist_1y is not None and not hist_1y.empty and len(hist_1y) > 1:
        price_1y_ago = hist_1y["Close"].iloc[0]
        return_1y = ((current_price - price_1y_ago) / price_1y_ago) * 100 if price_1y_ago > 0 else 0
    else:
        return_1y = 0

    # Extract data for new sections
    quarterly_rows = extract_quarterly_data(data)
    annual_rows = extract_annual_data(data)
    _, top_holders = extract_holder_data(data)
    news_items = extract_news(data)
    returns = calculate_returns(data, current_price)
    factor_scores, factor_reasons = calculate_factor_scores(data, scores, returns)
    spider_svg = generate_spider_chart_svg(factor_scores, factor_reasons)
    roe = calculate_roe_manual(data)

    # ── Quarterly table HTML (with QoQ %) ──
    qt_rows_html = ""
    for q in quarterly_rows:
        rev_str = fmt_val(q["revenue"]) if q.get("revenue") else "N/A"
        profit_str = fmt_val(q["profit"]) if q.get("profit") else "N/A"
        ebitda_str = f"{q['ebitda_margin']:.1f}%" if q['ebitda_margin'] else "N/A"
        cf_str = fmt_val(q["op_cash_flow"]) if q.get("op_cash_flow") else "N/A"

        def _qoq_cell(pct):
            if pct is None:
                return '<td style="color:var(--text3)">—</td>'
            cls = "tg" if pct >= 0 else "tr"
            return f'<td class="{cls}">{pct:+.1f}%</td>'

        profit_class = "tg" if q.get("profit") and q["profit"] > 0 else "tr" if q.get("profit") and q["profit"] < 0 else ""

        qt_rows_html += f'''
        <tr>
          <td>{q["quarter"]}</td>
          <td>{rev_str}</td>{_qoq_cell(q.get("rev_qoq_pct"))}
          <td class="{profit_class}">{profit_str}</td>{_qoq_cell(q.get("profit_qoq_pct"))}
          <td>{cf_str}</td>
          <td>{ebitda_str}</td>
        </tr>'''

    if not qt_rows_html:
        qt_rows_html = '<tr><td colspan="7" style="text-align:center;color:var(--text3);">Quarterly data not available from yfinance</td></tr>'

    # ── Annual YoY table HTML ──
    yoy_rows_html = ""
    for a in annual_rows:
        rev_str = fmt_val(a["revenue"]) if a.get("revenue") else "N/A"
        profit_str = fmt_val(a["profit"]) if a.get("profit") else "N/A"
        cf_str = fmt_val(a["op_cash_flow"]) if a.get("op_cash_flow") else "N/A"

        def _yoy_cell(pct):
            if pct is None:
                return '<td style="color:var(--text3)">—</td>'
            cls = "tg" if pct >= 0 else "tr"
            return f'<td class="{cls}">{pct:+.1f}%</td>'

        yoy_rows_html += f'''
        <tr>
          <td>{a["year"]}</td>
          <td>{rev_str}</td>{_yoy_cell(a.get("rev_yoy_pct"))}
          <td>{profit_str}</td>{_yoy_cell(a.get("profit_yoy_pct"))}
          <td>{cf_str}</td>{_yoy_cell(a.get("cf_yoy_pct"))}
        </tr>'''

    if not yoy_rows_html:
        yoy_rows_html = '<tr><td colspan="7" style="text-align:center;color:var(--text3);">Annual data not available</td></tr>'

    # ── Shareholding section HTML (yfinance US only) ──
    screener = {}

    holders_table_html = ""
    for h in top_holders:
        htype = h.get("type", "—")
        if htype == "Institutional":
            htype_short = "Inst"
        elif htype == "Mutual Fund":
            htype_short = "MF"
        else:
            htype_short = str(htype)[:6]
        pct_val = h.get("pct", 0)
        if isinstance(pct_val, str):
            pct_str = pct_val if "%" in str(pct_val) else (str(pct_val) + "%" if pct_val else "N/A")
        elif isinstance(pct_val, (int, float)) and 0 <= float(pct_val) <= 1:
            pct_str = f"{float(pct_val)*100:.2f}%"
        elif isinstance(pct_val, (int, float)):
            pct_str = f"{float(pct_val):.2f}%"
        else:
            pct_str = "N/A"
        shares = h.get("shares", 0)
        try:
            shares_f = float(shares)
            shares_str = f"{shares_f:,.0f}"
        except (TypeError, ValueError):
            shares_str = str(shares) if shares else "N/A"
        nm = str(h.get("name", ""))[:35]
        holders_table_html += f'<tr><td>{nm}</td><td>{htype_short}</td><td>{shares_str}</td><td>{pct_str}</td></tr>'
    if not holders_table_html:
        holders_table_html = '<tr><td colspan="4" style="text-align:center;color:var(--text3);">Holder data not available</td></tr>'

    shareholding_section_html = f'''
          <div class="col-card" style="width:100%">
            <div class="col-title">TOP HOLDERS</div>
            <div style="overflow-x:auto;">
            <table>
              <thead><tr><th>Holder</th><th>Type</th><th>Shares</th><th>% Held</th></tr></thead>
              <tbody>{holders_table_html}</tbody>
            </table>
            </div>
          </div>'''

    # ── Returns strip HTML ──
    returns_html = ""
    for period in ["1D", "1W", "1M", "6M", "1Y", "3Y", "5Y"]:
        val = returns.get(period)
        if val is not None:
            color = "#00e5a0" if val >= 0 else "#ff4d6d"
            icon = "▲" if val >= 0 else "▼"
            returns_html += f'<div class="kpi-card" style="text-align:center;"><div class="kpi-label">{period}</div><div class="kpi-value" style="color:{color};font-size:16px;">{icon} {val:+.1f}%</div></div>'
        else:
            returns_html += f'<div class="kpi-card" style="text-align:center;"><div class="kpi-label">{period}</div><div class="kpi-value" style="color:var(--text3);font-size:16px;">N/A</div></div>'

    # ── News section HTML ──
    news_html = ""
    if news_items:
        for item in news_items:
            link_open = f'<a href="{item["link"]}" target="_blank" rel="noopener" style="color:#fff;text-decoration:none;">' if item["link"] else ""
            link_close = "</a>" if item["link"] else ""
            news_html += f'''<div class="news-card">{link_open}<div class="news-title">{item["title"]}</div>{link_close}<div class="news-meta">{item["publisher"]}{" · " + item["date_str"] if item["date_str"] else ""}</div></div>'''
    else:
        news_html = '<div style="color:var(--text3);font-size:11px;text-align:center;padding:20px 0;">No recent news available for this stock</div>'

    industry_name = data.get("industry_name", "") or safe_get(info, "industry", "")
    peers_html = ""
    peers_note_html = ""
    best_peer = None

    val_color = score_color(scores["valuation"], 35)
    fin_color = score_color(scores["financial"], 35)
    growth_color = score_color(scores["growth"], 30)

    today_str = datetime.now().strftime("%B %d, %Y · %H:%M ET")

    # Recommendation — single source of truth via get_signal()
    composite = scores["composite"]
    signal, is_value_buy, signal_reason = get_signal(scores, info)

    signal_text = signal.split(" ", 1)[-1] if " " in signal else signal
    recommendation = signal_text

    if "STRONG BUY" in recommendation:
        rec_color = "#00e5a0"; needle_pct = 90
    elif "BUY" in recommendation and "SPEC" not in recommendation:
        rec_color = "#00e5a0"; needle_pct = 75
    elif "SPECULATIVE" in recommendation:
        rec_color = "#f5a623"; needle_pct = 60
    elif "HOLD" in recommendation:
        rec_color = "#f5a623"; needle_pct = 45
    elif "STRONG SELL" in recommendation:
        rec_color = "#ff4d6d"; needle_pct = 10
    elif "SELL" in recommendation:
        rec_color = "#ff4d6d"; needle_pct = 25
    else:
        rec_color = "#f5a623"; needle_pct = 50

    upside = ((target_mean - current_price) / current_price * 100) if target_mean and current_price and current_price > 0 else 0

    # Card status with tooltip reason
    def cs(val, good, bad, metric_name="", lower_better=False):
        if val is None:
            return "caution", f"{metric_name}: Data unavailable"
        if lower_better:
            if val <= good:
                return "beat", f"{metric_name} at {val:.1f} is below {good} — attractive"
            elif val <= bad:
                return "caution", f"{metric_name} at {val:.1f} is between {good} and {bad} — moderate"
            else:
                return "miss", f"{metric_name} at {val:.1f} exceeds {bad} — elevated"
        else:
            if val >= good:
                return "beat", f"{metric_name} at {val:.1f} exceeds {good} — strong"
            elif val >= bad:
                return "caution", f"{metric_name} at {val:.1f} is between {bad} and {good} — moderate"
            else:
                return "miss", f"{metric_name} at {val:.1f} is below {bad} — weak"

    # ── Industry averages: sector benchmarks only (no US peer screen) ──

    # Pre-compute metric card statuses
    pe_cls, pe_tip = cs(pe_ratio, 20, 40, "P/E", True) if pe_ratio else ("caution", "P/E: Data unavailable")
    pb_cls, pb_tip = cs(pb_ratio, 3, 10, "P/B", True) if pb_ratio else ("caution", "P/B: Data unavailable")
    roe_cls, roe_tip = cs(roe * 100, 15, 8, "ROE %") if roe else ("caution", "ROE: Data unavailable")
    pm_cls, pm_tip = cs(profit_margin * 100, 10, 0, "Profit Margin %") if profit_margin else ("caution", "Profit Margin: Data unavailable")
    opm_pct = operating_margin * 100 if operating_margin else None
    opm_cls, opm_tip = cs(opm_pct, 15, 5, "OPM %") if opm_pct is not None else ("caution", "Operating Margin: Data unavailable")
    tgt_cls = "beat" if target_mean > current_price else "miss" if target_mean else "caution"
    tgt_tip = f"Analyst target ${target_mean:,.2f} vs CMP ${current_price:,.2f} — {'upside' if target_mean > current_price else 'downside'}" if target_mean else "Analyst target: Data unavailable"
    peg_cls, peg_tip = cs(peg_ratio, 1.0, 2.0, "PEG", True) if peg_ratio else ("caution", "PEG: Data unavailable")
    eve_cls, eve_tip = cs(ev_ebitda, 12, 20, "EV/EBITDA", True) if ev_ebitda else ("caution", "EV/EBITDA: Data unavailable")
    cr_cls, cr_tip = cs(current_ratio, 1.5, 1.0, "Current Ratio") if current_ratio else ("caution", "Current Ratio: Data unavailable")
    dy_cls, dy_tip = cs(dy_pct, 2, 0.5, "Div Yield %") if dy_pct is not None else ("caution", "Dividend Yield: Data unavailable")
    roa_cls, roa_tip = cs(roa * 100, 10, 5, "ROA %") if roa else ("caution", "ROA: Data unavailable")
    gm_cls, gm_tip = cs(gross_margin * 100, 40, 20, "Gross Margin %") if gross_margin else ("caution", "Gross Margin: Data unavailable")

    # Determine catalysts and risks dynamically
    catalysts = []
    risks = []

    if rev_growth and rev_growth > 0.15:
        catalysts.append(f"<strong>Revenue Growth {rev_growth*100:.0f}%:</strong> Strong top-line momentum indicating market demand.")
    elif rev_growth and rev_growth > 0:
        catalysts.append(f"<strong>Positive Revenue Growth:</strong> Revenue growing at {rev_growth*100:.1f}% YoY.")

    if roe and roe > 0.15:
        catalysts.append(f"<strong>High ROE ({roe*100:.1f}%):</strong> Strong return on equity indicating efficient capital use.")

    if profit_margin and profit_margin > 0.1:
        catalysts.append(f"<strong>Healthy Margins ({profit_margin*100:.1f}%):</strong> Good profitability profile.")

    if upside > 10 and target_mean:
        catalysts.append(f"<strong>Analyst Upside ({upside:.0f}%):</strong> Mean target of ${target_mean:,.2f} above current price.")

    if beta and beta < 1.0:
        catalysts.append(f"<strong>Low Beta ({beta:.2f}):</strong> Less volatile than market — defensive play.")

    if earnings_growth and earnings_growth > 0.1:
        catalysts.append(f"<strong>Earnings Growth ({earnings_growth*100:.0f}%):</strong> Strong profit expansion.")

    if len(catalysts) < 3:
        catalysts.append(f"<strong>Sector Opportunity:</strong> {sector} / {industry} — positioned in growth sector.")

    if pe_ratio and pe_ratio > 50:
        risks.append(f"<strong>High P/E ({pe_ratio:.1f}x):</strong> Expensive valuation leaves little room for error.")
    elif pe_ratio and pe_ratio > 30:
        risks.append(f"<strong>Moderate P/E ({pe_ratio:.1f}x):</strong> Valuation premium to broad market.")

    if pb_ratio and pb_ratio > 10:
        risks.append(f"<strong>High P/B ({pb_ratio:.1f}x):</strong> Significant book value premium.")

    if debt_equity and debt_equity > 100:
        risks.append(f"<strong>High Debt/Equity ({debt_equity:.0f}%):</strong> Leverage could amplify downside risk.")

    if beta and beta > 1.3:
        risks.append(f"<strong>High Beta ({beta:.2f}):</strong> More volatile than market — higher swing risk.")

    if upside < 0:
        risks.append(f"<strong>Below Analyst Target:</strong> CMP above mean target — limited upside consensus.")

    if rev_growth and rev_growth < 0:
        risks.append(f"<strong>Revenue Decline ({rev_growth*100:.1f}%):</strong> Top-line shrinking — negative trend.")

    if profit_margin and profit_margin < 0:
        risks.append(f"<strong>Loss-Making:</strong> Negative profit margin — path to profitability unclear.")

    while len(risks) < 3:
        risks.append(f"<strong>Market Risk:</strong> Broader market correction or sentiment shift could impact stock.")
        if len(risks) < 3:
            risks.append(f"<strong>Sector Risk:</strong> Regulatory or competitive changes in {sector} space.")
        if len(risks) < 3:
            risks.append(f"<strong>Execution Risk:</strong> Growth may not meet elevated expectations.")

    catalysts_html = "\n".join([f'<div class="col-item"><span class="col-icon">{"🏆💹🔀🇺🇸🔬📈"[i % 6]}</span><span>{c}</span></div>' for i, c in enumerate(catalysts[:6])])
    risks_html = "\n".join([f'<div class="col-item"><span class="col-icon">{"📜💰🔓⚔️📉🌐"[i % 6]}</span><span>{r}</span></div>' for i, r in enumerate(risks[:6])])

    # ── Decision matrix ──
    bench = get_sector_bench(sector)
    sector_pe_cheap, _, _ = bench["pe"]

    fii_trend_str = ""

    alt_peer = None
    alt_name = ""
    alt_pe_str = "—"
    alt_roce_str = "—"

    sector_median_pe = None

    opm_str = f"{opm_pct:.0f}%" if opm_pct is not None else "N/A"
    roce_val = None
    roce_str_dm = "N/A"

    buy_up = f"Capture {upside:.1f}% analyst upside" if upside > 0 else "Benefit from potential re-rating"
    if roce_val and roce_val > 20:
        buy_up += f"; strong {roce_str_dm} ROCE compounds"
    buy_down = f"OPM of {opm_str} provides margin buffer" if opm_pct and opm_pct > 10 else "Fundamentals provide base support"
    if sector_median_pe and pe_ratio and pe_ratio > sector_median_pe * 1.2:
        buy_down += f"; P/E {pe_ratio:.0f}x vs sector median {sector_median_pe:.0f}x is a risk"

    hold_up = "Retain existing position; wait for better entry"
    if fii_trend_str:
        hold_up += f"; {fii_trend_str}"
    hold_down = "Miss further upside if momentum continues"
    if returns.get("1M") and returns["1M"] > 5:
        hold_down += f"; 1M return of {returns['1M']:+.1f}% shows momentum"

    sell_up = f"Lock in {returns.get('1Y', 0):+.1f}% 1Y return" if returns.get("1Y") else "Lock in existing gains"
    if alt_peer and alt_peer.get("pe") and pe_ratio and alt_peer["pe"] < pe_ratio:
        sell_up += f"; redeploy into {alt_name} at lower P/E"
    sell_down = "Avoid further drawdown"
    if pe_ratio and sector_median_pe and pe_ratio > sector_median_pe * 1.3:
        sell_down += f"; P/E compression risk at {pe_ratio:.0f}x"

    dm_table_html = f'''<table>
    <thead><tr><th style="width:80px;">Action</th><th>If Stock Rises</th><th>If Stock Falls</th></tr></thead>
    <tbody>
    <tr style="border-left:3px solid var(--green);"><td style="color:var(--green);font-weight:700;">BUY</td><td>{buy_up}</td><td>{buy_down}</td></tr>
    <tr style="border-left:3px solid var(--amber);"><td style="color:var(--amber);font-weight:700;">HOLD</td><td>{hold_up}</td><td>{hold_down}</td></tr>
    <tr style="border-left:3px solid var(--red);"><td style="color:var(--red);font-weight:700;">SELL</td><td>{sell_up}</td><td>{sell_down}</td></tr>
    </tbody></table>'''

    # Build pros/cons lists
    buy_reasons = []
    sell_reasons = []

    if upside > 0 and target_mean:
        buy_reasons.append(f"Analyst upside of {upside:.1f}% with mean target of ${target_mean:,.2f}")
    if roce_val and roce_val > 15:
        buy_reasons.append(f"ROCE at {roce_str_dm} indicates strong capital efficiency")
    if fii_trend_str and "rising" in fii_trend_str:
        buy_reasons.append(f"{fii_trend_str} — signals institutional confidence")
    if roe and roe > 0.15:
        buy_reasons.append(f"ROE of {roe*100:.1f}% above sector threshold")
    if rev_growth and rev_growth > 0.1:
        buy_reasons.append(f"Revenue growing at {rev_growth*100:.1f}% YoY")
    if opm_pct and opm_pct > 15:
        buy_reasons.append(f"Operating margin of {opm_str} shows pricing power")

    if pe_ratio and sector_median_pe and pe_ratio > sector_median_pe * 1.2:
        sell_reasons.append(f"P/E of {pe_ratio:.1f}x is {pe_ratio/sector_median_pe:.1f}x the sector median of {sector_median_pe:.0f}x")
    elif pe_ratio and pe_ratio > 40:
        sell_reasons.append(f"P/E of {pe_ratio:.1f}x is elevated — premium priced in")
    if fii_trend_str and "falling" in fii_trend_str:
        sell_reasons.append(f"{fii_trend_str} — institutional exit signal")
    if alt_peer and alt_peer.get("pe") and alt_peer.get("roce") is not None:
        if pe_ratio and alt_peer["pe"] < pe_ratio:
            sell_reasons.append(f"{alt_name} offers lower P/E ({alt_pe_str}) with ROCE of {alt_roce_str} in the same sector")
    if returns.get("1Y") and returns["1Y"] > 40:
        sell_reasons.append(f"1Y return of {returns['1Y']:+.1f}% — profit booking opportunity")
    if upside < 0:
        sell_reasons.append(f"Trading above analyst target — consensus sees {upside:.1f}% downside")
    if debt_equity and debt_equity > bench["de"][1]:
        sell_reasons.append(f"Debt/Equity at {debt_equity:.0f}% exceeds sector comfort zone")

    if not buy_reasons:
        buy_reasons.append("Limited strong buy signals at current levels")
    if not sell_reasons:
        sell_reasons.append("No major red flags identified")

    buy_list_html = "\n".join(f'<li style="margin-bottom:6px;">{r}</li>' for r in buy_reasons[:4])
    sell_list_html = "\n".join(f'<li style="margin-bottom:6px;">{r}</li>' for r in sell_reasons[:4])

    decision_matrix_html = f'''
    <div style="overflow-x:auto;margin-bottom:16px;">{dm_table_html}</div>
    <div class="dual-col">
      <div class="col-card" style="border-left:3px solid var(--green);">
        <div class="col-title" style="color:var(--green);">REASONS TO BUY</div>
        <ul style="font-family:var(--mono);font-size:11px;color:var(--text2);line-height:1.7;padding-left:16px;">{buy_list_html}</ul>
      </div>
      <div class="col-card" style="border-left:3px solid var(--red);">
        <div class="col-title" style="color:var(--red);">REASONS TO SELL / AVOID</div>
        <ul style="font-family:var(--mono);font-size:11px;color:var(--text2);line-height:1.7;padding-left:16px;">{sell_list_html}</ul>
      </div>
    </div>'''

    # ── Verdict with competitor suggestion ──
    profit_status = "profitable" if profit_margin and profit_margin > 0 else "loss-making"

    competitor_line = ""

    if rev_growth is None:
        rev_growth_sentence = "Revenue growth data is unavailable."
    else:
        _rgp = rev_growth * 100
        _sfx = (
            " — a strong positive signal" if rev_growth > 0.15
            else ("" if rev_growth > 0 else " — a concern")
        )
        rev_growth_sentence = f"Revenue growth is at {_rgp:.1f}%{_sfx}."

    verdict_text = f'''<strong>{company_name}</strong> trades at ${current_price:,.2f} with a composite risk score of {composite}/100.
    The stock scores {scores["valuation"]}/35 on valuation, {scores["financial"]}/35 on financial health, and {scores["growth"]}/30 on growth.
    The company is currently {profit_status} with {"strong" if roe and roe > 0.15 else "moderate" if roe and roe > 0 else "negative"} return on equity.
    <br><br>
    {"Analyst consensus suggests upside of " + f"{upside:.1f}%" + f" with a mean target of ${target_mean:,.2f}." if target_mean and upside > 0 else "The stock is trading near or above analyst consensus targets."}
    {rev_growth_sentence}
    {competitor_line}
    <br><br>
    <strong>Bottom Line:</strong> {signal_reason}. The current recommendation is <strong style="color:{rec_color}">{recommendation}</strong>.'''

    tags = []
    if profit_margin and profit_margin > 0.1:
        tags.append(("PROFITABLE", "green"))
    if roe and roe > 0.15:
        tags.append(("HIGH ROE", "green"))
    if rev_growth and rev_growth > 0.2:
        tags.append(("STRONG GROWTH", "green"))
    if upside > 10:
        tags.append(("UPSIDE POTENTIAL", "green"))
    if pe_ratio and pe_ratio > 50:
        tags.append(("EXPENSIVE", "amber"))
    if pe_ratio and pe_ratio < 20 and pe_ratio > 0:
        tags.append(("CHEAP", "green"))
    if beta and beta > 1.3:
        tags.append(("VOLATILE", "red"))
    if debt_equity and debt_equity > 100:
        tags.append(("HIGH DEBT", "red"))
    if profit_margin and profit_margin < 0:
        tags.append(("LOSS-MAKING", "red"))

    tags_html = "\n".join([f'<span class="vtag {t[1]}">{t[0]}</span>' for t in tags])

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{ticker_u} · Risk Score Report</title>
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
  body {{ background: var(--bg); color: var(--text); font-family: var(--sans); font-size: 13px; line-height: 1.6; -webkit-font-smoothing: antialiased; }}
  ::-webkit-scrollbar {{ width: 4px; }} ::-webkit-scrollbar-track {{ background: var(--bg); }} ::-webkit-scrollbar-thumb {{ background: var(--border2); border-radius: 2px; }}
  .page {{ max-width: 1120px; margin: 0 auto; padding: 32px 24px; }}
  .stock-header {{ display:flex; align-items:flex-start; justify-content:space-between; padding:28px 32px; background:linear-gradient(135deg,#0f1018,#131420 60%,#0d1020); border:1px solid var(--border2); border-radius:16px; position:relative; overflow:hidden; margin-bottom:20px; }}
  .stock-header::before {{ content:''; position:absolute; top:0; left:0; right:0; height:1px; background:linear-gradient(90deg,transparent,var(--green),transparent); opacity:0.4; }}
  .sh-ticker {{ font-family:var(--mono); font-size:11px; font-weight:600; color:var(--green); letter-spacing:2px; margin-bottom:4px; display:flex; align-items:center; gap:8px; }}
  .badge {{ border-radius:4px; padding:1px 6px; font-size:9px; font-weight:600; }}
  .badge-us {{ background:var(--green-dim); color:var(--green); border:1px solid rgba(0,229,160,0.2); }}
  .badge-sector {{ background:var(--blue-dim); color:var(--blue); border:1px solid rgba(61,156,245,0.2); }}
  .sh-name {{ font-family:var(--mono); font-size:26px; font-weight:700; color:#fff; letter-spacing:-0.5px; margin-bottom:8px; }}
  .sh-meta {{ display:flex; gap:16px; flex-wrap:wrap; font-family:var(--mono); font-size:10px; color:var(--text2); }}
  .sh-right {{ text-align:right; }}
  .sh-price {{ font-family:var(--mono); font-size:36px; font-weight:700; color:#fff; letter-spacing:-1px; }}
  .sh-change {{ font-family:var(--mono); font-size:13px; font-weight:600; margin-top:4px; }}
  .sh-volume {{ font-family:var(--mono); font-size:10px; color:var(--text3); margin-top:8px; }}
  .sh-timestamp {{ font-family:var(--mono); font-size:9px; color:var(--text3); margin-top:4px; }}
  .sh-ranges {{ display:flex; flex-direction:column; gap:6px; margin-top:10px; }}
  .sh-range {{ display:flex; align-items:center; gap:6px; font-family:var(--mono); font-size:9px; }}
  .sh-range-label {{ color:var(--text3); width:32px; text-align:right; letter-spacing:0.5px; flex-shrink:0; }}
  .sh-range-val {{ color:var(--text3); width:42px; text-align:right; flex-shrink:0; }}
  .sh-range-track {{ flex:1; height:4px; background:var(--border); border-radius:2px; position:relative; min-width:80px; }}
  .sh-range-fill {{ height:100%; border-radius:2px; background:linear-gradient(90deg,var(--green),var(--green)); }}
  .sh-range-dot {{ position:absolute; top:50%; width:10px; height:10px; border-radius:50%; background:var(--green); border:2px solid var(--bg); transform:translate(-50%,-50%); box-shadow:0 0 6px rgba(0,229,160,0.5); }}
  .gauge-kpi-row {{ display:grid; grid-template-columns:280px 1fr; gap:16px; margin-bottom:20px; }}
  .gauge-card {{ background:var(--bg2); border:1px solid var(--border); border-radius:14px; padding:24px; display:flex; flex-direction:column; align-items:center; }}
  .gauge-title {{ font-family:var(--mono); font-size:9px; letter-spacing:2px; text-transform:uppercase; color:var(--text3); margin-bottom:8px; }}
  .kpi-strip {{ display:grid; grid-template-columns:repeat(3,1fr); gap:10px; }}
  .kpi-card {{ background:var(--bg2); border:1px solid var(--border); border-radius:12px; padding:14px 16px; transition:border-color 0.3s; }}
  .kpi-card:hover {{ border-color:var(--border2); }}
  .kpi-label {{ font-family:var(--mono); font-size:9px; letter-spacing:1.5px; text-transform:uppercase; color:var(--text3); margin-bottom:4px; }}
  .kpi-value {{ font-family:var(--mono); font-size:18px; font-weight:700; color:#fff; }}
  .kpi-sub {{ font-size:10px; color:var(--text2); margin-top:2px; }}
  .section {{ background:var(--bg2); border:1px solid var(--border); border-radius:14px; padding:22px; margin-bottom:20px; }}
  .section-title {{ font-family:var(--mono); font-size:10px; color:var(--text3); letter-spacing:2px; text-transform:uppercase; margin-bottom:16px; display:flex; align-items:center; gap:8px; }}
  .section-title::after {{ content:''; flex:1; height:1px; background:var(--border); }}
  .card-grid {{ display:grid; grid-template-columns:repeat(3,1fr); gap:12px; margin-bottom:16px; }}
  .metric-card {{ background:var(--bg3); border:1px solid var(--border); border-radius:12px; padding:16px; position:relative; transition:transform 0.2s,box-shadow 0.2s; }}
  .metric-card:hover {{ transform:translateY(-2px); box-shadow:0 4px 20px rgba(0,0,0,0.3); }}
  .metric-card.beat {{ border-color:rgba(0,229,160,0.25); background:linear-gradient(145deg,var(--bg3),rgba(0,229,160,0.04)); }}
  .metric-card.beat::before {{ content:'✓ BEAT'; position:absolute; top:10px; right:10px; font-family:var(--mono); font-size:8px; color:var(--green); background:var(--green-dim); border:1px solid rgba(0,229,160,0.2); border-radius:3px; padding:1px 5px; }}
  .metric-card.miss {{ border-color:rgba(255,77,109,0.25); background:linear-gradient(145deg,var(--bg3),rgba(255,77,109,0.04)); }}
  .metric-card.miss::before {{ content:'✕ MISS'; position:absolute; top:10px; right:10px; font-family:var(--mono); font-size:8px; color:var(--red); background:var(--red-dim); border:1px solid rgba(255,77,109,0.2); border-radius:3px; padding:1px 5px; }}
  .metric-card.caution {{ border-color:rgba(245,166,35,0.25); background:linear-gradient(145deg,var(--bg3),rgba(245,166,35,0.04)); }}
  .metric-card.caution::before {{ content:'⚠ CAUTION'; position:absolute; top:10px; right:10px; font-family:var(--mono); font-size:8px; color:var(--amber); background:var(--amber-dim); border:1px solid rgba(245,166,35,0.2); border-radius:3px; padding:1px 5px; }}
  .metric-card[data-tip] {{ cursor:pointer; }}
  .metric-card[data-tip]::after {{ content:attr(data-tip); position:absolute; bottom:100%; left:50%; transform:translateX(-50%); background:#1e1f2e; color:var(--text); border:1px solid var(--border2); border-radius:8px; padding:8px 12px; font-family:var(--mono); font-size:10px; line-height:1.5; white-space:normal; width:max-content; max-width:260px; z-index:50; pointer-events:none; opacity:0; transition:opacity 0.15s; box-shadow:0 4px 16px rgba(0,0,0,0.5); }}
  .metric-card[data-tip]:hover::after {{ opacity:1; }}
  .mc-label {{ font-family:var(--mono); font-size:9px; letter-spacing:1.5px; text-transform:uppercase; color:var(--text3); margin-bottom:6px; }}
  .mc-value {{ font-family:var(--mono); font-size:22px; font-weight:700; color:#fff; }}
  .mc-bench {{ font-size:10px; color:var(--text2); margin-top:4px; }}
  .breakdown-grid {{ display:grid; grid-template-columns:repeat(3,1fr); gap:12px; margin-bottom:20px; }}
  .breakdown-card {{ background:var(--bg3); border:1px solid var(--border); border-radius:12px; padding:18px; }}
  .bc-header {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:10px; }}
  .bc-title {{ font-family:var(--mono); font-size:9px; letter-spacing:1.5px; text-transform:uppercase; color:var(--text3); }}
  .bc-score {{ font-family:var(--mono); font-size:28px; font-weight:700; }}
  .bc-max {{ font-family:var(--mono); font-size:12px; color:var(--text3); }}
  .bc-bar-track {{ height:4px; background:var(--bg4); border-radius:2px; overflow:hidden; margin-bottom:12px; }}
  .bc-bar-fill {{ height:100%; border-radius:2px; }}
  .bc-items {{ list-style:none; }} .bc-items li {{ display:flex; align-items:center; gap:6px; font-size:10px; color:var(--text2); padding:3px 0; font-family:var(--mono); }}
  .bc-items li::before {{ content:'›'; color:var(--text3); }}
  .returns-strip {{ display:grid; grid-template-columns:repeat(7,1fr); gap:10px; }}
  .page-break {{ border:none; border-top:2px dashed var(--border2); margin:36px 0; position:relative; }}
  .page-break::after {{ content:'PAGE 2'; position:absolute; top:-10px; left:50%; transform:translateX(-50%); background:var(--bg); padding:0 12px; font-family:var(--mono); font-size:9px; color:var(--text3); letter-spacing:2px; }}
  table {{ width:100%; border-collapse:collapse; font-family:var(--mono); font-size:11px; }}
  thead th {{ padding:10px 12px; text-align:right; color:var(--text3); font-weight:500; font-size:9px; letter-spacing:1px; text-transform:uppercase; border-bottom:2px solid var(--border2); }}
  thead th:first-child {{ text-align:left; }}
  tbody tr {{ border-bottom:1px solid var(--border); transition:background 0.2s; }} tbody tr:hover {{ background:rgba(255,255,255,0.02); }}
  tbody td {{ padding:10px 12px; text-align:right; }} tbody td:first-child {{ text-align:left; color:var(--text2); }}
  .tg {{ color:var(--green)!important; }} .tr {{ color:var(--red)!important; }} .ta {{ color:var(--amber)!important; }}
  .dual-col {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-bottom:20px; }}
  .col-card {{ background:var(--bg3); border:1px solid var(--border); border-radius:12px; padding:18px; }}
  .col-title {{ font-family:var(--mono); font-size:10px; color:var(--text3); letter-spacing:1.5px; text-transform:uppercase; margin-bottom:12px; }}
  .col-item {{ display:flex; align-items:flex-start; gap:8px; padding:8px 0; border-bottom:1px solid var(--border); font-size:12px; color:var(--text2); line-height:1.5; }}
  .col-item:last-child {{ border-bottom:none; }}
  .col-icon {{ font-size:14px; min-width:20px; text-align:center; }}
  .news-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:12px; }}
  .news-card {{ background:var(--bg3); border:1px solid var(--border); border-radius:10px; padding:14px; transition:border-color 0.3s; }}
  .news-card:hover {{ border-color:var(--border2); }}
  .news-title {{ font-family:var(--mono); font-size:11px; color:#fff; line-height:1.5; margin-bottom:6px; }}
  .news-meta {{ font-family:var(--mono); font-size:9px; color:var(--text3); }}
  .verdict-card {{ background:linear-gradient(135deg,#0d0e18,#10111e); border:1px solid var(--border2); border-radius:16px; padding:28px; position:relative; overflow:hidden; margin-bottom:20px; }}
  .verdict-card::before {{ content:''; position:absolute; top:0; left:0; right:0; height:2px; background:linear-gradient(90deg,var(--red),var(--amber),var(--green)); }}
  .verdict-header {{ display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:20px; }}
  .verdict-rec {{ font-family:var(--mono); font-size:10px; letter-spacing:2px; color:var(--text3); }}
  .verdict-rating {{ font-family:var(--mono); font-size:32px; font-weight:700; }}
  .verdict-score {{ font-family:var(--mono); font-size:14px; }}
  .rating-bar-track {{ width:100%; height:6px; background:linear-gradient(90deg,var(--red) 0%,var(--amber) 50%,var(--green) 100%); border-radius:3px; position:relative; margin-bottom:24px; }}
  .rating-needle {{ position:absolute; top:-4px; width:14px; height:14px; background:#fff; border-radius:50%; transform:translateX(-50%); box-shadow:0 0 8px rgba(255,255,255,0.4); }}
  .verdict-text {{ font-size:13px; color:var(--text2); line-height:1.7; border-left:3px solid var(--amber); padding-left:16px; }}
  .verdict-tags {{ display:flex; flex-wrap:wrap; gap:8px; margin-top:16px; }}
  .vtag {{ font-family:var(--mono); font-size:9px; letter-spacing:1px; padding:4px 10px; border-radius:4px; border:1px solid; }}
  .vtag.green {{ color:var(--green); border-color:rgba(0,229,160,0.3); background:var(--green-dim); }}
  .vtag.red {{ color:var(--red); border-color:rgba(255,77,109,0.3); background:var(--red-dim); }}
  .vtag.amber {{ color:var(--amber); border-color:rgba(245,166,35,0.3); background:var(--amber-dim); }}
  .vtag.blue {{ color:var(--blue); border-color:rgba(61,156,245,0.3); background:var(--blue-dim); }}
  .copy-btn {{ position:fixed; bottom:24px; right:24px; background:var(--bg3); border:1px solid var(--border2); border-radius:10px; padding:10px 16px; font-family:var(--mono); font-size:10px; color:var(--text2); cursor:pointer; display:flex; align-items:center; gap:6px; z-index:100; letter-spacing:1px; transition:all 0.3s; }}
  .copy-btn:hover {{ background:var(--bg4); color:#fff; border-color:var(--green); box-shadow:0 0 20px rgba(0,229,160,0.15); }}
  .footer {{ text-align:center; font-family:var(--mono); font-size:9px; color:var(--text3); letter-spacing:1px; padding:24px 0; border-top:1px solid var(--border); margin-top:8px; }}
  @keyframes fadeIn {{ from {{ opacity:0; transform:translateY(10px); }} to {{ opacity:1; transform:translateY(0); }} }}
  .section, .stock-header, .gauge-kpi-row, .breakdown-grid, .verdict-card {{ animation: fadeIn 0.6s ease both; }}
  @media (max-width: 768px) {{ .stock-header {{ flex-direction:column; gap:16px; }} .gauge-kpi-row {{ grid-template-columns:1fr; }} .card-grid {{ grid-template-columns:1fr 1fr; }} .breakdown-grid {{ grid-template-columns:1fr; }} .dual-col {{ grid-template-columns:1fr; }} .kpi-strip {{ grid-template-columns:repeat(2,1fr); }} .returns-strip {{ grid-template-columns:repeat(3,1fr); }} .news-grid {{ grid-template-columns:1fr; }} }}
  @media print {{ .copy-btn {{ display:none; }} .page {{ padding:16px; }} .page-break {{ page-break-before:always; border:none; margin:0; }} }}
</style>
</head>
<body>
<div id="report-content">
<div class="page">

  <div class="stock-header">
    <div>
      <div class="sh-ticker"><span>{ticker_u}</span><span class="badge badge-us">US</span><span class="badge badge-sector">{sector}</span></div>
      <div class="sh-name">{company_name}</div>
      <div class="sh-meta"><span>📊 {industry}</span></div>
      <div class="sh-ranges">
        <div class="sh-range">
          <span class="sh-range-label">Day</span>
          <span class="sh-range-val">${day_low:,.0f}</span>
          <div class="sh-range-track"><div class="sh-range-fill" style="width:{day_pct:.1f}%"></div><div class="sh-range-dot" style="left:{day_pct:.1f}%"></div></div>
          <span class="sh-range-val">${day_high:,.0f}</span>
        </div>
        <div class="sh-range">
          <span class="sh-range-label">52W</span>
          <span class="sh-range-val">${low_52w:,.0f}</span>
          <div class="sh-range-track"><div class="sh-range-fill" style="width:{w52_pct:.1f}%"></div><div class="sh-range-dot" style="left:{w52_pct:.1f}%"></div></div>
          <span class="sh-range-val">${high_52w:,.0f}</span>
        </div>
      </div>
    </div>
    <div class="sh-right">
      <div class="sh-price">${current_price:,.2f}</div>
      <div class="sh-change" style="color:{change_color}">{change_icon} ${abs(change):,.2f} ({change_pct:+.2f}%)</div>
      <div class="sh-volume">Vol: {volume:,} · Avg: {avg_volume:,}</div>
      <div class="sh-timestamp">As of {today_str}</div>
    </div>
  </div>

  <div class="gauge-kpi-row">
    <div class="gauge-card">
      <div class="gauge-title">COMPOSITE RISK SCORE</div>
      {gauge_svg}
      <div style="font-family:var(--mono);font-size:9px;color:var(--text3);margin-top:8px;letter-spacing:1px;">
        VAL:{scores["valuation"]}/35 · FIN:{scores["financial"]}/35 · GRO:{scores["growth"]}/30
      </div>
    </div>
    <div class="kpi-strip">
      <div class="kpi-card"><div class="kpi-label">📈 P/E RATIO</div><div class="kpi-value">{f"{pe_ratio:.1f}x" if pe_ratio else "N/A"}</div><div class="kpi-sub">Trailing</div></div>
      <div class="kpi-card"><div class="kpi-label">📖 P/B RATIO</div><div class="kpi-value">{f"{pb_ratio:.1f}x" if pb_ratio else "N/A"}</div><div class="kpi-sub">Price to Book</div></div>
      <div class="kpi-card"><div class="kpi-label">💰 EPS</div><div class="kpi-value">{f"${eps:,.2f}" if eps else "N/A"}</div><div class="kpi-sub">TTM</div></div>
      <div class="kpi-card"><div class="kpi-label">🏛 MARKET CAP</div><div class="kpi-value">{fmt_val(market_cap) if market_cap else "N/A"}</div><div class="kpi-sub">{mcap_cap_label} Cap</div></div>
      <div class="kpi-card"><div class="kpi-label">📊 ROE</div><div class="kpi-value">{f"{roe*100:.1f}%" if roe else "N/A"}</div><div class="kpi-sub">Return on Equity</div></div>
      <div class="kpi-card"><div class="kpi-label">📈 REV GROWTH</div><div class="kpi-value">{f"{rev_growth*100:.1f}%" if rev_growth is not None else "N/A"}</div><div class="kpi-sub">YoY</div></div>
    </div>
  </div>

  <div class="section">
    <div class="section-title">📈 12-Month Price Movement · Annotated</div>
    {price_chart_svg}
  </div>

  <div class="section">
    <div class="section-title">🕯 Daily Candlestick Chart · 50 EMA & 200 DMA</div>
    {candle_chart_svg}
  </div>

  <div class="section">
    <div class="section-title">🎯 Fair Value Analysis · CMP vs Analyst Targets</div>
    {fair_value_svg}
  </div>

  <div class="section">
    <div class="section-title">💎 Valuation & Financial Metrics</div>
    <div class="card-grid">
      <div class="metric-card {pe_cls}" data-tip="{pe_tip}"><div class="mc-label">P/E RATIO</div><div class="mc-value">{f"{pe_ratio:.1f}x" if pe_ratio else "N/A"}</div><div class="mc-bench">Trailing twelve months</div></div>
      <div class="metric-card {pb_cls}" data-tip="{pb_tip}"><div class="mc-label">P/B RATIO</div><div class="mc-value">{f"{pb_ratio:.1f}x" if pb_ratio else "N/A"}</div><div class="mc-bench">Price to Book value</div></div>
      <div class="metric-card {roe_cls}" data-tip="{roe_tip}"><div class="mc-label">ROE</div><div class="mc-value">{f"{roe*100:.1f}%" if roe else "N/A"}</div><div class="mc-bench">Return on Equity</div></div>
      <div class="metric-card {pm_cls}" data-tip="{pm_tip}"><div class="mc-label">PROFIT MARGIN</div><div class="mc-value">{f"{profit_margin*100:.1f}%" if profit_margin is not None else "N/A"}</div><div class="mc-bench">Net profit margin</div></div>
      <div class="metric-card {opm_cls}" data-tip="{opm_tip}"><div class="mc-label">OPM</div><div class="mc-value">{f"{opm_pct:.1f}%" if opm_pct is not None else "N/A"}</div><div class="mc-bench">Operating profit margin</div></div>
      <div class="metric-card {tgt_cls}" data-tip="{tgt_tip}"><div class="mc-label">ANALYST TARGET</div><div class="mc-value">{f"${target_mean:,.2f}" if target_mean else "N/A"}</div><div class="mc-bench">Range: {f"${fair_value_low:,.2f} - ${fair_value_high:,.2f}" if fair_value_low and fair_value_high else "N/A"}</div></div>
      <div class="metric-card {peg_cls}" data-tip="{peg_tip}"><div class="mc-label">PEG RATIO</div><div class="mc-value">{f"{peg_ratio:.2f}" if peg_ratio else "N/A"}</div><div class="mc-bench">Price/Earnings to Growth</div></div>
      <div class="metric-card {eve_cls}" data-tip="{eve_tip}"><div class="mc-label">EV/EBITDA</div><div class="mc-value">{f"{ev_ebitda:.1f}x" if ev_ebitda else "N/A"}</div><div class="mc-bench">Enterprise value ratio</div></div>
      <div class="metric-card {cr_cls}" data-tip="{cr_tip}"><div class="mc-label">CURRENT RATIO</div><div class="mc-value">{f"{current_ratio:.2f}" if current_ratio else "N/A"}</div><div class="mc-bench">Liquidity measure</div></div>
      <div class="metric-card {dy_cls}" data-tip="{dy_tip}"><div class="mc-label">DIVIDEND YIELD</div><div class="mc-value">{f"{dy_pct:.2f}%" if dy_pct is not None else "N/A"}</div><div class="mc-bench">Annual yield</div></div>
      <div class="metric-card {roa_cls}" data-tip="{roa_tip}"><div class="mc-label">ROA</div><div class="mc-value">{f"{roa*100:.1f}%" if roa else "N/A"}</div><div class="mc-bench">Return on Assets</div></div>
      <div class="metric-card {gm_cls}" data-tip="{gm_tip}"><div class="mc-label">GROSS MARGIN</div><div class="mc-value">{f"{gross_margin*100:.1f}%" if gross_margin else "N/A"}</div><div class="mc-bench">Gross profit margin</div></div>
    </div>
    {"" if not (industry_name or sector) else f"""<div style="margin-top:14px;padding:14px 16px;background:rgba(255,255,255,0.02);border:1px solid var(--border2);border-radius:8px;">
      <div style="font-family:var(--mono);font-size:9px;letter-spacing:1.5px;color:var(--text3);margin-bottom:10px;">SECTOR BENCHMARKS — {(industry_name or sector or "SECTOR").upper()}</div>
      <div style="display:flex;flex-wrap:wrap;gap:20px;">
        <div style="font-family:var(--mono);font-size:11px;"><span style="color:var(--text3);">P/E (fair)</span> <span style="color:#fff;font-weight:600;">{bench["pe"][1]:.1f}x</span> <span style="color:var(--text3);font-size:9px;">(sector mid)</span></div>
        <div style="font-family:var(--mono);font-size:11px;"><span style="color:var(--text3);">P/B (fair)</span> <span style="color:#fff;font-weight:600;">{bench["pb"][1]:.1f}x</span> <span style="color:var(--text3);font-size:9px;">(sector mid)</span></div>
        <div style="font-family:var(--mono);font-size:11px;"><span style="color:var(--text3);">ROE (good)</span> <span style="color:#fff;font-weight:600;">{bench["roe"][1]*100:.0f}%</span> <span style="color:var(--text3);font-size:9px;">(sector target)</span></div>
        <div style="font-family:var(--mono);font-size:11px;"><span style="color:var(--text3);">OPM (good)</span> <span style="color:#fff;font-weight:600;">{bench["margin"][1]*100:.0f}%</span> <span style="color:var(--text3);font-size:9px;">(sector target)</span></div>
        <div style="font-family:var(--mono);font-size:11px;"><span style="color:var(--text3);">D/E comfort</span> <span style="color:#fff;font-weight:600;">&lt;{bench["de"][0]:.0f}</span> <span style="color:var(--text3);font-size:9px;">(sector)</span></div>
      </div>
    </div>"""}
  </div>

  <div class="breakdown-grid">
    <div class="breakdown-card">
      <div class="bc-header"><div><div class="bc-title">VALUATION</div><div class="bc-score" style="color:{val_color}">{scores["valuation"]}<span class="bc-max">/35</span></div></div><div style="font-family:var(--mono);font-size:10px;color:var(--text3);">35% WEIGHT</div></div>
      <div class="bc-bar-track"><div class="bc-bar-fill" style="width:{scores['valuation']/35*100:.0f}%;background:{val_color};box-shadow:0 0 8px {val_color}44;"></div></div>
      <ul class="bc-items">
        <li>P/E at {f"{pe_ratio:.0f}x" if pe_ratio else "N/A"}</li>
        <li>P/B at {f"{pb_ratio:.1f}x" if pb_ratio else "N/A"}</li>
        <li>Analyst target: {f'${target_mean:,.2f}' if target_mean else 'N/A'} ({upside:+.1f}%)</li>
        <li>1Y return: {return_1y:+.1f}%</li>
      </ul>
    </div>
    <div class="breakdown-card">
      <div class="bc-header"><div><div class="bc-title">FINANCIAL HEALTH</div><div class="bc-score" style="color:{fin_color}">{scores["financial"]}<span class="bc-max">/35</span></div></div><div style="font-family:var(--mono);font-size:10px;color:var(--text3);">35% WEIGHT</div></div>
      <div class="bc-bar-track"><div class="bc-bar-fill" style="width:{scores['financial']/35*100:.0f}%;background:{fin_color};box-shadow:0 0 8px {fin_color}44;"></div></div>
      <ul class="bc-items">
        <li>ROE: {f"{roe*100:.1f}%" if roe else "N/A"}</li>
        <li>Profit margin: {f"{profit_margin*100:.1f}%" if profit_margin is not None else "N/A"}</li>
        <li>Revenue growth: {f"{rev_growth*100:.1f}%" if rev_growth is not None else "N/A"}</li>
        <li>Debt/Equity: {f"{debt_equity:.0f}%" if debt_equity is not None else "N/A"}</li>
      </ul>
    </div>
    <div class="breakdown-card">
      <div class="bc-header"><div><div class="bc-title">GROWTH</div><div class="bc-score" style="color:{growth_color}">{scores["growth"]}<span class="bc-max">/30</span></div></div><div style="font-family:var(--mono);font-size:10px;color:var(--text3);">30% WEIGHT</div></div>
      <div class="bc-bar-track"><div class="bc-bar-fill" style="width:{scores['growth']/30*100:.0f}%;background:{growth_color};box-shadow:0 0 8px {growth_color}44;"></div></div>
      <ul class="bc-items">
        <li>Revenue growth: {f"{rev_growth*100:.1f}%" if rev_growth is not None else "N/A"}</li>
        <li>Earnings growth: {f"{earnings_growth*100:.1f}%" if earnings_growth is not None else "N/A"}</li>
        <li>Beta: {beta:.2f}</li>
        <li>Sector: {sector}</li>
      </ul>
    </div>
  </div>

  <div class="section">
    <div class="section-title">⏱ Returns Across Time Horizons</div>
    <div class="returns-strip">{returns_html}</div>
  </div>

  <hr class="page-break">

  <div class="section">
    <div class="section-title">📋 Quarterly Performance Trend</div>
    <div style="overflow-x:auto;">
    <table>
      <thead><tr><th>Quarter</th><th>Revenue</th><th>QoQ %</th><th>Net Profit</th><th>QoQ %</th><th>Op. Cash Flow</th><th>EBITDA Margin</th></tr></thead>
      <tbody>{qt_rows_html}</tbody>
    </table>
    </div>
  </div>

  <div class="section">
    <div class="section-title">📊 Year-on-Year Trend</div>
    <div style="overflow-x:auto;">
    <table>
      <thead><tr><th>FY</th><th>Revenue</th><th>YoY %</th><th>Net Profit</th><th>YoY %</th><th>Op. Cash Flow</th><th>YoY %</th></tr></thead>
      <tbody>{yoy_rows_html}</tbody>
    </table>
    </div>
  </div>

  <div class="section">
    <div class="section-title">🏛 Shareholding Pattern</div>
    {shareholding_section_html}
  </div>

  <div class="dual-col">
    <div class="col-card">
      <div class="col-title" style="color:var(--green);">🟢 CATALYSTS</div>
      {catalysts_html}
    </div>
    <div class="col-card">
      <div class="col-title" style="color:var(--red);">🔴 RISKS</div>
      {risks_html}
    </div>
  </div>

  <div class="section">
    <div class="section-title">🕸 Factor Analysis · Radar</div>
    <div style="display:flex;gap:20px;align-items:center;flex-wrap:wrap;">
      <div style="flex:0 0 auto;max-width:420px;">
        {spider_svg}
      </div>
      <div style="flex:1;min-width:240px;display:flex;flex-direction:column;gap:8px;">
        {''.join(f'<div style="font-family:var(--mono);font-size:10px;padding:10px 12px;background:rgba(255,255,255,0.02);border-radius:6px;border-left:3px solid {"#00e5a0" if factor_scores[k]>=7 else "#f5a623" if factor_scores[k]>=4 else "#ff4d6d"};"><span style="color:#fff;font-weight:600;">{k}</span> <span style="color:{"#00e5a0" if factor_scores[k]>=7 else "#f5a623" if factor_scores[k]>=4 else "#ff4d6d"};font-weight:700;">{factor_scores[k]}/10</span><br><span style="color:var(--text3);">{factor_reasons.get(k,"")}</span></div>' for k in factor_scores)}
      </div>
    </div>
  </div>

  

  <div class="section">
    <div class="section-title">🎯 Decision Matrix — Game Theory</div>
    {decision_matrix_html}
  </div>

  <div class="section">
    <div class="section-title">📰 Latest News</div>
    <div class="news-grid">{news_html}</div>
  </div>

  <div class="verdict-card">
    <div class="verdict-header">
      <div><div class="verdict-rec">RECOMMENDATION</div><div class="verdict-rating" style="color:{rec_color}">{recommendation}</div></div>
      <div style="text-align:right;"><div class="verdict-rec">COMPOSITE SCORE</div><div class="verdict-score" style="color:{rec_color}"><span style="font-size:28px;font-weight:700;">{scores["composite"]}</span>/100</div></div>
    </div>
    <div class="rating-bar-track"><div class="rating-needle" style="left:{needle_pct}%;"></div></div>
    <div class="verdict-text">{verdict_text}</div>
    <div class="verdict-tags">{tags_html}</div>
  </div>

  <div class="footer">
    RISK SCORE REPORT · {ticker_u} · GENERATED {datetime.now().strftime("%b %d, %Y %H:%M ET").upper()} · DATA VIA YAHOO FINANCE<br>
    DISCLAIMER: THIS IS NOT FINANCIAL ADVICE. DATA MAY BE DELAYED. ALWAYS VERIFY WITH OFFICIAL SOURCES BEFORE INVESTING.
  </div>

</div>
</div>

<button class="copy-btn" onclick="copyReport()" id="copyBtn">📋 COPY REPORT</button>
<script>
function copyReport() {{
  const content = document.getElementById('report-content').innerText;
  navigator.clipboard.writeText(content).then(() => {{
    const btn = document.getElementById('copyBtn');
    btn.innerHTML = '✓ COPIED!';
    btn.style.borderColor = '#00e5a0';
    setTimeout(() => {{ btn.innerHTML = '📋 COPY REPORT'; btn.style.borderColor = ''; }}, 2000);
  }});
}}
const observer = new IntersectionObserver((entries) => {{
  entries.forEach(entry => {{ if (entry.isIntersecting) {{ entry.target.style.opacity = '1'; entry.target.style.transform = 'translateY(0)'; }} }});
}}, {{ threshold: 0.1 }});
document.querySelectorAll('.section, .breakdown-card, .metric-card').forEach(el => {{
  el.style.opacity = '0'; el.style.transform = 'translateY(20px)'; el.style.transition = 'opacity 0.5s ease, transform 0.5s ease';
  observer.observe(el);
}});
</script>
</body>
</html>'''

    return html


# ─────────────────────────────────────────────────────────────────────────────
# ALERT SUMMARY GENERATOR (for GitHub Actions notifications)
# ─────────────────────────────────────────────────────────────────────────────

GITHUB_REPORT_BASE = "https://htmlpreview.github.io/?https://github.com/nageshnnazare/recos/blob/main/us_reports"


def generate_alerts_summary(results, output_dir, date_str=None):
    """Generate a markdown summary of all stock alerts."""
    today = date_str or datetime.now().strftime("%Y-%m-%d")
    alerts = []
    all_rows = []

    for r in results:
        if r["status"] != "success":
            continue
        ticker = r["ticker"]
        scores = r["scores"]
        info = r["info"]
        signal, is_value_buy, reason = get_signal(scores, info)

        current = safe_get(info, "currentPrice", safe_get(info, "regularMarketPrice", 0))
        target = safe_get(info, "targetMeanPrice", 0)
        upside = ((target - current) / current * 100) if target and current and current > 0 else 0

        report_url = f"{GITHUB_REPORT_BASE}/{today}/{ticker}_RiskReport.html"
        row = f"| {ticker} | ${current:,.2f} | {scores['composite']}/100 | {signal} | {upside:+.1f}% | [Report]({report_url}) |"
        all_rows.append(row)

        if is_value_buy:
            alerts.append({
                "ticker": ticker,
                "price": current,
                "score": scores["composite"],
                "signal": signal,
                "upside": upside,
                "reason": reason,
            })

    md = f"""# 📊 Daily US Stock Risk Report — {today}

## 🔔 Action Required

"""
    if alerts:
        md += "### 🟢 Value Buy Opportunities\n\n"
        for a in alerts:
            md += f"""**{a['ticker']}** — ${a['price']:,.2f}
- Score: {a['score']}/100 | Signal: {a['signal']}
- Upside: {a['upside']:+.1f}% to analyst target
- Reason: {a['reason']}

"""
    else:
        md += "> No value-buy signals detected today. All positions at current levels.\n\n"

    md += """## 📋 Full Watchlist Summary

| Stock | CMP | Score | Signal | Upside | Report |
|-------|-----|-------|--------|--------|--------|
"""
    md += "\n".join(all_rows)

    md += f"""

---
*Generated on {today} · Data via Yahoo Finance · Not financial advice*
"""

    summary_file = os.path.join(output_dir, "DAILY_SUMMARY.md")
    with open(summary_file, "w", encoding="utf-8") as f:
        f.write(md)

    return summary_file, alerts


# ─────────────────────────────────────────────────────────────────────────────
# WATCHLIST READER
# ─────────────────────────────────────────────────────────────────────────────

def read_watchlist(filepath):
    """Read ticker symbols from a watchlist file."""
    tickers = []
    with open(filepath, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                for t in line.split(","):
                    t = t.strip().upper()
                    if t:
                        tickers.append(t)
    return tickers


def cleanup_old_reports(reports_root, keep_days=15):
    """Delete report date-folders older than keep_days."""
    cutoff = datetime.now() - timedelta(days=keep_days)
    removed = 0
    if not os.path.isdir(reports_root):
        return 0
    for name in sorted(os.listdir(reports_root)):
        dirpath = os.path.join(reports_root, name)
        if not os.path.isdir(dirpath):
            continue
        try:
            dir_date = datetime.strptime(name, "%Y-%m-%d")
            if dir_date < cutoff:
                shutil.rmtree(dirpath)
                removed += 1
        except ValueError:
            continue
    return removed


# ─────────────────────────────────────────────────────────────────────────────
# MAIN CLI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="US Stock Risk Score Report Generator (No API Key Required)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python us_report_generator.py AAPL
  python us_report_generator.py MSFT NVDA
  python us_report_generator.py --watchlist us_watchlist.txt
  python us_report_generator.py --watchlist us_watchlist.txt --alerts
  python us_report_generator.py AAPL -o ./us_reports/
        """,
    )

    parser.add_argument("tickers", nargs="*", help="US ticker symbol(s)")
    parser.add_argument("-w", "--watchlist", help="Path to watchlist file with tickers")
    parser.add_argument("-o", "--output-dir", default="./us_reports", help="Output directory (default: ./us_reports)")
    parser.add_argument("--alerts", action="store_true", help="Generate alerts summary markdown")

    args = parser.parse_args()

    tickers = []
    if args.watchlist:
        tickers = read_watchlist(args.watchlist)
        print(f"📋 Loaded {len(tickers)} tickers from {args.watchlist}")
    if args.tickers:
        tickers.extend([t.upper().strip() for t in args.tickers])

    if not tickers:
        parser.print_help()
        print("\n❌ No tickers provided. Use positional args or --watchlist file.")
        sys.exit(1)

    seen = set()
    unique_tickers = []
    for t in tickers:
        if t not in seen:
            seen.add(t)
            unique_tickers.append(t)
    tickers = unique_tickers

    reports_root = args.output_dir
    today_str = datetime.now().strftime("%Y-%m-%d")
    output_dir = os.path.join(reports_root, today_str)
    os.makedirs(output_dir, exist_ok=True)

    removed = cleanup_old_reports(reports_root, keep_days=15)
    if removed:
        print(f"🧹 Cleaned up {removed} report folder(s) older than 15 days")

    print("=" * 62)
    print("  US Stock Risk Score Report Generator")
    print("  No API Key Required · Powered by yfinance")
    print(f"  Stocks: {', '.join(tickers)}")
    print(f"  Date:   {today_str}")
    print(f"  Output: {os.path.abspath(output_dir)}/")
    print("=" * 62)
    print()

    results = []

    for i, ticker in enumerate(tickers, 1):
        tu = ticker.upper()
        print(f"[{i}/{len(tickers)}] Processing {tu}...")

        try:
            data = fetch_stock_data(tu)
            scores = calculate_risk_scores(data)
            signal, is_value_buy, reason = get_signal(scores, data["info"])
            print(f"  🧮 Score: {scores['composite']}/100 | {signal}")

            html = generate_html_report(data, scores)
            output_file = os.path.join(output_dir, f"{tu}_RiskReport.html")
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(html)

            file_size = os.path.getsize(output_file) / 1024
            print(f"  ✅ Saved: {output_file} ({file_size:.1f} KB)")

            if is_value_buy:
                print(f"  🟢 ** VALUE BUY ALERT ** — {reason}")

            results.append({
                "ticker": tu,
                "file": output_file,
                "status": "success",
                "scores": scores,
                "info": data["info"],
                "is_value_buy": is_value_buy,
                "signal": signal,
            })

        except Exception as e:
            print(f"  ❌ Failed: {e}")
            results.append({"ticker": tu, "status": "failed", "error": str(e)})

        print()

    if args.alerts or len(tickers) > 1:
        print("📝 Generating daily summary...")
        summary_file, alerts = generate_alerts_summary(results, output_dir, today_str)
        print(f"  📄 Summary: {summary_file}")

        root_summary = os.path.join(reports_root, "DAILY_SUMMARY.md")
        shutil.copy2(summary_file, root_summary)

        if alerts:
            print(f"\n  🔔 {len(alerts)} VALUE BUY ALERT(S):")
            for a in alerts:
                print(f"     🟢 {a['ticker']} — ${a['price']:,.2f} (Score: {a['score']}, Upside: {a['upside']:+.1f}%)")
        else:
            print("  ℹ️  No value-buy alerts today.")

    success = sum(1 for r in results if r["status"] == "success")
    failed = len(results) - success
    print(f"\n{'=' * 62}")
    print(f"  DONE: {success} reports generated, {failed} failed")
    print(f"  📂 Reports in: {os.path.abspath(output_dir)}/")
    print(f"  📅 Keeping last 15 days of reports")
    print(f"{'=' * 62}\n")


if __name__ == "__main__":
    main()
