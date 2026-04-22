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
# rev_growth: (moderate, strong) as decimal — sector-typical YoY revenue growth norms
# earn_growth: (moderate, strong) as decimal — sector-typical YoY earnings growth norms

_DEFAULT_BENCH = {"pe": (15, 25, 50), "pb": (2, 5, 12), "roe": (0.10, 0.18), "margin": (0.08, 0.18), "de": (40, 100), "rev_growth": (0.08, 0.20), "earn_growth": (0.10, 0.25)}

SECTOR_BENCHMARKS = {
    "Financial Services":      {"pe": (12, 22, 35), "pb": (1.5, 3, 5),  "roe": (0.12, 0.18), "margin": (0.15, 0.30), "de": (200, 500), "rev_growth": (0.06, 0.15), "earn_growth": (0.08, 0.20)},
    "Technology":              {"pe": (20, 35, 60), "pb": (3, 8, 15),   "roe": (0.15, 0.25), "margin": (0.15, 0.25), "de": (20, 60),   "rev_growth": (0.12, 0.30), "earn_growth": (0.15, 0.35)},
    "Energy":                  {"pe": (8, 15, 25),  "pb": (1, 2, 4),    "roe": (0.10, 0.18), "margin": (0.05, 0.12), "de": (40, 100),  "rev_growth": (0.05, 0.15), "earn_growth": (0.08, 0.20)},
    "Industrials":             {"pe": (15, 30, 50), "pb": (2, 5, 10),   "roe": (0.12, 0.20), "margin": (0.10, 0.20), "de": (30, 80),   "rev_growth": (0.06, 0.18), "earn_growth": (0.10, 0.25)},
    "Healthcare":              {"pe": (18, 30, 50), "pb": (2, 5, 10),   "roe": (0.12, 0.20), "margin": (0.12, 0.22), "de": (20, 60),   "rev_growth": (0.10, 0.25), "earn_growth": (0.12, 0.30)},
    "Consumer Cyclical":       {"pe": (15, 25, 45), "pb": (2, 5, 12),   "roe": (0.12, 0.20), "margin": (0.08, 0.18), "de": (30, 80),   "rev_growth": (0.08, 0.20), "earn_growth": (0.10, 0.25)},
    "Consumer Defensive":      {"pe": (18, 30, 50), "pb": (3, 8, 15),   "roe": (0.15, 0.25), "margin": (0.10, 0.20), "de": (30, 80),   "rev_growth": (0.04, 0.12), "earn_growth": (0.06, 0.15)},
    "Basic Materials":         {"pe": (8, 15, 30),  "pb": (1, 2.5, 6),  "roe": (0.10, 0.18), "margin": (0.08, 0.15), "de": (40, 100),  "rev_growth": (0.05, 0.15), "earn_growth": (0.08, 0.20)},
    "Communication Services":  {"pe": (12, 25, 45), "pb": (1.5, 4, 10), "roe": (0.08, 0.15), "margin": (0.10, 0.20), "de": (50, 120),  "rev_growth": (0.06, 0.18), "earn_growth": (0.10, 0.25)},
    "Real Estate":             {"pe": (10, 20, 40), "pb": (1, 2.5, 6),  "roe": (0.08, 0.15), "margin": (0.10, 0.25), "de": (50, 120),  "rev_growth": (0.03, 0.10), "earn_growth": (0.05, 0.12)},
    "Utilities":               {"pe": (10, 18, 30), "pb": (1, 2, 4),    "roe": (0.10, 0.15), "margin": (0.10, 0.20), "de": (80, 200),  "rev_growth": (0.02, 0.08), "earn_growth": (0.04, 0.10)},
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
        result["hist_1d_intra"] = ticker.history(period="1d", interval="15m")
    except Exception:
        result["hist_1d_intra"] = None

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

    # Corporate actions calendar (earnings, dividends)
    try:
        result["calendar"] = ticker.calendar
    except Exception:
        result["calendar"] = None

    try:
        result["earnings_history"] = ticker.earnings_history
    except Exception:
        result["earnings_history"] = None

    result["ticker_obj"] = ticker

    result["peers_page_url"] = ""
    result["industry_name"] = safe_get(result.get("info", {}), "industry", "")
    result["screener"] = {}

    sector = safe_get(result.get("info", {}), "sector", "")
    industry = safe_get(result.get("info", {}), "industry", "")
    try:
        print(f"  🏭 Fetching industry peers for {yf_symbol}...")
        result["_peers"] = fetch_industry_peers(yf_symbol, sector, industry)
        result["peers"] = result["_peers"]
    except Exception as e:
        print(f"    ⚠ Could not fetch peers: {e}")
        result["_peers"] = []
        result["peers"] = []

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
# TECHNICAL ANALYSIS HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _compute_rsi(closes, period=14):
    """Wilder's RSI from a pandas Series of closing prices."""
    delta = closes.diff()
    gain = delta.clip(lower=0)
    loss = (-delta.clip(upper=0))
    avg_gain = gain.ewm(alpha=1/period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, float("nan"))
    return 100 - (100 / (1 + rs))


def _compute_macd(closes, fast=12, slow=26, signal=9):
    """Return (macd_line, signal_line) as pandas Series."""
    ema_fast = closes.ewm(span=fast, min_periods=fast).mean()
    ema_slow = closes.ewm(span=slow, min_periods=slow).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, min_periods=signal).mean()
    return macd_line, signal_line


def _technical_score(data):
    """
    Score 0-25 from price-based technical indicators.
    Uses hist_1y (RSI, 200 DMA) and hist_6m (MACD, 50 EMA, volume).
    """
    score = 9  # base ~35% of 25

    hist_1y = data.get("hist_1y")
    hist_6m = data.get("hist_6m")

    if hist_1y is None or hist_1y.empty or len(hist_1y) < 30:
        return max(0, min(25, score))

    closes_1y = hist_1y["Close"].dropna()
    if closes_1y.empty:
        return max(0, min(25, score))

    # RSI(14)
    rsi_series = _compute_rsi(closes_1y)
    rsi = rsi_series.iloc[-1] if not rsi_series.empty else 50
    if rsi < 30:
        score += 6
    elif rsi < 45:
        score += 3
    elif rsi <= 65:
        score += 1
    elif rsi <= 75:
        score -= 1
    else:
        score -= 3

    # Price vs 200 DMA
    if len(closes_1y) >= 200:
        dma200 = closes_1y.rolling(200).mean().iloc[-1]
        last = closes_1y.iloc[-1]
        if dma200 and dma200 > 0:
            dist = (last - dma200) / dma200
            if dist > 0.05:
                score += 3
            elif dist > -0.02:
                score += 1
            elif dist > -0.10:
                score -= 1
            else:
                score -= 3

    closes_6m = hist_6m["Close"].dropna() if hist_6m is not None and not hist_6m.empty else closes_1y.tail(130)

    # MACD
    if len(closes_6m) >= 35:
        macd_line, sig_line = _compute_macd(closes_6m)
        if not macd_line.empty and not sig_line.empty:
            macd_val = macd_line.iloc[-1]
            sig_val = sig_line.iloc[-1]
            if macd_val > sig_val and macd_val > 0:
                score += 4
            elif macd_val > sig_val:
                score += 2
            elif macd_val < sig_val and macd_val < 0:
                score -= 4
            else:
                score -= 1

    # Price vs 50 EMA
    if len(closes_6m) >= 50:
        ema50 = closes_6m.ewm(span=50, min_periods=50).mean().iloc[-1]
        last = closes_6m.iloc[-1]
        if ema50 and ema50 > 0:
            if last > ema50 * 1.02:
                score += 3
            elif last > ema50 * 0.98:
                score += 1
            else:
                score -= 2

    # Volume trend
    if hist_6m is not None and not hist_6m.empty and len(hist_6m) >= 50:
        vol = hist_6m["Volume"].dropna()
        close = hist_6m["Close"].dropna()
        if len(vol) >= 50 and len(close) >= 50:
            vol_20 = vol.tail(20).mean()
            vol_50 = vol.tail(50).mean()
            price_chg = close.diff().tail(20)
            up_vol = vol.tail(20)[price_chg > 0].mean() if (price_chg > 0).any() else 0
            dn_vol = vol.tail(20)[price_chg < 0].mean() if (price_chg < 0).any() else 0
            if vol_20 > vol_50 * 1.1 and up_vol > dn_vol:
                score += 2
            elif vol_20 < vol_50 * 0.8:
                score -= 1

    return max(0, min(25, score))


# ─────────────────────────────────────────────────────────────────────────────
# RISK SCORE CALCULATION (Sector-calibrated)
# ─────────────────────────────────────────────────────────────────────────────

def calculate_risk_scores(data):
    """Calculate risk scores based on 25/25/25/25 weighting with sector-specific thresholds.
    Pillars: Valuation / Financial Health / Growth / Technical.
    """
    info = data["info"]
    sector = safe_get(info, "sector", "")
    bench = get_sector_bench(sector)
    pe_cheap, pe_fair, pe_exp = bench["pe"]
    pb_cheap, pb_fair, pb_exp = bench["pb"]
    roe_mod, roe_good = bench["roe"]
    margin_mod, margin_good = bench["margin"]
    de_ok, de_high = bench["de"]
    rg_mod, rg_strong = bench["rev_growth"]
    eg_mod, eg_strong = bench["earn_growth"]

    # ── VALUATION SCORE /25 ──
    val_score = 9
    pe = safe_get(info, "trailingPE", safe_get(info, "forwardPE"))
    pb = safe_get(info, "priceToBook")

    if pe:
        if pe < pe_cheap:       val_score += 8
        elif pe < pe_fair:      val_score += 5
        elif pe < pe_exp:       val_score += 2
        elif pe < pe_exp * 1.5: val_score -= 1
        elif pe < pe_exp * 2.5: val_score -= 4
        else:                   val_score -= 7

    if pb:
        if pb < pb_cheap:      val_score += 4
        elif pb < pb_fair:     val_score += 2
        elif pb < pb_exp:      val_score += 0
        elif pb < pb_exp * 2:  val_score -= 2
        else:                  val_score -= 4

    target = safe_get(info, "targetMeanPrice")
    current = safe_get(info, "currentPrice", safe_get(info, "regularMarketPrice"))
    if target and current and current > 0:
        upside = (target - current) / current * 100
        if upside > 30:      val_score += 4
        elif upside > 15:    val_score += 3
        elif upside > 5:     val_score += 1
        elif upside > 0:     val_score += 0
        elif upside > -10:   val_score -= 2
        else:                val_score -= 4

    val_score = max(0, min(25, val_score))

    # ── FINANCIAL HEALTH SCORE /25 ──
    fin_score = 9
    roe = calculate_roe_manual(data)
    if roe:
        if roe > roe_good * 1.4: fin_score += 6
        elif roe > roe_good:     fin_score += 4
        elif roe > roe_mod:      fin_score += 1
        elif roe > 0:            fin_score += 0
        else:                    fin_score -= 5

    profit_margin = safe_get(info, "profitMargins")
    if profit_margin:
        if profit_margin > margin_good * 1.3: fin_score += 5
        elif profit_margin > margin_mod:      fin_score += 2
        elif profit_margin > 0:               fin_score += 0
        else:                                 fin_score -= 4

    rev_growth = safe_get(info, "revenueGrowth")
    if rev_growth:
        if rev_growth > rg_strong * 1.5: fin_score += 4
        elif rev_growth > rg_strong:     fin_score += 2
        elif rev_growth > rg_mod:        fin_score += 1
        elif rev_growth > 0:             fin_score += 0
        else:                            fin_score -= 3

    debt_equity = safe_get(info, "debtToEquity")
    if debt_equity is not None:
        if debt_equity < de_ok:          fin_score += 2
        elif debt_equity < de_high:      fin_score += 0
        elif debt_equity < de_high * 1.5: fin_score -= 2
        else:                            fin_score -= 4

    fin_score = max(0, min(25, fin_score))

    # ── GROWTH SCORE /25 ──
    growth_score = 9
    if rev_growth:
        if rev_growth > rg_strong * 2:  growth_score += 7
        elif rev_growth > rg_strong:    growth_score += 4
        elif rev_growth > rg_mod:       growth_score += 2
        elif rev_growth > 0:            growth_score += 0
        else:                           growth_score -= 4

    earnings_growth = safe_get(info, "earningsGrowth")
    if earnings_growth:
        if earnings_growth > eg_strong:  growth_score += 5
        elif earnings_growth > eg_mod:   growth_score += 3
        elif earnings_growth > 0:        growth_score += 1
        else:                            growth_score -= 3

    beta = safe_get(info, "beta")
    if beta:
        if beta < 0.8:   growth_score += 2
        elif beta < 1.2: growth_score += 1
        else:            growth_score -= 1

    growth_score = max(0, min(25, growth_score))

    # ── TECHNICAL SCORE /25 ──
    tech_score = _technical_score(data)

    composite = val_score + fin_score + growth_score + tech_score

    return {"valuation": val_score, "financial": fin_score, "growth": growth_score, "technical": tech_score, "composite": composite}


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

    if composite >= 78 and upside > 20:
        return "🟢 STRONG BUY", True, f"Strong score with significant upside{sector_tag}"
    elif composite >= 68 and upside > 8:
        return "🟢 BUY", True, f"Attractive risk/reward{sector_tag} at current levels"
    elif composite >= 58 and upside > 0:
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


# ─────────────────────────────────────────────────────────────────────────────
# FINANCIAL STATEMENT TABLE BUILDERS (from yfinance DataFrames)
# ─────────────────────────────────────────────────────────────────────────────

_INCOME_ROWS = [
    ("Total Revenue", ["Total Revenue", "Operating Revenue", "Revenue"]),
    ("Cost of Revenue", ["Cost Of Revenue"]),
    ("Gross Profit", ["Gross Profit"]),
    ("Operating Expense", ["Operating Expense", "Total Operating Expenses"]),
    ("Operating Income", ["Operating Income", "EBIT"]),
    ("Interest Expense", ["Interest Expense", "Net Interest Income"]),
    ("Pretax Income", ["Pretax Income"]),
    ("Tax Provision", ["Tax Provision", "Income Tax Expense"]),
    ("Net Income", ["Net Income", "Net Income Common Stockholders"]),
    ("EBITDA", ["EBITDA", "Normalized EBITDA"]),
    ("EPS (Basic)", ["Basic EPS"]),
    ("EPS (Diluted)", ["Diluted EPS"]),
    ("Shares Outstanding", ["Diluted Average Shares", "Basic Average Shares"]),
]

_BALANCE_SHEET_ROWS = [
    ("Total Assets", ["Total Assets"]),
    ("Current Assets", ["Current Assets"]),
    ("Cash & Equivalents", ["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"]),
    ("Accounts Receivable", ["Accounts Receivable", "Net Receivables", "Receivables"]),
    ("Inventory", ["Inventory"]),
    ("Non-Current Assets", ["Total Non Current Assets"]),
    ("Property Plant & Equip", ["Net PPE", "Gross PPE"]),
    ("Goodwill", ["Goodwill"]),
    ("Intangible Assets", ["Intangible Assets", "Net Intangible Assets", "Goodwill And Other Intangible Assets"]),
    ("Total Liabilities", ["Total Liabilities Net Minority Interest", "Total Liabilities"]),
    ("Current Liabilities", ["Current Liabilities"]),
    ("Accounts Payable", ["Accounts Payable", "Payables"]),
    ("Short-Term Debt", ["Current Debt", "Current Debt And Capital Lease Obligation"]),
    ("Long-Term Debt", ["Long Term Debt", "Long Term Debt And Capital Lease Obligation"]),
    ("Total Equity", ["Total Equity Gross Minority Interest", "Stockholders Equity", "Total Stockholders Equity"]),
    ("Retained Earnings", ["Retained Earnings"]),
    ("Book Value/Share", ["Tangible Book Value"]),
]

_CASH_FLOW_ROWS = [
    ("Operating Cash Flow", ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"]),
    ("Depreciation & Amort.", ["Depreciation And Amortization"]),
    ("Change in Working Cap", ["Change In Working Capital", "Changes In Working Capital"]),
    ("Capital Expenditure", ["Capital Expenditure"]),
    ("Free Cash Flow", ["Free Cash Flow"]),
    ("Investing Cash Flow", ["Investing Cash Flow", "Cash Flow From Continuing Investing Activities"]),
    ("Acquisitions", ["Purchase Of Business", "Net Business Purchase And Sale"]),
    ("Financing Cash Flow", ["Financing Cash Flow", "Cash Flow From Continuing Financing Activities"]),
    ("Debt Issued", ["Long Term Debt Issuance", "Issuance Of Debt"]),
    ("Debt Repaid", ["Long Term Debt Payments", "Repayment Of Debt"]),
    ("Dividends Paid", ["Common Stock Dividend Paid", "Cash Dividends Paid"]),
    ("Share Buyback", ["Repurchase Of Capital Stock", "Common Stock Payments"]),
    ("Net Change in Cash", ["Changes In Cash", "Change In Cash Supplemental As Reported"]),
]

_KEY_ROW_LABELS = {"total revenue", "gross profit", "operating income", "net income", "ebitda",
                   "total assets", "total liabilities", "total equity", "operating cash flow",
                   "free cash flow", "net change in cash"}


def _fmt_statement_val(val, is_eps=False, is_shares=False):
    """Format a financial statement value for display."""
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return "—"
    try:
        v = float(val)
    except (ValueError, TypeError):
        return str(val)
    if is_eps:
        return f"${v:,.2f}"
    if is_shares:
        if abs(v) >= 1e9:
            return f"{v/1e9:,.2f}B"
        if abs(v) >= 1e6:
            return f"{v/1e6:,.1f}M"
        return f"{v:,.0f}"
    if abs(v) >= 1e9:
        return f"${v/1e9:,.2f}B"
    if abs(v) >= 1e6:
        return f"${v/1e6:,.1f}M"
    if abs(v) >= 1e3:
        return f"${v/1e3:,.1f}K"
    return f"${v:,.0f}"


def _build_yf_statement_table(df, row_defs, max_periods=8):
    """Convert a yfinance financial DataFrame into an HTML table string.
    df: columns are date timestamps, index is line-item names.
    row_defs: list of (display_label, [possible_index_names]).
    """
    if df is None or df.empty:
        return ""

    cols = list(df.columns[:max_periods])
    if not cols:
        return ""

    col_labels = []
    for c in cols:
        try:
            dt = c.to_pydatetime() if hasattr(c, 'to_pydatetime') else c
            col_labels.append(dt.strftime("%b '%y"))
        except Exception:
            col_labels.append(str(c))

    th_html = '<th style="text-align:left;">Item</th>' + "".join(f'<th style="text-align:right;">{lbl}</th>' for lbl in col_labels)

    body = ""
    for display_label, keys in row_defs:
        vals = []
        found_key = None
        for key in keys:
            if key in df.index:
                found_key = key
                break
        if not found_key:
            continue

        is_eps = "eps" in display_label.lower()
        is_shares = "shares" in display_label.lower() or "book value" in display_label.lower()
        is_key_row = display_label.lower() in _KEY_ROW_LABELS

        for c in cols:
            raw = df.loc[found_key, c] if found_key in df.index else None
            vals.append(raw)

        formatted = [_fmt_statement_val(v, is_eps, is_shares) for v in vals]
        nums = []
        for v in vals:
            try:
                nums.append(float(v) if v is not None and not (isinstance(v, float) and math.isnan(v)) else None)
            except (ValueError, TypeError):
                nums.append(None)

        label_style = 'font-weight:600;color:#e8e9f0;' if is_key_row else 'color:#9899a8;'
        val_cells = ""
        for j, fv in enumerate(formatted):
            cls = ""
            if j > 0 and nums[j] is not None and nums[j-1] is not None and nums[j-1] != 0:
                cls = ' class="tg"' if nums[j] > nums[j-1] else (' class="tr"' if nums[j] < nums[j-1] else '')
            val_style = 'font-weight:600;' if is_key_row else ''
            val_cells += f'<td style="text-align:right;{val_style}"{cls}>{fv}</td>'

        body += f'<tr><td style="{label_style}">{display_label}</td>{val_cells}</tr>\n'

    if not body:
        return ""
    return f'<div style="overflow-x:auto;"><table><thead><tr>{th_html}</tr></thead><tbody>{body}</tbody></table></div>'


def _compute_financial_ratios(data):
    """Compute key financial ratios from yfinance data across multiple years."""
    fi = data.get("financials")
    bs = data.get("annual_balance_sheet")
    cf = data.get("annual_cash_flow")
    info = data.get("info", {})
    if fi is None or fi.empty:
        return ""

    cols = list(fi.columns[:5])
    col_labels = []
    for c in cols:
        try:
            dt = c.to_pydatetime() if hasattr(c, 'to_pydatetime') else c
            col_labels.append(f"FY{dt.year}")
        except Exception:
            col_labels.append(str(c))

    ratio_rows = []
    for i, c in enumerate(cols):
        rev = _safe_df_value(fi, c, ["Total Revenue", "Operating Revenue", "Revenue"])
        cogs = _safe_df_value(fi, c, ["Cost Of Revenue"])
        gross = _safe_df_value(fi, c, ["Gross Profit"])
        op_inc = _safe_df_value(fi, c, ["Operating Income", "EBIT"])
        net_inc = _safe_df_value(fi, c, ["Net Income", "Net Income Common Stockholders"])
        ebitda = _safe_df_value(fi, c, ["EBITDA", "Normalized EBITDA"])

        total_assets = _safe_df_value(bs, c, ["Total Assets"]) if bs is not None and not bs.empty and c in bs.columns else None
        total_equity = _safe_df_value(bs, c, ["Total Equity Gross Minority Interest", "Stockholders Equity", "Total Stockholders Equity"]) if bs is not None and not bs.empty and c in bs.columns else None
        total_debt = _safe_df_value(bs, c, ["Total Debt", "Long Term Debt", "Long Term Debt And Capital Lease Obligation"]) if bs is not None and not bs.empty and c in bs.columns else None
        current_assets = _safe_df_value(bs, c, ["Current Assets"]) if bs is not None and not bs.empty and c in bs.columns else None
        current_liab = _safe_df_value(bs, c, ["Current Liabilities"]) if bs is not None and not bs.empty and c in bs.columns else None

        op_cf = _safe_df_value(cf, c, ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"]) if cf is not None and not cf.empty and c in cf.columns else None
        capex = _safe_df_value(cf, c, ["Capital Expenditure"]) if cf is not None and not cf.empty and c in cf.columns else None

        r = {}
        r["gross_margin"] = (gross / rev * 100) if gross and rev and rev != 0 else None
        r["operating_margin"] = (op_inc / rev * 100) if op_inc and rev and rev != 0 else None
        r["net_margin"] = (net_inc / rev * 100) if net_inc and rev and rev != 0 else None
        r["ebitda_margin"] = (ebitda / rev * 100) if ebitda and rev and rev != 0 else None
        r["roe"] = (net_inc / total_equity * 100) if net_inc and total_equity and total_equity != 0 else None
        r["roa"] = (net_inc / total_assets * 100) if net_inc and total_assets and total_assets != 0 else None
        r["debt_equity"] = (total_debt / total_equity * 100) if total_debt and total_equity and total_equity != 0 else None
        r["current_ratio"] = (current_assets / current_liab) if current_assets and current_liab and current_liab != 0 else None
        fcf = (op_cf + capex) if op_cf is not None and capex is not None else None
        r["fcf_margin"] = (fcf / rev * 100) if fcf is not None and rev and rev != 0 else None
        r["asset_turnover"] = (rev / total_assets) if rev and total_assets and total_assets != 0 else None
        ratio_rows.append(r)

    if not ratio_rows:
        return ""

    ratio_defs = [
        ("Gross Margin %", "gross_margin", False),
        ("Operating Margin %", "operating_margin", False),
        ("Net Margin %", "net_margin", False),
        ("EBITDA Margin %", "ebitda_margin", False),
        ("ROE %", "roe", False),
        ("ROA %", "roa", False),
        ("Debt/Equity %", "debt_equity", True),
        ("Current Ratio", "current_ratio", False),
        ("FCF Margin %", "fcf_margin", False),
        ("Asset Turnover", "asset_turnover", False),
    ]

    th = '<th style="text-align:left;">Ratio</th>' + "".join(f'<th style="text-align:right;">{lbl}</th>' for lbl in col_labels)
    body = ""
    for label, key, lower_better in ratio_defs:
        vals = [r.get(key) for r in ratio_rows]
        if all(v is None for v in vals):
            continue
        is_ratio = key in ("current_ratio", "asset_turnover")
        cells = ""
        for j, v in enumerate(vals):
            if v is None:
                cells += '<td style="text-align:right;color:#5c5d6e;">—</td>'
            else:
                cls = ""
                if j > 0 and vals[j-1] is not None:
                    if lower_better:
                        cls = ' class="tg"' if v < vals[j-1] else (' class="tr"' if v > vals[j-1] else '')
                    else:
                        cls = ' class="tg"' if v > vals[j-1] else (' class="tr"' if v < vals[j-1] else '')
                fmt = f"{v:.2f}" if is_ratio else f"{v:.1f}%"
                cells += f'<td style="text-align:right;"{cls}>{fmt}</td>'
        body += f'<tr><td style="color:#9899a8;">{label}</td>{cells}</tr>\n'

    if not body:
        return ""
    return f'<div style="overflow-x:auto;"><table><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table></div>'


def _compute_growth_rates(data):
    """Compute compounded growth rates (revenue, net profit, EPS) over 1Y, 3Y, 5Y."""
    fi = data.get("financials")
    if fi is None or fi.empty:
        return {}

    cols = sorted(fi.columns, reverse=False)
    rev_series = []
    profit_series = []
    eps_series = []
    for c in cols:
        rev = _safe_df_value(fi, c, ["Total Revenue", "Operating Revenue", "Revenue"])
        profit = _safe_df_value(fi, c, ["Net Income", "Net Income Common Stockholders"])
        eps = _safe_df_value(fi, c, ["Diluted EPS", "Basic EPS"])
        try:
            yr = c.to_pydatetime().year if hasattr(c, 'to_pydatetime') else int(c)
        except Exception:
            yr = None
        rev_series.append((yr, rev))
        profit_series.append((yr, profit))
        eps_series.append((yr, eps))

    def _cagr(series, years):
        if len(series) < 2:
            return None
        latest = series[-1][1]
        for yr, val in reversed(series[:-1]):
            if yr is not None and series[-1][0] is not None and series[-1][0] - yr >= years - 1:
                if val and val > 0 and latest and latest > 0:
                    n = series[-1][0] - yr
                    if n > 0:
                        return ((latest / val) ** (1 / n) - 1) * 100
                break
        return None

    result = {}
    for label, series in [("Revenue", rev_series), ("Net Profit", profit_series), ("EPS", eps_series)]:
        items = []
        y1 = _cagr(series, 1) if len(series) >= 2 else None
        y3 = _cagr(series, 3) if len(series) >= 4 else None
        y5 = _cagr(series, 5) if len(series) >= 5 else None
        if y1 is not None:
            items.append(("1-Year", f"{y1:+.1f}%"))
        if y3 is not None:
            items.append(("3-Year CAGR", f"{y3:+.1f}%"))
        if y5 is not None:
            items.append(("5-Year CAGR", f"{y5:+.1f}%"))
        if items:
            result[label] = items

    return result


# ─────────────────────────────────────────────────────────────────────────────
# INDUSTRY PEERS (live yfinance data)
# ─────────────────────────────────────────────────────────────────────────────

_SECTOR_PEER_MAP = {
    "Technology":              ["AAPL", "MSFT", "GOOGL", "META", "NVDA", "ORCL", "CRM", "ADBE", "INTC", "AMD", "CSCO", "IBM", "AVGO", "TXN", "QCOM", "NOW", "PANW", "SHOP", "SQ", "SNOW"],
    "Financial Services":      ["JPM", "BAC", "WFC", "GS", "MS", "C", "BLK", "SCHW", "AXP", "V", "MA", "PYPL", "COF", "USB", "PNC"],
    "Healthcare":              ["JNJ", "UNH", "PFE", "ABBV", "MRK", "LLY", "TMO", "ABT", "DHR", "BMY", "AMGN", "MDT", "ISRG", "GILD", "VRTX"],
    "Consumer Cyclical":       ["AMZN", "TSLA", "HD", "NKE", "MCD", "SBUX", "LOW", "TJX", "BKNG", "CMG", "ORLY", "ROST", "DG", "DLTR", "EBAY"],
    "Consumer Defensive":      ["PG", "KO", "PEP", "WMT", "COST", "CL", "MDLZ", "PM", "MO", "GIS", "KMB", "SJM", "HSY", "K", "EL"],
    "Energy":                  ["XOM", "CVX", "COP", "SLB", "EOG", "MPC", "PSX", "VLO", "OXY", "HES", "DVN", "HAL", "FANG", "BKR", "KMI"],
    "Industrials":             ["CAT", "HON", "UNP", "BA", "RTX", "DE", "GE", "LMT", "MMM", "UPS", "FDX", "WM", "EMR", "ITW", "ETN"],
    "Communication Services":  ["GOOGL", "META", "DIS", "NFLX", "CMCSA", "T", "VZ", "TMUS", "CHTR", "EA", "ATVI", "WBD", "PARA", "MTCH", "TTWO"],
    "Basic Materials":         ["LIN", "APD", "SHW", "ECL", "FCX", "NEM", "NUE", "DD", "DOW", "PPG", "VMC", "MLM", "ALB", "CF", "MOS"],
    "Real Estate":             ["AMT", "PLD", "CCI", "EQIX", "SPG", "PSA", "O", "WELL", "DLR", "AVB", "EQR", "VTR", "ARE", "MAA", "UDR"],
    "Utilities":               ["NEE", "DUK", "SO", "D", "AEP", "SRE", "XEL", "EXC", "WEC", "ED", "ES", "AWK", "AEE", "CMS", "DTE"],
}


def fetch_industry_peers(ticker_symbol, sector, industry, max_peers=8):
    """Fetch a handful of peers from the same sector for comparison."""
    candidates = _SECTOR_PEER_MAP.get(sector, [])
    symbol_upper = ticker_symbol.upper()
    candidates = [c for c in candidates if c != symbol_upper][:max_peers + 4]

    peers = []
    for sym in candidates:
        try:
            t = yf.Ticker(sym)
            inf = t.info or {}
            name = safe_get(inf, "shortName", sym)
            pe = safe_get(inf, "trailingPE", safe_get(inf, "forwardPE"))
            pb = safe_get(inf, "priceToBook")
            mcap = safe_get(inf, "marketCap", 0)
            roe_val = safe_get(inf, "returnOnEquity")
            margin = safe_get(inf, "profitMargins")
            price = safe_get(inf, "currentPrice", safe_get(inf, "regularMarketPrice"))
            rev_g = safe_get(inf, "revenueGrowth")
            peers.append({
                "symbol": sym, "name": name, "pe": pe, "pb": pb,
                "mcap": mcap, "roe": roe_val, "margin": margin,
                "price": price, "rev_growth": rev_g, "is_self": False,
            })
        except Exception:
            continue
        if len(peers) >= max_peers:
            break

    return peers


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
        mom_parts.append(f"1M {r1m:+.1f}%")
        if r1m > 10: momentum += 1
        elif r1m < -10: momentum -= 1
    if r6m is not None:
        mom_parts.append(f"6M {r6m:+.1f}%")
        if r6m > 20: momentum += 1
        elif r6m < -20: momentum -= 1

    hist_1y = data.get("hist_1y")
    if hist_1y is not None and not hist_1y.empty and len(hist_1y) >= 30:
        closes = hist_1y["Close"].dropna()
        if len(closes) >= 14:
            rsi_val = _compute_rsi(closes).iloc[-1]
            mom_parts.append(f"RSI {rsi_val:.0f}")
            if rsi_val < 35: momentum += 1
            elif rsi_val > 70: momentum -= 1
        if len(closes) >= 35:
            macd_l, sig_l = _compute_macd(closes)
            if not macd_l.empty and not sig_l.empty:
                if macd_l.iloc[-1] > sig_l.iloc[-1]:
                    momentum += 1
                    mom_parts.append("MACD bullish")
                else:
                    momentum -= 1
                    mom_parts.append("MACD bearish")
        if len(closes) >= 200:
            dma200 = closes.rolling(200).mean().iloc[-1]
            if dma200 and dma200 > 0:
                if closes.iloc[-1] > dma200:
                    momentum += 1
                    mom_parts.append("Above 200DMA")
                else:
                    momentum -= 1
                    mom_parts.append("Below 200DMA")

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


# ─────────────────────────────────────────────────────────────────────────────
# SANKEY FLOW DIAGRAM SVG GENERATORS
# ─────────────────────────────────────────────────────────────────────────────

def _fmt_money(val, currency="$"):
    """Format a value in millions to a readable string."""
    if val is None:
        return "—"
    sign = "-" if val < 0 else ""
    av = abs(val)
    if av >= 1e6:
        return f"{sign}{currency}{av/1e6:,.1f}T"
    if av >= 1e3:
        return f"{sign}{currency}{av/1e3:,.1f}B"
    if av >= 1:
        return f"{sign}{currency}{av:,.0f}M"
    return f"{sign}{currency}{av:,.1f}M"


def _sankey_band(x0, y0_top, y0_bot, x1, y1_top, y1_bot, color, opacity=0.45):
    """Cubic-bezier ribbon between two vertical spans."""
    mx = (x0 + x1) / 2
    return (f'<path d="M{x0:.1f},{y0_top:.1f} C{mx:.1f},{y0_top:.1f} {mx:.1f},{y1_top:.1f} {x1:.1f},{y1_top:.1f}'
            f' L{x1:.1f},{y1_bot:.1f} C{mx:.1f},{y1_bot:.1f} {mx:.1f},{y0_bot:.1f} {x0:.1f},{y0_bot:.1f} Z"'
            f' fill="{color}" opacity="{opacity}"/>\n')


def _build_income_sankey_svg(src, col, width=1040, height=480, currency="$", divisor=1e6, unit_label="Millions"):
    """Build a single income-statement Sankey for one period column."""
    def _v(keys):
        for k in keys:
            if k in src.index:
                v = src.loc[k, col]
                if v is not None and not (isinstance(v, float) and math.isnan(v)):
                    return float(v) / divisor
        return 0

    rev = _v(["Total Revenue", "Operating Revenue", "Revenue"])
    cogs = _v(["Cost Of Revenue", "Reconciled Cost Of Revenue"])
    gross = _v(["Gross Profit"])
    if not gross and rev and cogs: gross = rev - cogs
    if not cogs and rev and gross: cogs = rev - gross
    rd = _v(["Research And Development"])
    sga = _v(["Selling General And Administration"])
    opex = rd + sga if (rd or sga) else _v(["Operating Expense", "Total Operating Expenses"])
    op_inc = _v(["Operating Income", "EBIT"])
    if not op_inc and gross and opex: op_inc = gross - opex
    tax = _v(["Tax Provision", "Income Tax Expense"])
    interest = abs(_v(["Interest Expense"]))
    other = abs(_v(["Other Income Expense", "Other Non Operating Income Expenses"]))
    net = _v(["Net Income", "Net Income Common Stockholders"])

    if not rev or rev <= 0:
        return "", {}

    try:
        dt = col.to_pydatetime() if hasattr(col, 'to_pydatetime') else col
        period_label = dt.strftime("%b %Y")
    except Exception:
        period_label = str(col)

    fm = lambda v: _fmt_money(v, currency)

    pad = {"l": 100, "r": 120, "t": 25, "b": 25}
    usable_w = width - pad["l"] - pad["r"]
    node_w = 16
    cols_x = [pad["l"], pad["l"] + usable_w * 0.28, pad["l"] + usable_w * 0.56, pad["l"] + usable_w * 0.84]
    chart_h = height - pad["t"] - pad["b"]

    nodes = []
    nodes.append({"col": 0, "label": f"Revenue\n{fm(rev)}", "val": rev, "color": "#3d9cf5"})
    nodes.append({"col": 1, "label": f"Cost of Revenue\n{fm(cogs)}", "val": cogs, "color": "#ff4d6d"})
    nodes.append({"col": 1, "label": f"Gross Profit\n{fm(gross)}", "val": gross, "color": "#00e5a0"})
    col2_items = []
    if rd: col2_items.append({"label": f"R&D\n{fm(rd)}", "val": rd, "color": "#ff4d6d"})
    if sga: col2_items.append({"label": f"SG&A\n{fm(sga)}", "val": sga, "color": "#f5a623"})
    if not rd and not sga and opex:
        col2_items.append({"label": f"Op. Expenses\n{fm(opex)}", "val": opex, "color": "#ff4d6d"})
    col2_items.append({"label": f"Operating Inc.\n{fm(op_inc)}", "val": op_inc, "color": "#00e5a0"})
    for item in col2_items:
        item["col"] = 2
        nodes.append(item)
    col3_items = []
    if tax and tax > rev * 0.005:
        col3_items.append({"label": f"Tax\n{fm(tax)}", "val": tax, "color": "#f5a623"})
    if interest and interest > rev * 0.005:
        col3_items.append({"label": f"Interest\n{fm(interest)}", "val": interest, "color": "#9b7fff"})
    if other and other > rev * 0.005:
        col3_items.append({"label": f"Other\n{fm(other)}", "val": other, "color": "#5c5d6e"})
    margin_str = f"\n({net/rev*100:.1f}% margin)" if rev else ""
    col3_items.append({"label": f"Net Income\n{fm(net)}{margin_str}", "val": net, "color": "#00e5a0" if net >= 0 else "#ff4d6d"})
    for item in col3_items:
        item["col"] = 3
        nodes.append(item)

    # Two-pass layout per column to prevent overflow from min-height bumps
    for ci in range(4):
        cn_list = [n for n in nodes if n["col"] == ci]
        if not cn_list:
            continue
        gap = 8
        gap_total = max(0, (len(cn_list) - 1) * gap)
        bar_space = chart_h - gap_total
        raw = [(abs(n["val"]) / rev) * bar_space for n in cn_list]
        heights = [max(14, r) for r in raw]
        if sum(heights) > bar_space:
            fixed = sum(h for h in heights if h <= 14)
            remain = bar_space - fixed
            large_sum = sum(h for h in heights if h > 14)
            scale = remain / large_sum if large_sum > 0 else 1
            heights = [h if h <= 14 else h * scale for h in heights]
        y_cursor = pad["t"]
        for i, n in enumerate(cn_list):
            n["y"] = y_cursor; n["h"] = heights[i]; n["x"] = cols_x[ci]
            y_cursor += heights[i] + gap

    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" style="width:100%;height:auto;font-family:\'DM Sans\',Fira Code,monospace;">\n'
    svg += f'  <rect width="{width}" height="{height}" fill="#0d0e14" rx="10"/>\n'

    rev_node = [n for n in nodes if n["col"] == 0][0]
    cogs_node = [n for n in nodes if n["col"] == 1 and "Cost" in n["label"]][0]
    gross_node = [n for n in nodes if n["col"] == 1 and "Gross" in n["label"]][0]
    rx = rev_node["x"] + node_w
    cogs_src_h = (cogs / rev if rev else 0.5) * rev_node["h"]
    svg += _sankey_band(rx, rev_node["y"], rev_node["y"] + cogs_src_h, cogs_node["x"], cogs_node["y"], cogs_node["y"] + cogs_node["h"], cogs_node["color"], 0.35)
    svg += _sankey_band(rx, rev_node["y"] + cogs_src_h, rev_node["y"] + rev_node["h"], gross_node["x"], gross_node["y"], gross_node["y"] + gross_node["h"], gross_node["color"], 0.35)

    gx = gross_node["x"] + node_w
    col2_nodes = [n for n in nodes if n["col"] == 2]
    col2_total = sum(abs(c["val"]) for c in col2_nodes)
    g_cursor = gross_node["y"]
    for cn in col2_nodes:
        src_h = (abs(cn["val"]) / col2_total) * gross_node["h"] if col2_total else cn["h"]
        svg += _sankey_band(gx, g_cursor, g_cursor + src_h, cn["x"], cn["y"], cn["y"] + cn["h"], cn["color"], 0.35)
        g_cursor += src_h

    oi_node = [n for n in nodes if n["col"] == 2 and "Operating Inc" in n["label"]]
    if oi_node:
        oi_node = oi_node[0]
        ox = oi_node["x"] + node_w
        col3_nodes = [n for n in nodes if n["col"] == 3]
        col3_total = sum(abs(c["val"]) for c in col3_nodes)
        o_cursor = oi_node["y"]
        for cn in col3_nodes:
            src_h = (abs(cn["val"]) / col3_total) * oi_node["h"] if col3_total else cn["h"]
            svg += _sankey_band(ox, o_cursor, o_cursor + src_h, cn["x"], cn["y"], cn["y"] + cn["h"], cn["color"], 0.35)
            o_cursor += src_h

    for n in nodes:
        svg += f'  <rect x="{n["x"]:.1f}" y="{n["y"]:.1f}" width="{node_w}" height="{n["h"]:.1f}" rx="4" fill="{n["color"]}" opacity="0.95"/>\n'

    for n in nodes:
        lines = n["label"].split("\n")
        tx = (n["x"] - 6) if n["col"] == 0 else (n["x"] + node_w + 6)
        anchor = "end" if n["col"] == 0 else "start"
        ty = n["y"] + n["h"] / 2 - (len(lines) - 1) * 6
        for li, line in enumerate(lines):
            fw = "700" if li == 0 else "500"
            fs = "10" if li == 0 else "9"
            fc = "#e8e9f0" if li == 0 else n["color"]
            svg += f'  <text x="{tx}" y="{ty + li * 13:.1f}" text-anchor="{anchor}" font-size="{fs}" fill="{fc}" font-weight="{fw}">{line}</text>\n'

    svg += f'  <text x="{width/2}" y="{height - 6}" text-anchor="middle" font-size="9" fill="#5c5d6e">{period_label} · All values in {currency} {unit_label}</text>\n'
    svg += '</svg>'
    return svg, {"period": period_label, "revenue": rev, "net_income": net}


def generate_income_sankey_svg(data, width=1040, height=480, currency="$", divisor=1e6, unit_label="Millions"):
    """Generate income Sankey for the latest annual period (backward-compat wrapper)."""
    fi = data.get("financials")
    qi = data.get("quarterly_income")
    src = fi if fi is not None and not fi.empty else qi
    if src is None or src.empty:
        return "", {}
    return _build_income_sankey_svg(src, src.columns[0], width, height, currency, divisor, unit_label)


def generate_income_sankey_panels(data, max_periods=4, width=1040, height=480, currency="$", divisor=1e6, unit_label="Millions"):
    """Generate quarterly + annual income Sankey panels for carousel."""
    panels = {"quarterly": [], "annual": []}
    qi = data.get("quarterly_income")
    if qi is not None and not qi.empty:
        for col in qi.columns[:max_periods]:
            svg, meta = _build_income_sankey_svg(qi, col, width, height, currency, divisor, unit_label)
            if svg:
                panels["quarterly"].append({"svg": svg, "label": meta["period"]})
    fi = data.get("financials")
    if fi is not None and not fi.empty:
        for col in fi.columns[:max_periods]:
            svg, meta = _build_income_sankey_svg(fi, col, width, height, currency, divisor, unit_label)
            if svg:
                panels["annual"].append({"svg": svg, "label": meta["period"]})
    return panels


def _build_bs_sankey_svg(src, col, width=1040, height=500, currency="$", divisor=1e6, unit_label="Millions"):
    """Build a single balance-sheet Sankey for one period column."""
    def _v(keys):
        for k in keys:
            if k in src.index:
                v = src.loc[k, col]
                if v is not None and not (isinstance(v, float) and math.isnan(v)):
                    return float(v) / divisor
        return 0

    total_assets = _v(["Total Assets"])
    cash = _v(["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"])
    receivables = _v(["Accounts Receivable", "Net Receivables", "Receivables"])
    inventory = _v(["Inventory"])
    current_assets = _v(["Current Assets"])
    ppe = _v(["Net PPE", "Gross PPE"])
    goodwill = _v(["Goodwill"])
    intangibles = _v(["Intangible Assets", "Net Intangible Assets"])
    if not intangibles:
        goia = _v(["Goodwill And Other Intangible Assets"])
        intangibles = max(0, goia - goodwill) if (goia and goodwill) else (goia or 0)
    total_liab = _v(["Total Liabilities Net Minority Interest", "Total Liabilities"])
    current_liab = _v(["Current Liabilities"])
    long_debt = _v(["Long Term Debt", "Long Term Debt And Capital Lease Obligation"])
    total_equity = _v(["Total Equity Gross Minority Interest", "Stockholders Equity", "Total Stockholders Equity"])

    if not total_assets or total_assets <= 0:
        return "", {}

    try:
        dt = col.to_pydatetime() if hasattr(col, 'to_pydatetime') else col
        period_label = dt.strftime("%b %Y")
    except Exception:
        period_label = str(col)

    fm = lambda v: _fmt_money(v, currency)
    pad = {"l": 100, "r": 140, "t": 30, "b": 25}
    usable_w = width - pad["l"] - pad["r"]
    node_w = 16
    cx = [pad["l"], pad["l"] + usable_w * 0.45, pad["l"] + usable_w * 0.80]
    half_h = (height - pad["t"] - pad["b"] - 20) / 2

    asset_detail = []
    if cash: asset_detail.append(("Cash & Equiv.", cash, "#00e5a0"))
    if receivables: asset_detail.append(("Receivables", receivables, "#3d9cf5"))
    if inventory: asset_detail.append(("Inventory", inventory, "#f5a623"))
    other_ca = max(0, current_assets - cash - receivables - inventory)
    if other_ca > total_assets * 0.01: asset_detail.append(("Other Current", other_ca, "#5c5d6e"))
    if ppe: asset_detail.append(("PP&E", ppe, "#9b7fff"))
    if goodwill: asset_detail.append(("Goodwill", goodwill, "#3d9cf5"))
    if intangibles > total_assets * 0.01: asset_detail.append(("Other Intangibles", intangibles, "#f5a623"))
    non_current_other = max(0, total_assets - current_assets - ppe - goodwill - intangibles)
    if non_current_other > total_assets * 0.02: asset_detail.append(("Other Non-Curr.", non_current_other, "#5c5d6e"))

    le_detail = []
    if current_liab: le_detail.append(("Current Liab.", current_liab, "#ff4d6d"))
    if long_debt: le_detail.append(("Long-Term Debt", long_debt, "#f5a623"))
    other_liab = max(0, total_liab - current_liab - long_debt)
    if other_liab > total_assets * 0.02: le_detail.append(("Other Liab.", other_liab, "#5c5d6e"))
    if total_equity: le_detail.append(("Equity", abs(total_equity), "#00e5a0" if total_equity >= 0 else "#ff4d6d"))

    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" style="width:100%;height:auto;font-family:\'DM Sans\',Fira Code,monospace;">\n'
    svg += f'  <rect width="{width}" height="{height}" fill="#0d0e14" rx="10"/>\n'

    def _layout_col(items, y_start, avail_h, col_x):
        nodes_out = []
        total_val = sum(v for _, v, _ in items)
        n = len(items)
        if not n or not total_val: return nodes_out
        gap = 6; gap_total = max(0, (n - 1) * gap); bar_space = avail_h - gap_total; min_h = 14
        raw = [(val / total_val) * bar_space for _, val, _ in items]
        heights = [max(min_h, r) for r in raw]
        if sum(heights) > bar_space:
            fixed = sum(h for h in heights if h <= min_h)
            remain = bar_space - fixed
            large_sum = sum(h for h in heights if h > min_h)
            scale = remain / large_sum if large_sum > 0 else 1
            heights = [h if h <= min_h else h * scale for h in heights]
        y_cur = y_start
        for i, (lbl, val, clr) in enumerate(items):
            nodes_out.append({"x": col_x, "y": y_cur, "h": heights[i], "val": val, "label": lbl, "color": clr})
            y_cur += heights[i] + gap
        return nodes_out

    a_y0 = pad["t"]
    root_h = half_h - 5
    a_subs = _layout_col(asset_detail, a_y0, root_h, cx[2])
    svg += f'  <text x="{cx[0] - 6}" y="{a_y0 + half_h / 2:.1f}" text-anchor="end" font-size="10" fill="#e8e9f0" font-weight="700">Total Assets</text>\n'
    svg += f'  <text x="{cx[0] - 6}" y="{a_y0 + half_h / 2 + 14:.1f}" text-anchor="end" font-size="9" fill="#3d9cf5" font-weight="600">{fm(total_assets)}</text>\n'
    if a_subs:
        a_total = sum(d["val"] for d in a_subs)
        a_cur = a_y0
        for d in a_subs:
            bh = (d["val"] / a_total) * root_h if a_total > 0 else root_h / len(a_subs)
            svg += _sankey_band(cx[0] + node_w, a_cur, a_cur + bh, d["x"], d["y"], d["y"] + d["h"], d["color"], 0.30)
            a_cur += bh
    svg += f'  <rect x="{cx[0]}" y="{a_y0:.1f}" width="{node_w}" height="{root_h:.1f}" rx="4" fill="#3d9cf5" opacity="0.95"/>\n'
    for d in a_subs:
        svg += f'  <rect x="{d["x"]}" y="{d["y"]:.1f}" width="{node_w}" height="{d["h"]:.1f}" rx="4" fill="{d["color"]}" opacity="0.9"/>\n'
        pct = f" ({d['val']/total_assets*100:.1f}%)" if total_assets else ""
        svg += f'  <text x="{d["x"] + node_w + 6}" y="{d["y"] + d["h"]/2 + 4:.1f}" font-size="9" fill="{d["color"]}" font-weight="500">{d["label"]}: {fm(d["val"])}{pct}</text>\n'

    div_y = a_y0 + half_h + 4
    svg += f'  <line x1="20" y1="{div_y}" x2="{width - 20}" y2="{div_y}" stroke="rgba(255,255,255,0.08)" stroke-width="1"/>\n'

    le_y0 = a_y0 + half_h + 10
    le_total_val = total_liab + total_equity
    le_subs = _layout_col(le_detail, le_y0, root_h, cx[2])
    svg += f'  <text x="{cx[0] - 6}" y="{le_y0 + root_h / 2:.1f}" text-anchor="end" font-size="10" fill="#e8e9f0" font-weight="700">Liab. + Equity</text>\n'
    svg += f'  <text x="{cx[0] - 6}" y="{le_y0 + root_h / 2 + 14:.1f}" text-anchor="end" font-size="9" fill="#f5a623" font-weight="600">{fm(le_total_val)}</text>\n'
    if le_subs:
        le_d_total = sum(d["val"] for d in le_subs)
        le_cur = le_y0
        for d in le_subs:
            bh = (d["val"] / le_d_total) * root_h if le_d_total > 0 else root_h / len(le_subs)
            svg += _sankey_band(cx[0] + node_w, le_cur, le_cur + bh, d["x"], d["y"], d["y"] + d["h"], d["color"], 0.30)
            le_cur += bh
    svg += f'  <rect x="{cx[0]}" y="{le_y0:.1f}" width="{node_w}" height="{root_h:.1f}" rx="4" fill="#f5a623" opacity="0.95"/>\n'
    for d in le_subs:
        svg += f'  <rect x="{d["x"]}" y="{d["y"]:.1f}" width="{node_w}" height="{d["h"]:.1f}" rx="4" fill="{d["color"]}" opacity="0.9"/>\n'
        pct = f" ({d['val']/le_total_val*100:.1f}%)" if le_total_val else ""
        svg += f'  <text x="{d["x"] + node_w + 6}" y="{d["y"] + d["h"]/2 + 4:.1f}" font-size="9" fill="{d["color"]}" font-weight="500">{d["label"]}: {fm(d["val"])}{pct}</text>\n'

    svg += f'  <text x="{width/2}" y="{height - 6}" text-anchor="middle" font-size="9" fill="#5c5d6e">As of {period_label} · All values in {currency} {unit_label}</text>\n'
    svg += '</svg>'
    return svg, {"period": period_label}


def generate_balance_sheet_sankey_svg(data, width=1040, height=500, currency="$", divisor=1e6, unit_label="Millions"):
    """Backward-compat wrapper — latest annual period."""
    bs = data.get("annual_balance_sheet")
    qbs = data.get("balance_sheet")
    src = bs if bs is not None and not bs.empty else qbs
    if src is None or src.empty:
        return ""
    svg, _ = _build_bs_sankey_svg(src, src.columns[0], width, height, currency, divisor, unit_label)
    return svg


def generate_bs_sankey_panels(data, max_periods=4, width=1040, height=500, currency="$", divisor=1e6, unit_label="Millions"):
    """Generate quarterly + annual balance-sheet Sankey panels."""
    panels = {"quarterly": [], "annual": []}
    qbs = data.get("balance_sheet")
    if qbs is not None and not qbs.empty:
        for col in qbs.columns[:max_periods]:
            svg, meta = _build_bs_sankey_svg(qbs, col, width, height, currency, divisor, unit_label)
            if svg:
                panels["quarterly"].append({"svg": svg, "label": meta["period"]})
    bs = data.get("annual_balance_sheet")
    if bs is not None and not bs.empty:
        for col in bs.columns[:max_periods]:
            svg, meta = _build_bs_sankey_svg(bs, col, width, height, currency, divisor, unit_label)
            if svg:
                panels["annual"].append({"svg": svg, "label": meta["period"]})
    return panels


def _build_cf_sankey_svg(src, col, width=1040, height=420, currency="$", divisor=1e6, unit_label="Millions"):
    """Build a single cash-flow Sankey for one period column."""
    def _v(keys):
        for k in keys:
            if k in src.index:
                v = src.loc[k, col]
                if v is not None and not (isinstance(v, float) and math.isnan(v)):
                    return float(v) / divisor
        return 0

    op_cf = _v(["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"])
    capex = abs(_v(["Capital Expenditure"]))
    fcf = op_cf - capex if capex else _v(["Free Cash Flow"])
    dividends = abs(_v(["Common Stock Dividend Paid", "Cash Dividends Paid"]))
    buybacks = abs(_v(["Repurchase Of Capital Stock", "Common Stock Payments"]))
    debt_repaid = abs(_v(["Long Term Debt Payments", "Repayment Of Debt"]))

    if not op_cf or op_cf <= 0:
        return "", {}

    # Guard: if FCF is negative, show it as zero with capex consuming all of OpCF
    if fcf < 0:
        fcf = 0

    try:
        dt = col.to_pydatetime() if hasattr(col, 'to_pydatetime') else col
        period_label = dt.strftime("FY%Y")
    except Exception:
        period_label = str(col)

    fm = lambda v: _fmt_money(v, currency)
    pad = {"l": 100, "r": 120, "t": 25, "b": 25}
    usable_w = width - pad["l"] - pad["r"]
    node_w = 16
    chart_h = height - pad["t"] - pad["b"]

    col0 = [{"label": f"Operating CF\n{fm(op_cf)}", "val": op_cf, "color": "#00e5a0"}]
    col1 = []
    if capex > op_cf * 0.01:
        col1.append({"label": f"Capital Exp.\n{fm(capex)}", "val": min(capex, op_cf), "color": "#ff4d6d"})
    if fcf > 0:
        col1.append({"label": f"Free Cash Flow\n{fm(fcf)}", "val": fcf, "color": "#3d9cf5"})
    if not col1:
        col1.append({"label": f"Capital Exp.\n{fm(capex)}", "val": op_cf, "color": "#ff4d6d"})

    col2 = []
    if fcf > 0:
        if dividends > op_cf * 0.01:
            col2.append({"label": f"Dividends\n{fm(dividends)}", "val": dividends, "color": "#f5a623"})
        if buybacks > op_cf * 0.01:
            col2.append({"label": f"Buybacks\n{fm(buybacks)}", "val": buybacks, "color": "#9b7fff"})
        if debt_repaid > op_cf * 0.01:
            col2.append({"label": f"Debt Repaid\n{fm(debt_repaid)}", "val": debt_repaid, "color": "#ff4d6d"})
        remaining = max(0, fcf - dividends - buybacks - debt_repaid)
        if remaining > op_cf * 0.01:
            col2.append({"label": f"Retained / Other\n{fm(remaining)}", "val": remaining, "color": "#00e5a0"})

    # Only include col2 if it has items; adjust column positions accordingly
    all_cols = [col0, col1] + ([col2] if col2 else [])
    n_cols = len(all_cols)
    cx = [pad["l"] + usable_w * (i / max(1, n_cols - 1)) * 0.85 for i in range(n_cols)] if n_cols > 1 else [pad["l"]]

    for ci, cn_list in enumerate(all_cols):
        col_total = sum(n["val"] for n in cn_list)
        gap = 8; gap_total = max(0, (len(cn_list) - 1) * gap)
        avail_h = chart_h - gap_total; y_cur = pad["t"]
        for n in cn_list:
            h = max(16, (n["val"] / col_total) * avail_h) if col_total else 20
            n["x"] = cx[ci]; n["y"] = y_cur; n["h"] = h
            y_cur += h + gap

    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" style="width:100%;height:auto;font-family:\'DM Sans\',Fira Code,monospace;">\n'
    svg += f'  <rect width="{width}" height="{height}" fill="#0d0e14" rx="10"/>\n'

    # Bands: col0 → col1, proportional to col0
    col1_total = sum(n["val"] for n in col1)
    s_cur = col0[0]["y"]
    for dn in col1:
        bh = (dn["val"] / col1_total) * col0[0]["h"] if col1_total else dn["h"]
        svg += _sankey_band(col0[0]["x"] + node_w, s_cur, s_cur + bh, dn["x"], dn["y"], dn["y"] + dn["h"], dn["color"], 0.35)
        s_cur += bh
    # Bands: FCF → col2 (only if col2 exists)
    if col2:
        fcf_node = [n for n in col1 if "Free" in n["label"]]
        if fcf_node:
            fn = fcf_node[0]
            col2_total = sum(n["val"] for n in col2)
            f_cur = fn["y"]
            for dn in col2:
                bh = (dn["val"] / col2_total) * fn["h"] if col2_total else dn["h"]
                svg += _sankey_band(fn["x"] + node_w, f_cur, f_cur + bh, dn["x"], dn["y"], dn["y"] + dn["h"], dn["color"], 0.35)
                f_cur += bh

    for ci, cn_list in enumerate(all_cols):
        for n in cn_list:
            svg += f'  <rect x="{n["x"]:.1f}" y="{n["y"]:.1f}" width="{node_w}" height="{n["h"]:.1f}" rx="4" fill="{n["color"]}" opacity="0.95"/>\n'
            lines = n["label"].split("\n")
            tx = (n["x"] - 6) if ci == 0 else (n["x"] + node_w + 6)
            anchor = "end" if ci == 0 else "start"
            ty = n["y"] + n["h"] / 2 - (len(lines) - 1) * 6
            for li, line in enumerate(lines):
                fw = "700" if li == 0 else "500"; fs = "10" if li == 0 else "9"
                fc = "#e8e9f0" if li == 0 else n["color"]
                svg += f'  <text x="{tx}" y="{ty + li * 13:.1f}" text-anchor="{anchor}" font-size="{fs}" fill="{fc}" font-weight="{fw}">{line}</text>\n'

    svg += f'  <text x="{width/2}" y="{height - 6}" text-anchor="middle" font-size="9" fill="#5c5d6e">{period_label} · All values in {currency} {unit_label}</text>\n'
    svg += '</svg>'
    return svg, {"period": period_label}


def generate_cashflow_sankey_svg(data, width=1040, height=420, currency="$", divisor=1e6, unit_label="Millions"):
    """Backward-compat wrapper — latest annual period."""
    cf = data.get("annual_cash_flow")
    qcf = data.get("quarterly_cash_flow")
    src = cf if cf is not None and not cf.empty else qcf
    if src is None or src.empty:
        return ""
    svg, _ = _build_cf_sankey_svg(src, src.columns[0], width, height, currency, divisor, unit_label)
    return svg


def generate_cf_sankey_panels(data, max_periods=4, width=1040, height=420, currency="$", divisor=1e6, unit_label="Millions"):
    """Generate quarterly + annual cash-flow Sankey panels."""
    panels = {"quarterly": [], "annual": []}
    qcf = data.get("quarterly_cash_flow")
    if qcf is not None and not qcf.empty:
        for col in qcf.columns[:max_periods]:
            svg, meta = _build_cf_sankey_svg(qcf, col, width, height, currency, divisor, unit_label)
            if svg:
                panels["quarterly"].append({"svg": svg, "label": meta["period"]})
    cf = data.get("annual_cash_flow")
    if cf is not None and not cf.empty:
        for col in cf.columns[:max_periods]:
            svg, meta = _build_cf_sankey_svg(cf, col, width, height, currency, divisor, unit_label)
            if svg:
                panels["annual"].append({"svg": svg, "label": meta["period"]})
    return panels


def generate_pe_pb_chart_svg(series, label="P/E", color="#3d9cf5", width=520, height=200):
    """Generate a trend line chart SVG for PE, PB, or other valuation ratio."""
    headers = series.get("headers", [])
    values = series.get("values", [])
    if not headers or not values:
        return f'<svg viewBox="0 0 {width} {height}"><text x="{width//2}" y="{height//2}" text-anchor="middle" fill="#5c5d6e" font-family="Fira Code,monospace" font-size="12">{label} data unavailable</text></svg>'
    pts = [(h, v) for h, v in zip(headers, values) if v is not None and v > 0]
    if len(pts) < 2:
        return f'<svg viewBox="0 0 {width} {height}"><text x="{width//2}" y="{height//2}" text-anchor="middle" fill="#5c5d6e" font-family="Fira Code,monospace" font-size="12">Insufficient {label} data</text></svg>'
    labels_list = [p[0] for p in pts]
    vals = [p[1] for p in pts]
    pad_l, pad_r, pad_t, pad_b = 50, 55, 20, 32
    cw = width - pad_l - pad_r
    ch = height - pad_t - pad_b
    min_v = min(vals) * 0.85
    max_v = max(vals) * 1.15
    vr = max_v - min_v if max_v != min_v else 1
    def xp(i): return pad_l + (i / (len(vals) - 1)) * cw
    def yp(v): return pad_t + (1 - (v - min_v) / vr) * ch
    svg = f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" style="width:100%;">\n'
    svg += f'  <defs><linearGradient id="ag_{label.replace("/","")}" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="{color}" stop-opacity="0.20"/><stop offset="100%" stop-color="{color}" stop-opacity="0.01"/></linearGradient></defs>\n'
    for i in range(5):
        y = pad_t + (i / 4) * ch
        v = max_v - (i / 4) * vr
        svg += f'  <line x1="{pad_l}" y1="{y:.1f}" x2="{width - pad_r}" y2="{y:.1f}" stroke="rgba(255,255,255,0.04)" stroke-width="1"/>\n'
        svg += f'  <text x="{pad_l - 6}" y="{y + 3:.1f}" text-anchor="end" font-family="Fira Code,monospace" font-size="8" fill="#5c5d6e">{v:.1f}</text>\n'
    for i, lb in enumerate(labels_list):
        short = lb[-4:] if len(lb) > 4 else lb
        svg += f'  <text x="{xp(i):.1f}" y="{height - 6}" text-anchor="middle" font-family="Fira Code,monospace" font-size="7" fill="#5c5d6e">{short}</text>\n'
    area = f"M {xp(0):.1f} {yp(vals[0]):.1f} "
    for i in range(1, len(vals)):
        area += f"L {xp(i):.1f} {yp(vals[i]):.1f} "
    area += f"L {xp(len(vals)-1):.1f} {pad_t + ch:.1f} L {xp(0):.1f} {pad_t + ch:.1f} Z"
    svg += f'  <path d="{area}" fill="url(#ag_{label.replace("/","")})"/>\n'
    line_pts = " ".join([f"{xp(i):.1f},{yp(vals[i]):.1f}" for i in range(len(vals))])
    svg += f'  <polyline points="{line_pts}" fill="none" stroke="{color}" stroke-width="2" stroke-linejoin="round"/>\n'
    for i, v in enumerate(vals):
        svg += f'  <circle cx="{xp(i):.1f}" cy="{yp(v):.1f}" r="3" fill="{color}" stroke="#08090d" stroke-width="1.5"><title>{labels_list[i]}: {v:.1f}</title></circle>\n'
    last_v = vals[-1]
    svg += f'  <text x="{xp(len(vals)-1) + 4:.1f}" y="{yp(last_v) + 3:.1f}" font-family="Fira Code,monospace" font-size="9" font-weight="600" fill="{color}">{last_v:.1f}</text>\n'
    svg += '</svg>'
    return svg


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
# CORPORATE ACTIONS BANNER
# ─────────────────────────────────────────────────────────────────────────────

def _build_corporate_actions_html(data):
    """Build an HTML banner showing upcoming earnings and ex-dividend dates."""
    cal = data.get("calendar")
    if not cal:
        return ""

    badges = []
    now = datetime.now()

    earnings_dates = cal.get("Earnings Date") if isinstance(cal, dict) else None
    if earnings_dates:
        if not isinstance(earnings_dates, (list, tuple)):
            earnings_dates = [earnings_dates]
        for ed in earnings_dates:
            try:
                if hasattr(ed, "date"):
                    edt = datetime(ed.year, ed.month, ed.day)
                elif isinstance(ed, str):
                    edt = datetime.strptime(ed[:10], "%Y-%m-%d")
                else:
                    continue
                days_away = (edt - now).days
                date_str = edt.strftime("%b %d")
                if -7 <= days_away <= 0:
                    badges.append(f'<span class="badge badge-earnings badge-imminent">EARNINGS JUST REPORTED: {date_str}</span>')
                elif 0 < days_away <= 7:
                    badges.append(f'<span class="badge badge-earnings badge-imminent">EARNINGS IMMINENT: {date_str}</span>')
                elif 0 < days_away <= 30:
                    badges.append(f'<span class="badge badge-earnings">EARNINGS: {date_str}</span>')
            except Exception:
                continue

    exdiv = cal.get("Ex-Dividend Date") if isinstance(cal, dict) else None
    if exdiv:
        try:
            if hasattr(exdiv, "date"):
                exdt = datetime(exdiv.year, exdiv.month, exdiv.day)
            elif isinstance(exdiv, str):
                exdt = datetime.strptime(str(exdiv)[:10], "%Y-%m-%d")
            else:
                exdt = None
            if exdt:
                days_away = (exdt - now).days
                if -7 <= days_away <= 60:
                    date_str = exdt.strftime("%b %d")
                    badges.append(f'<span class="badge badge-exdiv">EX-DIVIDEND: {date_str}</span>')
        except Exception:
            pass

    divdate = cal.get("Dividend Date") if isinstance(cal, dict) else None
    if divdate and not exdiv:
        try:
            if hasattr(divdate, "date"):
                ddt = datetime(divdate.year, divdate.month, divdate.day)
            elif isinstance(divdate, str):
                ddt = datetime.strptime(str(divdate)[:10], "%Y-%m-%d")
            else:
                ddt = None
            if ddt:
                days_away = (ddt - now).days
                if 0 < days_away <= 60:
                    date_str = ddt.strftime("%b %d")
                    badges.append(f'<span class="badge badge-exdiv">DIVIDEND: {date_str}</span>')
        except Exception:
            pass

    if not badges:
        return ""
    return '<div class="sh-actions">' + " ".join(badges) + "</div>"


def _serialize_chart_data(data):
    """Serialize all historical price data into a JSON string for interactive charts."""
    import json as _json
    import numpy as _np

    full_hist = None
    for fk in ["hist_5y", "hist_3y", "hist_1y", "hist_6m"]:
        fh = data.get(fk)
        if fh is not None and not fh.empty:
            fh_clean = fh[["Open", "High", "Low", "Close", "Volume"]].dropna()
            if full_hist is None or len(fh_clean) > len(full_hist):
                full_hist = fh_clean

    ema50_full = []
    sma200_full = []
    full_date_idx = {}
    if full_hist is not None and not full_hist.empty:
        all_c = [float(v) for v in full_hist["Close"]]
        total = len(all_c)
        ema50_full = [all_c[0]]
        k50 = 2 / 51
        for i in range(1, total):
            ema50_full.append(all_c[i] * k50 + ema50_full[-1] * (1 - k50))
        for i in range(min(49, total)):
            ema50_full[i] = None
        sma200_full = [None] * total
        for i in range(199, total):
            sma200_full[i] = sum(all_c[i - 199 : i + 1]) / 200
        for i, d in enumerate(full_hist.index):
            full_date_idx[d.strftime("%Y-%m-%d")] = i

    periods = [
        ("1D", "hist_1d_intra"), ("1W", "hist_5d"), ("1M", "hist_1mo"),
        ("6M", "hist_6m"), ("1Y", "hist_1y"), ("3Y", "hist_3y"), ("5Y", "hist_5y"),
    ]
    result = {}
    for label, key in periods:
        hist = data.get(key)
        if hist is None or hist.empty or len(hist) < 2:
            continue
        hist = hist[["Open", "High", "Low", "Close", "Volume"]].dropna()
        if len(hist) < 2:
            continue
        is_intraday = (label == "1D")
        dates = [d.strftime("%H:%M") if is_intraday else d.strftime("%Y-%m-%d") for d in hist.index]
        opens = [round(float(v), 2) for v in hist["Open"]]
        highs = [round(float(v), 2) for v in hist["High"]]
        lows = [round(float(v), 2) for v in hist["Low"]]
        closes = [round(float(v), 2) for v in hist["Close"]]
        volumes = [int(v) for v in hist["Volume"]]
        entry = {"d": dates, "o": opens, "h": highs, "l": lows, "c": closes, "v": volumes}

        if len(closes) >= 15:
            c_arr = _np.array(closes, dtype=float)
            delta = _np.diff(c_arr, prepend=c_arr[0])
            gain = _np.where(delta > 0, delta, 0.0)
            loss = _np.where(delta < 0, -delta, 0.0)
            avg_g = _np.full(len(c_arr), _np.nan)
            avg_l = _np.full(len(c_arr), _np.nan)
            avg_g[14] = _np.mean(gain[1:15])
            avg_l[14] = _np.mean(loss[1:15])
            for j in range(15, len(c_arr)):
                avg_g[j] = (avg_g[j-1] * 13 + gain[j]) / 14
                avg_l[j] = (avg_l[j-1] * 13 + loss[j]) / 14
            rs = _np.where(avg_l > 0, avg_g / avg_l, 100.0)
            rsi_arr = 100 - (100 / (1 + rs))
            entry["rsi"] = [round(float(v), 1) if not _np.isnan(v) else None for v in rsi_arr]

        if len(closes) >= 26:
            c_arr = _np.array(closes, dtype=float)
            def _ema_np(arr, span):
                k = 2 / (span + 1)
                out = _np.full(len(arr), _np.nan)
                out[span - 1] = _np.mean(arr[:span])
                for j in range(span, len(arr)):
                    out[j] = arr[j] * k + out[j-1] * (1 - k)
                return out
            ema12 = _ema_np(c_arr, 12)
            ema26 = _ema_np(c_arr, 26)
            macd_line = ema12 - ema26
            sig_arr = _np.full(len(c_arr), _np.nan)
            valid_macd = macd_line[~_np.isnan(macd_line)]
            if len(valid_macd) >= 9:
                sig_start = int(_np.where(~_np.isnan(macd_line))[0][0])
                k_s = 2 / 10
                sig_arr[sig_start + 8] = _np.mean(macd_line[sig_start:sig_start + 9])
                for j in range(sig_start + 9, len(c_arr)):
                    if not _np.isnan(macd_line[j]):
                        sig_arr[j] = macd_line[j] * k_s + sig_arr[j-1] * (1 - k_s)
            hist_arr = macd_line - sig_arr
            entry["macd"] = [round(float(v), 2) if not _np.isnan(v) else None for v in macd_line]
            entry["macd_sig"] = [round(float(v), 2) if not _np.isnan(v) else None for v in sig_arr]
            entry["macd_hist"] = [round(float(v), 2) if not _np.isnan(v) else None for v in hist_arr]

        if not is_intraday and full_date_idx:
            ema_slice = []
            sma_slice = []
            for d in hist.index:
                idx = full_date_idx.get(d.strftime("%Y-%m-%d"))
                if idx is not None:
                    e = ema50_full[idx] if idx < len(ema50_full) else None
                    s = sma200_full[idx] if idx < len(sma200_full) else None
                    ema_slice.append(round(e, 2) if e is not None else None)
                    sma_slice.append(round(s, 2) if s is not None else None)
                else:
                    ema_slice.append(None)
                    sma_slice.append(None)
            entry["ema50"] = ema_slice
            entry["sma200"] = sma_slice

        result[label] = entry
    return _json.dumps(result, separators=(",", ":"))


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
    corp_actions_html = _build_corporate_actions_html(data)

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
    chart_json = _serialize_chart_data(data)

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

    # ── Rich Company Analysis ──
    import math
    yf_summary = safe_get(info, "longBusinessSummary", "")
    desc_text = yf_summary or ""
    earn_q_growth = safe_get(info, "earningsQuarterlyGrowth", None)
    rec_key = safe_get(info, "recommendationKey", "")
    n_analysts = safe_get(info, "numberOfAnalystOpinions", 0)
    employees = safe_get(info, "fullTimeEmployees", 0)

    biz_bullets = []
    if desc_text:
        sentences = [s.strip() + "." for s in desc_text.replace(". ", ".\n").split("\n") if s.strip()]
        biz_bullets = sentences[:4]
    if industry != "N/A":
        biz_bullets.append(f"Operates in <strong>{industry}</strong> within the <strong>{sector}</strong> sector.")
    if employees and employees > 0:
        biz_bullets.append(f"Workforce of <strong>{employees:,}</strong> employees.")
    if not biz_bullets:
        biz_bullets.append("Company business description not available.")

    moat_bullets = []
    if _mcap > 200e9:
        moat_bullets.append(f"Mega-cap (${_mcap/1e9:,.0f}B) — dominant market position with significant scale advantages.")
    elif _mcap > 10e9:
        moat_bullets.append(f"Large-cap (${_mcap/1e9:,.0f}B) — established player with meaningful market presence.")
    elif _mcap > 2e9:
        moat_bullets.append(f"Mid-cap (${_mcap/1e9:,.1f}B) — growing company in a competitive landscape.")
    else:
        moat_bullets.append(f"Small-cap (${_mcap/1e6:,.0f}M) — higher risk/reward profile.")
    roe_val = safe_get(info, "returnOnEquity", 0) or 0
    pm_val = safe_get(info, "profitMargins", 0) or 0
    if roe_val > 0.20:
        moat_bullets.append(f"ROE of <strong>{roe_val*100:.1f}%</strong> indicates strong competitive advantage and efficient capital deployment.")
    elif roe_val > 0.12:
        moat_bullets.append(f"ROE of <strong>{roe_val*100:.1f}%</strong> — decent but not exceptional capital efficiency.")
    if pm_val > 0.20:
        moat_bullets.append(f"Profit margin of <strong>{pm_val*100:.1f}%</strong> suggests pricing power / cost moat.")
    elif pm_val > 0.10:
        moat_bullets.append(f"Profit margin of <strong>{pm_val*100:.1f}%</strong> — moderate pricing power.")
    if not moat_bullets:
        moat_bullets.append("Competitive analysis data limited.")

    catalyst_bullets = []
    for ni in news_items[:5]:
        title_l = ni.get("title", "").lower()
        if any(kw in title_l for kw in ["launch", "partner", "deal", "acqui", "expan", "approv", "regul", "invest", "order", "contract"]):
            catalyst_bullets.append(f'{ni["title"]} <span style="color:var(--text3);">({ni.get("publisher", "")})</span>')
    if rev_growth and rev_growth > 0.15:
        catalyst_bullets.append(f"Revenue growing at <strong>{rev_growth*100:.0f}%</strong> — strong top-line momentum.")
    if earnings_growth and earnings_growth > 0.20:
        catalyst_bullets.append(f"Earnings growth of <strong>{earnings_growth*100:.0f}%</strong> signals execution on profitability.")
    if not catalyst_bullets:
        catalyst_bullets.append("No specific near-term catalysts identified from available data.")
    catalyst_bullets = catalyst_bullets[:5]

    asym_bullets = []
    if target_mean and current_price:
        _upside = (target_mean - current_price) / current_price * 100
        downside_floor = (target_low - current_price) / current_price * 100 if target_low else 0
        upside_ceiling = (target_high - current_price) / current_price * 100 if target_high else 0
        asym_bullets.append(f"Analyst target range: ${target_low:,.0f} — ${target_high:,.0f} (mean ${target_mean:,.0f}, {n_analysts} analysts).")
        if upside_ceiling > 0 and abs(downside_floor) > 0:
            ratio = abs(upside_ceiling / downside_floor) if downside_floor != 0 else float('inf')
            if ratio > 2:
                asym_bullets.append(f"<strong style='color:var(--green);'>Favorable asymmetry</strong> — upside potential of <strong>{upside_ceiling:+.0f}%</strong> vs downside floor of <strong>{downside_floor:+.0f}%</strong> ({ratio:.1f}x reward-to-risk).")
            elif ratio > 1:
                asym_bullets.append(f"<strong style='color:var(--amber);'>Moderate asymmetry</strong> — upside {upside_ceiling:+.0f}% vs downside {downside_floor:+.0f}% ({ratio:.1f}x).")
            else:
                asym_bullets.append(f"<strong style='color:var(--red);'>Unfavorable asymmetry</strong> — limited upside {upside_ceiling:+.0f}% vs downside {downside_floor:+.0f}% ({ratio:.1f}x).")
    if pe_ratio and pe_ratio > 0:
        if pe_ratio < 15:
            asym_bullets.append(f"P/E of {pe_ratio:.1f}x — <strong>low valuation floor</strong>, limited downside from de-rating.")
        elif pe_ratio > 40:
            asym_bullets.append(f"P/E of {pe_ratio:.1f}x — <strong>premium valuation</strong>, growth must sustain to avoid de-rating risk.")
        else:
            asym_bullets.append(f"P/E of {pe_ratio:.1f}x — fair value territory; catalysts needed for re-rating.")
    if not asym_bullets:
        asym_bullets.append("Insufficient analyst data for asymmetry assessment.")

    outlook_bullets = []
    if rec_key:
        rec_label = rec_key.replace("_", " ").title()
        outlook_bullets.append(f"Analyst consensus: <strong>{rec_label}</strong> ({n_analysts} analysts).")
    if earn_q_growth is not None:
        if earn_q_growth > 0.10:
            outlook_bullets.append(f"Latest quarter earnings grew <strong>{earn_q_growth*100:.0f}%</strong> YoY — positive trajectory.")
        elif earn_q_growth < -0.10:
            outlook_bullets.append(f"Latest quarter earnings declined <strong>{earn_q_growth*100:.0f}%</strong> YoY — watch for recovery signals.")
        else:
            outlook_bullets.append(f"Latest quarter earnings change: <strong>{earn_q_growth*100:+.0f}%</strong> YoY — relatively flat.")
    if not outlook_bullets:
        outlook_bullets.append("Limited forward-looking data available.")

    def _bullets_html(items):
        return "".join(f'<li style="margin-bottom:6px;">{it}</li>' for it in items)

    company_overview_html = f'''
  <div class="section">
    <div class="section-title">🏢 Company Analysis · {company_name}</div>
    <div style="display:grid;grid-template-columns:1fr;gap:14px;">
      <div style="background:var(--bg3);border:1px solid var(--border);border-radius:10px;padding:16px 18px;border-left:3px solid var(--blue);">
        <div style="font-family:var(--mono);font-size:10px;font-weight:600;letter-spacing:1.5px;color:var(--blue);margin-bottom:8px;">💼 BUSINESS MODEL</div>
        <ul style="font-size:11px;color:var(--text2);line-height:1.75;padding-left:16px;margin:0;">{_bullets_html(biz_bullets)}</ul>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;">
        <div style="background:var(--bg3);border:1px solid var(--border);border-radius:10px;padding:16px 18px;border-left:3px solid var(--purple);">
          <div style="font-family:var(--mono);font-size:10px;font-weight:600;letter-spacing:1.5px;color:var(--purple);margin-bottom:8px;">🏰 MOAT &amp; COMPETITION</div>
          <ul style="font-size:11px;color:var(--text2);line-height:1.75;padding-left:16px;margin:0;">{_bullets_html(moat_bullets)}</ul>
        </div>
        <div style="background:var(--bg3);border:1px solid var(--border);border-radius:10px;padding:16px 18px;border-left:3px solid var(--green);">
          <div style="font-family:var(--mono);font-size:10px;font-weight:600;letter-spacing:1.5px;color:var(--green);margin-bottom:8px;">🚀 CATALYSTS</div>
          <ul style="font-size:11px;color:var(--text2);line-height:1.75;padding-left:16px;margin:0;">{_bullets_html(catalyst_bullets)}</ul>
        </div>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;">
        <div style="background:var(--bg3);border:1px solid var(--border);border-radius:10px;padding:16px 18px;border-left:3px solid var(--amber);">
          <div style="font-family:var(--mono);font-size:10px;font-weight:600;letter-spacing:1.5px;color:var(--amber);margin-bottom:8px;">⚖️ ASYMMETRY CHECK</div>
          <ul style="font-size:11px;color:var(--text2);line-height:1.75;padding-left:16px;margin:0;">{_bullets_html(asym_bullets)}</ul>
        </div>
        <div style="background:var(--bg3);border:1px solid var(--border);border-radius:10px;padding:16px 18px;border-left:3px solid var(--blue);">
          <div style="font-family:var(--mono);font-size:10px;font-weight:600;letter-spacing:1.5px;color:var(--blue);margin-bottom:8px;">🔭 FUTURE OUTLOOK</div>
          <ul style="font-size:11px;color:var(--text2);line-height:1.75;padding-left:16px;margin:0;">{_bullets_html(outlook_bullets)}</ul>
        </div>
      </div>
    </div>
  </div>'''

    # ── Valuation Trends (P/E, P/B, MCap/Sales, EPS via yfinance history) ──
    def _build_valuation_series(data, info, current_price):
        """Build valuation trend series from yfinance historical data."""
        pe_series = {"headers": [], "values": []}
        pb_series = {"headers": [], "values": []}
        mcap_sales_series = {"headers": [], "values": []}
        eps_series = {"headers": [], "values": []}

        fi = data.get("financials")
        qi = data.get("quarterly_income")
        bs = data.get("annual_balance_sheet")

        if fi is not None and not fi.empty:
            for col in sorted(fi.columns, reverse=False):
                yr = col.strftime("%Y") if hasattr(col, 'strftime') else str(col)
                rev_val = _safe_df_value(fi, col, ["Total Revenue", "Revenue"])
                ni_val = _safe_df_value(fi, col, ["Net Income", "Net Income Common Stockholders"])
                eps_val = _safe_df_value(fi, col, ["Diluted EPS", "Basic EPS"])
                shares = safe_get(info, "sharesOutstanding", 0) or 0

                if eps_val and eps_val > 0 and current_price:
                    pe_series["headers"].append(yr)
                    pe_series["values"].append(round(current_price / eps_val, 1))

                if ni_val and shares > 0:
                    bv_per_share = None
                    if bs is not None and not bs.empty:
                        for bc in bs.columns:
                            if hasattr(bc, 'year') and hasattr(col, 'year') and bc.year == col.year:
                                equity = _safe_df_value(bs, bc, ["Stockholders Equity", "Total Stockholder Equity", "Common Stock Equity"])
                                if equity and equity > 0 and shares > 0:
                                    bv_per_share = equity / shares
                                break
                    if bv_per_share and bv_per_share > 0 and current_price:
                        pb_series["headers"].append(yr)
                        pb_series["values"].append(round(current_price / bv_per_share, 2))

                if rev_val and rev_val > 0 and _mcap > 0:
                    mcap_sales_series["headers"].append(yr)
                    mcap_sales_series["values"].append(round(_mcap / rev_val, 2))

                if eps_val:
                    eps_series["headers"].append(yr)
                    eps_series["values"].append(round(eps_val, 2))

        return pe_series, pb_series, mcap_sales_series, eps_series

    pe_series, pb_series, mcap_sales_series, eps_series = _build_valuation_series(data, info, current_price)

    vt_charts = []
    vt_labels = []
    for label_vt, series_vt, color_vt in [
        ("P/E", pe_series, "#3d9cf5"),
        ("P/B", pb_series, "#9b7fff"),
        ("MCap/Sales", mcap_sales_series, "#f5a623"),
        ("EPS", eps_series, "#00e5a0"),
    ]:
        svg = generate_pe_pb_chart_svg(series_vt, label_vt, color_vt)
        vt_charts.append(svg)
        vt_labels.append(label_vt)

    has_vt = any(s.get("values") and len(s["values"]) >= 2 for s in [pe_series, pb_series, mcap_sales_series, eps_series])

    vt_html = ""
    if has_vt:
        vt_btns = "".join(f'<button class="tf-btn{" active" if i == 0 else ""}" data-idx="{i}">{lb}</button>' for i, lb in enumerate(vt_labels))
        vt_panels = "".join(f'<div class="vt-panel" id="vt-panel-{i}" style="{"" if i == 0 else "display:none;"}">{svg}</div>' for i, svg in enumerate(vt_charts))
        vt_html = f'''
  <div class="section">
    <div class="section-title" style="display:flex;align-items:center;gap:16px;flex-wrap:wrap;">
      <span>📉 Valuation Trends (at current CMP)</span>
      <div class="tf-btns" id="vt-btns">{vt_btns}</div>
    </div>
    {vt_panels}
  </div>'''

    # ── Revenue vs Earnings chart data ──
    fin_chart_data = {"quarterly": [], "annual": []}
    for q in quarterly_rows:
        entry = {"label": q.get("quarter", "?"), "rev": None, "profit": None, "eps": None}
        if q.get("revenue") is not None:
            entry["rev"] = round(q["revenue"] / 1e6, 1) if abs(q["revenue"]) > 1e6 else round(q["revenue"], 0)
        if q.get("profit") is not None:
            entry["profit"] = round(q["profit"] / 1e6, 1) if abs(q["profit"]) > 1e6 else round(q["profit"], 0)
        qi = data.get("quarterly_income")
        if qi is not None and not qi.empty:
            dt = q.get("date")
            if dt is not None and dt in qi.columns:
                for ek in ["Diluted EPS", "Basic EPS"]:
                    if ek in qi.index:
                        ev = qi.loc[ek, dt]
                        if ev is not None and not (isinstance(ev, float) and math.isnan(ev)):
                            entry["eps"] = round(float(ev), 2)
                            break
        fin_chart_data["quarterly"].append(entry)
    for a in annual_rows:
        entry = {"label": a.get("year", "?"), "rev": None, "profit": None, "eps": None}
        if a.get("revenue") is not None:
            entry["rev"] = round(a["revenue"] / 1e6, 1) if abs(a["revenue"]) > 1e6 else round(a["revenue"], 0)
        if a.get("profit") is not None:
            entry["profit"] = round(a["profit"] / 1e6, 1) if abs(a["profit"]) > 1e6 else round(a["profit"], 0)
        fi = data.get("financials")
        if fi is not None and not fi.empty:
            dt = a.get("date")
            if dt is not None and dt in fi.columns:
                for ek in ["Diluted EPS", "Basic EPS"]:
                    if ek in fi.index:
                        ev = fi.loc[ek, dt]
                        if ev is not None and not (isinstance(ev, float) and math.isnan(ev)):
                            entry["eps"] = round(float(ev), 2)
                            break
        fin_chart_data["annual"].append(entry)

    _any_q_rev = any(q.get("revenue") and abs(q["revenue"]) > 1e6 for q in quarterly_rows)
    _any_a_rev = any(a.get("revenue") and abs(a["revenue"]) > 1e6 for a in annual_rows)
    fin_chart_data["scale"] = "$ Millions" if (_any_q_rev or _any_a_rev) else "$"

    import json as _json2
    fin_chart_json = _json2.dumps(fin_chart_data, separators=(",", ":"))

    # ── Sankey flow SVG panels (quarterly + annual) ──
    inc_panels = generate_income_sankey_panels(data)
    bs_panels = generate_bs_sankey_panels(data)
    cf_panels = generate_cf_sankey_panels(data)

    def _build_sankey_carousel(panel_id, title, panels_dict):
        """Build HTML carousel with quarterly/annual toggle + period sub-tabs."""
        q_list = panels_dict.get("quarterly", [])
        a_list = panels_dict.get("annual", [])
        if not q_list and not a_list:
            return ""
        html_parts = [f'<div class="section"><div class="section-title" style="display:flex;align-items:center;gap:16px;flex-wrap:wrap;">']
        html_parts.append(f'<span>{title}</span>')
        html_parts.append(f'<div class="tf-btns" id="{panel_id}-mode">')
        if q_list:
            html_parts.append(f'<button class="tf-btn active" data-mode="quarterly">Quarterly</button>')
        if a_list:
            active = "" if q_list else " active"
            html_parts.append(f'<button class="tf-btn{active}" data-mode="annual">Annual</button>')
        html_parts.append('</div></div>')
        # Quarterly panels
        for i, p in enumerate(q_list):
            vis = ' style="display:none;"' if i > 0 else ''
            html_parts.append(f'<div class="{panel_id}-panel {panel_id}-quarterly" data-idx="{i}"{vis}>{p["svg"]}</div>')
        # Annual panels
        for i, p in enumerate(a_list):
            vis = ' style="display:none;"' if (q_list or i > 0) else ''
            html_parts.append(f'<div class="{panel_id}-panel {panel_id}-annual" data-idx="{i}"{vis}>{p["svg"]}</div>')
        # Period sub-tabs
        html_parts.append(f'<div class="tf-btns" id="{panel_id}-periods" style="margin-top:8px;justify-content:center;">')
        default_list = q_list if q_list else a_list
        for i, p in enumerate(default_list):
            active = " active" if i == 0 else ""
            html_parts.append(f'<button class="tf-btn{active}" data-idx="{i}">{p["label"]}</button>')
        html_parts.append('</div>')
        html_parts.append('</div>')
        return "\n    ".join(html_parts)

    income_sankey_html = _build_sankey_carousel("sk-inc", f"💰 How {company_name} Makes Its Money", inc_panels)
    bs_sankey_html = _build_sankey_carousel("sk-bs", f"🏦 Snapshot of {company_name}'s Balance Sheet", bs_panels)
    cf_sankey_html = _build_sankey_carousel("sk-cf", f"💸 Looking into {company_name}'s Cash Flow", cf_panels)

    # ── Earnings estimates vs actual ──
    earnings_hist_data = []
    eh = data.get("earnings_history")
    def _safe_eps_float(v):
        if v is None:
            return None
        try:
            fv = float(v)
            return None if math.isnan(fv) else fv
        except (ValueError, TypeError):
            return None

    if eh is not None and hasattr(eh, 'empty') and not eh.empty:
        for _, row in eh.iterrows():
            try:
                dt_val = row.name if hasattr(row.name, 'strftime') else None
                label = dt_val.strftime("%b %Y") if dt_val else str(row.name)
                est_f = _safe_eps_float(row.get("epsEstimate") if "epsEstimate" in row.index else None)
                act_f = _safe_eps_float(row.get("epsActual") if "epsActual" in row.index else None)
                sur_f = _safe_eps_float(row.get("surprisePercent") if "surprisePercent" in row.index else None)
                if est_f is not None or act_f is not None:
                    earnings_hist_data.append({
                        "label": label,
                        "estimate": round(est_f, 2) if est_f is not None else None,
                        "actual": round(act_f, 2) if act_f is not None else None,
                        "surprise": round(sur_f, 1) if sur_f is not None else None,
                    })
            except Exception:
                continue
    elif eh is not None and isinstance(eh, list):
        for item in eh:
            try:
                earnings_hist_data.append({
                    "label": str(item.get("date", item.get("quarter", "?"))),
                    "estimate": round(float(item["epsEstimate"]), 2) if item.get("epsEstimate") else None,
                    "actual": round(float(item["epsActual"]), 2) if item.get("epsActual") else None,
                    "surprise": round(float(item["surprisePercent"]), 1) if item.get("surprisePercent") else None,
                })
            except Exception:
                continue
    earnings_hist_json = _json2.dumps(earnings_hist_data, separators=(",", ":"))

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

    val_color = score_color(scores["valuation"], 25)
    fin_color = score_color(scores["financial"], 25)
    growth_color = score_color(scores["growth"], 25)
    tech_color = score_color(scores["technical"], 25)

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

    # Sector benchmarks for metric card evaluation
    bench = get_sector_bench(sector)
    _pe_cheap, _pe_fair, _pe_exp = bench["pe"]
    _pb_cheap, _pb_fair, _pb_exp = bench["pb"]
    _roe_mod, _roe_good = bench["roe"]
    _margin_mod, _margin_good = bench["margin"]
    _rg_mod, _rg_strong = bench["rev_growth"]
    _eg_mod, _eg_strong = bench["earn_growth"]

    # Card status with tooltip reason
    def cs(val, good, bad, metric_name="", lower_better=False):
        if val is None:
            return "caution", f"{metric_name}: Data unavailable"
        if lower_better:
            if val <= good:
                return "beat", f"{metric_name} at {val:.1f} is below {good:.1f} (sector norm) — attractive"
            elif val <= bad:
                return "caution", f"{metric_name} at {val:.1f} is between {good:.1f} and {bad:.1f} (sector norm) — moderate"
            else:
                return "miss", f"{metric_name} at {val:.1f} exceeds {bad:.1f} (sector norm) — elevated"
        else:
            if val >= good:
                return "beat", f"{metric_name} at {val:.1f} exceeds {good:.1f} (sector norm) — strong"
            elif val >= bad:
                return "caution", f"{metric_name} at {val:.1f} is between {bad:.1f} and {good:.1f} (sector norm) — moderate"
            else:
                return "miss", f"{metric_name} at {val:.1f} is below {bad:.1f} (sector norm) — weak"

    # Pre-compute metric card statuses (sector-relative thresholds)
    pe_cls, pe_tip = cs(pe_ratio, _pe_fair, _pe_exp, "P/E", True) if pe_ratio else ("caution", "P/E: Data unavailable")
    pb_cls, pb_tip = cs(pb_ratio, _pb_fair, _pb_exp, "P/B", True) if pb_ratio else ("caution", "P/B: Data unavailable")
    roe_cls, roe_tip = cs(roe * 100, _roe_good * 100, _roe_mod * 100, "ROE %") if roe else ("caution", "ROE: Data unavailable")
    pm_cls, pm_tip = cs(profit_margin * 100, _margin_good * 100, _margin_mod * 100, "Profit Margin %") if profit_margin else ("caution", "Profit Margin: Data unavailable")
    opm_pct = operating_margin * 100 if operating_margin else None
    opm_cls, opm_tip = cs(opm_pct, _margin_good * 100 * 0.75, _margin_mod * 100 * 0.5, "OPM %") if opm_pct is not None else ("caution", "Operating Margin: Data unavailable")
    tgt_cls = "beat" if target_mean > current_price else "miss" if target_mean else "caution"
    tgt_tip = f"Analyst target ${target_mean:,.2f} vs CMP ${current_price:,.2f} — {'upside' if target_mean > current_price else 'downside'}" if target_mean else "Analyst target: Data unavailable"
    peg_cls, peg_tip = cs(peg_ratio, 1.0, 2.0, "PEG", True) if peg_ratio else ("caution", "PEG: Data unavailable")
    eve_cls, eve_tip = cs(ev_ebitda, 12, 20, "EV/EBITDA", True) if ev_ebitda else ("caution", "EV/EBITDA: Data unavailable")
    cr_cls, cr_tip = cs(current_ratio, 1.5, 1.0, "Current Ratio") if current_ratio else ("caution", "Current Ratio: Data unavailable")
    dy_cls, dy_tip = cs(dy_pct, 2, 0.5, "Div Yield %") if dy_pct is not None else ("caution", "Dividend Yield: Data unavailable")
    roa_cls, roa_tip = cs(roa * 100, 10, 5, "ROA %") if roa else ("caution", "ROA: Data unavailable")
    gm_cls, gm_tip = cs(gross_margin * 100, 40, 20, "Gross Margin %") if gross_margin else ("caution", "Gross Margin: Data unavailable")

    # Determine catalysts and risks dynamically (sector-relative)
    catalysts = []
    risks = []

    if rev_growth and rev_growth > _rg_strong:
        catalysts.append(f"<strong>Revenue Growth {rev_growth*100:.0f}%:</strong> Above sector norm of {_rg_strong*100:.0f}% — strong top-line momentum.")
    elif rev_growth and rev_growth > 0:
        catalysts.append(f"<strong>Positive Revenue Growth:</strong> Revenue growing at {rev_growth*100:.1f}% YoY.")

    if roe and roe > _roe_good:
        catalysts.append(f"<strong>High ROE ({roe*100:.1f}%):</strong> Above sector norm of {_roe_good*100:.0f}% — efficient capital use.")

    if profit_margin and profit_margin > _margin_good:
        catalysts.append(f"<strong>Healthy Margins ({profit_margin*100:.1f}%):</strong> Above sector norm of {_margin_good*100:.0f}%.")

    if upside > 10 and target_mean:
        catalysts.append(f"<strong>Analyst Upside ({upside:.0f}%):</strong> Mean target of ${target_mean:,.2f} above current price.")

    if beta and beta < 1.0:
        catalysts.append(f"<strong>Low Beta ({beta:.2f}):</strong> Less volatile than market — defensive play.")

    if earnings_growth and earnings_growth > _eg_mod:
        catalysts.append(f"<strong>Earnings Growth ({earnings_growth*100:.0f}%):</strong> Above sector norm — strong profit expansion.")

    if len(catalysts) < 3:
        catalysts.append(f"<strong>Sector Opportunity:</strong> {sector} / {industry} — positioned in growth sector.")

    if pe_ratio and pe_ratio > _pe_exp * 1.5:
        risks.append(f"<strong>High P/E ({pe_ratio:.1f}x):</strong> Well above sector expensive threshold of {_pe_exp:.0f}x — leaves little room for error.")
    elif pe_ratio and pe_ratio > _pe_exp:
        risks.append(f"<strong>Elevated P/E ({pe_ratio:.1f}x):</strong> Above sector expensive threshold of {_pe_exp:.0f}x.")

    if pb_ratio and pb_ratio > _pb_exp * 1.5:
        risks.append(f"<strong>High P/B ({pb_ratio:.1f}x):</strong> Well above sector expensive threshold of {_pb_exp:.0f}x.")

    _de_ok, _de_high = bench["de"]
    if debt_equity and debt_equity > _de_high:
        risks.append(f"<strong>High Debt/Equity ({debt_equity:.0f}%):</strong> Above sector threshold of {_de_high:.0f}% — leverage risk.")

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
    if roe and roe > _roe_good:
        buy_reasons.append(f"ROE of {roe*100:.1f}% above sector norm of {_roe_good*100:.0f}%")
    if rev_growth and rev_growth > _rg_mod:
        buy_reasons.append(f"Revenue growing at {rev_growth*100:.1f}% YoY (sector norm: {_rg_mod*100:.0f}%)")
    if opm_pct and opm_pct > _margin_good * 100:
        buy_reasons.append(f"Operating margin of {opm_str} shows pricing power (sector norm: {_margin_good*100:.0f}%)")

    if pe_ratio and sector_median_pe and pe_ratio > sector_median_pe * 1.2:
        sell_reasons.append(f"P/E of {pe_ratio:.1f}x is {pe_ratio/sector_median_pe:.1f}x the sector median of {sector_median_pe:.0f}x")
    elif pe_ratio and pe_ratio > _pe_exp:
        sell_reasons.append(f"P/E of {pe_ratio:.1f}x exceeds sector expensive threshold of {_pe_exp:.0f}x")
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
    The stock scores {scores["valuation"]}/25 on valuation, {scores["financial"]}/25 on financial health, {scores["growth"]}/25 on growth, and {scores["technical"]}/25 on technicals.
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

    # ── Build financial statement tables from yfinance DataFrames ──
    yahoo_url = f"https://finance.yahoo.com/quote/{ticker_symbol}/"

    qr_table_html = _build_yf_statement_table(data.get("quarterly_income"), _INCOME_ROWS, max_periods=8)
    qr_section_html = f'''
  <div class="section">
    <div class="section-title">📅 Quarterly Results <a href="{yahoo_url}financials/" target="_blank" class="src-link-header">Source: Yahoo Finance ↗</a></div>
    {qr_table_html}
  </div>''' if qr_table_html else ""

    pl_table_html = _build_yf_statement_table(data.get("financials"), _INCOME_ROWS, max_periods=6)
    pl_section_html = f'''
  <div class="section">
    <div class="section-title">📊 Profit & Loss Statement <a href="{yahoo_url}financials/" target="_blank" class="src-link-header">Source: Yahoo Finance ↗</a></div>
    {pl_table_html}
  </div>''' if pl_table_html else ""

    bs_table_html = _build_yf_statement_table(data.get("annual_balance_sheet"), _BALANCE_SHEET_ROWS, max_periods=6)
    bs_section_html = f'''
  <div class="section">
    <div class="section-title">🏦 Balance Sheet <a href="{yahoo_url}balance-sheet/" target="_blank" class="src-link-header">Source: Yahoo Finance ↗</a></div>
    {bs_table_html}
  </div>''' if bs_table_html else ""

    cf_table_html = _build_yf_statement_table(data.get("annual_cash_flow"), _CASH_FLOW_ROWS, max_periods=6)
    cf_section_html = f'''
  <div class="section">
    <div class="section-title">💰 Cash Flow Statement <a href="{yahoo_url}cash-flow/" target="_blank" class="src-link-header">Source: Yahoo Finance ↗</a></div>
    {cf_table_html}
  </div>''' if cf_table_html else ""

    ratios_html = _compute_financial_ratios(data)
    ratios_section_html = f'''
  <div class="section">
    <div class="section-title">📈 Key Financial Ratios</div>
    {ratios_html}
  </div>''' if ratios_html else ""

    growth_rates = _compute_growth_rates(data)
    growth_section_html = ""
    if growth_rates:
        cards = ""
        for gtitle, items in growth_rates.items():
            rows_h = "".join(f'<tr><td style="color:var(--text2);">{k}</td><td style="text-align:right;font-weight:600;">{v}</td></tr>' for k, v in items)
            cards += f'<div class="col-card"><div class="col-title">{gtitle}</div><table><tbody>{rows_h}</tbody></table></div>'
        growth_section_html = f'''
  <div class="section">
    <div class="section-title">🚀 Compounded Growth Rates</div>
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;">{cards}</div>
  </div>'''

    # ── Industry Peers ──
    peers = data.get("_peers", [])
    peer_table_html = ""
    if peers:
        p_rows = ""
        for p in peers:
            mcap_str = f"${p['mcap']/1e9:,.1f}B" if p.get("mcap") and p["mcap"] > 0 else "—"
            pe_str = f"{p['pe']:.1f}" if p.get("pe") else "—"
            pb_str = f"{p['pb']:.1f}" if p.get("pb") else "—"
            roe_str = f"{p['roe']*100:.1f}%" if p.get("roe") else "—"
            margin_str = f"{p['margin']*100:.1f}%" if p.get("margin") else "—"
            rg_str = f"{p['rev_growth']*100:.1f}%" if p.get("rev_growth") else "—"
            price_str = f"${p['price']:,.2f}" if p.get("price") else "—"
            p_rows += f'<tr><td><strong>{p["symbol"]}</strong></td><td>{p["name"][:30]}</td><td style="text-align:right;">{price_str}</td><td style="text-align:right;">{pe_str}</td><td style="text-align:right;">{pb_str}</td><td style="text-align:right;">{mcap_str}</td><td style="text-align:right;">{roe_str}</td><td style="text-align:right;">{margin_str}</td><td style="text-align:right;">{rg_str}</td></tr>'
        peer_table_html = f'''
  <div class="section">
    <div class="section-title">🏭 Industry Peers — {industry}</div>
    <div style="overflow-x:auto;">
      <table>
        <thead><tr><th>Ticker</th><th>Company</th><th style="text-align:right;">Price</th><th style="text-align:right;">P/E</th><th style="text-align:right;">P/B</th><th style="text-align:right;">MCap</th><th style="text-align:right;">ROE</th><th style="text-align:right;">Margin</th><th style="text-align:right;">Rev Growth</th></tr></thead>
        <tbody>{p_rows}</tbody>
      </table>
    </div>
    <p style="font-size:10px;color:var(--text3);margin-top:8px;">Peers selected from {sector} sector · Data from Yahoo Finance</p>
  </div>'''

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
  .badge-earnings {{ background:rgba(245,166,35,0.1); color:#f5a623; border:1px solid rgba(245,166,35,0.25); }}
  .badge-imminent {{ background:rgba(245,166,35,0.25); color:#ffcc00; border:1px solid rgba(255,204,0,0.4); animation: pulse-amber 1.5s ease-in-out infinite; }}
  .badge-exdiv {{ background:rgba(61,156,245,0.1); color:#3d9cf5; border:1px solid rgba(61,156,245,0.25); }}
  @keyframes pulse-amber {{ 0%,100% {{ box-shadow:0 0 4px rgba(255,204,0,0.2); }} 50% {{ box-shadow:0 0 12px rgba(255,204,0,0.5); }} }}
  .sh-actions {{ display:flex; gap:8px; flex-wrap:wrap; margin:6px 0 2px 0; }}
  .sh-actions .badge {{ font-size:10px; padding:2px 8px; border-radius:4px; font-weight:600; letter-spacing:0.3px; }}
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
  .src-link-header {{ font-size:9px; letter-spacing:1px; color:var(--blue); text-decoration:none; margin-left:auto; flex-shrink:0; }}
  .src-link-header:hover {{ text-decoration:underline; }}
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
  .breakdown-grid {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin-bottom:20px; }}
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
  .fade-target {{ opacity:0; transform:translateY(12px); transition:opacity 0.5s ease, transform 0.5s ease; }}
  .fade-target.visible {{ opacity:1; transform:translateY(0); }}
  @media (max-width: 768px) {{ .stock-header {{ flex-direction:column; gap:16px; }} .gauge-kpi-row {{ grid-template-columns:1fr; }} .card-grid {{ grid-template-columns:1fr 1fr; }} .breakdown-grid {{ grid-template-columns:1fr; }} .dual-col {{ grid-template-columns:1fr; }} .kpi-strip {{ grid-template-columns:repeat(2,1fr); }} .returns-strip {{ grid-template-columns:repeat(3,1fr); }} .news-grid {{ grid-template-columns:1fr; }} }}
  .tf-btns {{ display:flex; gap:2px; }}
  .tf-btn {{ background:var(--bg4); border:1px solid var(--border); color:var(--text3); font-family:var(--mono); font-size:9px; padding:3px 9px; border-radius:4px; cursor:pointer; transition:all .15s; }}
  .tf-btn:hover {{ color:var(--text); border-color:var(--border2); }}
  .tf-btn.active {{ color:#fff; background:var(--bg3); border-color:var(--border2); }}
  .tf-ret {{ font-family:var(--mono); font-size:12px; font-weight:600; }}
  .tf-ret.up {{ color:var(--green); }}
  .tf-ret.dn {{ color:var(--red); }}
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
      {corp_actions_html}
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
        VAL:{scores["valuation"]}/25 · FIN:{scores["financial"]}/25 · GRO:{scores["growth"]}/25 · TECH:{scores["technical"]}/25
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

  {company_overview_html}

  <div class="section">
    <div class="section-title" style="display:flex;align-items:center;gap:16px;flex-wrap:wrap;">
      <span>📈 Price Movement</span>
      <div class="tf-btns" id="tf-line">
        <button class="tf-btn" data-tf="1D">1D</button><button class="tf-btn" data-tf="1W">1W</button><button class="tf-btn" data-tf="1M">1M</button>
        <button class="tf-btn" data-tf="6M">6M</button><button class="tf-btn active" data-tf="1Y">1Y</button><button class="tf-btn" data-tf="3Y">3Y</button><button class="tf-btn" data-tf="5Y">5Y</button>
      </div>
      <span class="tf-ret" id="tf-line-ret"></span>
    </div>
    <canvas id="cv-line" style="width:100%;height:280px;display:block;"></canvas>
  </div>

  <div class="section">
    <div class="section-title" style="display:flex;align-items:center;gap:16px;flex-wrap:wrap;">
      <span>🕯 Candlestick Chart</span>
      <div class="tf-btns" id="tf-candle">
        <button class="tf-btn" data-tf="1D">1D</button><button class="tf-btn" data-tf="1W">1W</button><button class="tf-btn" data-tf="1M">1M</button>
        <button class="tf-btn active" data-tf="6M">6M</button><button class="tf-btn" data-tf="1Y">1Y</button><button class="tf-btn" data-tf="3Y">3Y</button><button class="tf-btn" data-tf="5Y">5Y</button>
      </div>
      <span class="tf-ret" id="tf-candle-ret"></span>
    </div>
    <canvas id="cv-candle" style="width:100%;height:520px;display:block;"></canvas>
  </div>

  <div class="section">
    <div class="section-title">🎯 Fair Value Analysis · CMP vs Analyst Targets</div>
    {fair_value_svg}
  </div>

  {vt_html}

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
      <div class="bc-header"><div><div class="bc-title">VALUATION</div><div class="bc-score" style="color:{val_color}">{scores["valuation"]}<span class="bc-max">/25</span></div></div><div style="font-family:var(--mono);font-size:10px;color:var(--text3);">25% WEIGHT</div></div>
      <div class="bc-bar-track"><div class="bc-bar-fill" style="width:{scores['valuation']/25*100:.0f}%;background:{val_color};box-shadow:0 0 8px {val_color}44;"></div></div>
      <ul class="bc-items">
        <li>P/E at {f"{pe_ratio:.0f}x" if pe_ratio else "N/A"}</li>
        <li>P/B at {f"{pb_ratio:.1f}x" if pb_ratio else "N/A"}</li>
        <li>Analyst target: {f'${target_mean:,.2f}' if target_mean else 'N/A'} ({upside:+.1f}%)</li>
        <li>1Y return: {return_1y:+.1f}%</li>
      </ul>
    </div>
    <div class="breakdown-card">
      <div class="bc-header"><div><div class="bc-title">FINANCIAL HEALTH</div><div class="bc-score" style="color:{fin_color}">{scores["financial"]}<span class="bc-max">/25</span></div></div><div style="font-family:var(--mono);font-size:10px;color:var(--text3);">25% WEIGHT</div></div>
      <div class="bc-bar-track"><div class="bc-bar-fill" style="width:{scores['financial']/25*100:.0f}%;background:{fin_color};box-shadow:0 0 8px {fin_color}44;"></div></div>
      <ul class="bc-items">
        <li>ROE: {f"{roe*100:.1f}%" if roe else "N/A"}</li>
        <li>Profit margin: {f"{profit_margin*100:.1f}%" if profit_margin is not None else "N/A"}</li>
        <li>Revenue growth: {f"{rev_growth*100:.1f}%" if rev_growth is not None else "N/A"}</li>
        <li>Debt/Equity: {f"{debt_equity:.0f}%" if debt_equity is not None else "N/A"}</li>
      </ul>
    </div>
    <div class="breakdown-card">
      <div class="bc-header"><div><div class="bc-title">GROWTH</div><div class="bc-score" style="color:{growth_color}">{scores["growth"]}<span class="bc-max">/25</span></div></div><div style="font-family:var(--mono);font-size:10px;color:var(--text3);">25% WEIGHT</div></div>
      <div class="bc-bar-track"><div class="bc-bar-fill" style="width:{scores['growth']/25*100:.0f}%;background:{growth_color};box-shadow:0 0 8px {growth_color}44;"></div></div>
      <ul class="bc-items">
        <li>Revenue growth: {f"{rev_growth*100:.1f}%" if rev_growth is not None else "N/A"}</li>
        <li>Earnings growth: {f"{earnings_growth*100:.1f}%" if earnings_growth is not None else "N/A"}</li>
        <li>Beta: {beta:.2f}</li>
        <li>Sector: {sector}</li>
      </ul>
    </div>
    <div class="breakdown-card">
      <div class="bc-header"><div><div class="bc-title">TECHNICAL</div><div class="bc-score" style="color:{tech_color}">{scores["technical"]}<span class="bc-max">/25</span></div></div><div style="font-family:var(--mono);font-size:10px;color:var(--text3);">25% WEIGHT</div></div>
      <div class="bc-bar-track"><div class="bc-bar-fill" style="width:{scores['technical']/25*100:.0f}%;background:{tech_color};box-shadow:0 0 8px {tech_color}44;"></div></div>
      <ul class="bc-items">
        <li>RSI, MACD, MA crossovers</li>
        <li>200 DMA &amp; 50 EMA position</li>
        <li>Volume trend analysis</li>
        <li>Price momentum signals</li>
      </ul>
    </div>
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
    <div class="section-title" style="display:flex;align-items:center;gap:16px;flex-wrap:wrap;">
      <span>📈 Revenue vs Earnings</span>
      <div class="tf-btns" id="fin-toggle">
        <button class="tf-btn active" data-mode="quarterly">Quarterly</button>
        <button class="tf-btn" data-mode="annual">Annual</button>
      </div>
    </div>
    <canvas id="cv-fin" style="width:100%;height:280px;display:block;"></canvas>
  </div>

  {income_sankey_html}
  {bs_sankey_html}
  {cf_sankey_html}

  <div class="section">
    <div class="section-title" style="display:flex;align-items:center;gap:16px;flex-wrap:wrap;">
      <span>🎯 EPS: Estimate vs Actual</span>
      <div class="tf-btns" id="eps-toggle">
        <button class="tf-btn active" data-mode="estimates">Estimates</button>
        <button class="tf-btn" data-mode="quarterly">Quarterly</button>
        <button class="tf-btn" data-mode="annual">Annual</button>
      </div>
    </div>
    <canvas id="cv-eps-est" style="width:100%;height:260px;display:block;"></canvas>
  </div>

  {qr_section_html}
  {pl_section_html}
  {bs_section_html}
  {cf_section_html}
  {ratios_section_html}
  {growth_section_html}

  {peer_table_html}

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
  entries.forEach(entry => {{ if (entry.isIntersecting) {{ entry.target.classList.add('visible'); }} }});
}}, {{ threshold: 0.1 }});
document.querySelectorAll('.breakdown-card, .metric-card').forEach(el => {{
  el.classList.add('fade-target');
  observer.observe(el);
}});

const CHART_DATA = {chart_json};

function _setupCanvas(id) {{
  const c = document.getElementById(id);
  if (!c) return null;
  const ctx = c.getContext('2d');
  const dpr = window.devicePixelRatio || 1;
  const w = c.clientWidth, h = c.clientHeight;
  if (w === 0 || h === 0) return null;
  c.width = w * dpr; c.height = h * dpr;
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, w, h);
  return {{ ctx, w, h }};
}}

function drawLineChart(tf) {{
  const d = CHART_DATA[tf];
  if (!d || !d.c.length) return;
  const s = _setupCanvas('cv-line');
  if (!s) return;
  const {{ ctx, w, h }} = s;
  const closes = d.c, n = closes.length;
  const mn = Math.min(...closes), mx = Math.max(...closes);
  const range = mx - mn || 1;
  const pad = {{ t:18, b:24, l:55, r:32 }};
  const cw = w - pad.l - pad.r, ch = h - pad.t - pad.b;

  const ret = ((closes[n-1] - closes[0]) / closes[0] * 100);
  const retEl = document.getElementById('tf-line-ret');
  if (retEl) {{
    retEl.textContent = (ret >= 0 ? '+' : '') + ret.toFixed(2) + '%';
    retEl.className = 'tf-ret ' + (ret >= 0 ? 'up' : 'dn');
  }}

  ctx.strokeStyle = 'rgba(255,255,255,0.06)'; ctx.lineWidth = 1;
  for (let i = 0; i < 5; i++) {{
    const y = pad.t + (i / 4) * ch;
    ctx.beginPath(); ctx.moveTo(pad.l, y); ctx.lineTo(w - pad.r, y); ctx.stroke();
    const val = mx - (i / 4) * range;
    ctx.fillStyle = '#5c5d6e'; ctx.font = '9px "Fira Code",monospace'; ctx.textAlign = 'right';
    ctx.fillText(val >= 1000 ? val.toFixed(0) : val.toFixed(2), pad.l - 6, y + 3);
  }}

  const nLabels = Math.min(6, n);
  ctx.fillStyle = '#5c5d6e'; ctx.font = '9px "Fira Code",monospace'; ctx.textAlign = 'center';
  for (let i = 0; i < nLabels; i++) {{
    const idx = Math.round(i / (nLabels - 1) * (n - 1));
    const x = pad.l + (idx / (n - 1)) * cw;
    ctx.fillText(d.d[idx], x, h - 4);
  }}

  const color = ret >= 0 ? '#00e5a0' : '#ff4d6d';
  ctx.strokeStyle = color; ctx.lineWidth = 1.8; ctx.lineJoin = 'round';
  ctx.beginPath();
  closes.forEach((v, i) => {{
    const x = pad.l + (i / (n - 1 || 1)) * cw;
    const y = pad.t + (1 - (v - mn) / range) * ch;
    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  }});
  ctx.stroke();

  const grad = ctx.createLinearGradient(0, pad.t, 0, pad.t + ch);
  grad.addColorStop(0, color + '22');
  grad.addColorStop(1, color + '00');
  ctx.lineTo(pad.l + cw, pad.t + ch);
  ctx.lineTo(pad.l, pad.t + ch);
  ctx.closePath();
  ctx.fillStyle = grad;
  ctx.fill();
}}

function drawCandleChart(tf) {{
  const d = CHART_DATA[tf];
  if (!d || !d.c.length) return;
  const s = _setupCanvas('cv-candle');
  if (!s) return;
  const {{ ctx, w, h }} = s;
  const n = d.c.length;
  const L = 55, R = 32;
  const cw = w - L - R;
  const hasRsi = d.rsi && d.rsi.some(v => v !== null);
  const hasMacd = d.macd && d.macd.some(v => v !== null);
  const panels = 1 + 1 + (hasRsi ? 1 : 0) + (hasMacd ? 1 : 0);
  const gap = 6;
  const totalGap = (panels - 1) * gap;
  const usable = h - 18 - 22 - totalGap;
  const candleH = usable * 0.50;
  const volH = usable * 0.12;
  const rsiH = hasRsi ? usable * (hasMacd ? 0.19 : 0.38) : 0;
  const macdH = hasMacd ? usable * (hasRsi ? 0.19 : 0.38) : 0;
  let yOff = 18;
  const pCandle = {{ t: yOff, h: candleH }};
  yOff += candleH + gap;
  const pVol = {{ t: yOff, h: volH }};
  yOff += volH + gap;
  const pRsi = {{ t: yOff, h: rsiH }};
  if (hasRsi) yOff += rsiH + gap;
  const pMacd = {{ t: yOff, h: macdH }};

  const ret = ((d.c[n-1] - d.c[0]) / d.c[0] * 100);
  const retEl = document.getElementById('tf-candle-ret');
  if (retEl) {{
    retEl.textContent = (ret >= 0 ? '+' : '') + ret.toFixed(2) + '%';
    retEl.className = 'tf-ret ' + (ret >= 0 ? 'up' : 'dn');
  }}

  function xPos(i) {{ return L + ((i + 0.5) / n) * cw; }}
  function drawGrid(pt, minV, maxV, count, fmt) {{
    const rng = maxV - minV || 1;
    ctx.strokeStyle = 'rgba(255,255,255,0.05)'; ctx.lineWidth = 0.5;
    ctx.font = '8px "Fira Code",monospace'; ctx.textAlign = 'right'; ctx.fillStyle = '#5c5d6e';
    for (let i = 0; i <= count; i++) {{
      const y = pt.t + (i / count) * pt.h;
      ctx.beginPath(); ctx.moveTo(L, y); ctx.lineTo(w - R, y); ctx.stroke();
      const val = maxV - (i / count) * rng;
      ctx.fillText(fmt(val), L - 5, y + 3);
    }}
  }}

  function drawSep(y, label) {{
    ctx.strokeStyle = 'rgba(255,255,255,0.08)'; ctx.lineWidth = 0.5;
    ctx.beginPath(); ctx.moveTo(L, y); ctx.lineTo(w - R, y); ctx.stroke();
    ctx.fillStyle = '#5c5d6e'; ctx.font = '8px "Fira Code",monospace'; ctx.textAlign = 'left';
    ctx.fillText(label, L + 4, y + 10);
  }}

  const allVals = d.h.concat(d.l);
  const mn = Math.min(...allVals), mx = Math.max(...allVals);
  const range = mx - mn || 1;
  const fmtP = v => v >= 1000 ? v.toFixed(0) : v.toFixed(1);
  drawGrid(pCandle, mn, mx, 4, fmtP);

  const barW = Math.max(1, Math.min(8, (cw / n) * 0.65));
  for (let i = 0; i < n; i++) {{
    const x = xPos(i);
    const oY = pCandle.t + (1 - (d.o[i] - mn) / range) * pCandle.h;
    const cY = pCandle.t + (1 - (d.c[i] - mn) / range) * pCandle.h;
    const hY = pCandle.t + (1 - (d.h[i] - mn) / range) * pCandle.h;
    const lY = pCandle.t + (1 - (d.l[i] - mn) / range) * pCandle.h;
    const bull = d.c[i] >= d.o[i];
    const clr = bull ? '#00e5a0' : '#ff4d6d';
    ctx.strokeStyle = clr; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(x, hY); ctx.lineTo(x, lY); ctx.stroke();
    ctx.fillStyle = bull ? clr + '88' : clr;
    const top = Math.min(oY, cY), bh = Math.max(1, Math.abs(oY - cY));
    ctx.fillRect(x - barW/2, top, barW, bh);
  }}

  const ema50 = d.ema50 || (n >= 50 ? _calcEMA(d.c, 50) : null);
  const sma200 = d.sma200 || (n >= 200 ? _calcSMA(d.c, 200) : null);
  if (ema50) _drawMA(ctx, ema50, n, mn, range, {{ t: pCandle.t, b: 0, l: L, r: R }}, cw, pCandle.h, '#9b7fff', []);
  if (sma200) _drawMA(ctx, sma200, n, mn, range, {{ t: pCandle.t, b: 0, l: L, r: R }}, cw, pCandle.h, '#f5a623', [5, 3]);

  ctx.font = '8px "Fira Code",monospace'; ctx.textAlign = 'left';
  let lx = L + 4, ly = pCandle.t + 10;
  if (ema50) {{ const e = ema50.filter(v=>v!==null).pop(); ctx.fillStyle='#9b7fff'; ctx.fillText('── 50 EMA'+(e?' ('+e.toLocaleString('en-US',{{maximumFractionDigits:0}})+')':''), lx, ly); ly+=11; }}
  if (sma200) {{ const sv = sma200.filter(v=>v!==null).pop(); ctx.fillStyle='#f5a623'; ctx.fillText('╌╌ 200 DMA'+(sv?' ('+sv.toLocaleString('en-US',{{maximumFractionDigits:0}})+')':''), lx, ly); }}

  drawSep(pVol.t, 'VOLUME');
  const maxVol = Math.max(...d.v);
  for (let i = 0; i < n; i++) {{
    const x = xPos(i);
    const vH = (d.v[i] / maxVol) * pVol.h * 0.85;
    const bull = d.c[i] >= d.o[i];
    ctx.fillStyle = bull ? 'rgba(0,229,160,0.3)' : 'rgba(255,77,109,0.3)';
    ctx.fillRect(x - barW/2, pVol.t + pVol.h - vH, barW, vH);
  }}

  if (hasRsi) {{
    drawSep(pRsi.t, 'RSI (14)');
    ctx.fillStyle = 'rgba(0,229,160,0.04)';
    const y30 = pRsi.t + (1 - 30/100) * pRsi.h;
    const y70 = pRsi.t + (1 - 70/100) * pRsi.h;
    ctx.fillRect(L, y70, cw, y30 - y70);
    ctx.setLineDash([3,3]); ctx.strokeStyle = 'rgba(255,255,255,0.1)'; ctx.lineWidth = 0.5;
    [30, 50, 70].forEach(lv => {{
      const y = pRsi.t + (1 - lv/100) * pRsi.h;
      ctx.beginPath(); ctx.moveTo(L, y); ctx.lineTo(w-R, y); ctx.stroke();
      ctx.fillStyle = '#5c5d6e'; ctx.font = '7px "Fira Code",monospace'; ctx.textAlign = 'right';
      ctx.fillText(lv.toString(), L-4, y+3);
    }});
    ctx.setLineDash([]);
    ctx.strokeStyle = '#9b7fff'; ctx.lineWidth = 1.2;
    ctx.beginPath();
    let started = false;
    d.rsi.forEach((v, i) => {{
      if (v === null) return;
      const x = xPos(i);
      const y = pRsi.t + (1 - v/100) * pRsi.h;
      if (!started) {{ ctx.moveTo(x, y); started = true; }} else ctx.lineTo(x, y);
    }});
    ctx.stroke();
    const lastRsi = d.rsi.filter(v=>v!==null).pop();
    if (lastRsi) {{
      ctx.fillStyle = lastRsi < 30 ? '#00e5a0' : lastRsi > 70 ? '#ff4d6d' : '#9b7fff';
      ctx.font = '9px "Fira Code",monospace'; ctx.textAlign = 'left';
      ctx.fillText(lastRsi.toFixed(0), w - R + 2, pRsi.t + (1 - lastRsi/100) * pRsi.h + 3);
    }}
  }}

  if (hasMacd) {{
    drawSep(pMacd.t, 'MACD');
    const mVals = d.macd.filter(v=>v!==null);
    const sVals = d.macd_sig.filter(v=>v!==null);
    const hVals = d.macd_hist.filter(v=>v!==null);
    const allM = mVals.concat(sVals).concat(hVals);
    if (allM.length) {{
      const mMn = Math.min(...allM), mMx = Math.max(...allM);
      const mRng = Math.max(Math.abs(mMn), Math.abs(mMx)) || 1;
      const mScale = v => pMacd.t + pMacd.h/2 - (v / mRng) * pMacd.h * 0.45;
      ctx.strokeStyle = 'rgba(255,255,255,0.08)'; ctx.lineWidth = 0.5;
      ctx.beginPath(); ctx.moveTo(L, pMacd.t + pMacd.h/2); ctx.lineTo(w-R, pMacd.t + pMacd.h/2); ctx.stroke();
      for (let i = 0; i < n; i++) {{
        const hv = d.macd_hist[i];
        if (hv === null) continue;
        const x = xPos(i);
        const zY = pMacd.t + pMacd.h/2;
        const bY = mScale(hv);
        ctx.fillStyle = hv >= 0 ? 'rgba(0,229,160,0.35)' : 'rgba(255,77,109,0.35)';
        ctx.fillRect(x - barW/2, Math.min(zY, bY), barW, Math.abs(bY - zY));
      }}
      ctx.strokeStyle = '#3d9cf5'; ctx.lineWidth = 1.2; ctx.beginPath();
      let ms = false;
      d.macd.forEach((v,i) => {{ if (v===null) return; const x=xPos(i), y=mScale(v); if(!ms){{ctx.moveTo(x,y);ms=true;}}else ctx.lineTo(x,y); }});
      ctx.stroke();
      ctx.strokeStyle = '#f5a623'; ctx.lineWidth = 1; ctx.setLineDash([3,2]); ctx.beginPath();
      let ss = false;
      d.macd_sig.forEach((v,i) => {{ if (v===null) return; const x=xPos(i), y=mScale(v); if(!ss){{ctx.moveTo(x,y);ss=true;}}else ctx.lineTo(x,y); }});
      ctx.stroke(); ctx.setLineDash([]);
    }}
  }}

  const nLabels = Math.min(6, n);
  ctx.fillStyle = '#5c5d6e'; ctx.font = '8px "Fira Code",monospace'; ctx.textAlign = 'center';
  for (let i = 0; i < nLabels; i++) {{
    const idx = Math.round(i / (nLabels - 1) * (n - 1));
    ctx.fillText(d.d[idx], xPos(idx), h - 4);
  }}
}}

function _calcEMA(data, period) {{
  const result = new Array(data.length).fill(null);
  if (data.length < period) return result;
  let sum = 0;
  for (let i = 0; i < period; i++) sum += data[i];
  result[period-1] = sum / period;
  const k = 2 / (period + 1);
  for (let i = period; i < data.length; i++) result[i] = data[i] * k + result[i-1] * (1-k);
  return result;
}}
function _calcSMA(data, period) {{
  const result = new Array(data.length).fill(null);
  if (data.length < period) return result;
  let sum = 0;
  for (let i = 0; i < period; i++) sum += data[i];
  result[period-1] = sum / period;
  for (let i = period; i < data.length; i++) {{ sum += data[i] - data[i-period]; result[i] = sum / period; }}
  return result;
}}
function _drawMA(ctx, vals, n, mn, range, pad, cw, ch, color, dash) {{
  ctx.strokeStyle = color; ctx.lineWidth = 1.2; ctx.setLineDash(dash);
  ctx.beginPath();
  let started = false;
  vals.forEach((v, i) => {{
    if (v === null) return;
    const x = pad.l + ((i + 0.5) / n) * cw;
    const y = pad.t + (1 - (v - mn) / range) * ch;
    if (!started) {{ ctx.moveTo(x, y); started = true; }} else ctx.lineTo(x, y);
  }});
  ctx.stroke();
  ctx.setLineDash([]);
}}

function _bindTF(groupId, drawFn, defaultTf) {{
  const btns = document.querySelectorAll('#' + groupId + ' .tf-btn');
  btns.forEach(btn => {{
    btn.addEventListener('click', () => {{
      btns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      drawFn(btn.dataset.tf);
    }});
  }});
  drawFn(defaultTf);
}}

window.addEventListener('DOMContentLoaded', function() {{
  requestAnimationFrame(function() {{
    _bindTF('tf-line', drawLineChart, '1Y');
    _bindTF('tf-candle', drawCandleChart, '6M');
    if (typeof drawFinChart === 'function') drawFinChart('quarterly');
    if (typeof drawEpsEstChart === 'function') drawEpsEstChart('estimates');
  }});
}});

// Valuation trend carousel
(function() {{
  const wrap = document.getElementById('vt-btns');
  if (!wrap) return;
  const btns = wrap.querySelectorAll('.tf-btn');
  btns.forEach(btn => {{
    btn.addEventListener('click', () => {{
      btns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      document.querySelectorAll('.vt-panel').forEach(p => p.style.display = 'none');
      const panel = document.getElementById('vt-panel-' + btn.dataset.idx);
      if (panel) panel.style.display = '';
    }});
  }});
}})();

// Revenue vs Earnings chart
const FIN_DATA = {fin_chart_json};
function drawFinChart(mode) {{
  const items = FIN_DATA[mode] || [];
  if (!items.length) return;
  const c = document.getElementById('cv-fin');
  if (!c) return;
  const ctx = c.getContext('2d');
  const dpr = window.devicePixelRatio || 1;
  const W = c.clientWidth, H = c.clientHeight;
  if (W === 0 || H === 0) return;
  c.width = W * dpr; c.height = H * dpr;
  ctx.scale(dpr, dpr); ctx.clearRect(0, 0, W, H);
  const pad = {{ t:24, b:28, l:60, r:50 }};
  const cw = W - pad.l - pad.r, ch = H - pad.t - pad.b;
  const n = items.length;
  const revs = items.map(d => d.rev || 0);
  const profs = items.map(d => d.profit || 0);
  const epsList = items.map(d => d.eps);
  const hasEps = epsList.some(v => v !== null);
  const allBars = revs.concat(profs);
  const barMn = Math.min(0, ...allBars), barMx = Math.max(...allBars);
  const barRng = barMx - barMn || 1;
  const yBar = v => pad.t + (1 - (v - barMn) / barRng) * ch;
  ctx.strokeStyle = 'rgba(255,255,255,0.05)'; ctx.lineWidth = 0.5;
  ctx.font = '8px "Fira Code",monospace'; ctx.fillStyle = '#5c5d6e'; ctx.textAlign = 'right';
  for (let i = 0; i <= 4; i++) {{
    const val = barMx - (i / 4) * barRng;
    const y = pad.t + (i / 4) * ch;
    ctx.beginPath(); ctx.moveTo(pad.l, y); ctx.lineTo(W - pad.r, y); ctx.stroke();
    ctx.fillText(val >= 1000 ? (val/1000).toFixed(0)+'K' : val.toFixed(0), pad.l - 5, y + 3);
  }}
  if (barMn < 0) {{
    const zy = yBar(0);
    ctx.strokeStyle = 'rgba(255,255,255,0.12)'; ctx.lineWidth = 0.5;
    ctx.beginPath(); ctx.moveTo(pad.l, zy); ctx.lineTo(W - pad.r, zy); ctx.stroke();
  }}
  const groupW = cw / n;
  const bw = Math.max(4, groupW * 0.3);
  for (let i = 0; i < n; i++) {{
    const cx = pad.l + (i + 0.5) * groupW;
    const ry1 = yBar(revs[i]), ry0 = yBar(0);
    ctx.fillStyle = 'rgba(61,156,245,0.55)';
    ctx.fillRect(cx - bw - 1, Math.min(ry0, ry1), bw, Math.abs(ry1 - ry0));
    const py1 = yBar(profs[i]), py0 = yBar(0);
    ctx.fillStyle = profs[i] >= 0 ? 'rgba(0,229,160,0.55)' : 'rgba(255,77,109,0.55)';
    ctx.fillRect(cx + 1, Math.min(py0, py1), bw, Math.abs(py1 - py0));
    ctx.fillStyle = '#5c5d6e'; ctx.font = '8px "Fira Code",monospace'; ctx.textAlign = 'center';
    ctx.fillText(items[i].label, cx, H - 6);
  }}
  if (hasEps) {{
    const epsVals = epsList.filter(v => v !== null);
    const eMn = Math.min(...epsVals), eMx = Math.max(...epsVals);
    const eRng = eMx - eMn || 1;
    ctx.strokeStyle = '#f5a623'; ctx.lineWidth = 1.5; ctx.setLineDash([4,2]);
    ctx.beginPath();
    let started = false;
    items.forEach((d, i) => {{
      if (d.eps === null) return;
      const x = pad.l + (i + 0.5) * groupW;
      const y = pad.t + (1 - (d.eps - eMn) / eRng) * ch;
      if (!started) {{ ctx.moveTo(x, y); started = true; }} else ctx.lineTo(x, y);
    }});
    ctx.stroke(); ctx.setLineDash([]);
    ctx.fillStyle = '#f5a623'; ctx.font = '7px "Fira Code",monospace'; ctx.textAlign = 'left';
    for (let i = 0; i <= 3; i++) {{
      const val = eMx - (i / 3) * eRng;
      const y = pad.t + (i / 3) * ch;
      ctx.fillText('$'+val.toFixed(1), W - pad.r + 4, y + 3);
    }}
  }}
  ctx.font = '9px "Fira Code",monospace'; ctx.textAlign = 'left';
  let lgx = pad.l + 4;
  ctx.fillStyle = 'rgba(61,156,245,0.7)'; ctx.fillRect(lgx, pad.t - 14, 10, 8); lgx += 13;
  ctx.fillStyle = '#9899a8'; ctx.fillText('Revenue', lgx, pad.t - 7); lgx += 56;
  ctx.fillStyle = 'rgba(0,229,160,0.7)'; ctx.fillRect(lgx, pad.t - 14, 10, 8); lgx += 13;
  ctx.fillStyle = '#9899a8'; ctx.fillText('Net Profit', lgx, pad.t - 7); lgx += 66;
  if (hasEps) {{
    ctx.strokeStyle = '#f5a623'; ctx.lineWidth = 1.5; ctx.setLineDash([4,2]);
    ctx.beginPath(); ctx.moveTo(lgx, pad.t - 10); ctx.lineTo(lgx + 14, pad.t - 10); ctx.stroke(); ctx.setLineDash([]);
    ctx.fillStyle = '#9899a8'; ctx.fillText('EPS (right)', lgx + 17, pad.t - 7);
  }}
  ctx.fillStyle = '#5c5d6e'; ctx.font = '7px "Fira Code",monospace'; ctx.textAlign = 'left';
  ctx.fillText(FIN_DATA.scale || '', pad.l, H - 16);
}}
(function() {{
  const btns = document.querySelectorAll('#fin-toggle .tf-btn');
  btns.forEach(btn => {{
    btn.addEventListener('click', () => {{
      btns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      drawFinChart(btn.dataset.mode);
    }});
  }});
}})();
(function() {{
  const btns = document.querySelectorAll('#eps-toggle .tf-btn');
  btns.forEach(btn => {{
    btn.addEventListener('click', () => {{
      btns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      drawEpsEstChart(btn.dataset.mode);
    }});
  }});
}})();

// Sankey carousel wiring
function _initSankeyCarousel(id) {{
  const modeWrap = document.getElementById(id + '-mode');
  const periodWrap = document.getElementById(id + '-periods');
  if (!modeWrap) return;
  const modeBtns = modeWrap.querySelectorAll('.tf-btn');

  function showPanel(mode, idx) {{
    document.querySelectorAll('.' + id + '-panel').forEach(p => p.style.display = 'none');
    const targets = document.querySelectorAll('.' + id + '-' + mode);
    if (!targets.length) return;
    targets.forEach((p, i) => p.style.display = i === idx ? '' : 'none');
  }}

  function buildPeriodTabs(mode) {{
    if (!periodWrap) return;
    periodWrap.innerHTML = '';
    const targets = document.querySelectorAll('.' + id + '-' + mode);
    targets.forEach((p, i) => {{
      const b = document.createElement('button');
      b.className = 'tf-btn' + (i === 0 ? ' active' : '');
      const svg = p.querySelector('svg');
      const texts = svg ? svg.querySelectorAll('text') : [];
      let label = 'Period ' + (i + 1);
      if (texts.length) {{
        const last = texts[texts.length - 1].textContent;
        const m = last.match(/([A-Z][a-z]{{2}} \\d{{4}}|FY\\d{{4}}|As of .+?·)/);
        if (m) label = m[1].replace('As of ','').replace(' ·','');
      }}
      b.textContent = label;
      b.addEventListener('click', () => {{
        periodWrap.querySelectorAll('.tf-btn').forEach(x => x.classList.remove('active'));
        b.classList.add('active');
        showPanel(mode, i);
      }});
      periodWrap.appendChild(b);
    }});
  }}

  modeBtns.forEach(btn => {{
    btn.addEventListener('click', () => {{
      modeBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const mode = btn.dataset.mode;
      buildPeriodTabs(mode);
      showPanel(mode, 0);
    }});
  }});
  const activeBtn = modeWrap.querySelector('.tf-btn.active');
  if (activeBtn) {{
    const mode = activeBtn.dataset.mode;
    buildPeriodTabs(mode);
    showPanel(mode, 0);
  }}
}}
_initSankeyCarousel('sk-inc');
_initSankeyCarousel('sk-bs');
_initSankeyCarousel('sk-cf');

const EPS_EST = {earnings_hist_json};
function drawEpsEstChart(mode) {{
  const c = document.getElementById('cv-eps-est');
  if (!c) return;
  const ctx = c.getContext('2d');
  const dpr = window.devicePixelRatio || 1;
  const W = c.clientWidth, H = c.clientHeight;
  if (W === 0 || H === 0) return;
  c.width = W * dpr; c.height = H * dpr;
  ctx.scale(dpr, dpr); ctx.clearRect(0, 0, W, H);

  if (mode === 'quarterly' || mode === 'annual') {{
    const items = FIN_DATA[mode] || [];
    const epsItems = items.filter(d => d.eps !== null);
    if (!epsItems.length) {{
      ctx.fillStyle = '#5c5d6e'; ctx.font = '12px "Fira Code",monospace'; ctx.textAlign = 'center';
      ctx.fillText('EPS data not available for ' + mode, W/2, H/2);
      return;
    }}
    const pad = {{ t:30, b:34, l:55, r:20 }};
    const cw = W - pad.l - pad.r, ch = H - pad.t - pad.b;
    const n = epsItems.length;
    const vals = epsItems.map(d => d.eps);
    const mn = Math.min(...vals) * (Math.min(...vals) > 0 ? 0.8 : 1.2);
    const mx = Math.max(...vals) * 1.15;
    const rng = mx - mn || 1;
    const yV = v => pad.t + (1 - (v - mn) / rng) * ch;
    ctx.strokeStyle = 'rgba(255,255,255,0.05)'; ctx.lineWidth = 0.5;
    ctx.font = '8px "Fira Code",monospace'; ctx.fillStyle = '#5c5d6e'; ctx.textAlign = 'right';
    for (let i = 0; i <= 4; i++) {{
      const val = mx - (i / 4) * rng;
      const y = pad.t + (i / 4) * ch;
      ctx.beginPath(); ctx.moveTo(pad.l, y); ctx.lineTo(W - pad.r, y); ctx.stroke();
      ctx.fillText('$'+val.toFixed(1), pad.l - 5, y + 3);
    }}
    const groupW = cw / n;
    const barW = Math.max(12, Math.min(40, groupW * 0.5));
    const zeroY = yV(0);
    epsItems.forEach((d, i) => {{
      const x = pad.l + (i + 0.5) * groupW;
      const ey = yV(d.eps);
      const barTop = Math.min(zeroY, ey);
      const barH = Math.abs(ey - zeroY);
      ctx.fillStyle = d.eps >= 0 ? 'rgba(0,229,160,0.5)' : 'rgba(255,77,109,0.5)';
      ctx.strokeStyle = d.eps >= 0 ? '#00e5a0' : '#ff4d6d';
      ctx.lineWidth = 1;
      ctx.fillRect(x - barW/2, barTop, barW, barH);
      ctx.strokeRect(x - barW/2, barTop, barW, barH);
      ctx.fillStyle = '#e8e9f0'; ctx.font = '9px "Fira Code",monospace'; ctx.textAlign = 'center';
      ctx.fillText('$' + d.eps.toFixed(1), x, ey - 8);
      ctx.fillStyle = '#9899a8'; ctx.font = '9px "Fira Code",monospace'; ctx.textAlign = 'center';
      ctx.fillText(d.label, x, H - 10);
    }});
    ctx.font = '9px "Fira Code",monospace'; ctx.textAlign = 'left'; ctx.fillStyle = '#9899a8';
    ctx.fillText(mode === 'quarterly' ? 'Quarterly EPS ($/share)' : 'Annual EPS ($/share)', pad.l + 4, pad.t - 14);
    return;
  }}

  if (!EPS_EST.length) {{
    ctx.fillStyle = '#5c5d6e'; ctx.font = '12px "Fira Code",monospace'; ctx.textAlign = 'center';
    ctx.fillText('Earnings estimate data not available', W/2, H/2);
    return;
  }}
  const pad = {{ t:30, b:34, l:55, r:20 }};
  const cw = W - pad.l - pad.r, ch = H - pad.t - pad.b;
  const n = EPS_EST.length;
  const allV = EPS_EST.flatMap(d => [d.estimate, d.actual]).filter(v => v !== null);
  if (!allV.length) return;
  const mn = Math.min(...allV) * 0.8, mx = Math.max(...allV) * 1.2;
  const rng = mx - mn || 1;
  const yV = v => pad.t + (1 - (v - mn) / rng) * ch;
  ctx.strokeStyle = 'rgba(255,255,255,0.05)'; ctx.lineWidth = 0.5;
  ctx.font = '8px "Fira Code",monospace'; ctx.fillStyle = '#5c5d6e'; ctx.textAlign = 'right';
  for (let i = 0; i <= 4; i++) {{
    const val = mx - (i / 4) * rng;
    const y = pad.t + (i / 4) * ch;
    ctx.beginPath(); ctx.moveTo(pad.l, y); ctx.lineTo(W - pad.r, y); ctx.stroke();
    ctx.fillText('$'+val.toFixed(1), pad.l - 5, y + 3);
  }}
  const groupW = cw / n;
  const dotR = 6;
  EPS_EST.forEach((d, i) => {{
    if (d.estimate === null || d.actual === null) return;
    const x = pad.l + (i + 0.5) * groupW;
    ctx.strokeStyle = 'rgba(255,255,255,0.08)'; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(x, yV(d.estimate)); ctx.lineTo(x, yV(d.actual)); ctx.stroke();
  }});
  EPS_EST.forEach((d, i) => {{
    const x = pad.l + (i + 0.5) * groupW;
    const hasEst = d.estimate !== null;
    const hasAct = d.actual !== null;
    const beat = hasAct && hasEst && d.actual >= d.estimate;
    if (hasEst) {{
      const ex = x - 8;
      const ey = yV(d.estimate);
      ctx.beginPath(); ctx.arc(ex, ey, dotR, 0, Math.PI*2);
      ctx.fillStyle = '#9b7fff'; ctx.fill();
      ctx.strokeStyle = '#08090d'; ctx.lineWidth = 1.5; ctx.stroke();
      ctx.fillStyle = '#9b7fff'; ctx.font = '8px "Fira Code",monospace'; ctx.textAlign = 'right';
      ctx.fillText('$' + d.estimate.toFixed(1), ex - 9, ey + 3);
    }}
    if (hasAct) {{
      const ax = x + 8;
      const ay = yV(d.actual);
      ctx.beginPath(); ctx.arc(ax, ay, dotR, 0, Math.PI*2);
      ctx.fillStyle = beat ? '#00e5a0' : '#ff4d6d'; ctx.fill();
      ctx.strokeStyle = '#08090d'; ctx.lineWidth = 1.5; ctx.stroke();
      ctx.fillStyle = beat ? '#00e5a0' : '#ff4d6d'; ctx.font = '8px "Fira Code",monospace'; ctx.textAlign = 'left';
      ctx.fillText('$' + d.actual.toFixed(1), ax + 9, ay + 3);
    }}
    if (d.surprise !== null) {{
      ctx.font = '9px "Fira Code",monospace'; ctx.textAlign = 'center';
      ctx.fillStyle = d.surprise >= 0 ? '#00e5a0' : '#ff4d6d';
      const bottomY = Math.max(hasEst ? yV(d.estimate) : 0, hasAct ? yV(d.actual) : 0);
      ctx.fillText((d.surprise >= 0 ? '+' : '') + d.surprise.toFixed(1) + '%', x, bottomY + 18);
    }}
    ctx.fillStyle = '#5c5d6e'; ctx.font = '7px "Fira Code",monospace'; ctx.textAlign = 'center';
    ctx.fillText(d.label, x, H - 8);
  }});
  ctx.font = '9px "Fira Code",monospace'; ctx.textAlign = 'left';
  let lx2 = pad.l + 4;
  ctx.beginPath(); ctx.arc(lx2 + 4, pad.t - 16, 4, 0, Math.PI*2); ctx.fillStyle = '#9b7fff'; ctx.fill(); lx2 += 12;
  ctx.fillStyle = '#9899a8'; ctx.fillText('Estimate', lx2, pad.t - 13); lx2 += 60;
  ctx.beginPath(); ctx.arc(lx2 + 4, pad.t - 16, 4, 0, Math.PI*2); ctx.fillStyle = '#00e5a0'; ctx.fill(); lx2 += 12;
  ctx.fillStyle = '#9899a8'; ctx.fillText('Beat', lx2, pad.t - 13); lx2 += 38;
  ctx.beginPath(); ctx.arc(lx2 + 4, pad.t - 16, 4, 0, Math.PI*2); ctx.fillStyle = '#ff4d6d'; ctx.fill(); lx2 += 12;
  ctx.fillStyle = '#9899a8'; ctx.fillText('Miss', lx2, pad.t - 13);
}}


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
