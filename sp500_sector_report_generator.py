#!/usr/bin/env python3
"""
S&P 500 Sector Report Generator
=================================
Generates a dark-themed, interactive HTML report of all 11 GICS sectors.

Features:
  - Color-coded cards by YTD performance (green=gains, amber/red=loss)
  - Expandable cards with top-5 holdings, market-cap breakdown, 52-week range
  - Index pills (S&P 500, NASDAQ, DOW JONES YTD)
  - Sort toggles (YTD / Weight / P/E / Div Yield)
  - Scroll-triggered fade-in animations
  - Beginner explainer box
  - Gradient legend bar

Usage:
    python sp500_sector_report_generator.py
    python sp500_sector_report_generator.py -o ./sp500_reports/

Requirements:
    pip install yfinance pandas numpy
"""

import os
import sys
import json
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
# SECTOR DEFINITIONS — 11 GICS sectors via Select Sector SPDR ETFs
# ─────────────────────────────────────────────────────────────────────────────

GICS_SECTORS = {
    "Technology": {
        "etf": "XLK",
        "weight": 31.6,
        "top5": ["AAPL", "MSFT", "NVDA", "AVGO", "CRM"],
        "desc": "Software, hardware, semiconductors, IT services",
    },
    "Health Care": {
        "etf": "XLV",
        "weight": 11.8,
        "top5": ["UNH", "LLY", "JNJ", "ABBV", "MRK"],
        "desc": "Pharma, biotech, medical devices, health insurance",
    },
    "Financials": {
        "etf": "XLF",
        "weight": 13.5,
        "top5": ["BRK-B", "JPM", "V", "MA", "BAC"],
        "desc": "Banks, insurance, asset management, fintech",
    },
    "Consumer Discretionary": {
        "etf": "XLY",
        "weight": 10.2,
        "top5": ["AMZN", "TSLA", "HD", "MCD", "NKE"],
        "desc": "Retail, autos, restaurants, apparel, leisure",
    },
    "Communication Services": {
        "etf": "XLC",
        "weight": 9.1,
        "top5": ["META", "GOOGL", "GOOG", "NFLX", "DIS"],
        "desc": "Social media, telecom, streaming, advertising",
    },
    "Industrials": {
        "etf": "XLI",
        "weight": 8.5,
        "top5": ["GE", "CAT", "UNP", "HON", "RTX"],
        "desc": "Aerospace, defense, machinery, transport, logistics",
    },
    "Consumer Staples": {
        "etf": "XLP",
        "weight": 5.9,
        "top5": ["PG", "COST", "KO", "PEP", "WMT"],
        "desc": "Food, beverages, household products, tobacco",
    },
    "Energy": {
        "etf": "XLE",
        "weight": 3.4,
        "top5": ["XOM", "CVX", "COP", "SLB", "EOG"],
        "desc": "Oil & gas exploration, refining, equipment, pipelines",
    },
    "Utilities": {
        "etf": "XLU",
        "weight": 2.4,
        "top5": ["NEE", "SO", "DUK", "CEG", "SRE"],
        "desc": "Electric, gas, water utilities, renewables",
    },
    "Real Estate": {
        "etf": "XLRE",
        "weight": 2.2,
        "top5": ["PLD", "AMT", "EQIX", "WELL", "SPG"],
        "desc": "REITs — data centers, towers, industrial, healthcare",
    },
    "Materials": {
        "etf": "XLB",
        "weight": 2.1,
        "top5": ["LIN", "SHW", "APD", "ECL", "FCX"],
        "desc": "Chemicals, metals, mining, packaging, construction",
    },
}

INDEX_TICKERS = [
    {"symbol": "^GSPC", "label": "S&P 500", "color": "#3d9cf5"},
    {"symbol": "^IXIC", "label": "NASDAQ", "color": "#9b7fff"},
    {"symbol": "^DJI", "label": "DOW JONES", "color": "#f5a623"},
]


# ─────────────────────────────────────────────────────────────────────────────
# DATA FETCHING
# ─────────────────────────────────────────────────────────────────────────────

def _safe_float(val, default=None):
    try:
        v = float(val)
        return v if not (np.isnan(v) or np.isinf(v)) else default
    except (TypeError, ValueError):
        return default


def fetch_sector_data(sector_name, sector_info):
    """Fetch comprehensive data for a single sector ETF."""
    etf_symbol = sector_info["etf"]
    print(f"    Fetching {etf_symbol} ({sector_name})...")

    try:
        tk = yf.Ticker(etf_symbol)
        info = tk.info or {}
        hist = tk.history(period="13mo")

        if hist is None or hist.empty or len(hist) < 2:
            print(f"    ⚠ No price history for {etf_symbol}")
            return None

        close = hist["Close"]
        current = float(close.iloc[-1])

        # YTD: from first trading day of current year
        year_start = datetime(datetime.now().year, 1, 1)
        ytd_hist = close[close.index >= pd.Timestamp(year_start, tz=close.index.tz)]
        if len(ytd_hist) >= 2:
            ytd_return = ((current / float(ytd_hist.iloc[0])) - 1) * 100
        else:
            ytd_return = 0.0

        returns = {"YTD": ytd_return}
        for label, days in [("6M", 126), ("1Y", 252)]:
            if len(close) >= days + 1:
                returns[label] = ((current / float(close.iloc[-(days + 1)])) - 1) * 100
            elif len(close) >= 2:
                returns[label] = ((current / float(close.iloc[0])) - 1) * 100
            else:
                returns[label] = None

        # 52-week range
        tail_252 = close.tail(252) if len(close) >= 252 else close
        high_52w = float(tail_252.max())
        low_52w = float(tail_252.min())

        pe_ratio = _safe_float(info.get("trailingPE") or info.get("forwardPE"))
        div_yield = _safe_float(info.get("dividendYield") or info.get("yield"))
        if div_yield and div_yield < 1:
            div_yield *= 100

        # Holdings data
        holdings = []
        for sym in sector_info["top5"]:
            try:
                htk = yf.Ticker(sym)
                hinfo = htk.info or {}
                hhist = htk.history(period="ytd")
                h_ytd = None
                if hhist is not None and len(hhist) >= 2:
                    h_ytd = ((float(hhist["Close"].iloc[-1]) / float(hhist["Close"].iloc[0])) - 1) * 100

                mktcap = _safe_float(hinfo.get("marketCap"), 0)
                holdings.append({
                    "symbol": sym,
                    "name": hinfo.get("shortName", sym),
                    "marketCap": mktcap,
                    "ytd": h_ytd,
                    "price": _safe_float(hinfo.get("currentPrice") or hinfo.get("regularMarketPrice")),
                })
            except Exception:
                holdings.append({"symbol": sym, "name": sym, "marketCap": 0, "ytd": None, "price": None})

        total_mcap = sum(h["marketCap"] for h in holdings)
        mega = sum(h["marketCap"] for h in holdings if h["marketCap"] >= 200e9)
        large = sum(h["marketCap"] for h in holdings if 10e9 <= h["marketCap"] < 200e9)
        mid = sum(h["marketCap"] for h in holdings if h["marketCap"] < 10e9)
        if total_mcap > 0:
            cap_breakdown = {
                "mega": round(mega / total_mcap * 100, 1),
                "large": round(large / total_mcap * 100, 1),
                "mid": round(mid / total_mcap * 100, 1),
            }
        else:
            cap_breakdown = {"mega": 0, "large": 0, "mid": 0}

        # Schwab-style composite forward score (1-5 scale)
        # Based on: YTD momentum, P/E attractiveness, dividend yield, 52w range position
        score_components = []
        if ytd_return is not None:
            mom_score = 3 + min(max(ytd_return / 10, -2), 2)
            score_components.append(mom_score)
        if pe_ratio and pe_ratio > 0:
            pe_score = max(1, min(5, 5 - (pe_ratio - 15) / 10))
            score_components.append(pe_score)
        if div_yield and div_yield > 0:
            dy_score = min(5, 1 + div_yield * 1.5)
            score_components.append(dy_score)
        range_pos = (current - low_52w) / (high_52w - low_52w) if high_52w != low_52w else 0.5
        range_score = 1 + (1 - range_pos) * 4
        score_components.append(range_score)
        forward_rating = round(sum(score_components) / len(score_components), 1) if score_components else 3.0

        return {
            "sector": sector_name,
            "etf": etf_symbol,
            "weight": sector_info["weight"],
            "desc": sector_info["desc"],
            "current": current,
            "returns": returns,
            "pe": pe_ratio,
            "divYield": div_yield,
            "high52w": high_52w,
            "low52w": low_52w,
            "forwardRating": forward_rating,
            "holdings": holdings,
            "capBreakdown": cap_breakdown,
        }

    except Exception as e:
        print(f"    ⚠ Error fetching {etf_symbol}: {e}")
        return None


def fetch_index_ytd():
    """Fetch YTD return for major indices."""
    results = []
    for idx in INDEX_TICKERS:
        try:
            tk = yf.Ticker(idx["symbol"])
            hist = tk.history(period="ytd")
            if hist is not None and len(hist) >= 2:
                close = hist["Close"]
                ytd = ((float(close.iloc[-1]) / float(close.iloc[0])) - 1) * 100
                price = float(close.iloc[-1])
            else:
                ytd, price = 0.0, 0.0
            results.append({**idx, "ytd": ytd, "price": price})
        except Exception:
            results.append({**idx, "ytd": 0.0, "price": 0.0})
    return results


# ─────────────────────────────────────────────────────────────────────────────
# HTML GENERATION
# ─────────────────────────────────────────────────────────────────────────────

def _fmt(val, fmt=".1f", suffix="%", fallback="N/A"):
    if val is None:
        return fallback
    return f"{val:{fmt}}{suffix}"


def _sign(val):
    if val is None:
        return ""
    return "+" if val >= 0 else ""


def _perf_color(val):
    """Return CSS color class based on performance value."""
    if val is None:
        return "neutral"
    if val >= 0:
        return "positive"
    return "negative"


def _rating_label(r):
    if r >= 4.0:
        return "Outperform"
    if r >= 3.0:
        return "Market Perform"
    if r >= 2.0:
        return "Underperform"
    return "Sell"


def _rating_color(r):
    if r >= 4.0:
        return "#00e5a0"
    if r >= 3.0:
        return "#3d9cf5"
    if r >= 2.0:
        return "#f5a623"
    return "#ff4d6d"


def _mcap_fmt(val):
    if val is None or val == 0:
        return "N/A"
    if val >= 1e12:
        return f"${val / 1e12:.1f}T"
    if val >= 1e9:
        return f"${val / 1e9:.0f}B"
    if val >= 1e6:
        return f"${val / 1e6:.0f}M"
    return f"${val:,.0f}"


def generate_html(sectors_data, index_data, gen_date):
    """Generate the full self-contained HTML heatmap."""
    sectors_json = json.dumps(sectors_data, default=str, separators=(",", ":"))

    # Build sector cards
    cards_html = ""
    for i, s in enumerate(sectors_data):
        ytd = s["returns"].get("YTD", 0) or 0
        six_m = s["returns"].get("6M")
        one_y = s["returns"].get("1Y")
        pe = s.get("pe")
        dy = s.get("divYield")
        fr = s.get("forwardRating", 3.0)

        # Heatmap background: green for positive, amber→red for negative
        if ytd >= 15:
            card_bg = "rgba(0,229,160,0.18)"
            accent = "#00e5a0"
        elif ytd >= 5:
            card_bg = "rgba(0,229,160,0.10)"
            accent = "#00e5a0"
        elif ytd >= 0:
            card_bg = "rgba(0,229,160,0.05)"
            accent = "#4ade80"
        elif ytd >= -5:
            card_bg = "rgba(245,166,35,0.08)"
            accent = "#f5a623"
        elif ytd >= -15:
            card_bg = "rgba(245,166,35,0.15)"
            accent = "#f59e0b"
        else:
            card_bg = "rgba(255,77,109,0.14)"
            accent = "#ff4d6d"

        # Holdings HTML
        holdings_rows = ""
        for h in s.get("holdings", []):
            h_ytd = h.get("ytd")
            h_ytd_cls = _perf_color(h_ytd)
            holdings_rows += f"""<tr>
              <td class="h-sym">{h['symbol']}</td>
              <td class="h-name">{h.get('name', h['symbol'])[:22]}</td>
              <td class="h-mcap">{_mcap_fmt(h.get('marketCap'))}</td>
              <td class="h-ytd {h_ytd_cls}">{_sign(h_ytd)}{_fmt(h_ytd)}</td>
            </tr>"""

        # Cap breakdown
        cb = s.get("capBreakdown", {})

        # 52-week range marker position
        low = s.get("low52w", 0)
        high = s.get("high52w", 0)
        cur = s.get("current", 0)
        if high > low:
            range_pct = ((cur - low) / (high - low)) * 100
        else:
            range_pct = 50

        cards_html += f"""
    <div class="sector-card fade-in" data-ytd="{ytd:.2f}" data-weight="{s['weight']}"
         data-pe="{pe if pe else 0}" data-div="{dy if dy else 0}"
         style="--card-bg:{card_bg};--card-accent:{accent}" onclick="toggleExpand(this)">
      <div class="card-top">
        <div class="card-header">
          <div class="sector-name">{s['sector']}</div>
          <div class="etf-ticker">{s['etf']}</div>
        </div>
        <div class="ytd-badge {_perf_color(ytd)}">
          {_sign(ytd)}{ytd:.1f}%
        </div>
      </div>
      <div class="card-desc">{s['desc']}</div>
      <div class="card-metrics">
        <div class="metric">
          <span class="metric-label">S&P Wt</span>
          <span class="metric-value">{s['weight']}%</span>
        </div>
        <div class="metric">
          <span class="metric-label">6M</span>
          <span class="metric-value {_perf_color(six_m)}">{_sign(six_m)}{_fmt(six_m)}</span>
        </div>
        <div class="metric">
          <span class="metric-label">1Y</span>
          <span class="metric-value {_perf_color(one_y)}">{_sign(one_y)}{_fmt(one_y)}</span>
        </div>
        <div class="metric">
          <span class="metric-label">P/E</span>
          <span class="metric-value">{_fmt(pe, '.1f', 'x')}</span>
        </div>
        <div class="metric">
          <span class="metric-label">Div Yld</span>
          <span class="metric-value">{_fmt(dy)}</span>
        </div>
        <div class="metric rating" style="--r-color:{_rating_color(fr)}">
          <span class="metric-label">Rating</span>
          <span class="metric-value">{_rating_label(fr)}</span>
        </div>
      </div>

      <div class="expand-section">
        <div class="expand-block">
          <div class="expand-title">Top 5 Holdings</div>
          <table class="holdings-table">
            <thead><tr><th>Ticker</th><th>Name</th><th>Mkt Cap</th><th>YTD</th></tr></thead>
            <tbody>{holdings_rows}</tbody>
          </table>
        </div>

        <div class="expand-block">
          <div class="expand-title">Market Cap Breakdown</div>
          <div class="cap-bar">
            <div class="cap-seg mega" style="width:{cb.get('mega',0)}%"><span>Mega {cb.get('mega',0)}%</span></div>
            <div class="cap-seg large" style="width:{cb.get('large',0)}%"><span>Large {cb.get('large',0)}%</span></div>
            <div class="cap-seg mid" style="width:{cb.get('mid',0)}%"><span>Mid {cb.get('mid',0)}%</span></div>
          </div>
          <div class="cap-legend">
            <span class="cap-l mega-l">● Mega (&gt;$200B)</span>
            <span class="cap-l large-l">● Large ($10-200B)</span>
            <span class="cap-l mid-l">● Mid (&lt;$10B)</span>
          </div>
        </div>

        <div class="expand-block">
          <div class="expand-title">52-Week Price Range</div>
          <div class="range-track">
            <div class="range-fill" style="width:100%"></div>
            <div class="range-marker" style="left:{range_pct:.1f}%">
              <div class="marker-label">${cur:,.2f}</div>
            </div>
          </div>
          <div class="range-labels">
            <span>${low:,.2f}</span>
            <span>${high:,.2f}</span>
          </div>
        </div>
      </div>
    </div>"""

    # Index pills
    pills_html = ""
    for idx in index_data:
        cls = "up" if idx["ytd"] >= 0 else "dn"
        pills_html += f"""<div class="idx-pill">
      <span class="idx-label">{idx['label']}</span>
      <span class="idx-price">{idx['price']:,.0f}</span>
      <span class="idx-ytd {cls}">{_sign(idx['ytd'])}{idx['ytd']:.2f}%</span>
    </div>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>S&P 500 Sector Report — {gen_date}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;600;700&family=DM+Sans:ital,opsz,wght@0,9..40,400..700;1,9..40,400..700&display=swap" rel="stylesheet">
<style>
:root {{
  --bg:#08090d; --bg2:#0d0e14; --bg3:#12131a; --bg4:#181922;
  --border:rgba(255,255,255,0.07); --border2:rgba(255,255,255,0.12);
  --green:#00e5a0; --green-dim:rgba(0,229,160,0.12);
  --red:#ff4d6d; --red-dim:rgba(255,77,109,0.12);
  --amber:#f5a623; --amber-dim:rgba(245,166,35,0.12);
  --blue:#3d9cf5; --blue-dim:rgba(61,156,245,0.12);
  --purple:#9b7fff;
  --text:#e8e9f0; --text2:#9899a8; --text3:#5c5d6e;
  --mono:'Fira Code',monospace; --sans:'DM Sans',sans-serif;
}}
*,*::before,*::after {{ box-sizing:border-box; margin:0; padding:0; }}
html {{ scroll-behavior:smooth; }}
body {{ background:var(--bg); color:var(--text); font-family:var(--sans); font-size:13px; line-height:1.6; -webkit-font-smoothing:antialiased; }}

.page {{ max-width:1200px; margin:0 auto; padding:24px 22px 60px; }}

/* ── Header ──────────────────────────────────────── */
.header {{ background:linear-gradient(135deg,#0f1018,#131420 60%,#0d1020); border:1px solid var(--border); border-radius:16px; padding:28px 32px 22px; margin-bottom:20px; position:relative; overflow:hidden; }}
.header::before {{ content:''; position:absolute; top:0; left:0; right:0; height:2px; background:linear-gradient(90deg,transparent,var(--blue),transparent); opacity:.5; }}
.header-top {{ display:flex; justify-content:space-between; align-items:flex-start; flex-wrap:wrap; gap:12px; }}
.title {{ font-family:var(--mono); font-size:20px; font-weight:700; color:#fff; letter-spacing:-0.5px; }}
.subtitle {{ font-family:var(--mono); font-size:11px; color:var(--text3); margin-top:4px; }}
.gen-badge {{ font-family:var(--mono); font-size:9px; color:var(--text3); background:var(--bg4); padding:4px 12px; border-radius:6px; border:1px solid var(--border); white-space:nowrap; }}

/* ── Index Pills ─────────────────────────────────── */
.idx-strip {{ display:flex; gap:10px; flex-wrap:wrap; margin:18px 0 6px; }}
.idx-pill {{ display:flex; align-items:center; gap:8px; background:var(--bg4); border:1px solid var(--border); border-radius:8px; padding:8px 14px; font-family:var(--mono); font-size:11px; }}
.idx-label {{ color:var(--text2); font-weight:600; font-size:10px; letter-spacing:0.5px; text-transform:uppercase; }}
.idx-price {{ color:#fff; font-weight:700; }}
.idx-ytd {{ font-weight:600; }}
.idx-ytd.up {{ color:var(--green); }}
.idx-ytd.dn {{ color:var(--red); }}

/* ── Sort Buttons ────────────────────────────────── */
.controls {{ display:flex; align-items:center; gap:8px; flex-wrap:wrap; margin-bottom:18px; }}
.controls-label {{ font-family:var(--mono); font-size:10px; color:var(--text3); text-transform:uppercase; letter-spacing:1px; margin-right:4px; }}
.sort-btn {{ font-family:var(--mono); font-size:10px; font-weight:600; padding:6px 14px; border-radius:6px; border:1px solid var(--border); background:var(--bg3); color:var(--text3); cursor:pointer; transition:all .18s; }}
.sort-btn:hover {{ color:var(--text); border-color:var(--border2); }}
.sort-btn.active {{ color:#fff; background:var(--bg4); border-color:var(--blue); box-shadow:0 0 8px rgba(61,156,245,0.15); }}

/* ── Legend ───────────────────────────────────────── */
.legend {{ display:flex; align-items:center; gap:12px; margin-bottom:20px; background:var(--bg2); border:1px solid var(--border); border-radius:10px; padding:12px 18px; }}
.legend-label {{ font-family:var(--mono); font-size:9px; color:var(--text3); text-transform:uppercase; letter-spacing:0.8px; white-space:nowrap; }}
.legend-bar {{ flex:1; height:10px; border-radius:5px; background:linear-gradient(90deg,#ff4d6d,#f5a623 40%,#4ade80 60%,#00e5a0); }}
.legend-range {{ display:flex; justify-content:space-between; font-family:var(--mono); font-size:9px; color:var(--text3); flex:1; }}

/* ── Sector Grid ─────────────────────────────────── */
.sector-grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(320px,1fr)); gap:14px; }}
@media(max-width:700px) {{ .sector-grid {{ grid-template-columns:1fr; }} }}

.sector-card {{ background:var(--card-bg, var(--bg2)); border:1px solid var(--border); border-radius:14px; padding:18px 20px; cursor:pointer; transition:all .22s ease; position:relative; overflow:hidden; }}
.sector-card::before {{ content:''; position:absolute; top:0; left:0; right:0; height:2px; background:linear-gradient(90deg,transparent,var(--card-accent,var(--blue)),transparent); opacity:.35; }}
.sector-card:hover {{ border-color:var(--card-accent,var(--border2)); transform:translateY(-2px); box-shadow:0 8px 24px rgba(0,0,0,0.35); }}

.card-top {{ display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:6px; }}
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

/* ── Expandable Section ──────────────────────────── */
.expand-section {{ max-height:0; overflow:hidden; transition:max-height .4s cubic-bezier(0.4,0,0.2,1), opacity .3s ease; opacity:0; margin-top:0; }}
.sector-card.expanded .expand-section {{ max-height:600px; opacity:1; margin-top:14px; }}
.expand-block {{ margin-bottom:14px; }}
.expand-title {{ font-family:var(--mono); font-size:10px; font-weight:600; color:var(--text2); text-transform:uppercase; letter-spacing:1px; margin-bottom:8px; padding-bottom:4px; border-bottom:1px solid var(--border); }}

/* Holdings table */
.holdings-table {{ width:100%; border-collapse:collapse; font-family:var(--mono); font-size:10px; }}
.holdings-table th {{ text-align:left; color:var(--text3); font-size:8px; text-transform:uppercase; letter-spacing:0.8px; padding:4px 6px; border-bottom:1px solid var(--border); }}
.holdings-table td {{ padding:5px 6px; border-bottom:1px solid rgba(255,255,255,0.03); }}
.h-sym {{ color:#fff; font-weight:600; }}
.h-name {{ color:var(--text2); }}
.h-mcap {{ color:var(--text2); text-align:right; }}
.h-ytd {{ text-align:right; font-weight:600; }}
.h-ytd.positive {{ color:var(--green); }}
.h-ytd.negative {{ color:var(--red); }}

/* Cap breakdown bar */
.cap-bar {{ display:flex; height:22px; border-radius:6px; overflow:hidden; background:var(--bg4); }}
.cap-seg {{ display:flex; align-items:center; justify-content:center; min-width:0; transition:width .3s; }}
.cap-seg span {{ font-family:var(--mono); font-size:8px; font-weight:600; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; padding:0 4px; }}
.cap-seg.mega {{ background:var(--blue); color:#fff; }}
.cap-seg.large {{ background:var(--purple); color:#fff; }}
.cap-seg.mid {{ background:var(--amber); color:#08090d; }}
.cap-legend {{ display:flex; gap:12px; margin-top:6px; }}
.cap-l {{ font-family:var(--mono); font-size:9px; color:var(--text3); }}
.mega-l {{ color:var(--blue); }}
.large-l {{ color:var(--purple); }}
.mid-l {{ color:var(--amber); }}

/* 52-week range */
.range-track {{ position:relative; height:8px; background:linear-gradient(90deg,var(--red),var(--amber),var(--green)); border-radius:4px; margin:12px 0 4px; }}
.range-fill {{ height:100%; border-radius:4px; }}
.range-marker {{ position:absolute; top:-6px; width:3px; height:20px; background:#fff; border-radius:2px; transform:translateX(-50%); box-shadow:0 0 8px rgba(255,255,255,0.4); }}
.marker-label {{ position:absolute; top:-20px; left:50%; transform:translateX(-50%); font-family:var(--mono); font-size:9px; font-weight:700; color:#fff; white-space:nowrap; background:var(--bg4); padding:1px 6px; border-radius:3px; }}
.range-labels {{ display:flex; justify-content:space-between; font-family:var(--mono); font-size:9px; color:var(--text3); }}

/* ── Explainer Box ───────────────────────────────── */
.explainer {{ background:var(--bg2); border:1px solid var(--border); border-radius:14px; padding:22px 26px; margin-top:24px; position:relative; overflow:hidden; }}
.explainer::before {{ content:''; position:absolute; top:0; left:0; right:0; height:2px; background:linear-gradient(90deg,transparent,var(--amber),transparent); opacity:.4; }}
.explainer-toggle {{ font-family:var(--mono); font-size:12px; font-weight:700; color:#fff; cursor:pointer; display:flex; align-items:center; gap:8px; }}
.explainer-toggle::after {{ content:'▸'; transition:transform .2s; font-size:10px; }}
.explainer.open .explainer-toggle::after {{ transform:rotate(90deg); }}
.explainer-body {{ max-height:0; overflow:hidden; transition:max-height .35s ease; }}
.explainer.open .explainer-body {{ max-height:800px; }}
.explainer-content {{ padding-top:14px; }}
.explainer-content h4 {{ font-family:var(--mono); font-size:11px; color:var(--amber); margin:12px 0 4px; }}
.explainer-content h4:first-child {{ margin-top:0; }}
.explainer-content p {{ font-size:12px; color:var(--text2); line-height:1.7; margin-bottom:8px; }}
.explainer-content .term {{ color:var(--green); font-weight:600; }}

/* ── Animations ──────────────────────────────────── */
.fade-in {{ opacity:0; transform:translateY(20px); transition:opacity .5s ease, transform .5s ease; }}
.fade-in.visible {{ opacity:1; transform:translateY(0); }}

/* ── Footer ──────────────────────────────────────── */
.footer {{ text-align:center; margin-top:40px; padding:20px; font-family:var(--mono); font-size:9px; color:var(--text3); line-height:1.8; }}
.footer a {{ color:var(--blue); text-decoration:none; }}
.footer a:hover {{ text-decoration:underline; }}

/* ── Back link ───────────────────────────────────── */
.back-link {{ display:inline-block; font-family:var(--mono); font-size:10px; color:var(--text3); text-decoration:none; margin-bottom:16px; padding:5px 12px; border:1px solid var(--border); border-radius:6px; transition:all .15s; }}
.back-link:hover {{ color:var(--text); border-color:var(--border2); }}

/* ── Scrollbar ───────────────────────────────────── */
::-webkit-scrollbar {{ width:6px; }}
::-webkit-scrollbar-track {{ background:transparent; }}
::-webkit-scrollbar-thumb {{ background:var(--border2); border-radius:3px; }}
</style>
</head>
<body>
<div class="page">

  <a href="../index.html" class="back-link">← Dashboard</a>

  <div class="header fade-in">
    <div class="header-top">
      <div>
        <div class="title">S&P 500 Sector Report</div>
        <div class="subtitle">All 11 GICS sectors · Color-coded by YTD performance</div>
      </div>
      <div class="gen-badge">Updated {gen_date}</div>
    </div>
    <div class="idx-strip">
      {pills_html}
    </div>
  </div>

  <div class="controls fade-in">
    <span class="controls-label">Sort by</span>
    <button class="sort-btn active" data-sort="ytd" onclick="sortCards('ytd',this)">YTD Return</button>
    <button class="sort-btn" data-sort="weight" onclick="sortCards('weight',this)">S&P Weight</button>
    <button class="sort-btn" data-sort="pe" onclick="sortCards('pe',this)">P/E Ratio</button>
    <button class="sort-btn" data-sort="div" onclick="sortCards('div',this)">Div Yield</button>
  </div>

  <div class="legend fade-in">
    <span class="legend-label">YTD Performance</span>
    <div style="flex:1">
      <div class="legend-bar"></div>
      <div class="legend-range">
        <span>−20%</span>
        <span>0%</span>
        <span>+20%</span>
      </div>
    </div>
  </div>

  <div class="sector-grid" id="sector-grid">
    {cards_html}
  </div>

  <div class="explainer fade-in" id="explainer">
    <div class="explainer-toggle" onclick="document.getElementById('explainer').classList.toggle('open')">
      📖 New to Sector Investing? Read this
    </div>
    <div class="explainer-body">
      <div class="explainer-content">
        <h4>What is a GICS Sector?</h4>
        <p>The <span class="term">Global Industry Classification Standard (GICS)</span> divides the S&P 500 into 11 sectors. Each sector groups companies in similar industries — for example, Apple and Microsoft are in <span class="term">Technology</span>, while JPMorgan and Visa are in <span class="term">Financials</span>.</p>
        <h4>Reading the Cards</h4>
        <p><span class="term">YTD Return</span> shows how much the sector has gained or lost since January 1st. Green cards = gains, amber/red = losses. <span class="term">S&P Weight</span> shows how much of the total S&P 500 index that sector represents — higher weight = bigger influence on the index.</p>
        <h4>P/E Ratio & Dividend Yield</h4>
        <p><span class="term">P/E (Price-to-Earnings)</span> compares a stock's price to its earnings — lower P/E can mean better value, but growth sectors (like Tech) often have higher P/E. <span class="term">Dividend Yield</span> is the annual dividend payment as a percentage of price — higher yield means more passive income.</p>
        <h4>Market Cap Breakdown</h4>
        <p><span class="term">Mega-cap</span> (&gt;$200B) are the largest companies like Apple and Amazon. <span class="term">Large-cap</span> ($10B-$200B) are well-established companies. <span class="term">Mid-cap</span> (&lt;$10B) are smaller but can offer higher growth potential.</p>
        <h4>Forward Rating</h4>
        <p>A composite score based on momentum, valuation, yield, and price position within the 52-week range. <span class="term">Outperform</span> = strong outlook, <span class="term">Market Perform</span> = average, <span class="term">Underperform</span> = caution.</p>
      </div>
    </div>
  </div>

  <div class="footer">
    Generated {gen_date} · Data from Yahoo Finance<br>
    <a href="https://github.com/nageshnnazare/recos">github.com/nageshnnazare/recos</a> ·
    Not financial advice · For informational purposes only
  </div>

</div>

<script>
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
    if (key === 'pe') return av - bv;
    return bv - av;
  }});

  cards.forEach(c => grid.appendChild(c));
}}

// Scroll-triggered fade-in
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
</html>"""

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
    parser = argparse.ArgumentParser(description="S&P 500 Sector Report Generator")
    parser.add_argument("-o", "--output-dir", default="./sp500_reports", help="Output directory (default: ./sp500_reports)")
    args = parser.parse_args()

    reports_root = args.output_dir
    today_str = datetime.now().strftime("%Y-%m-%d")
    output_dir = os.path.join(reports_root, today_str)
    os.makedirs(output_dir, exist_ok=True)

    removed = cleanup_old_reports(reports_root, keep_days=15)
    if removed:
        print(f"  🧹 Cleaned up {removed} report folder(s) older than 15 days")

    print("=" * 62)
    print("  S&P 500 Sector Report Generator")
    print("  Powered by yfinance · No API Key Required")
    print(f"  Sectors: {len(GICS_SECTORS)}")
    print(f"  Date:    {today_str}")
    print(f"  Output:  {os.path.abspath(output_dir)}/")
    print("=" * 62)
    print()

    # Fetch index YTD
    print("  📊 Fetching index data (S&P 500, NASDAQ, DOW)...")
    index_data = fetch_index_ytd()
    for idx in index_data:
        cls = "🟢" if idx["ytd"] >= 0 else "🔴"
        print(f"    {cls} {idx['label']}: {idx['ytd']:+.2f}% YTD")
    print()

    # Fetch all sector data
    sectors_data = []
    for i, (name, info) in enumerate(GICS_SECTORS.items(), 1):
        print(f"  [{i}/{len(GICS_SECTORS)}] {name}")
        data = fetch_sector_data(name, info)
        if data:
            ytd = data["returns"].get("YTD", 0) or 0
            cls = "🟢" if ytd >= 0 else "🔴"
            print(f"    {cls} YTD: {ytd:+.1f}% | P/E: {_fmt(data.get('pe'), '.1f', 'x')} | Div: {_fmt(data.get('divYield'))}")
            sectors_data.append(data)
        print()

    if not sectors_data:
        print("  ❌ No sector data fetched. Aborting.")
        sys.exit(1)

    # Sort by YTD (best first) for initial render
    sectors_data.sort(key=lambda s: s["returns"].get("YTD", 0) or 0, reverse=True)

    gen_date = datetime.now().strftime("%Y-%m-%d %H:%M")
    print("  📄 Generating HTML report...")
    html = generate_html(sectors_data, index_data, gen_date)

    output_file = os.path.join(output_dir, "SP500_SectorReport.html")
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html)

    root_report = os.path.join(reports_root, "SP500_SectorReport.html")
    shutil.copy2(output_file, root_report)

    file_size = os.path.getsize(output_file) / 1024
    print(f"  ✅ Saved: {output_file} ({file_size:.1f} KB)")
    print(f"  📋 Also at: {root_report}")

    # Summary
    print(f"\n{'=' * 62}")
    print("  SECTOR PERFORMANCE SUMMARY (YTD)")
    print(f"{'=' * 62}")
    for s in sectors_data:
        ytd = s["returns"].get("YTD", 0) or 0
        bar = "█" * max(1, int(abs(ytd) / 2))
        sign = "+" if ytd >= 0 else ""
        cls = "🟢" if ytd >= 0 else "🔴"
        print(f"  {cls} {s['sector']:26s} {s['etf']}  {sign}{ytd:6.1f}%  {bar}")
    print(f"{'=' * 62}\n")


if __name__ == "__main__":
    main()
