#!/usr/bin/env python3
"""
NSE Stock Risk Score Report Generator (No API Key Required)
============================================================
Generates 2-page dark HTML risk score reports for any NSE stock
using yfinance for live data. No prompting or API keys needed.

Usage:
    # Single stock
    python report_generator.py GROWW
    python report_generator.py RELIANCE

    # Multiple stocks
    python report_generator.py GROWW RELIANCE INFY

    # From watchlist file
    python report_generator.py --watchlist watchlist.txt

    # Generate alerts summary (for GitHub Actions)
    python report_generator.py --watchlist watchlist.txt --alerts

    # Custom output directory
    python report_generator.py GROWW -o ./reports/

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
# DATA FETCHING (Generic for any NSE ticker)
# ─────────────────────────────────────────────────────────────────────────────

def fetch_stock_data(ticker_symbol):
    """Fetch all required data for any NSE stock from yfinance."""
    yf_symbol = f"{ticker_symbol}.NS"
    print(f"  📊 Fetching live data for NSE:{ticker_symbol}...")

    ticker = yf.Ticker(yf_symbol)

    result = {"ticker_symbol": ticker_symbol, "yf_symbol": yf_symbol}

    # Basic info
    try:
        result["info"] = ticker.info or {}
    except Exception as e:
        print(f"    ⚠ Could not fetch info: {e}")
        result["info"] = {}

    # Historical price data (1 year)
    try:
        result["hist_1y"] = ticker.history(period="1y")
    except Exception as e:
        print(f"    ⚠ Could not fetch 1Y history: {e}")
        result["hist_1y"] = None

    # Historical price data (6 months for candle chart)
    try:
        result["hist_6m"] = ticker.history(period="6mo")
    except Exception as e:
        print(f"    ⚠ Could not fetch 6M history: {e}")
        result["hist_6m"] = None

    # Quarterly income statement
    try:
        result["quarterly_income"] = ticker.quarterly_income_stmt
    except Exception as e:
        print(f"    ⚠ Could not fetch quarterly income: {e}")
        result["quarterly_income"] = None

    # Quarterly balance sheet
    try:
        result["balance_sheet"] = ticker.quarterly_balance_sheet
    except Exception as e:
        print(f"    ⚠ Could not fetch quarterly balance sheet: {e}")
        result["balance_sheet"] = None

    # Annual income statement
    try:
        result["financials"] = ticker.financials
    except Exception as e:
        print(f"    ⚠ Could not fetch annual financials: {e}")
        result["financials"] = None

    # Annual balance sheet
    try:
        result["annual_balance_sheet"] = ticker.balance_sheet
    except Exception as e:
        print(f"    ⚠ Could not fetch annual balance sheet: {e}")
        result["annual_balance_sheet"] = None

    result["ticker_obj"] = ticker
    return result


def calculate_roe_manual(data):
    """
    Calculate Return on Equity manualy if info['returnOnEquity'] is missing.
    ROE = Net Income / Common Stock Equity
    """
    info = data.get("info", {})
    roe = safe_get(info, "returnOnEquity")
    
    # If info has ROE (and it's not exactly 0.0 which is rare for large firms), use it
    if roe is not None and roe != 0:
        return roe
        
    # Manual fallback using annual reports
    try:
        f = data.get("financials")
        b = data.get("annual_balance_sheet")
        
        if f is not None and not f.empty and b is not None and not b.empty:
            # Get latest annual net income
            # Try multiple keys because yfinance indices can vary
            ni = None
            for key in ["Net Income", "Net Income Common Stockholders", "Diluted NI Availto Com Stockholders"]:
                if key in f.index:
                    ni = f.loc[key].iloc[0]
                    if ni is not None and not math.isnan(ni):
                        break
            
            # Get latest annual equity
            equity = None
            for key in ["Common Stock Equity", "Stockholders Equity", "Total Equity Gross Minority Interest"]:
                if key in b.index:
                    equity = b.loc[key].iloc[0]
                    if equity is not None and not math.isnan(equity) and equity != 0:
                        break
            
            if ni is not None and equity is not None:
                calc_roe = ni / equity
                return calc_roe
    except:
        pass
        
    return roe or 0  # Fallback to whatever we had or 0


def safe_get(d, key, default=None):
    """Safely get a value from dict."""
    try:
        val = d.get(key, default)
        return default if val is None else val
    except:
        return default


def fmt_cr(val):
    """Format value in Crores."""
    if val is None:
        return "N/A"
    cr = val / 1e7
    if abs(cr) >= 100:
        return f"₹{cr:,.0f} Cr"
    return f"₹{cr:,.1f} Cr"


# ─────────────────────────────────────────────────────────────────────────────
# RISK SCORE CALCULATION (Generic — works for any stock)
# ─────────────────────────────────────────────────────────────────────────────

def calculate_risk_scores(data):
    """
    Calculate risk scores based on 35/35/30 weighting.
    Higher score = Lower risk = Better.
    Works generically for any stock using yfinance data.
    """
    info = data["info"]

    # ── VALUATION SCORE /35 ──
    val_score = 17  # start neutral

    pe = safe_get(info, "trailingPE", safe_get(info, "forwardPE"))
    pb = safe_get(info, "priceToBook")

    if pe:
        if pe < 15:
            val_score += 10
        elif pe < 25:
            val_score += 7
        elif pe < 40:
            val_score += 4
        elif pe < 60:
            val_score += 0
        elif pe < 100:
            val_score -= 3
        else:
            val_score -= 7

    if pb:
        if pb < 2:
            val_score += 5
        elif pb < 5:
            val_score += 3
        elif pb < 10:
            val_score += 1
        elif pb < 20:
            val_score -= 2
        else:
            val_score -= 5

    # Analyst target vs current price
    target = safe_get(info, "targetMeanPrice")
    current = safe_get(info, "currentPrice", safe_get(info, "regularMarketPrice"))
    if target and current and current > 0:
        upside = (target - current) / current * 100
        if upside > 30:
            val_score += 5
        elif upside > 15:
            val_score += 4
        elif upside > 5:
            val_score += 2
        elif upside > 0:
            val_score += 1
        elif upside > -10:
            val_score -= 1
        else:
            val_score -= 4

    val_score = max(0, min(35, val_score))

    # ── FINANCIAL HEALTH SCORE /35 ──
    fin_score = 17

    roe = calculate_roe_manual(data)
    if roe:
        if roe > 0.25:
            fin_score += 7
        elif roe > 0.15:
            fin_score += 5
        elif roe > 0.08:
            fin_score += 2
        elif roe > 0:
            fin_score += 0
        else:
            fin_score -= 5

    profit_margin = safe_get(info, "profitMargins")
    if profit_margin:
        if profit_margin > 0.25:
            fin_score += 6
        elif profit_margin > 0.1:
            fin_score += 3
        elif profit_margin > 0:
            fin_score += 1
        else:
            fin_score -= 5

    rev_growth = safe_get(info, "revenueGrowth")
    if rev_growth:
        if rev_growth > 0.3:
            fin_score += 5
        elif rev_growth > 0.15:
            fin_score += 3
        elif rev_growth > 0.05:
            fin_score += 1
        elif rev_growth > 0:
            fin_score += 0
        else:
            fin_score -= 4

    debt_equity = safe_get(info, "debtToEquity")
    if debt_equity is not None:
        if debt_equity < 30:
            fin_score += 3
        elif debt_equity < 80:
            fin_score += 1
        elif debt_equity < 150:
            fin_score -= 1
        else:
            fin_score -= 3

    fin_score = max(0, min(35, fin_score))

    # ── GROWTH SCORE /30 ──
    growth_score = 15

    if rev_growth:
        if rev_growth > 0.4:
            growth_score += 8
        elif rev_growth > 0.25:
            growth_score += 5
        elif rev_growth > 0.1:
            growth_score += 3
        elif rev_growth > 0:
            growth_score += 1
        else:
            growth_score -= 4

    earnings_growth = safe_get(info, "earningsGrowth")
    if earnings_growth:
        if earnings_growth > 0.3:
            growth_score += 5
        elif earnings_growth > 0.1:
            growth_score += 3
        elif earnings_growth > 0:
            growth_score += 1
        else:
            growth_score -= 3

    # Beta assessment (stability)
    beta = safe_get(info, "beta")
    if beta:
        if beta < 0.8:
            growth_score += 2  # Defensive
        elif beta < 1.2:
            growth_score += 1  # Moderate
        else:
            growth_score -= 1  # Volatile

    growth_score = max(0, min(30, growth_score))

    composite = val_score + fin_score + growth_score

    return {
        "valuation": val_score,
        "financial": fin_score,
        "growth": growth_score,
        "composite": composite,
    }


def get_signal(scores, info):
    """Determine buy/sell/hold signal and whether it's a value buy."""
    composite = scores["composite"]
    current = safe_get(info, "currentPrice", safe_get(info, "regularMarketPrice"))
    target = safe_get(info, "targetMeanPrice")
    target_low = safe_get(info, "targetLowPrice")

    upside = 0
    if target and current and current > 0:
        upside = (target - current) / current * 100

    if composite >= 75 and upside > 15:
        return "🟢 STRONG BUY", True, "Value buy — strong score with significant upside"
    elif composite >= 65 and upside > 5:
        return "🟢 BUY", True, "Attractive risk/reward at current levels"
    elif composite >= 55:
        return "🟡 SPECULATIVE BUY", False, "Positive but monitor closely"
    elif composite >= 40:
        return "🟡 HOLD", False, "Neutral — wait for better entry or catalyst"
    elif composite >= 25:
        return "🔴 SELL", False, "Elevated risk — consider exiting"
    else:
        return "🔴 STRONG SELL", False, "High risk — exit recommended"


# ─────────────────────────────────────────────────────────────────────────────
# SVG CHART GENERATORS
# ─────────────────────────────────────────────────────────────────────────────

def generate_risk_gauge_svg(score):
    """Generate an SVG risk gauge (0-100)."""
    cx, cy = 130, 130
    r = 100
    start_angle = 225
    end_angle = -45
    total_angle = start_angle - end_angle  # 270 degrees

    score_angle = start_angle - (score / 100) * total_angle
    score_rad = math.radians(score_angle)

    needle_len = 75
    nx = cx + needle_len * math.cos(score_rad)
    ny = cy - needle_len * math.sin(score_rad)

    if score >= 70:
        color = "#00e5a0"
        label = "LOW RISK"
    elif score >= 40:
        color = "#f5a623"
        label = "MODERATE"
    else:
        color = "#ff4d6d"
        label = "HIGH RISK"

    def arc_point(angle_deg, radius):
        rad = math.radians(angle_deg)
        return (cx + radius * math.cos(rad), cy - radius * math.sin(rad))

    svg = f'''<svg viewBox="0 0 260 170" xmlns="http://www.w3.org/2000/svg" style="width:100%;max-width:260px;">
  <defs>
    <filter id="glow"><feGaussianBlur stdDeviation="3" result="blur"/><feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
    <linearGradient id="arcGrad" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="#ff4d6d"/>
      <stop offset="50%" stop-color="#f5a623"/>
      <stop offset="100%" stop-color="#00e5a0"/>
    </linearGradient>
  </defs>'''

    for pct_start, pct_end, seg_color in [(0, 33, "#ff4d6d22"), (33, 66, "#f5a62322"), (66, 100, "#00e5a022")]:
        a1 = start_angle - (pct_start / 100) * total_angle
        a2 = start_angle - (pct_end / 100) * total_angle
        p1 = arc_point(a1, r)
        p2 = arc_point(a2, r)
        large = 1 if abs(a1 - a2) > 180 else 0
        svg += f'\n  <path d="M {p1[0]:.1f} {p1[1]:.1f} A {r} {r} 0 {large} 1 {p2[0]:.1f} {p2[1]:.1f}" fill="none" stroke="{seg_color}" stroke-width="16" stroke-linecap="round"/>'

    score_end_angle = start_angle - (score / 100) * total_angle
    p_start = arc_point(start_angle, r)
    p_end = arc_point(score_end_angle, r)
    large = 1 if abs(start_angle - score_end_angle) > 180 else 0
    svg += f'\n  <path d="M {p_start[0]:.1f} {p_start[1]:.1f} A {r} {r} 0 {large} 1 {p_end[0]:.1f} {p_end[1]:.1f}" fill="none" stroke="url(#arcGrad)" stroke-width="8" stroke-linecap="round" filter="url(#glow)"/>'

    for i in range(0, 101, 10):
        angle = start_angle - (i / 100) * total_angle
        p_out = arc_point(angle, r + 12)
        p_in = arc_point(angle, r + 6)
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
    """Generate a 12-month price chart with line, area fill, and annotated markers."""
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

    def x_pos(i):
        return pad_left + (i / (len(prices) - 1)) * chart_w

    def y_pos(p):
        return pad_top + (1 - (p - min_p) / p_range) * chart_h

    svg = f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" style="width:100%;">\n'
    svg += '  <defs>\n'
    svg += '    <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">\n'
    svg += '      <stop offset="0%" stop-color="#00e5a0" stop-opacity="0.25"/>\n'
    svg += '      <stop offset="100%" stop-color="#00e5a0" stop-opacity="0.01"/>\n'
    svg += '    </linearGradient>\n'
    svg += '    <filter id="lineGlow"><feGaussianBlur stdDeviation="2" result="blur"/><feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter>\n'
    svg += '  </defs>\n'

    num_grid = 5
    for i in range(num_grid + 1):
        y = pad_top + (i / num_grid) * chart_h
        p_val = max_p - (i / num_grid) * p_range
        svg += f'  <line x1="{pad_left}" y1="{y:.1f}" x2="{width - pad_right}" y2="{y:.1f}" stroke="rgba(255,255,255,0.04)" stroke-width="1"/>\n'
        svg += f'  <text x="{pad_left - 8}" y="{y + 4:.1f}" text-anchor="end" font-family="Fira Code,monospace" font-size="9" fill="#5c5d6e">₹{p_val:.0f}</text>\n'

    shown_months = set()
    for i, d in enumerate(dates):
        try:
            dt = d.to_pydatetime() if hasattr(d, 'to_pydatetime') else d
            month_key = f"{dt.year}-{dt.month}"
            if month_key not in shown_months and dt.day <= 7:
                shown_months.add(month_key)
                x = x_pos(i)
                label = dt.strftime("%b'%y")
                svg += f'  <text x="{x:.1f}" y="{height - 8}" text-anchor="middle" font-family="Fira Code,monospace" font-size="8" fill="#5c5d6e">{label}</text>\n'
        except:
            pass

    area_points = f"M {x_pos(0):.1f} {y_pos(prices[0]):.1f} "
    for i in range(1, len(prices)):
        area_points += f"L {x_pos(i):.1f} {y_pos(prices[i]):.1f} "
    area_points += f"L {x_pos(len(prices)-1):.1f} {pad_top + chart_h:.1f} L {x_pos(0):.1f} {pad_top + chart_h:.1f} Z"
    svg += f'  <path d="{area_points}" fill="url(#areaGrad)"/>\n'

    line_points = " ".join([f"{x_pos(i):.1f},{y_pos(prices[i]):.1f}" for i in range(len(prices))])
    svg += f'  <polyline points="{line_points}" fill="none" stroke="#00e5a0" stroke-width="2" stroke-linejoin="round" filter="url(#lineGlow)"/>\n'

    events = []
    max_idx = highs.index(max(highs))
    events.append((max_idx, f"52W High: ₹{max(highs):.0f}", "#00e5a0"))
    min_idx = lows.index(min(lows))
    events.append((min_idx, f"52W Low: ₹{min(lows):.0f}", "#ff4d6d"))
    events.append((len(prices) - 1, f"CMP: ₹{prices[-1]:.0f}", "#3d9cf5"))

    for idx, label, color in events:
        if 0 <= idx < len(prices):
            ex = x_pos(idx)
            ey = y_pos(prices[idx])
            svg += f'  <line x1="{ex:.1f}" y1="{ey:.1f}" x2="{ex:.1f}" y2="{pad_top + chart_h:.1f}" stroke="{color}" stroke-width="0.5" stroke-dasharray="3,3" opacity="0.5"/>\n'
            svg += f'  <circle cx="{ex:.1f}" cy="{ey:.1f}" r="4" fill="{color}" stroke="#08090d" stroke-width="2"/>\n'
            label_y = ey - 12 if ey > pad_top + 30 else ey + 20
            svg += f'  <text x="{ex:.1f}" y="{label_y:.1f}" text-anchor="middle" font-family="Fira Code,monospace" font-size="8" fill="{color}">{label}</text>\n'

    svg += '</svg>'
    return svg


def generate_candle_chart_svg(hist_data, width=1040, height=280):
    """Generate a daily (1D) candlestick chart with 50 EMA and 200 DMA overlays."""
    if hist_data is None or hist_data.empty:
        return '<svg viewBox="0 0 1040 280"><text x="520" y="140" text-anchor="middle" fill="#5c5d6e" font-family="Fira Code,monospace" font-size="14">Candle data unavailable</text></svg>'

    # Use daily data — show last 90 trading days for readability
    daily = hist_data.tail(90).copy()

    opens = daily["Open"].values.tolist()
    highs = daily["High"].values.tolist()
    lows = daily["Low"].values.tolist()
    closes = daily["Close"].values.tolist()
    n = len(opens)

    if n < 5:
        return '<svg viewBox="0 0 1040 280"><text x="520" y="140" text-anchor="middle" fill="#5c5d6e">Insufficient candle data</text></svg>'

    # Compute 50 EMA and 200 DMA using FULL history, then slice to display range
    all_closes = hist_data["Close"].values.tolist()
    total = len(all_closes)
    display_start = total - n  # index where displayed candles start

    # 50 EMA (exponential moving average)
    ema50_all = [all_closes[0]]
    mult_50 = 2 / 51
    for i in range(1, total):
        ema50_all.append(all_closes[i] * mult_50 + ema50_all[-1] * (1 - mult_50))

    # 200 DMA (simple moving average)
    dma200_all = []
    for i in range(total):
        if i >= 199:
            dma200_all.append(sum(all_closes[i-199:i+1]) / 200)
        else:
            dma200_all.append(None)

    # Slice to display range
    ema50_display = ema50_all[display_start:]
    dma200_display = dma200_all[display_start:]

    pad_left, pad_right, pad_top, pad_bottom = 60, 20, 20, 40
    chart_w = width - pad_left - pad_right
    chart_h = height - pad_top - pad_bottom

    # Include EMA/DMA values in price range calculation
    all_prices = lows + highs
    for v in ema50_display:
        if v is not None:
            all_prices.append(v)
    for v in dma200_display:
        if v is not None:
            all_prices.append(v)
    min_p = min(all_prices) * 0.97
    max_p = max(all_prices) * 1.03
    p_range = max_p - min_p if max_p != min_p else 1

    candle_w = max(1.5, min(8, (chart_w / n) * 0.65))
    gap = chart_w / n

    def y_pos(p):
        return pad_top + (1 - (p - min_p) / p_range) * chart_h

    svg = f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" style="width:100%;">\n'

    # Grid lines
    for i in range(6):
        y = pad_top + (i / 5) * chart_h
        p_val = max_p - (i / 5) * p_range
        svg += f'  <line x1="{pad_left}" y1="{y:.1f}" x2="{width - pad_right}" y2="{y:.1f}" stroke="rgba(255,255,255,0.04)" stroke-width="1"/>\n'
        svg += f'  <text x="{pad_left - 8}" y="{y + 4:.1f}" text-anchor="end" font-family="Fira Code,monospace" font-size="8" fill="#5c5d6e">\u20b9{p_val:.0f}</text>\n'

    # Month labels
    dates = daily.index.tolist()
    shown_months = set()
    for i, d in enumerate(dates):
        try:
            dt = d.to_pydatetime() if hasattr(d, 'to_pydatetime') else d
            month_key = f"{dt.year}-{dt.month}"
            if month_key not in shown_months and dt.day <= 7:
                shown_months.add(month_key)
                x = pad_left + (i + 0.5) * gap
                label = dt.strftime("%b'%y")
                svg += f'  <text x="{x:.1f}" y="{height - 8}" text-anchor="middle" font-family="Fira Code,monospace" font-size="8" fill="#5c5d6e">{label}</text>\n'
        except:
            pass

    # 200 DMA line (drawn first, behind candles)
    dma_points = []
    for i in range(n):
        if dma200_display[i] is not None:
            x = pad_left + (i + 0.5) * gap
            y = y_pos(dma200_display[i])
            dma_points.append(f"{x:.1f},{y:.1f}")
    if dma_points:
        svg += f'  <polyline points="{" ".join(dma_points)}" fill="none" stroke="#f5a623" stroke-width="1.5" opacity="0.5" stroke-dasharray="6,3"/>\n'

    # 50 EMA line
    ema_points = []
    for i in range(n):
        if ema50_display[i] is not None:
            x = pad_left + (i + 0.5) * gap
            y = y_pos(ema50_display[i])
            ema_points.append(f"{x:.1f},{y:.1f}")
    if ema_points:
        svg += f'  <polyline points="{" ".join(ema_points)}" fill="none" stroke="#9b7fff" stroke-width="1.5" opacity="0.7"/>\n'

    # Daily candles
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

    # Legend
    svg += f'''
  <text x="{width - 20}" y="{pad_top + 12}" text-anchor="end" font-family="Fira Code,monospace" font-size="8" fill="#9b7fff">── 50 EMA</text>
  <text x="{width - 20}" y="{pad_top + 24}" text-anchor="end" font-family="Fira Code,monospace" font-size="8" fill="#f5a623">╌╌ 200 DMA</text>
'''
    svg += '</svg>'
    return svg


def generate_fair_value_svg(current_price, fair_value_low, fair_value_mid, fair_value_high, width=480, height=90):
    """Generate a fair value comparison bar chart."""
    all_vals = [current_price, fair_value_low, fair_value_mid, fair_value_high]
    min_v = min(all_vals) * 0.8
    max_v = max(all_vals) * 1.2
    v_range = max_v - min_v if max_v != min_v else 1

    def x_pos(v):
        return 60 + ((v - min_v) / v_range) * (width - 100)

    svg = f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" style="width:100%;">\n'

    x1 = x_pos(fair_value_low)
    x2 = x_pos(fair_value_high)
    svg += f'  <rect x="{x1:.1f}" y="25" width="{x2 - x1:.1f}" height="30" rx="4" fill="rgba(0,229,160,0.08)" stroke="rgba(0,229,160,0.2)" stroke-width="1" stroke-dasharray="4,2"/>\n'
    svg += f'  <text x="{(x1+x2)/2:.1f}" y="20" text-anchor="middle" font-family="Fira Code,monospace" font-size="8" fill="#00e5a0">FAIR VALUE ZONE</text>\n'

    xm = x_pos(fair_value_mid)
    svg += f'  <line x1="{xm:.1f}" y1="22" x2="{xm:.1f}" y2="58" stroke="#00e5a0" stroke-width="2"/>\n'
    svg += f'  <text x="{xm:.1f}" y="72" text-anchor="middle" font-family="Fira Code,monospace" font-size="9" fill="#00e5a0">₹{fair_value_mid:.0f}</text>\n'
    svg += f'  <text x="{xm:.1f}" y="82" text-anchor="middle" font-family="Fira Code,monospace" font-size="7" fill="#5c5d6e">FAIR VALUE</text>\n'

    svg += f'  <text x="{x1:.1f}" y="72" text-anchor="middle" font-family="Fira Code,monospace" font-size="8" fill="#5c5d6e">₹{fair_value_low:.0f}</text>\n'
    svg += f'  <text x="{x2:.1f}" y="72" text-anchor="middle" font-family="Fira Code,monospace" font-size="8" fill="#5c5d6e">₹{fair_value_high:.0f}</text>\n'

    xc = x_pos(current_price)
    color = "#00e5a0" if current_price <= fair_value_mid * 1.1 else "#f5a623" if current_price <= fair_value_high else "#ff4d6d"
    svg += f'  <line x1="{xc:.1f}" y1="22" x2="{xc:.1f}" y2="58" stroke="{color}" stroke-width="3"/>\n'
    svg += f'  <polygon points="{xc:.1f},20 {xc-5:.1f},12 {xc+5:.1f},12" fill="{color}"/>\n'
    svg += f'  <text x="{xc:.1f}" y="8" text-anchor="middle" font-family="Fira Code,monospace" font-size="10" font-weight="700" fill="{color}">₹{current_price:.0f} CMP</text>\n'

    svg += '</svg>'
    return svg


# ─────────────────────────────────────────────────────────────────────────────
# QUARTERLY DATA EXTRACTION
# ─────────────────────────────────────────────────────────────────────────────

def extract_quarterly_data(data):
    """Extract quarterly financial data from yfinance income statement."""
    qi = data.get("quarterly_income")
    rows = []
    if qi is not None and not qi.empty:
        for col in qi.columns[:8]:  # last 8 quarters max
            try:
                dt = col.to_pydatetime() if hasattr(col, 'to_pydatetime') else col
                month = dt.month
                year = dt.year
                # Determine Indian fiscal quarter
                if month in [1, 2, 3]:
                    q_label = f"Q4 FY{year % 100}"
                elif month in [4, 5, 6]:
                    q_label = f"Q1 FY{(year + 1) % 100}"
                elif month in [7, 8, 9]:
                    q_label = f"Q2 FY{(year + 1) % 100}"
                else:
                    q_label = f"Q3 FY{(year + 1) % 100}"

                rev = None
                for key in ["Total Revenue", "Operating Revenue", "Revenue"]:
                    if key in qi.index:
                        val = qi.loc[key, col]
                        if val is not None and not (isinstance(val, float) and math.isnan(val)):
                            rev = val / 1e7  # Convert to Crores
                            break

                profit = None
                for key in ["Net Income", "Net Income Common Stockholders", "Net Income From Continuing Operations"]:
                    if key in qi.index:
                        val = qi.loc[key, col]
                        if val is not None and not (isinstance(val, float) and math.isnan(val)):
                            profit = val / 1e7
                            break

                ebitda = None
                for key in ["EBITDA", "Normalized EBITDA"]:
                    if key in qi.index:
                        val = qi.loc[key, col]
                        if val is not None and not (isinstance(val, float) and math.isnan(val)):
                            ebitda = val / 1e7
                            break

                ebitda_margin = None
                if ebitda and rev and rev > 0:
                    ebitda_margin = (ebitda / rev) * 100

                rows.append({
                    "quarter": q_label,
                    "date": dt,
                    "revenue_cr": rev,
                    "profit_cr": profit,
                    "ebitda_margin": ebitda_margin,
                })
            except Exception as e:
                continue

    rows.sort(key=lambda x: x.get("date", datetime.min))
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# HTML REPORT GENERATOR (Generic for any NSE stock)
# ─────────────────────────────────────────────────────────────────────────────

def generate_html_report(data, scores):
    """Generate the complete 2-page HTML report for any NSE stock."""
    info = data["info"]
    hist_1y = data["hist_1y"]
    hist_6m = data["hist_6m"]
    ticker_symbol = data["ticker_symbol"]

    # Extract values with fallbacks
    current_price = safe_get(info, "currentPrice", safe_get(info, "regularMarketPrice", 0))
    prev_close = safe_get(info, "previousClose", safe_get(info, "regularMarketPreviousClose", current_price))
    change = current_price - prev_close if current_price and prev_close else 0
    change_pct = (change / prev_close * 100) if prev_close and prev_close > 0 else 0
    high_52w = safe_get(info, "fiftyTwoWeekHigh", 0)
    low_52w = safe_get(info, "fiftyTwoWeekLow", 0)
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
    dividend_yield = safe_get(info, "dividendYield", 0)
    beta = safe_get(info, "beta", 0)
    volume = safe_get(info, "volume", safe_get(info, "regularMarketVolume", 0))
    avg_volume = safe_get(info, "averageVolume", 0)
    sector = safe_get(info, "sector", "N/A")
    industry = safe_get(info, "industry", "N/A")
    company_name = safe_get(info, "longName", safe_get(info, "shortName", ticker_symbol))
    total_revenue = safe_get(info, "totalRevenue", 0)
    debt_equity = safe_get(info, "debtToEquity", 0)
    gross_margin = safe_get(info, "grossMargins", 0)
    operating_margin = safe_get(info, "operatingMargins", 0)
    earnings_growth = safe_get(info, "earningsGrowth", 0)

    mcap_cr = market_cap / 1e7 if market_cap else 0
    change_color = "#00e5a0" if change >= 0 else "#ff4d6d"
    change_icon = "▲" if change >= 0 else "▼"

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

    # Extract quarterly data from yfinance
    quarterly_rows = extract_quarterly_data(data)
    roe = calculate_roe_manual(data)
    
    qt_rows_html = ""
    for q in quarterly_rows:
        rev_str = f"₹{q['revenue_cr']:,.0f} Cr" if q['revenue_cr'] else "N/A"
        profit_str = f"₹{q['profit_cr']:,.0f} Cr" if q['profit_cr'] else "N/A"
        ebitda_str = f"{q['ebitda_margin']:.1f}%" if q['ebitda_margin'] else "N/A"

        rev_class = "tg" if q['revenue_cr'] and q.get('_prev_rev') and q['revenue_cr'] > q['_prev_rev'] else ""
        profit_class = "tg" if q['profit_cr'] and q['profit_cr'] > 0 else "tr" if q['profit_cr'] and q['profit_cr'] < 0 else ""

        qt_rows_html += f'''
        <tr>
          <td>{q["quarter"]}</td>
          <td class="{rev_class}">{rev_str}</td>
          <td class="{profit_class}">{profit_str}</td>
          <td>{ebitda_str}</td>
        </tr>'''

    if not qt_rows_html:
        qt_rows_html = '<tr><td colspan="4" style="text-align:center;color:var(--text3);">Quarterly data not available from yfinance</td></tr>'

    val_color = score_color(scores["valuation"], 35)
    fin_color = score_color(scores["financial"], 35)
    growth_color = score_color(scores["growth"], 30)

    today_str = datetime.now().strftime("%B %d, %Y · %H:%M IST")

    # Recommendation
    composite = scores["composite"]
    signal, is_value_buy, signal_reason = get_signal(scores, info)

    if composite >= 80:
        recommendation = "STRONG BUY"
        rec_color = "#00e5a0"
        needle_pct = 90
    elif composite >= 65:
        recommendation = "BUY"
        rec_color = "#00e5a0"
        needle_pct = 75
    elif composite >= 50:
        recommendation = "SPECULATIVE BUY"
        rec_color = "#f5a623"
        needle_pct = 60
    elif composite >= 35:
        recommendation = "HOLD"
        rec_color = "#f5a623"
        needle_pct = 45
    elif composite >= 20:
        recommendation = "SELL"
        rec_color = "#ff4d6d"
        needle_pct = 25
    else:
        recommendation = "STRONG SELL"
        rec_color = "#ff4d6d"
        needle_pct = 10

    ev_revenue = mcap_cr / (total_revenue / 1e7) if total_revenue else 0

    upside = ((target_mean - current_price) / current_price * 100) if target_mean and current_price and current_price > 0 else 0

    # Card status helpers
    def cs(val, good, bad, lower_better=False):
        if val is None or val == 0:
            return "caution"
        if lower_better:
            return "beat" if val <= good else ("caution" if val <= bad else "miss")
        return "beat" if val >= good else ("caution" if val >= bad else "miss")

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

    if upside > 10:
        catalysts.append(f"<strong>Analyst Upside ({upside:.0f}%):</strong> Mean target of ₹{target_mean:.0f} above current price.")

    if beta and beta < 1.0:
        catalysts.append(f"<strong>Low Beta ({beta:.2f}):</strong> Less volatile than market — defensive play.")

    if earnings_growth and earnings_growth > 0.1:
        catalysts.append(f"<strong>Earnings Growth ({earnings_growth*100:.0f}%):</strong> Strong profit expansion.")

    # Default catalysts if we have few
    if len(catalysts) < 3:
        catalysts.append(f"<strong>Sector Opportunity:</strong> {sector} / {industry} — positioned in growth sector.")

    # Risks
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

    # Default risks if few
    while len(risks) < 3:
        risks.append(f"<strong>Market Risk:</strong> Broader market correction or sentiment shift could impact stock.")
        if len(risks) < 3:
            risks.append(f"<strong>Sector Risk:</strong> Regulatory or competitive changes in {sector} space.")
        if len(risks) < 3:
            risks.append(f"<strong>Execution Risk:</strong> Growth may not meet elevated expectations.")

    catalysts_html = "\n".join([f'<div class="col-item"><span class="col-icon">{"🏆💹🔀🇮🇳🔬📈"[i % 6]}</span><span>{c}</span></div>' for i, c in enumerate(catalysts[:6])])
    risks_html = "\n".join([f'<div class="col-item"><span class="col-icon">{"📜💰🔓⚔️📉🌐"[i % 6]}</span><span>{r}</span></div>' for i, r in enumerate(risks[:6])])

    # Verdict text
    profit_status = "profitable" if profit_margin and profit_margin > 0 else "loss-making"
    verdict_text = f'''<strong>{company_name}</strong> trades at ₹{current_price:,.2f} with a composite risk score of {composite}/100.
    The stock scores {scores["valuation"]}/35 on valuation, {scores["financial"]}/35 on financial health, and {scores["growth"]}/30 on growth.
    The company is currently {profit_status} with {"strong" if roe and roe > 0.15 else "moderate" if roe and roe > 0 else "negative"} return on equity.
    <br><br>
    {"Analyst consensus suggests upside of " + f"{upside:.1f}%" + f" with a mean target of ₹{target_mean:.0f}." if target_mean and upside > 0 else "The stock is trading near or above analyst consensus targets."}
    Revenue growth is at {rev_growth*100:.1f}%{" — a strong positive signal" if rev_growth and rev_growth > 0.15 else "" if rev_growth and rev_growth > 0 else " — a concern"}.
    <br><br>
    <strong>Bottom Line:</strong> {signal_reason}. The current recommendation is <strong style="color:{rec_color}">{recommendation}</strong>.'''

    # Verdict tags
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
<title>NSE:{ticker_symbol} · Risk Score Report</title>
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
  .badge-nse {{ background:var(--green-dim); color:var(--green); border:1px solid rgba(0,229,160,0.2); }}
  .badge-sector {{ background:var(--blue-dim); color:var(--blue); border:1px solid rgba(61,156,245,0.2); }}
  .sh-name {{ font-family:var(--mono); font-size:26px; font-weight:700; color:#fff; letter-spacing:-0.5px; margin-bottom:8px; }}
  .sh-meta {{ display:flex; gap:16px; flex-wrap:wrap; font-family:var(--mono); font-size:10px; color:var(--text2); }}
  .sh-right {{ text-align:right; }}
  .sh-price {{ font-family:var(--mono); font-size:36px; font-weight:700; color:#fff; letter-spacing:-1px; }}
  .sh-change {{ font-family:var(--mono); font-size:13px; font-weight:600; margin-top:4px; }}
  .sh-volume {{ font-family:var(--mono); font-size:10px; color:var(--text3); margin-top:8px; }}
  .sh-timestamp {{ font-family:var(--mono); font-size:9px; color:var(--text3); margin-top:4px; }}
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
  @media (max-width: 768px) {{ .stock-header {{ flex-direction:column; gap:16px; }} .gauge-kpi-row {{ grid-template-columns:1fr; }} .card-grid {{ grid-template-columns:1fr 1fr; }} .breakdown-grid {{ grid-template-columns:1fr; }} .dual-col {{ grid-template-columns:1fr; }} .kpi-strip {{ grid-template-columns:repeat(2,1fr); }} }}
  @media print {{ .copy-btn {{ display:none; }} .page {{ padding:16px; }} .page-break {{ page-break-before:always; border:none; margin:0; }} }}
</style>
</head>
<body>
<div id="report-content">
<div class="page">

  <div class="stock-header">
    <div>
      <div class="sh-ticker"><span>NSE:{ticker_symbol}</span><span class="badge badge-nse">NSE</span><span class="badge badge-sector">{sector}</span></div>
      <div class="sh-name">{company_name}</div>
      <div class="sh-meta"><span>📊 {industry}</span><span>📍 52W: ₹{low_52w:,.0f} — ₹{high_52w:,.0f}</span></div>
    </div>
    <div class="sh-right">
      <div class="sh-price">₹{current_price:,.2f}</div>
      <div class="sh-change" style="color:{change_color}">{change_icon} ₹{abs(change):,.2f} ({change_pct:+.2f}%)</div>
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
      <div class="kpi-card"><div class="kpi-label">📈 P/E RATIO</div><div class="kpi-value">{pe_ratio:.1f}x</div><div class="kpi-sub">Trailing</div></div>
      <div class="kpi-card"><div class="kpi-label">📖 P/B RATIO</div><div class="kpi-value">{pb_ratio:.1f}x</div><div class="kpi-sub">Price to Book</div></div>
      <div class="kpi-card"><div class="kpi-label">💰 EPS</div><div class="kpi-value">₹{eps:.2f}</div><div class="kpi-sub">TTM</div></div>
      <div class="kpi-card"><div class="kpi-label">🏛 MARKET CAP</div><div class="kpi-value">₹{mcap_cr:,.0f}Cr</div><div class="kpi-sub">{"Large" if mcap_cr > 20000 else "Mid" if mcap_cr > 5000 else "Small"} Cap</div></div>
      <div class="kpi-card"><div class="kpi-label">📊 ROE</div><div class="kpi-value">{roe*100:.1f}%</div><div class="kpi-sub">Return on Equity</div></div>
      <div class="kpi-card"><div class="kpi-label">📈 REV GROWTH</div><div class="kpi-value">{rev_growth*100:.1f}%</div><div class="kpi-sub">YoY</div></div>
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
      <div class="metric-card {cs(pe_ratio, 20, 40, True) if pe_ratio else 'caution'}"><div class="mc-label">P/E RATIO</div><div class="mc-value">{pe_ratio:.1f}x</div><div class="mc-bench">Trailing twelve months</div></div>
      <div class="metric-card {cs(pb_ratio, 3, 10, True) if pb_ratio else 'caution'}"><div class="mc-label">P/B RATIO</div><div class="mc-value">{pb_ratio:.1f}x</div><div class="mc-bench">Price to Book value</div></div>
      <div class="metric-card {cs(roe*100 if roe else 0, 15, 8)}"><div class="mc-label">ROE</div><div class="mc-value">{roe*100:.1f}%</div><div class="mc-bench">Return on Equity</div></div>
      <div class="metric-card {cs(profit_margin*100 if profit_margin else 0, 10, 0)}"><div class="mc-label">PROFIT MARGIN</div><div class="mc-value">{profit_margin*100:.1f}%</div><div class="mc-bench">Net profit margin</div></div>
      <div class="metric-card {"beat" if return_1y > 15 else "caution" if return_1y > 0 else "miss"}"><div class="mc-label">1Y RETURN</div><div class="mc-value" style="color:{"#00e5a0" if return_1y > 0 else "#ff4d6d"}">{return_1y:+.1f}%</div><div class="mc-bench">12-month return</div></div>
      <div class="metric-card {"beat" if target_mean > current_price else "miss" if target_mean else "caution"}"><div class="mc-label">ANALYST TARGET</div><div class="mc-value">₹{target_mean:,.0f}</div><div class="mc-bench">Range: ₹{fair_value_low:,.0f} - ₹{fair_value_high:,.0f}</div></div>
    </div>
  </div>

  <div class="breakdown-grid">
    <div class="breakdown-card">
      <div class="bc-header"><div><div class="bc-title">VALUATION</div><div class="bc-score" style="color:{val_color}">{scores["valuation"]}<span class="bc-max">/35</span></div></div><div style="font-family:var(--mono);font-size:10px;color:var(--text3);">35% WEIGHT</div></div>
      <div class="bc-bar-track"><div class="bc-bar-fill" style="width:{scores['valuation']/35*100:.0f}%;background:{val_color};box-shadow:0 0 8px {val_color}44;"></div></div>
      <ul class="bc-items">
        <li>P/E at {pe_ratio:.0f}x</li>
        <li>P/B at {pb_ratio:.1f}x</li>
        <li>Analyst target: ₹{target_mean:.0f} ({upside:+.1f}%)</li>
        <li>1Y return: {return_1y:+.1f}%</li>
      </ul>
    </div>
    <div class="breakdown-card">
      <div class="bc-header"><div><div class="bc-title">FINANCIAL HEALTH</div><div class="bc-score" style="color:{fin_color}">{scores["financial"]}<span class="bc-max">/35</span></div></div><div style="font-family:var(--mono);font-size:10px;color:var(--text3);">35% WEIGHT</div></div>
      <div class="bc-bar-track"><div class="bc-bar-fill" style="width:{scores['financial']/35*100:.0f}%;background:{fin_color};box-shadow:0 0 8px {fin_color}44;"></div></div>
      <ul class="bc-items">
        <li>ROE: {roe*100:.1f}%</li>
        <li>Profit margin: {profit_margin*100:.1f}%</li>
        <li>Revenue growth: {rev_growth*100:.1f}%</li>
        <li>Debt/Equity: {debt_equity:.0f}%</li>
      </ul>
    </div>
    <div class="breakdown-card">
      <div class="bc-header"><div><div class="bc-title">GROWTH</div><div class="bc-score" style="color:{growth_color}">{scores["growth"]}<span class="bc-max">/30</span></div></div><div style="font-family:var(--mono);font-size:10px;color:var(--text3);">30% WEIGHT</div></div>
      <div class="bc-bar-track"><div class="bc-bar-fill" style="width:{scores['growth']/30*100:.0f}%;background:{growth_color};box-shadow:0 0 8px {growth_color}44;"></div></div>
      <ul class="bc-items">
        <li>Revenue growth: {rev_growth*100:.1f}%</li>
        <li>Earnings growth: {earnings_growth*100:.1f}%</li>
        <li>Beta: {beta:.2f}</li>
        <li>Sector: {sector}</li>
      </ul>
    </div>
  </div>

  <hr class="page-break">

  <div class="section">
    <div class="section-title">📋 Quarterly Performance Trend</div>
    <div style="overflow-x:auto;">
    <table>
      <thead><tr><th>Quarter</th><th>Revenue</th><th>Net Profit</th><th>EBITDA Margin</th></tr></thead>
      <tbody>{qt_rows_html}</tbody>
    </table>
    </div>
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
    RISK SCORE REPORT · NSE:{ticker_symbol} · GENERATED {datetime.now().strftime("%b %d, %Y %H:%M IST").upper()} · DATA VIA YAHOO FINANCE<br>
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

        row = f"| {ticker} | ₹{current:,.2f} | {scores['composite']}/100 | {signal} | {upside:+.1f}% | [Report](./{today}/{ticker}_RiskReport.html) |"
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

    md = f"""# 📊 Daily Stock Risk Report — {today}

## 🔔 Action Required

"""
    if alerts:
        md += "### 🟢 Value Buy Opportunities\n\n"
        for a in alerts:
            md += f"""**NSE:{a['ticker']}** — ₹{a['price']:,.2f}
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
                # Support comma-separated on same line
                for t in line.split(","):
                    t = t.strip().upper()
                    if t:
                        tickers.append(t)
    return tickers


def cleanup_old_reports(reports_root, keep_days=30):
    """Delete report date-folders older than keep_days."""
    cutoff = datetime.now() - timedelta(days=keep_days)
    removed = 0
    if not os.path.isdir(reports_root):
        return 0
    for name in sorted(os.listdir(reports_root)):
        dirpath = os.path.join(reports_root, name)
        if not os.path.isdir(dirpath):
            continue
        # Match YYYY-MM-DD directory names
        try:
            dir_date = datetime.strptime(name, "%Y-%m-%d")
            if dir_date < cutoff:
                shutil.rmtree(dirpath)
                removed += 1
        except ValueError:
            continue  # skip non-date dirs
    return removed


# ─────────────────────────────────────────────────────────────────────────────
# MAIN CLI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="NSE Stock Risk Score Report Generator (No API Key Required)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python report_generator.py GROWW
  python report_generator.py RELIANCE INFY TCS
  python report_generator.py --watchlist watchlist.txt
  python report_generator.py --watchlist watchlist.txt --alerts
  python report_generator.py GROWW -o ./reports/
        """
    )

    parser.add_argument("tickers", nargs="*", help="NSE ticker symbol(s)")
    parser.add_argument("-w", "--watchlist", help="Path to watchlist file with tickers")
    parser.add_argument("-o", "--output-dir", default="./reports", help="Output directory (default: ./reports)")
    parser.add_argument("--alerts", action="store_true", help="Generate alerts summary markdown")

    args = parser.parse_args()

    # Determine tickers
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

    # Remove duplicates, preserve order
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

    # Clean up reports older than 30 days
    removed = cleanup_old_reports(reports_root, keep_days=30)
    if removed:
        print(f"🧹 Cleaned up {removed} report folder(s) older than 30 days")

    print("=" * 62)
    print("  NSE Stock Risk Score Report Generator")
    print("  No API Key Required · Powered by yfinance")
    print(f"  Stocks: {', '.join(tickers)}")
    print(f"  Date:   {today_str}")
    print(f"  Output: {os.path.abspath(output_dir)}/")
    print("=" * 62)
    print()

    results = []

    for i, ticker in enumerate(tickers, 1):
        print(f"[{i}/{len(tickers)}] Processing NSE:{ticker}...")

        try:
            # Fetch
            data = fetch_stock_data(ticker)

            # Score
            scores = calculate_risk_scores(data)
            signal, is_value_buy, reason = get_signal(scores, data["info"])
            print(f"  🧮 Score: {scores['composite']}/100 | {signal}")

            # Generate HTML
            html = generate_html_report(data, scores)
            output_file = os.path.join(output_dir, f"{ticker}_RiskReport.html")
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(html)

            file_size = os.path.getsize(output_file) / 1024
            print(f"  ✅ Saved: {output_file} ({file_size:.1f} KB)")

            if is_value_buy:
                print(f"  🟢 ** VALUE BUY ALERT ** — {reason}")

            results.append({
                "ticker": ticker,
                "file": output_file,
                "status": "success",
                "scores": scores,
                "info": data["info"],
                "is_value_buy": is_value_buy,
                "signal": signal,
            })

        except Exception as e:
            print(f"  ❌ Failed: {e}")
            results.append({"ticker": ticker, "status": "failed", "error": str(e)})

        print()

    # Generate alerts summary
    if args.alerts or len(tickers) > 1:
        print("📝 Generating daily summary...")
        summary_file, alerts = generate_alerts_summary(results, output_dir, today_str)
        print(f"  📄 Summary: {summary_file}")

        # Also copy summary to reports root for easy access
        root_summary = os.path.join(reports_root, "DAILY_SUMMARY.md")
        shutil.copy2(summary_file, root_summary)

        if alerts:
            print(f"\n  🔔 {len(alerts)} VALUE BUY ALERT(S):")
            for a in alerts:
                print(f"     🟢 NSE:{a['ticker']} — ₹{a['price']:,.2f} (Score: {a['score']}, Upside: {a['upside']:+.1f}%)")
        else:
            print("  ℹ️  No value-buy alerts today.")

    # Final summary
    success = sum(1 for r in results if r["status"] == "success")
    failed = len(results) - success
    print(f"\n{'=' * 62}")
    print(f"  DONE: {success} reports generated, {failed} failed")
    print(f"  📂 Reports in: {os.path.abspath(output_dir)}/")
    print(f"  📅 Keeping last 30 days of reports")
    print(f"{'=' * 62}\n")


if __name__ == "__main__":
    main()
