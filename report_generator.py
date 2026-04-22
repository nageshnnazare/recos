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
import time
import random
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

    # Quarterly cash flow
    try:
        result["quarterly_cash_flow"] = ticker.quarterly_cash_flow
    except Exception as e:
        print(f"    ⚠ Could not fetch quarterly cash flow: {e}")
        result["quarterly_cash_flow"] = None

    # Annual cash flow
    try:
        result["annual_cash_flow"] = ticker.cash_flow
    except Exception as e:
        print(f"    ⚠ Could not fetch annual cash flow: {e}")
        result["annual_cash_flow"] = None

    # Earnings history (estimated vs actual EPS per quarter)
    try:
        result["earnings_history"] = ticker.earnings_history
    except Exception:
        result["earnings_history"] = None

    # Additional history periods for multi-period returns and charts
    for period_key, period_val in [("hist_5d", "5d"), ("hist_1mo", "1mo"), ("hist_3y", "3y"), ("hist_5y", "5y")]:
        try:
            result[period_key] = ticker.history(period=period_val)
        except Exception:
            result[period_key] = None

    # Intraday 1D at 15-min intervals for the interactive chart
    try:
        result["hist_1d_intra"] = ticker.history(period="1d", interval="15m")
    except Exception:
        result["hist_1d_intra"] = None

    # Holder data
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

    # News
    try:
        result["news"] = ticker.get_news(count=8)
    except Exception:
        result["news"] = None

    # Corporate actions calendar (earnings, dividends)
    try:
        result["calendar"] = ticker.calendar
    except Exception:
        result["calendar"] = None

    result["ticker_obj"] = ticker

    # Enrich with Screener.in data (fallback for missing yfinance fields)
    try:
        screener = fetch_screener_data(ticker_symbol)
        result["screener"] = screener
        if screener:
            info = result["info"]
            # Backfill ratios that yfinance doesn't provide for many NSE stocks
            if not info.get("trailingPegRatio") and not info.get("pegRatio") and screener.get("peg_ratio"):
                info["pegRatio"] = screener["peg_ratio"]
            if not info.get("returnOnAssets") and screener.get("roa"):
                info["returnOnAssets"] = screener["roa"]
            if not info.get("currentRatio") and screener.get("current_ratio"):
                info["currentRatio"] = screener["current_ratio"]
            if not info.get("operatingMargins") and screener.get("opm") is not None:
                info["operatingMargins"] = screener["opm"] / 100
            if screener.get("roce"):
                info["_roce"] = screener["roce"]
    except Exception as e:
        print(f"    ⚠ Screener.in fallback failed: {e}")
        result["screener"] = None

    # Fetch industry peers from Screener.in
    try:
        screener = result.get("screener") or {}
        industry_url = screener.get("industry_url", "")
        if industry_url:
            peers, peers_page_url = fetch_industry_peers(industry_url, ticker_symbol)
            result["peers"] = peers
            result["peers_page_url"] = peers_page_url
            result["industry_name"] = screener.get("industry_name", "")
        else:
            result["peers"] = []
            result["peers_page_url"] = ""
            result["industry_name"] = ""
    except Exception as e:
        print(f"    ⚠ Peer fetch failed: {e}")
        result["peers"] = []
        result["peers_page_url"] = ""
        result["industry_name"] = ""

    return result


def _screener_get(url, headers, max_retries=4):
    """HTTP GET with exponential backoff for Screener.in rate-limiting / SSL errors."""
    import requests as _req
    for attempt in range(max_retries):
        try:
            resp = _req.get(url, headers=headers, timeout=15)
            if resp.status_code == 429:
                wait = (2 ** attempt) + random.uniform(1, 3)
                print(f"    ⏳ Screener.in 429 — backing off {wait:.1f}s (attempt {attempt+1})")
                time.sleep(wait)
                continue
            return resp
        except (_req.exceptions.SSLError, _req.exceptions.ConnectionError) as e:
            wait = (2 ** attempt) + random.uniform(1, 3)
            if attempt < max_retries - 1:
                print(f"    ⏳ Screener.in {type(e).__name__} — retry in {wait:.1f}s (attempt {attempt+1})")
                time.sleep(wait)
            else:
                raise
    return None


def fetch_screener_data(ticker_symbol):
    """Scrape Screener.in for fundamental ratios and shareholding data."""
    import requests
    from bs4 import BeautifulSoup

    url = f"https://www.screener.in/company/{ticker_symbol}/consolidated/"
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"}

    resp = _screener_get(url, headers)
    if resp is None:
        return None
    if resp.status_code == 404:
        url = f"https://www.screener.in/company/{ticker_symbol}/"
        resp = _screener_get(url, headers)
    if resp is None or resp.status_code != 200:
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    result = {}

    # ── Top ratios (P/E, ROE, ROCE, Dividend Yield, etc.) ──
    for li in soup.select("#top-ratios li"):
        name_el = li.select_one(".name")
        val_el = li.select_one(".value, .number")
        if not name_el:
            continue
        name = name_el.text.strip().lower()
        raw = val_el.text.strip().replace("₹", "").replace(",", "").replace("Cr.", "").replace("%", "").strip() if val_el else ""
        try:
            val = float(raw)
        except (ValueError, TypeError):
            continue
        if "stock p/e" in name:
            result["pe"] = val
        elif "roe" in name and "roce" not in name:
            result["roe"] = val
        elif "roce" in name:
            result["roce"] = val
        elif "dividend yield" in name:
            result["dividend_yield"] = val

    # ── P&L table: OPM %, Net Profit, EPS ──
    pl_section = soup.find("h2", string=lambda x: x and "profit" in x.lower() if x else False)
    if pl_section:
        table = pl_section.find_next("table")
        if table:
            for row in table.select("tr"):
                cells = [c.text.strip() for c in row.select("th, td")]
                if not cells:
                    continue
                label = cells[0].lower()
                last_val = cells[-1].replace(",", "").replace("%", "").strip() if len(cells) > 1 else ""
                try:
                    num = float(last_val)
                except (ValueError, TypeError):
                    num = None
                if "opm" in label and num is not None:
                    result["opm"] = num
                elif label.startswith("net profit") and num is not None:
                    result["net_profit_cr"] = num
                elif "eps" in label and num is not None:
                    result["eps"] = num

    # ── Ratios table: ROCE historical ──
    ratio_section = soup.find("h2", string=lambda x: x and "ratio" in x.lower() if x else False)
    if ratio_section:
        table = ratio_section.find_next("table")
        if table:
            for row in table.select("tr"):
                cells = [c.text.strip() for c in row.select("th, td")]
                if cells and "roce" in cells[0].lower():
                    vals = [c.replace("%", "").strip() for c in cells[1:] if c.strip()]
                    try:
                        result["roce_history"] = [float(v) for v in vals if v]
                    except ValueError:
                        pass

    # ── Balance sheet: compute Current Ratio if possible ──
    bs_section = soup.find("h2", string=lambda x: x and "balance sheet" in x.lower() if x else False)
    if bs_section:
        table = bs_section.find_next("table")
        if table:
            bs_data = {}
            for row in table.select("tr"):
                cells = [c.text.strip() for c in row.select("th, td")]
                if len(cells) > 1:
                    label = cells[0].lower().replace("\xa0", " ").strip()
                    last_val = cells[-1].replace(",", "").strip()
                    try:
                        bs_data[label] = float(last_val)
                    except (ValueError, TypeError):
                        pass
            total_assets = bs_data.get("total assets")
            if result.get("net_profit_cr") and total_assets and total_assets > 0:
                result["roa"] = result["net_profit_cr"] / total_assets

    # ── PEG ratio: P/E ÷ earnings growth ──
    growth_sections = soup.select(".ranges-table")
    for section in growth_sections:
        text = section.get_text()
        if "Compounded Profit Growth" in text:
            items = section.select("li, tr")
            for item in items:
                t = item.get_text()
                if "3 Years" in t or "3Years" in t:
                    pct = t.split(":")[-1].strip().replace("%", "")
                    try:
                        growth_3y = float(pct)
                        if result.get("pe") and growth_3y > 0:
                            result["peg_ratio"] = result["pe"] / growth_3y
                    except (ValueError, TypeError):
                        pass
                    break

    # ── Industry peer URL from section#peers breadcrumb ──
    peer_section = soup.select_one("section#peers")
    if peer_section:
        industry_links = peer_section.select('p.sub a[href*="/market/"]')
        if industry_links:
            last_link = industry_links[-1]
            result["industry_url"] = last_link.get("href", "")
            result["industry_name"] = last_link.text.strip()

    # ── Shareholding pattern (QoQ with Promoter, FII, DII, Public) ──
    sh_section = soup.find("h2", string=lambda x: x and "shareholding" in x.lower() if x else False)
    if sh_section:
        table = sh_section.find_next("table")
        if table:
            sh_hdrs = [th.text.strip() for th in table.select("tr")[0].select("th, td")]
            sh_data = []
            for row in table.select("tr")[1:]:
                cells = [c.text.strip().replace("\xa0", " ") for c in row.select("th, td")]
                if len(cells) >= 2:
                    category = cells[0].replace("+", "").strip()
                    values = cells[1:]
                    sh_data.append({"category": category, "values": values})
            result["shareholding_headers"] = sh_hdrs[1:]
            result["shareholding_rows"] = sh_data

    # ── About / Business Description ──
    about_el = soup.select_one(".company-profile .about p, .about p")
    if about_el:
        result["about"] = about_el.get_text(strip=True)

    # ── Pros & Cons ──
    for section_cls, key in [("pros", "pros"), ("cons", "cons")]:
        ul = soup.select_one(f".{section_cls} ul")
        if ul:
            result[key] = [li.get_text(strip=True) for li in ul.select("li") if li.get_text(strip=True)]

    # ── Full P&L Statement table ──
    def _scrape_financial_table(heading_text, section_key):
        h = soup.find("h2", string=lambda x: x and heading_text in x.lower() if x else False)
        if not h:
            return None, None
        table = h.find_next("table")
        if not table:
            return None, None
        head_row = table.select("tr")[0]
        headers = [c.text.strip() for c in head_row.select("th, td")]
        rows = []
        for tr in table.select("tr")[1:]:
            tds = tr.select("th, td")
            cells = [c.text.strip().replace("\xa0", " ") for c in tds]
            if not cells or not any(c.strip() for c in cells):
                continue
            has_btn = bool(tds[0].select_one("button")) if tds else False
            parent_name = cells[0].replace("+", "").strip() if has_btn else None
            rows.append({"cells": cells, "expandable": parent_name})
        return headers, rows

    # ── Get company-id for sub-row API calls ──
    company_info_el = soup.select_one("#company-info")
    company_id = company_info_el.get("data-company-id") if company_info_el else None
    is_consolidated = company_info_el.has_attr("data-consolidated") if company_info_el else False

    def _fetch_sub_rows(parent_name, section_key, headers_list):
        if not company_id:
            return []
        api_url = f"https://www.screener.in/api/company/{company_id}/schedules/?parent={parent_name}&section={section_key}"
        if is_consolidated:
            api_url += "&consolidated"
        try:
            import json as _json
            r = requests.get(api_url, headers=headers, timeout=8)
            if r.status_code != 200:
                return []
            data = _json.loads(r.text)
            sub_rows = []
            date_cols = headers_list[1:]
            if isinstance(data, dict):
                for label, vals in data.items():
                    if isinstance(vals, dict) and not vals.get("isExpandable"):
                        row_cells = [label]
                        for dc in date_cols:
                            row_cells.append(str(vals.get(dc, "")))
                        sub_rows.append({"cells": row_cells, "expandable": None, "is_sub": True})
            return sub_rows
        except Exception:
            return []

    pl_headers, pl_rows_raw = _scrape_financial_table("profit", "profit-loss")
    if pl_headers and pl_rows_raw:
        pl_rows = []
        for row in pl_rows_raw:
            pl_rows.append(row)
            if row["expandable"]:
                subs = _fetch_sub_rows(row["expandable"], "profit-loss", pl_headers)
                for s in subs:
                    pl_rows.append(s)
        result["pl_headers"] = pl_headers
        result["pl_rows"] = pl_rows

    bs_headers, bs_rows_raw = _scrape_financial_table("balance sheet", "balance-sheet")
    if bs_headers and bs_rows_raw:
        bs_rows = []
        for row in bs_rows_raw:
            bs_rows.append(row)
            if row["expandable"]:
                subs = _fetch_sub_rows(row["expandable"], "balance-sheet", bs_headers)
                for s in subs:
                    bs_rows.append(s)
        result["bs_headers"] = bs_headers
        result["bs_rows"] = bs_rows

    # ── Cash Flow Statement table ──
    cf_headers, cf_rows_raw = _scrape_financial_table("cash flow", "cash-flow")
    if cf_headers and cf_rows_raw:
        cf_rows = []
        for row in cf_rows_raw:
            cf_rows.append(row)
            if row["expandable"]:
                subs = _fetch_sub_rows(row["expandable"], "cash-flow", cf_headers)
                for s in subs:
                    cf_rows.append(s)
        result["cf_headers"] = cf_headers
        result["cf_rows"] = cf_rows

    # ── Quarterly Results table ──
    qr_headers, qr_rows_raw = _scrape_financial_table("quarterly", "quarters")
    if qr_headers and qr_rows_raw:
        qr_rows = []
        for row in qr_rows_raw:
            qr_rows.append(row)
            if row["expandable"]:
                subs = _fetch_sub_rows(row["expandable"], "quarters", qr_headers)
                for s in subs:
                    qr_rows.append(s)
        result["qr_headers"] = qr_headers
        result["qr_rows"] = qr_rows

    # ── Ratios table (ROCE, ROE, Debt/Equity, etc.) ──
    rt_headers, rt_rows_raw = _scrape_financial_table("ratio", "ratios")
    if rt_headers and rt_rows_raw:
        result["rt_headers"] = rt_headers
        result["rt_rows"] = rt_rows_raw

    # ── Compounded Growth Rates ──
    growth_data = {}
    for section in soup.select(".ranges-table"):
        items = section.select("li")
        if not items:
            continue
        parent_heading = section.find_previous(["h2", "h3", "h4"])
        parent_text = parent_heading.get_text(strip=True) if parent_heading else ""
        table_items = []
        for li in items:
            t = li.get_text(strip=True)
            parts = t.split(":")
            if len(parts) == 2:
                table_items.append((parts[0].strip(), parts[1].strip()))
        if table_items:
            growth_data[parent_text] = table_items
    if growth_data:
        result["growth_rates"] = growth_data

    # ── Extract EPS, Sales, and Book Value series for valuation charts ──
    pl_rows_data = result.get("pl_rows", [])
    if pl_rows_data:
        for row in pl_rows_data:
            c = row["cells"]
            if not c:
                continue
            label = c[0].lower().replace("+", "").strip()
            if label.startswith("eps") and "eps_series" not in result:
                try:
                    result["eps_series"] = {
                        "headers": pl_headers[1:],
                        "values": [_try_float(v) for v in c[1:]]
                    }
                except Exception:
                    pass
            if label.startswith("sales") and "sales_series" not in result:
                try:
                    result["sales_series"] = {
                        "headers": pl_headers[1:],
                        "values": [_try_float(v) for v in c[1:]]
                    }
                except Exception:
                    pass

    bs_rows_data = result.get("bs_rows", [])
    if bs_rows_data:
        for row in bs_rows_data:
            c = row["cells"]
            label = c[0].lower().replace("+", "").strip() if c else ""
            if "equity capital" in label:
                result["_equity_capital_row"] = c[1:]
            if "reserves" in label:
                result["_reserves_row"] = c[1:]

        eq_row = result.get("_equity_capital_row", [])
        res_row = result.get("_reserves_row", [])
        if eq_row and res_row and len(eq_row) == len(res_row):
            bv_list = []
            for i in range(len(eq_row)):
                ec = _try_float(eq_row[i])
                rs = _try_float(res_row[i])
                if ec is not None and rs is not None and ec > 0:
                    face_value = 10
                    shares_cr = ec / face_value
                    bv = (ec + rs) / shares_cr if shares_cr > 0 else None
                    bv_list.append(bv)
                else:
                    bv_list.append(None)
            result["bv_series"] = {
                "headers": bs_headers[1:],
                "values": bv_list
            }

    return result


def _try_float(s):
    """Attempt to parse a string as float, return None on failure."""
    if s is None:
        return None
    s = str(s).replace(",", "").replace("%", "").strip()
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def fetch_industry_peers(industry_url, current_ticker, limit=8):
    """Fetch peer comparison table from Screener.in industry page."""
    from bs4 import BeautifulSoup

    if not industry_url:
        return [], ""
    base = "https://www.screener.in"
    url = base + industry_url if industry_url.startswith("/") else industry_url
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

    try:
        resp = _screener_get(url, headers)
        if resp is None or resp.status_code != 200:
            return [], ""
    except Exception:
        return [], ""

    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.select_one("table")
    if not table:
        return [], ""

    peers = []
    current_upper = current_ticker.upper()
    for row in table.select("tbody tr"):
        cells = [c.text.strip().replace("\n", " ").replace(",", "") for c in row.select("td")]
        if len(cells) < 10:
            continue
        link = row.select_one("td a")
        href = link.get("href", "") if link else ""
        # Extract ticker from href like /company/BEL/consolidated/
        ticker_from_href = href.split("/company/")[-1].split("/")[0].upper() if "/company/" in href else ""

        try:
            name = cells[1].strip()
            cmp = float(cells[2]) if cells[2] else None
            pe = float(cells[3]) if cells[3] else None
            mcap = float(cells[4]) if cells[4] else None
            div_yield = float(cells[5]) if cells[5] else None
            np_qtr = float(cells[6]) if cells[6] else None
            qtr_profit_var = float(cells[7]) if cells[7] else None
            sales_qtr = float(cells[8]) if cells[8] else None
            qtr_sales_var = float(cells[9]) if cells[9] else None
            roce = float(cells[10]) if len(cells) > 10 and cells[10] else None
        except (ValueError, TypeError, IndexError):
            continue

        is_self = ticker_from_href == current_upper
        peers.append({
            "name": name, "ticker": ticker_from_href, "cmp": cmp, "pe": pe,
            "mcap": mcap, "div_yield": div_yield, "roce": roce,
            "qtr_profit_var": qtr_profit_var, "qtr_sales_var": qtr_sales_var,
            "is_self": is_self, "screener_url": base + href if href else "",
        })

    # Compute techno-fundamental composite score for ranking
    if peers:
        pe_vals = [p["pe"] for p in peers if p["pe"] and p["pe"] > 0]
        roce_vals = [p["roce"] for p in peers if p["roce"] is not None]
        growth_vals = [p["qtr_profit_var"] for p in peers if p["qtr_profit_var"] is not None]
        mcap_vals = [p["mcap"] for p in peers if p["mcap"] is not None]

        def _norm(val, vals, invert=False):
            if val is None or not vals:
                return 0.5
            mn, mx = min(vals), max(vals)
            if mx == mn:
                return 0.5
            n = (val - mn) / (mx - mn)
            return (1 - n) if invert else n

        for p in peers:
            p["tf_score"] = (
                _norm(p["pe"], pe_vals, invert=True) * 30 +
                _norm(p["roce"], roce_vals) * 30 +
                _norm(p["qtr_profit_var"], growth_vals) * 20 +
                _norm(p["mcap"], mcap_vals) * 20
            )

        peers.sort(key=lambda x: x.get("tf_score", 0), reverse=True)

    # Keep top N but always include self
    self_peer = next((p for p in peers if p["is_self"]), None)
    top_peers = [p for p in peers if not p["is_self"]][:limit]
    if self_peer:
        top_peers.append(self_peer)
        top_peers.sort(key=lambda x: x.get("tf_score", 0), reverse=True)

    return top_peers, url


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
        score += 6       # oversold — potential bounce
    elif rsi < 45:
        score += 3       # mildly oversold
    elif rsi <= 65:
        score += 1       # neutral
    elif rsi <= 75:
        score -= 1       # getting warm
    else:
        score -= 3       # overbought risk

    # Price vs 200 DMA
    if len(closes_1y) >= 200:
        dma200 = closes_1y.rolling(200).mean().iloc[-1]
        last = closes_1y.iloc[-1]
        if dma200 and dma200 > 0:
            dist = (last - dma200) / dma200
            if dist > 0.05:
                score += 3    # comfortably above — uptrend
            elif dist > -0.02:
                score += 1    # near 200 DMA
            elif dist > -0.10:
                score -= 1    # below but not far
            else:
                score -= 3    # deep below — downtrend

    closes_6m = hist_6m["Close"].dropna() if hist_6m is not None and not hist_6m.empty else closes_1y.tail(130)

    # MACD
    if len(closes_6m) >= 35:
        macd_line, sig_line = _compute_macd(closes_6m)
        if not macd_line.empty and not sig_line.empty:
            macd_val = macd_line.iloc[-1]
            sig_val = sig_line.iloc[-1]
            if macd_val > sig_val and macd_val > 0:
                score += 4     # bullish crossover in positive territory
            elif macd_val > sig_val:
                score += 2     # bullish but below zero
            elif macd_val < sig_val and macd_val < 0:
                score -= 4     # bearish in negative territory
            else:
                score -= 1     # bearish but above zero

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

    # Volume trend — 20-day avg vs 50-day avg on up-days
    if hist_6m is not None and not hist_6m.empty and len(hist_6m) >= 50:
        aligned = hist_6m[["Close", "Volume"]].dropna()
        if len(aligned) >= 50:
            vol = aligned["Volume"]
            close = aligned["Close"]
            vol_20 = vol.tail(20).mean()
            vol_50 = vol.tail(50).mean()
            price_chg = close.diff().tail(20)
            vol_tail = vol.tail(20)
            up_mask = price_chg > 0
            dn_mask = price_chg < 0
            up_vol = vol_tail[up_mask].mean() if up_mask.any() else 0
            dn_vol = vol_tail[dn_mask].mean() if dn_mask.any() else 0
            if vol_20 > vol_50 * 1.1 and up_vol > dn_vol:
                score += 2    # rising volume on up-days
            elif vol_20 < vol_50 * 0.8:
                score -= 1    # declining participation

    return max(0, min(25, score))


# ─────────────────────────────────────────────────────────────────────────────
# RISK SCORE CALCULATION (Generic — works for any stock)
# ─────────────────────────────────────────────────────────────────────────────

def calculate_risk_scores(data):
    """
    Calculate risk scores based on 25/25/25/25 weighting with sector-specific thresholds.
    Pillars: Valuation / Financial Health / Growth / Technical.
    Higher score = Lower risk = Better.
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
        if pe < pe_cheap:
            val_score += 8
        elif pe < pe_fair:
            val_score += 5
        elif pe < pe_exp:
            val_score += 2
        elif pe < pe_exp * 1.5:
            val_score -= 1
        elif pe < pe_exp * 2.5:
            val_score -= 4
        else:
            val_score -= 7

    if pb:
        if pb < pb_cheap:
            val_score += 4
        elif pb < pb_fair:
            val_score += 2
        elif pb < pb_exp:
            val_score += 0
        elif pb < pb_exp * 2:
            val_score -= 2
        else:
            val_score -= 4

    target = safe_get(info, "targetMeanPrice")
    current = safe_get(info, "currentPrice", safe_get(info, "regularMarketPrice"))
    if target and current and current > 0:
        upside = (target - current) / current * 100
        if upside > 30:
            val_score += 4
        elif upside > 15:
            val_score += 3
        elif upside > 5:
            val_score += 1
        elif upside > 0:
            val_score += 0
        elif upside > -10:
            val_score -= 2
        else:
            val_score -= 4

    val_score = max(0, min(25, val_score))

    # ── FINANCIAL HEALTH SCORE /25 ──
    fin_score = 9

    roe = calculate_roe_manual(data)
    if roe:
        if roe > roe_good * 1.4:
            fin_score += 6
        elif roe > roe_good:
            fin_score += 4
        elif roe > roe_mod:
            fin_score += 1
        elif roe > 0:
            fin_score += 0
        else:
            fin_score -= 5

    profit_margin = safe_get(info, "profitMargins")
    if profit_margin:
        if profit_margin > margin_good * 1.3:
            fin_score += 5
        elif profit_margin > margin_mod:
            fin_score += 2
        elif profit_margin > 0:
            fin_score += 0
        else:
            fin_score -= 4

    rev_growth = safe_get(info, "revenueGrowth")
    if rev_growth:
        if rev_growth > rg_strong * 1.5:
            fin_score += 4
        elif rev_growth > rg_strong:
            fin_score += 2
        elif rev_growth > rg_mod:
            fin_score += 1
        elif rev_growth > 0:
            fin_score += 0
        else:
            fin_score -= 3

    debt_equity = safe_get(info, "debtToEquity")
    if debt_equity is not None:
        if debt_equity < de_ok:
            fin_score += 2
        elif debt_equity < de_high:
            fin_score += 0
        elif debt_equity < de_high * 1.5:
            fin_score -= 2
        else:
            fin_score -= 4

    fin_score = max(0, min(25, fin_score))

    # ── GROWTH SCORE /25 ──
    growth_score = 9

    if rev_growth:
        if rev_growth > rg_strong * 2:
            growth_score += 7
        elif rev_growth > rg_strong:
            growth_score += 4
        elif rev_growth > rg_mod:
            growth_score += 2
        elif rev_growth > 0:
            growth_score += 0
        else:
            growth_score -= 4

    earnings_growth = safe_get(info, "earningsGrowth")
    if earnings_growth:
        if earnings_growth > eg_strong:
            earnings_bump = 5
        elif earnings_growth > eg_mod:
            earnings_bump = 3
        elif earnings_growth > 0:
            earnings_bump = 1
        else:
            earnings_bump = -3
        growth_score += earnings_bump

    beta = safe_get(info, "beta")
    if beta:
        if beta < 0.8:
            growth_score += 2
        elif beta < 1.2:
            growth_score += 1
        else:
            growth_score -= 1

    growth_score = max(0, min(25, growth_score))

    # ── TECHNICAL SCORE /25 ──
    tech_score = _technical_score(data)

    composite = val_score + fin_score + growth_score + tech_score

    return {
        "valuation": val_score,
        "financial": fin_score,
        "growth": growth_score,
        "technical": tech_score,
        "composite": composite,
    }


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

    pad_left, pad_right, pad_top, pad_bottom = 60, 70, 20, 40
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
    dma_last_val = None
    for i in range(n):
        if dma200_display[i] is not None:
            x = pad_left + (i + 0.5) * gap
            y = y_pos(dma200_display[i])
            dma_points.append(f"{x:.1f},{y:.1f}")
            dma_last_val = dma200_display[i]
    if dma_points:
        svg += f'  <polyline points="{" ".join(dma_points)}" fill="none" stroke="#f5a623" stroke-width="1.5" opacity="0.5" stroke-dasharray="6,3"/>\n'
        if dma_last_val is not None:
            lx = pad_left + (n - 0.5) * gap + 4
            ly = y_pos(dma_last_val)
            svg += f'  <text x="{lx:.1f}" y="{ly + 3:.1f}" font-family="Fira Code,monospace" font-size="8" font-weight="600" fill="#f5a623">₹{dma_last_val:,.0f}</text>\n'

    # 50 EMA line
    ema_points = []
    ema_last_val = None
    for i in range(n):
        if ema50_display[i] is not None:
            x = pad_left + (i + 0.5) * gap
            y = y_pos(ema50_display[i])
            ema_points.append(f"{x:.1f},{y:.1f}")
            ema_last_val = ema50_display[i]
    if ema_points:
        svg += f'  <polyline points="{" ".join(ema_points)}" fill="none" stroke="#9b7fff" stroke-width="1.5" opacity="0.7"/>\n'
        if ema_last_val is not None:
            lx = pad_left + (n - 0.5) * gap + 4
            ly = y_pos(ema_last_val)
            svg += f'  <text x="{lx:.1f}" y="{ly + 3:.1f}" font-family="Fira Code,monospace" font-size="8" font-weight="600" fill="#9b7fff">₹{ema_last_val:,.0f}</text>\n'

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
    ema_legend = f"── 50 EMA (₹{ema_last_val:,.0f})" if ema_last_val else "── 50 EMA"
    dma_legend = f"╌╌ 200 DMA (₹{dma_last_val:,.0f})" if dma_last_val else "╌╌ 200 DMA"
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

def _get_fiscal_quarter(dt):
    """Return Indian fiscal quarter label from a datetime."""
    month, year = dt.month, dt.year
    if month in [1, 2, 3]:
        return f"Q4 FY{year % 100}"
    elif month in [4, 5, 6]:
        return f"Q1 FY{(year + 1) % 100}"
    elif month in [7, 8, 9]:
        return f"Q2 FY{(year + 1) % 100}"
    return f"Q3 FY{(year + 1) % 100}"


def _safe_df_value(df, col, key_list):
    """Try multiple row keys in a DataFrame column, return value in Crores or None."""
    for key in key_list:
        if key in df.index:
            val = df.loc[key, col]
            if val is not None and not (isinstance(val, float) and math.isnan(val)):
                return val / 1e7
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

                rev = _safe_df_value(qi, col, ["Total Revenue", "Operating Revenue", "Revenue"])
                profit = _safe_df_value(qi, col, ["Net Income", "Net Income Common Stockholders", "Net Income From Continuing Operations"])
                ebitda = _safe_df_value(qi, col, ["EBITDA", "Normalized EBITDA"])

                ebitda_margin = None
                if ebitda and rev and rev > 0:
                    ebitda_margin = (ebitda / rev) * 100

                op_cf = None
                if qcf is not None and not qcf.empty and col in qcf.columns:
                    op_cf = _safe_df_value(qcf, col, ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities", "Free Cash Flow"])

                rows.append({
                    "quarter": _get_fiscal_quarter(dt),
                    "date": dt,
                    "revenue_cr": rev,
                    "profit_cr": profit,
                    "ebitda_margin": ebitda_margin,
                    "op_cash_flow_cr": op_cf,
                })
            except Exception:
                continue

    rows.sort(key=lambda x: x.get("date", datetime.min))

    for i in range(len(rows)):
        prev = rows[i - 1] if i > 0 else None
        rows[i]["rev_qoq_pct"] = _pct_change(rows[i]["revenue_cr"], prev["revenue_cr"] if prev else None)
        rows[i]["profit_qoq_pct"] = _pct_change(rows[i]["profit_cr"], prev["profit_cr"] if prev else None)

    return rows


def _pct_change(current, previous):
    """Compute % change; returns None if either value is missing or previous is zero."""
    if current is None or previous is None or previous == 0:
        return None
    return ((current - previous) / abs(previous)) * 100


def extract_annual_data(data):
    """Extract annual revenue, net profit, operating cash flow with YoY % changes."""
    fi = data.get("financials")
    acf = data.get("annual_cash_flow")
    rows = []

    if fi is not None and not fi.empty:
        for col in fi.columns[:5]:
            try:
                dt = col.to_pydatetime() if hasattr(col, 'to_pydatetime') else col
                fy_label = f"FY{dt.year % 100}" if dt.month <= 3 else f"FY{(dt.year + 1) % 100}"

                rev = _safe_df_value(fi, col, ["Total Revenue", "Operating Revenue", "Revenue"])
                profit = _safe_df_value(fi, col, ["Net Income", "Net Income Common Stockholders", "Diluted NI Availto Com Stockholders"])

                op_cf = None
                if acf is not None and not acf.empty and col in acf.columns:
                    op_cf = _safe_df_value(acf, col, ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities", "Free Cash Flow"])

                rows.append({"fy": fy_label, "date": dt, "revenue_cr": rev, "profit_cr": profit, "op_cash_flow_cr": op_cf})
            except Exception:
                continue

    rows.sort(key=lambda x: x.get("date", datetime.min))

    for i in range(len(rows)):
        prev = rows[i - 1] if i > 0 else None
        rows[i]["rev_yoy_pct"] = _pct_change(rows[i]["revenue_cr"], prev["revenue_cr"] if prev else None)
        rows[i]["profit_yoy_pct"] = _pct_change(rows[i]["profit_cr"], prev["profit_cr"] if prev else None)
        rows[i]["cf_yoy_pct"] = _pct_change(rows[i]["op_cash_flow_cr"], prev["op_cash_flow_cr"] if prev else None)

    return rows


def extract_holder_data(data):
    """Parse major_holders and top institutional/MF holders from yfinance."""
    mh = data.get("major_holders")
    ih = data.get("institutional_holders")
    mfh = data.get("mutualfund_holders")

    summary = {}
    if mh is not None and not mh.empty:
        try:
            for idx, row in mh.iterrows():
                # yfinance major_holders: index is the breakdown key, columns may be
                # ["Value"] or [0, 1] depending on version. Try both layouts.
                label = str(idx).lower()
                if len(row) > 1:
                    label = str(row.iloc[1]).lower()
                    val = row.iloc[0]
                elif "Value" in row.index:
                    val = row["Value"]
                else:
                    val = row.iloc[0]
                if "count" in label:
                    summary["num_institutions"] = val
                elif "insider" in label:
                    summary["insiders"] = val
                elif "float" in label:
                    summary["float_held"] = val
                elif "institution" in label:
                    summary["institutions"] = val
        except Exception:
            pass

    top_inst = []
    if ih is not None and not ih.empty and len(ih.columns) > 0:
        for _, row in ih.head(5).iterrows():
            try:
                name = str(row.get("Holder", row.iloc[0]) if "Holder" in row.index else row.iloc[0])
                top_inst.append({
                    "name": name,
                    "shares": row.get("Shares", 0),
                    "pct": row.get("pctHeld", row.get("% Out", 0)),
                })
            except Exception:
                continue

    top_mf = []
    if mfh is not None and not mfh.empty and len(mfh.columns) > 0:
        for _, row in mfh.head(5).iterrows():
            try:
                name = str(row.get("Holder", row.iloc[0]) if "Holder" in row.index else row.iloc[0])
                top_mf.append({
                    "name": name,
                    "shares": row.get("Shares", 0),
                    "pct": row.get("pctHeld", row.get("% Out", 0)),
                })
            except Exception:
                continue

    return summary, top_inst, top_mf


def extract_news(data):
    """Parse news items from yfinance into a clean list."""
    raw = data.get("news")
    if not raw:
        return []
    items = []
    for article in raw[:6]:
        try:
            content = article.get("content", article) if isinstance(article, dict) else article
            title = content.get("title", "")
            if not title:
                continue
            provider = content.get("provider", {})
            publisher = provider.get("displayName", "") if isinstance(provider, dict) else str(provider)
            pub_time = content.get("pubDate", content.get("providerPublishTime", ""))
            link = content.get("canonicalUrl", {}).get("url", content.get("link", "")) if isinstance(content.get("canonicalUrl"), dict) else content.get("link", "")

            date_str = ""
            if pub_time:
                try:
                    if isinstance(pub_time, (int, float)):
                        date_str = datetime.fromtimestamp(pub_time).strftime("%b %d, %Y")
                    else:
                        date_str = str(pub_time)[:16]
                except Exception:
                    date_str = str(pub_time)[:16]

            items.append({"title": title, "publisher": publisher, "date_str": date_str, "link": link})
        except Exception:
            continue
    return items


def calculate_returns(data, current_price):
    """Calculate returns across multiple time horizons."""
    info = data.get("info", {})
    prev_close = safe_get(info, "previousClose", safe_get(info, "regularMarketPreviousClose"))
    ret = {}

    ret["1D"] = ((current_price - prev_close) / prev_close * 100) if prev_close and prev_close > 0 else None

    period_map = [("1W", "hist_5d"), ("1M", "hist_1mo"), ("6M", "hist_6m"), ("1Y", "hist_1y"), ("3Y", "hist_3y"), ("5Y", "hist_5y")]
    for label, key in period_map:
        hist = data.get(key)
        if hist is not None and not hist.empty and len(hist) > 1:
            first_close = hist["Close"].iloc[0]
            if first_close and first_close > 0:
                ret[label] = ((current_price - first_close) / first_close) * 100
            else:
                ret[label] = None
        else:
            ret[label] = None

    return ret


def calculate_factor_scores(data, scores, returns):
    """Calculate 5 factor scores (0-10 each) for the radar chart, with reasoning."""
    info = data.get("info", {})
    reasons = {}

    # Momentum: RSI + MACD + trend + returns
    momentum = 5
    mom_parts = []
    r1m = returns.get("1M")
    r6m = returns.get("6M")
    if r1m is not None:
        mom_parts.append(f"1M {r1m:+.1f}%")
        if r1m > 10:
            momentum += 1
        elif r1m < -10:
            momentum -= 1
    if r6m is not None:
        mom_parts.append(f"6M {r6m:+.1f}%")
        if r6m > 20:
            momentum += 1
        elif r6m < -20:
            momentum -= 1

    hist_1y = data.get("hist_1y")
    if hist_1y is not None and not hist_1y.empty and len(hist_1y) >= 30:
        closes = hist_1y["Close"].dropna()
        if len(closes) >= 14:
            rsi_val = _compute_rsi(closes).iloc[-1]
            mom_parts.append(f"RSI {rsi_val:.0f}")
            if rsi_val < 35:
                momentum += 1
            elif rsi_val > 70:
                momentum -= 1
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

    # Sentiment: analyst upside and recommendation key
    sentiment = 5
    sent_parts = []
    target = safe_get(info, "targetMeanPrice")
    current = safe_get(info, "currentPrice", safe_get(info, "regularMarketPrice"))
    if target and current and current > 0:
        upside = (target - current) / current * 100
        sent_parts.append(f"Analyst upside {upside:+.1f}%")
        if upside > 30:
            sentiment += 3
        elif upside > 15:
            sentiment += 2
        elif upside > 5:
            sentiment += 1
        elif upside < -10:
            sentiment -= 2
        elif upside < 0:
            sentiment -= 1
    rec_key = safe_get(info, "recommendationKey", "")
    if rec_key:
        sent_parts.append(f"Rec: {rec_key.replace('_', ' ')}")
    if rec_key in ("strong_buy", "buy"):
        sentiment += 1
    elif rec_key in ("sell", "strong_sell"):
        sentiment -= 1
    reasons["Sentiment"] = ", ".join(sent_parts) if sent_parts else "No analyst data"

    # Value: P/E, P/B, PEG, EV/EBITDA
    value = 5
    val_parts = []
    pe = safe_get(info, "trailingPE")
    pb = safe_get(info, "priceToBook")
    peg = safe_get(info, "trailingPegRatio", safe_get(info, "pegRatio"))
    ev_ebitda = safe_get(info, "enterpriseToEbitda")
    if pe:
        val_parts.append(f"P/E {pe:.1f}")
        if pe < 15:
            value += 2
        elif pe < 25:
            value += 1
        elif pe > 60:
            value -= 2
        elif pe > 40:
            value -= 1
    if pb:
        val_parts.append(f"P/B {pb:.1f}")
        if pb < 2:
            value += 1
        elif pb > 10:
            value -= 1
    if peg:
        val_parts.append(f"PEG {peg:.2f}")
        if peg < 1:
            value += 1
        elif peg > 2:
            value -= 1
    if ev_ebitda:
        val_parts.append(f"EV/EBITDA {ev_ebitda:.1f}")
        if ev_ebitda < 12:
            value += 1
        elif ev_ebitda > 25:
            value -= 1
    reasons["Value"] = ", ".join(val_parts) if val_parts else "No valuation data"

    # Quality: ROE, profit margin, debt/equity, current ratio
    quality = 5
    qual_parts = []
    roe = safe_get(info, "returnOnEquity")
    pm = safe_get(info, "profitMargins")
    de = safe_get(info, "debtToEquity")
    cr = safe_get(info, "currentRatio")
    if roe:
        qual_parts.append(f"ROE {roe*100:.1f}%")
        if roe > 0.25:
            quality += 2
        elif roe > 0.15:
            quality += 1
        elif roe < 0:
            quality -= 2
    if pm:
        qual_parts.append(f"Margin {pm*100:.1f}%")
        if pm > 0.2:
            quality += 1
        elif pm < 0:
            quality -= 2
        elif pm < 0.05:
            quality -= 1
    if de is not None:
        qual_parts.append(f"D/E {de:.0f}")
        if de < 30:
            quality += 1
        elif de > 150:
            quality -= 1
    if cr:
        qual_parts.append(f"CR {cr:.2f}")
        if cr > 1.5:
            quality += 1
        elif cr < 1.0:
            quality -= 1
    reasons["Quality"] = ", ".join(qual_parts) if qual_parts else "No quality data"

    # Low Volatility: beta and price stability
    low_vol = 5
    lv_parts = []
    beta = safe_get(info, "beta")
    if beta:
        lv_parts.append(f"Beta {beta:.2f}")
        if beta < 0.6:
            low_vol += 3
        elif beta < 0.8:
            low_vol += 2
        elif beta < 1.0:
            low_vol += 1
        elif beta > 1.5:
            low_vol -= 3
        elif beta > 1.3:
            low_vol -= 2
        elif beta > 1.1:
            low_vol -= 1
    hist = data.get("hist_1y")
    if hist is not None and not hist.empty and len(hist) > 20:
        daily_returns = hist["Close"].pct_change().dropna()
        if len(daily_returns) > 0:
            vol = daily_returns.std() * (252 ** 0.5)
            lv_parts.append(f"Ann. vol {vol*100:.0f}%")
            if vol < 0.25:
                low_vol += 2
            elif vol < 0.35:
                low_vol += 1
            elif vol > 0.6:
                low_vol -= 2
            elif vol > 0.45:
                low_vol -= 1
    reasons["Low Volatility"] = ", ".join(lv_parts) if lv_parts else "No volatility data"

    factor_scores = {
        "Momentum": max(0, min(10, momentum)),
        "Sentiment": max(0, min(10, sentiment)),
        "Value": max(0, min(10, value)),
        "Quality": max(0, min(10, quality)),
        "Low Volatility": max(0, min(10, low_vol)),
    }
    return factor_scores, reasons


def generate_pe_pb_chart_svg(series, label="P/E", color="#3d9cf5", width=520, height=200):
    """Generate a trend line chart SVG for PE or PB ratio over years."""
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
        short = lb.replace("Mar ", "'").replace("Sep ", "S'") if "Mar" in lb or "Sep" in lb else lb[-4:]
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
    """Generate a radar/spider chart SVG for 5 factor scores with hover tooltips."""
    short_labels = {"Low Volatility": "Low Vol"}
    labels = list(factors.keys())
    values = list(factors.values())
    n = len(labels)
    cx, cy = width / 2, height / 2
    max_r = 130
    if reasons is None:
        reasons = {}

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
        r = max_r * v / 10
        data_points.append(polar(i, r))

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
        if lx < cx - 10:
            anchor = "end"
            lx -= 4
        elif lx > cx + 10:
            anchor = "start"
            lx += 4
        if ly < cy:
            dy = -4
        elif ly > cy:
            dy = 8
        svg += f'  <text x="{lx:.1f}" y="{ly + dy:.1f}" text-anchor="{anchor}" font-family="Fira Code,monospace" font-size="10" fill="#9899a8">{display_label}</text>\n'
        sx, sy = polar(i, max_r + 38)
        if sx < cx - 10:
            sx -= 4
        elif sx > cx + 10:
            sx += 4
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

    # Earnings dates
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
                    badges.append(f'<span class="badge badge-earnings badge-imminent">RESULTS JUST REPORTED: {date_str}</span>')
                elif 0 < days_away <= 7:
                    badges.append(f'<span class="badge badge-earnings badge-imminent">RESULTS IMMINENT: {date_str}</span>')
                elif 0 < days_away <= 30:
                    badges.append(f'<span class="badge badge-earnings">RESULTS: {date_str}</span>')
            except Exception:
                continue

    # Ex-dividend date
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

    # Dividend date
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

    # Use the longest available daily history for accurate MA warm-up
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
        # Drop rows where any OHLCV value is NaN to prevent JS Math.min/max failures
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

        # Pre-compute RSI(14) and MACD for each period
        if len(closes) >= 14:
            import numpy as _np
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
            import numpy as _np
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

    mcap_cr = market_cap / 1e7 if market_cap else 0
    change_color = "#00e5a0" if change >= 0 else "#ff4d6d"
    change_icon = "▲" if change >= 0 else "▼"
    corp_actions_html = _build_corporate_actions_html(data)

    day_range = day_high - day_low if day_high and day_low and day_high > day_low else 0
    day_pct = max(0, min(100, ((current_price - day_low) / day_range * 100))) if day_range > 0 else 50
    w52_range = high_52w - low_52w if high_52w and low_52w and high_52w > low_52w else 0
    w52_pct = max(0, min(100, ((current_price - low_52w) / w52_range * 100))) if w52_range > 0 else 50

    def _range_dot_color(pct):
        if pct <= 30:
            return "#00e5a0"
        elif pct <= 70:
            return "#f5a623"
        else:
            return "#ff4d6d"

    day_dot_color = _range_dot_color(day_pct)
    w52_dot_color = _range_dot_color(w52_pct)
    day_zone = "Oversold" if day_pct <= 30 else ("Overbought" if day_pct >= 70 else "Neutral")
    w52_zone = "Oversold" if w52_pct <= 30 else ("Overbought" if w52_pct >= 70 else "Neutral")

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
    holder_summary, top_inst, top_mf = extract_holder_data(data)
    news_items = extract_news(data)
    returns = calculate_returns(data, current_price)
    factor_scores, factor_reasons = calculate_factor_scores(data, scores, returns)
    spider_svg = generate_spider_chart_svg(factor_scores, factor_reasons)
    roe = calculate_roe_manual(data)

    # ── Screener-sourced sections ──
    screener = data.get("screener") or {}

    about_text = screener.get("about", "")
    pros_list = screener.get("pros", [])
    cons_list = screener.get("cons", [])

    # ── Rich Company Analysis ──
    yf_summary = safe_get(info, "longBusinessSummary", "")
    desc_text = yf_summary or about_text or ""

    rev_growth = safe_get(info, "revenueGrowth", None)
    earn_growth = safe_get(info, "earningsGrowth", None)
    earn_q_growth = safe_get(info, "earningsQuarterlyGrowth", None)
    rec_key = safe_get(info, "recommendationKey", "")
    n_analysts = safe_get(info, "numberOfAnalystOpinions", 0)
    employees = safe_get(info, "fullTimeEmployees", 0)

    # -- 1. Business Model --
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

    # -- 2. Moat & Competition --
    moat_bullets = []
    if mcap_cr > 100000:
        moat_bullets.append(f"Mega-cap (₹{mcap_cr:,.0f} Cr) — dominant market position with significant scale advantages.")
    elif mcap_cr > 20000:
        moat_bullets.append(f"Large-cap (₹{mcap_cr:,.0f} Cr) — established player with meaningful market presence.")
    elif mcap_cr > 5000:
        moat_bullets.append(f"Mid-cap (₹{mcap_cr:,.0f} Cr) — growing company in a competitive landscape.")
    else:
        moat_bullets.append(f"Small-cap (₹{mcap_cr:,.0f} Cr) — higher risk/reward profile.")

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

    peers = data.get("peers", [])
    if peers:
        peer_names = [p.get("name", "") for p in peers[:4] if p.get("name")]
        if peer_names:
            moat_bullets.append(f"Key competitors: {', '.join(peer_names)}.")

    for p in pros_list:
        lp = p.lower()
        if any(kw in lp for kw in ["market leader", "brand", "moat", "dominant", "monopoly", "leader", "scale"]):
            moat_bullets.append(p)
            break
    if not moat_bullets:
        moat_bullets.append("Competitive analysis data limited.")

    # -- 3. Catalysts --
    catalyst_bullets = []
    for p in pros_list:
        lp = p.lower()
        if any(kw in lp for kw in ["launch", "expand", "partner", "approv", "new", "grow", "capex", "invest", "capacity", "enter"]):
            catalyst_bullets.append(p)
    for ni in news_items[:5]:
        title_l = ni.get("title", "").lower()
        if any(kw in title_l for kw in ["launch", "partner", "deal", "acqui", "expan", "approv", "regul", "invest", "order", "contract"]):
            catalyst_bullets.append(f'{ni["title"]} <span style="color:var(--text3);">({ni.get("publisher", "")})</span>')
    if rev_growth and rev_growth > 0.15:
        catalyst_bullets.append(f"Revenue growing at <strong>{rev_growth*100:.0f}%</strong> — strong top-line momentum.")
    if earn_growth and earn_growth > 0.20:
        catalyst_bullets.append(f"Earnings growth of <strong>{earn_growth*100:.0f}%</strong> signals execution on profitability.")
    if not catalyst_bullets:
        catalyst_bullets.append("No specific near-term catalysts identified from available data.")
    catalyst_bullets = catalyst_bullets[:5]

    # -- 4. Asymmetry Check --
    asym_bullets = []
    target_mean_price = safe_get(info, "targetMeanPrice", 0) or 0
    target_high = safe_get(info, "targetHighPrice", 0) or 0
    target_low = safe_get(info, "targetLowPrice", 0) or 0
    if target_mean_price and current_price:
        upside = (target_mean_price - current_price) / current_price * 100
        downside_floor = (target_low - current_price) / current_price * 100 if target_low else 0
        upside_ceiling = (target_high - current_price) / current_price * 100 if target_high else 0
        asym_bullets.append(f"Analyst target range: ₹{target_low:,.0f} — ₹{target_high:,.0f} (mean ₹{target_mean_price:,.0f}, {n_analysts} analysts).")
        if upside_ceiling > 0 and abs(downside_floor) > 0:
            ratio = abs(upside_ceiling / downside_floor) if downside_floor != 0 else float('inf')
            if ratio > 2:
                asym_bullets.append(f"<strong style='color:var(--green);'>Favorable asymmetry</strong> — upside potential of <strong>{upside_ceiling:+.0f}%</strong> vs downside floor of <strong>{downside_floor:+.0f}%</strong> ({ratio:.1f}x reward-to-risk).")
            elif ratio > 1:
                asym_bullets.append(f"<strong style='color:var(--amber);'>Moderate asymmetry</strong> — upside {upside_ceiling:+.0f}% vs downside {downside_floor:+.0f}% ({ratio:.1f}x).")
            else:
                asym_bullets.append(f"<strong style='color:var(--red);'>Unfavorable asymmetry</strong> — limited upside {upside_ceiling:+.0f}% vs downside {downside_floor:+.0f}% ({ratio:.1f}x).")
    pe_asym = safe_get(info, "trailingPE", 0) or 0
    if pe_asym > 0:
        if pe_asym < 15:
            asym_bullets.append(f"P/E of {pe_asym:.1f}x — <strong>low valuation floor</strong>, limited downside from de-rating.")
        elif pe_asym > 40:
            asym_bullets.append(f"P/E of {pe_asym:.1f}x — <strong>premium valuation</strong>, growth must sustain to avoid de-rating risk.")
        else:
            asym_bullets.append(f"P/E of {pe_asym:.1f}x — fair value territory; catalysts needed for re-rating.")
    for c in cons_list:
        lc = c.lower()
        if any(kw in lc for kw in ["expensive", "high valuation", "overvalued", "debt", "slow"]):
            asym_bullets.append(f'<span style="color:var(--red);">⚠</span> {c}')
            break
    if not asym_bullets:
        asym_bullets.append("Insufficient analyst data for asymmetry assessment.")

    # -- 5. Future Outlook --
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
    for p in pros_list:
        if p not in catalyst_bullets:
            lp = p.lower()
            if any(kw in lp for kw in ["growth", "future", "potential", "opportunity", "margin", "improv"]):
                outlook_bullets.append(p)
                break
    for c in cons_list:
        lc = c.lower()
        if any(kw in lc for kw in ["risk", "threat", "decline", "slow", "head", "regulatory"]):
            outlook_bullets.append(f'<span style="color:var(--amber);">Risk:</span> {c}')
            break
    if not outlook_bullets:
        outlook_bullets.append("Limited forward-looking data available.")

    def _bullets_html(items, accent_color="#3d9cf5"):
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
        <div style="background:var(--bg3);border:1px solid var(--border);border-radius:10px;padding:16px 18px;border-left:3px solid #3d9cf5;">
          <div style="font-family:var(--mono);font-size:10px;font-weight:600;letter-spacing:1.5px;color:#3d9cf5;margin-bottom:8px;">🔭 FUTURE OUTLOOK</div>
          <ul style="font-size:11px;color:var(--text2);line-height:1.75;padding-left:16px;margin:0;">{_bullets_html(outlook_bullets)}</ul>
        </div>
      </div>

      <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;">
        <div style="background:var(--bg3);border:1px solid var(--border);border-radius:10px;padding:16px 18px;border-left:3px solid var(--green);">
          <div style="font-family:var(--mono);font-size:10px;font-weight:600;letter-spacing:1.5px;color:var(--green);margin-bottom:8px;">✅ PROS</div>
          <ul style="font-size:11px;color:var(--text2);line-height:1.75;padding-left:16px;margin:0;">{"".join(f"<li style='margin-bottom:4px;color:var(--green);'>{p}</li>" for p in pros_list[:6]) or "<li style='color:var(--text3);'>None identified</li>"}</ul>
        </div>
        <div style="background:var(--bg3);border:1px solid var(--border);border-radius:10px;padding:16px 18px;border-left:3px solid var(--red);">
          <div style="font-family:var(--mono);font-size:10px;font-weight:600;letter-spacing:1.5px;color:var(--red);margin-bottom:8px;">❌ CONS</div>
          <ul style="font-size:11px;color:var(--text2);line-height:1.75;padding-left:16px;margin:0;">{"".join(f"<li style='margin-bottom:4px;color:var(--red);'>{c}</li>" for c in cons_list[:6]) or "<li style='color:var(--text3);'>None identified</li>"}</ul>
        </div>
      </div>

    </div>
  </div>'''

    # ── Build financial table HTML helper ──
    _expand_counter = [0]

    def _build_screener_table_html(headers, rows, max_cols=10):
        if not headers or not rows:
            return ""
        display_headers = headers[:1] + headers[-max_cols+1:] if len(headers) > max_cols else headers
        start_idx = len(headers) - len(display_headers)
        th_html = "".join(f'<th>{h}</th>' for h in display_headers)
        body = ""
        current_group_id = None
        for row in rows:
            if not row:
                continue
            cells_data = row.get("cells", row) if isinstance(row, dict) else row
            expandable = row.get("expandable") if isinstance(row, dict) else None
            is_sub = row.get("is_sub", False) if isinstance(row, dict) else False
            label = cells_data[0].replace("+", "").strip()
            vals = cells_data[1:]
            display_vals = vals[start_idx:] if start_idx > 0 else vals
            while len(display_vals) < len(display_headers) - 1:
                display_vals.append("")
            is_key = not is_sub and any(kw in label.lower() for kw in ["total", "net profit", "operating profit", "sales", "eps"])
            is_pct = "%" in label.lower() or "opm" in label.lower()
            dv = display_vals[:max_cols-1]
            nums = [_try_float(v) for v in dv]

            if expandable:
                _expand_counter[0] += 1
                current_group_id = f"grp{_expand_counter[0]}"
                toggle_icon = f'<span class="exp-icon" id="icon-{current_group_id}">+</span>'
                bold_s = "font-weight:600;color:#fff;" if is_key else ""
                label_html = f'<td class="exp-parent" onclick="toggleGroup(\'{current_group_id}\')" style="cursor:pointer;{bold_s}">{label} {toggle_icon}</td>'
            elif is_sub:
                label_html = f'<td style="padding-left:2.2rem;color:#8a8b9f;font-size:0.85em;">{label}</td>'
            else:
                current_group_id = None
                bold_attr = ' style="font-weight:600;color:#fff;"' if is_key else ""
                label_html = f'<td{bold_attr}>{label}</td>'

            val_cells = ""
            for j, v in enumerate(dv):
                n = nums[j]
                prev = nums[j - 1] if j > 0 else None
                cls = ""
                if n is not None and prev is not None and prev != 0:
                    cls = " class=\"tg\"" if n > prev else (" class=\"tr\"" if n < prev else "")
                if is_sub:
                    val_cells += f'<td{cls} style="font-size:0.85em;">{v}</td>'
                elif is_key:
                    val_cells += f'<td{cls} style="font-weight:600;color:#fff;">{v}</td>'
                else:
                    val_cells += f'<td{cls}>{v}</td>'

            tr_attrs = ""
            if is_sub and current_group_id:
                tr_attrs = f' class="sub-row sub-{current_group_id}" style="display:none;"'
            body += f'<tr{tr_attrs}>{label_html}{val_cells}</tr>\n'
        return f'''<div style="overflow-x:auto;"><table><thead><tr>{th_html}</tr></thead><tbody>{body}</tbody></table></div>'''

    pl_table_html = _build_screener_table_html(screener.get("pl_headers"), screener.get("pl_rows"))
    bs_table_html = _build_screener_table_html(screener.get("bs_headers"), screener.get("bs_rows"))
    cf_table_html = _build_screener_table_html(screener.get("cf_headers"), screener.get("cf_rows"))
    qr_table_html = _build_screener_table_html(screener.get("qr_headers"), screener.get("qr_rows"), max_cols=12)

    screener_url = f"https://www.screener.in/company/{ticker_symbol}/consolidated/"

    qr_section_html = f'''
  <div class="section">
    <div class="section-title">📅 Quarterly Results <a href="{screener_url}" target="_blank" class="src-link-header">Source: Screener ↗</a></div>
    {qr_table_html}
  </div>''' if qr_table_html else ""

    pl_section_html = f'''
  <div class="section">
    <div class="section-title">📊 Profit & Loss Statement <a href="{screener_url}" target="_blank" class="src-link-header">Source: Screener ↗</a></div>
    {pl_table_html}
  </div>''' if pl_table_html else ""

    bs_section_html = f'''
  <div class="section">
    <div class="section-title">🏦 Balance Sheet <a href="{screener_url}" target="_blank" class="src-link-header">Source: Screener ↗</a></div>
    {bs_table_html}
  </div>''' if bs_table_html else ""

    cf_section_html = f'''
  <div class="section">
    <div class="section-title">💰 Cash Flow Statement <a href="{screener_url}" target="_blank" class="src-link-header">Source: Screener ↗</a></div>
    {cf_table_html}
  </div>''' if cf_table_html else ""

    # ── Ratios table ──
    rt_table_html = _build_screener_table_html(screener.get("rt_headers"), screener.get("rt_rows"))
    rt_section_html = f'''
  <div class="section">
    <div class="section-title">📈 Key Financial Ratios</div>
    {rt_table_html}
  </div>''' if rt_table_html else ""

    # ── Compounded Growth Rates ──
    growth_rates = screener.get("growth_rates", {})
    growth_html = ""
    if growth_rates:
        cards = ""
        for title, items in growth_rates.items():
            rows_h = "".join(f'<tr><td style="color:var(--text2);">{k}</td><td style="text-align:right;font-weight:600;">{v}</td></tr>' for k, v in items)
            cards += f'''<div class="col-card"><div class="col-title">{title}</div><table><tbody>{rows_h}</tbody></table></div>'''
        growth_html = f'''
  <div class="section">
    <div class="section-title">🚀 Compounded Growth Rates</div>
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;">{cards}</div>
  </div>'''

    # ── Valuation trend carousel (P/E, P/B, MCap/Sales, EPS) ──
    eps_series = screener.get("eps_series")
    bv_series = screener.get("bv_series")
    sales_series = screener.get("sales_series")

    pe_chart_data = None
    if eps_series and eps_series.get("values"):
        pe_values = []
        for v in eps_series["values"]:
            if v is not None and v > 0:
                pe_values.append(current_price / v if current_price else None)
            else:
                pe_values.append(None)
        pe_chart_data = {"headers": eps_series["headers"], "values": pe_values}

    pb_chart_data = None
    if bv_series and bv_series.get("values"):
        pb_values = []
        for v in bv_series["values"]:
            if v is not None and v > 0:
                pb_values.append(current_price / v if current_price else None)
            else:
                pb_values.append(None)
        pb_chart_data = {"headers": bv_series["headers"], "values": pb_values}

    mcap_sales_data = None
    if sales_series and sales_series.get("values") and market_cap:
        mcap_cr = market_cap / 1e7
        ms_values = []
        for v in sales_series["values"]:
            ms_values.append(mcap_cr / v if v is not None and v > 0 else None)
        mcap_sales_data = {"headers": sales_series["headers"], "values": ms_values}

    eps_trend_data = None
    if eps_series and eps_series.get("values"):
        eps_trend_data = {"headers": eps_series["headers"], "values": eps_series["values"]}

    unavail = '<div style="color:var(--text3);font-size:11px;text-align:center;padding:40px 0;">Data unavailable</div>'
    carousel_charts = [
        ("P/E", "#3d9cf5", pe_chart_data, "P/E Ratio at current CMP"),
        ("P/B", "#9b7fff", pb_chart_data, "P/B Ratio at current CMP"),
        ("MCap/Sales", "#f5a623", mcap_sales_data, "Market Cap to Sales at current MCap"),
        ("EPS", "#00e5a0", eps_trend_data, "Earnings Per Share (₹)"),
    ]

    carousel_panels = ""
    carousel_btns = ""
    has_any_chart = False
    for i, (lbl, clr, cdata, subtitle) in enumerate(carousel_charts):
        svg = generate_pe_pb_chart_svg(cdata, label=lbl, color=clr) if cdata else ""
        if svg:
            has_any_chart = True
        active = " active" if i == 0 else ""
        hidden = "" if i == 0 else ' style="display:none;"'
        carousel_btns += f'<button class="tf-btn{active}" data-idx="{i}">{lbl}</button>'
        carousel_panels += f'<div class="vt-panel" id="vt-panel-{i}"{hidden}><div style="font-family:var(--mono);font-size:9px;color:var(--text3);margin-bottom:4px;letter-spacing:1px;text-transform:uppercase;">{subtitle}</div>{svg if svg else unavail}</div>'

    pe_pb_section_html = ""
    if has_any_chart:
        pe_pb_section_html = f'''
  <div class="section">
    <div class="section-title" style="display:flex;align-items:center;gap:16px;flex-wrap:wrap;">
      <span>📉 Valuation Trends (at current CMP)</span>
      <div class="tf-btns" id="vt-btns">{carousel_btns}</div>
    </div>
    {carousel_panels}
  </div>'''

    # ── Quarterly table HTML (with QoQ %) ──
    qt_rows_html = ""
    for q in quarterly_rows:
        rev_str = f"₹{q['revenue_cr']:,.0f} Cr" if q['revenue_cr'] else "N/A"
        profit_str = f"₹{q['profit_cr']:,.0f} Cr" if q['profit_cr'] else "N/A"
        ebitda_str = f"{q['ebitda_margin']:.1f}%" if q['ebitda_margin'] else "N/A"
        cf_str = f"₹{q['op_cash_flow_cr']:,.0f} Cr" if q.get('op_cash_flow_cr') else "N/A"

        def _qoq_cell(pct):
            if pct is None:
                return '<td style="color:var(--text3)">—</td>'
            cls = "tg" if pct >= 0 else "tr"
            return f'<td class="{cls}">{pct:+.1f}%</td>'

        profit_class = "tg" if q['profit_cr'] and q['profit_cr'] > 0 else "tr" if q['profit_cr'] and q['profit_cr'] < 0 else ""

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
        rev_str = f"₹{a['revenue_cr']:,.0f} Cr" if a['revenue_cr'] else "N/A"
        profit_str = f"₹{a['profit_cr']:,.0f} Cr" if a['profit_cr'] else "N/A"
        cf_str = f"₹{a['op_cash_flow_cr']:,.0f} Cr" if a.get('op_cash_flow_cr') else "N/A"

        def _yoy_cell(pct):
            if pct is None:
                return '<td style="color:var(--text3)">—</td>'
            cls = "tg" if pct >= 0 else "tr"
            return f'<td class="{cls}">{pct:+.1f}%</td>'

        yoy_rows_html += f'''
        <tr>
          <td>{a["fy"]}</td>
          <td>{rev_str}</td>{_yoy_cell(a.get("rev_yoy_pct"))}
          <td>{profit_str}</td>{_yoy_cell(a.get("profit_yoy_pct"))}
          <td>{cf_str}</td>{_yoy_cell(a.get("cf_yoy_pct"))}
        </tr>'''

    if not yoy_rows_html:
        yoy_rows_html = '<tr><td colspan="7" style="text-align:center;color:var(--text3);">Annual data not available</td></tr>'

    # ── Revenue vs Earnings chart data (for interactive JS chart) ──
    fin_chart_data = {"quarterly": [], "annual": []}
    for q in quarterly_rows:
        entry = {"label": q.get("quarter", "?"), "rev": None, "profit": None, "eps": None}
        if q.get("revenue_cr") is not None:
            entry["rev"] = round(q["revenue_cr"] / 1e7, 2) if q["revenue_cr"] > 1e8 else round(q["revenue_cr"], 0)
        if q.get("profit_cr") is not None:
            entry["profit"] = round(q["profit_cr"] / 1e7, 2) if abs(q["profit_cr"]) > 1e8 else round(q["profit_cr"], 0)
        # Extract quarterly EPS (raw per-share value, not in Crores)
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
        entry = {"label": a.get("fy", "?"), "rev": None, "profit": None, "eps": None}
        if a.get("revenue_cr") is not None:
            entry["rev"] = round(a["revenue_cr"] / 1e7, 2) if a["revenue_cr"] > 1e8 else round(a["revenue_cr"], 0)
        if a.get("profit_cr") is not None:
            entry["profit"] = round(a["profit_cr"] / 1e7, 2) if abs(a["profit_cr"]) > 1e8 else round(a["profit_cr"], 0)
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

    # Determine scale label
    _any_q_rev = any(q.get("revenue_cr") and q["revenue_cr"] > 1e8 for q in quarterly_rows)
    _any_a_rev = any(a.get("revenue_cr") and a["revenue_cr"] > 1e8 for a in annual_rows)
    fin_chart_data["scale"] = "₹ Cr (÷ 10M)" if (_any_q_rev or _any_a_rev) else "₹ Cr"

    import json as _json2
    fin_chart_json = _json2.dumps(fin_chart_data, separators=(",", ":"))

    # ── Earnings estimates vs actual (target vs achieved) ──
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

    # ── Shareholding section HTML (prefer Screener.in QoQ data) ──
    screener = data.get("screener") or {}
    sh_headers = screener.get("shareholding_headers", [])
    sh_rows = screener.get("shareholding_rows", [])

    use_screener_sh = bool(sh_headers and sh_rows)

    if use_screener_sh:
        # Show last N quarters as a proper QoQ table
        n_cols = min(6, len(sh_headers))
        display_headers = sh_headers[-n_cols:]
        sh_table_head = "".join(f"<th>{h}</th>" for h in display_headers)
        sh_table_body = ""
        for row_data in sh_rows:
            cat = row_data["category"]
            vals = row_data["values"][-n_cols:]
            if cat.lower().startswith("no. of share") or cat.lower().startswith("no."):
                cells = "".join(f"<td>{v}</td>" for v in vals)
            else:
                # Color-code: compare each quarter to previous
                cells = ""
                for j, v in enumerate(vals):
                    try:
                        pct_val = float(v.replace("%", ""))
                        prev_val = float(vals[j - 1].replace("%", "")) if j > 0 else pct_val
                        diff = pct_val - prev_val
                        cls = "tg" if diff > 0.01 else "tr" if diff < -0.01 else ""
                        cells += f'<td class="{cls}">{v}</td>'
                    except (ValueError, TypeError):
                        cells += f"<td>{v}</td>"
            sh_table_body += f"<tr><td><strong>{cat}</strong></td>{cells}</tr>"

        holder_summary_html = ""
        holders_table_html = ""
        shareholding_section_html = f'''
        <div style="overflow-x:auto;">
        <table>
          <thead><tr><th></th>{sh_table_head}</tr></thead>
          <tbody>{sh_table_body}</tbody>
        </table>
        </div>'''
    else:
        # Fallback to yfinance holder data
        holder_summary_html = ""
        if holder_summary:
            for label, key in [("Insiders", "insiders"), ("Institutions", "institutions"), ("Float Held by Inst.", "float_held"), ("No. of Institutions", "num_institutions")]:
                val = holder_summary.get(key)
                if val is not None:
                    if key == "num_institutions":
                        display = f"{int(val):,}"
                    elif isinstance(val, float) and val <= 1:
                        display = f"{val*100:.1f}%"
                    elif isinstance(val, float):
                        display = f"{val:.1f}%"
                    else:
                        display = str(val)
                    holder_summary_html += f'<div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--border);font-family:var(--mono);font-size:11px;"><span style="color:var(--text2)">{label}</span><span style="color:#fff">{display}</span></div>'
        if not holder_summary_html:
            holder_summary_html = '<div style="color:var(--text3);font-size:11px;text-align:center;padding:20px 0;">Holder summary not available</div>'

        holders_table_html = ""
        all_holders = [(h, "Inst") for h in top_inst] + [(h, "MF") for h in top_mf]
        if all_holders:
            for h, htype in all_holders:
                pct_val = h.get("pct", 0)
                pct_str = f"{pct_val*100:.2f}%" if isinstance(pct_val, float) and pct_val < 1 else f"{pct_val:.2f}%" if isinstance(pct_val, float) else "N/A"
                shares = h.get("shares", 0)
                shares_str = f"{shares:,.0f}" if shares else "N/A"
                holders_table_html += f'<tr><td>{h["name"][:35]}</td><td>{htype}</td><td>{shares_str}</td><td>{pct_str}</td></tr>'
        else:
            holders_table_html = '<tr><td colspan="4" style="text-align:center;color:var(--text3);">Holder data not available</td></tr>'

        shareholding_section_html = f'''
        <div class="dual-col">
          <div class="col-card">
            <div class="col-title">HOLDER SUMMARY</div>
            {holder_summary_html}
          </div>
          <div class="col-card">
            <div class="col-title">TOP HOLDERS</div>
            <div style="overflow-x:auto;">
            <table>
              <thead><tr><th>Holder</th><th>Type</th><th>Shares</th><th>% Held</th></tr></thead>
              <tbody>{holders_table_html}</tbody>
            </table>
            </div>
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

    # ── Industry peers section HTML ──
    peers = data.get("peers", [])
    industry_name = data.get("industry_name", "") or safe_get(info, "industry", "")
    best_peer = peers[0] if peers else None

    peers_html = ""
    peers_note_html = ""
    if peers:
        rows_html = ""
        for rank, p in enumerate(peers, 1):
            is_best = (rank == 1)
            is_you = p.get("is_self", False)
            name_display = p["name"]
            if is_best:
                name_display += ' <span style="color:var(--green);font-size:9px;">★</span>'
            name_link = f'<a href="{p["screener_url"]}" target="_blank" rel="noopener" style="color:#fff;text-decoration:none;">{name_display}</a>' if p.get("screener_url") else name_display
            if is_best:
                row_style = ' style="border-left:3px solid var(--green);background:rgba(0,229,160,0.04);"'
            elif is_you:
                row_style = ' style="border-left:3px solid var(--amber);background:rgba(245,166,35,0.04);"'
            else:
                row_style = ""
            pe_str = f'{p["pe"]:.1f}' if p.get("pe") else "—"
            mcap_str = f'₹{p["mcap"]:,.0f}' if p.get("mcap") else "—"
            roce_str = f'{p["roce"]:.1f}%' if p.get("roce") is not None else "—"
            gpv = p.get("qtr_profit_var")
            gpv_str = f'<span class="{"tg" if gpv >= 0 else "tr"}">{gpv:+.1f}%</span>' if gpv is not None else "—"
            score_str = f'{p.get("tf_score", 0):.0f}'

            rows_html += f'<tr{row_style}><td>{rank}</td><td>{name_link}</td><td>₹{p["cmp"]:,.0f}</td><td>{pe_str}</td><td>{mcap_str}</td><td>{roce_str}</td><td>{gpv_str}</td><td>{score_str}</td></tr>'

        peers_html = f'''<div style="overflow-x:auto;">
        <table>
          <thead><tr><th>#</th><th>Company</th><th>CMP</th><th>P/E</th><th>Mkt Cap</th><th>ROCE</th><th>Qtr Profit</th><th>Score</th></tr></thead>
          <tbody>{rows_html}</tbody>
        </table></div>'''

        if best_peer:
            if best_peer.get("is_self"):
                peers_note_html = f'<div style="font-family:var(--mono);font-size:10px;color:var(--green);margin-top:10px;text-align:center;">★ {ticker_symbol} is the top-ranked techno-fundamental pick in {industry_name}</div>'
            else:
                peers_note_html = f'<div style="font-family:var(--mono);font-size:10px;color:var(--amber);margin-top:10px;text-align:center;">★ {best_peer["name"]} ranks higher on combined P/E, ROCE, and growth metrics in {industry_name}</div>'

    val_color = score_color(scores["valuation"], 25)
    fin_color = score_color(scores["financial"], 25)
    growth_color = score_color(scores["growth"], 25)
    tech_color = score_color(scores["technical"], 25)

    today_str = datetime.now().strftime("%B %d, %Y · %H:%M IST")

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

    ev_revenue = mcap_cr / (total_revenue / 1e7) if total_revenue else 0

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

    # ── Industry averages from peer data ──
    def _median(vals):
        s = sorted(vals)
        n = len(s)
        if n == 0:
            return None
        return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2

    all_peers = data.get("peers", [])
    ind_pe = _median([p["pe"] for p in all_peers if p.get("pe") and p["pe"] > 0])
    ind_roce = _median([p["roce"] for p in all_peers if p.get("roce") is not None])
    ind_dy = _median([p["div_yield"] for p in all_peers if p.get("div_yield") is not None and p["div_yield"] > 0])

    # Pre-compute metric card statuses (sector-relative thresholds)
    pe_cls, pe_tip = cs(pe_ratio, _pe_fair, _pe_exp, "P/E", True) if pe_ratio else ("caution", "P/E: Data unavailable")
    pb_cls, pb_tip = cs(pb_ratio, _pb_fair, _pb_exp, "P/B", True) if pb_ratio else ("caution", "P/B: Data unavailable")
    roe_cls, roe_tip = cs(roe * 100, _roe_good * 100, _roe_mod * 100, "ROE %") if roe else ("caution", "ROE: Data unavailable")
    pm_cls, pm_tip = cs(profit_margin * 100, _margin_good * 100, _margin_mod * 100, "Profit Margin %") if profit_margin else ("caution", "Profit Margin: Data unavailable")
    opm_pct = operating_margin * 100 if operating_margin else None
    opm_cls, opm_tip = cs(opm_pct, _margin_good * 100 * 0.75, _margin_mod * 100 * 0.5, "OPM %") if opm_pct is not None else ("caution", "Operating Margin: Data unavailable")
    tgt_cls = "beat" if target_mean > current_price else "miss" if target_mean else "caution"
    tgt_tip = f"Analyst target ₹{target_mean:,.0f} vs CMP ₹{current_price:,.0f} — {'upside' if target_mean > current_price else 'downside'}" if target_mean else "Analyst target: Data unavailable"
    yahoo_analysis_url = f"https://finance.yahoo.com/quote/{ticker_symbol}.NS/analyst-price-targets/"
    peg_cls, peg_tip = cs(peg_ratio, 1.0, 2.0, "PEG", True) if peg_ratio else ("caution", "PEG: Data unavailable")
    eve_cls, eve_tip = cs(ev_ebitda, 12, 20, "EV/EBITDA", True) if ev_ebitda else ("caution", "EV/EBITDA: Data unavailable")
    cr_cls, cr_tip = cs(current_ratio, 1.5, 1.0, "Current Ratio") if current_ratio else ("caution", "Current Ratio: Data unavailable")
    dy_pct = dividend_yield
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

    if upside > 10:
        catalysts.append(f"<strong>Analyst Upside ({upside:.0f}%):</strong> Mean target of ₹{target_mean:.0f} above current price.")

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

    catalysts_html = "\n".join([f'<div class="col-item"><span class="col-icon">{"🏆💹🔀🇮🇳🔬📈"[i % 6]}</span><span>{c}</span></div>' for i, c in enumerate(catalysts[:6])])
    risks_html = "\n".join([f'<div class="col-item"><span class="col-icon">{"📜💰🔓⚔️📉🌐"[i % 6]}</span><span>{r}</span></div>' for i, r in enumerate(risks[:6])])

    # ── Decision matrix ──
    screener = data.get("screener") or {}
    bench = get_sector_bench(sector)
    sector_pe_cheap, _, _ = bench["pe"]

    # Extract shareholding trend for reasoning
    sh_rows = screener.get("shareholding_rows", [])
    fii_trend_str = ""
    for sr in sh_rows:
        if "fii" in sr["category"].lower():
            vals = sr["values"]
            if len(vals) >= 2:
                try:
                    latest = float(vals[-1].replace("%", ""))
                    prev = float(vals[-2].replace("%", ""))
                    diff = latest - prev
                    fii_trend_str = f"FII stake {'rising' if diff > 0 else 'falling'} ({diff:+.2f}%)"
                except (ValueError, TypeError):
                    pass
            break

    # Identify best alternative peer (not self)
    alt_peer = next((p for p in peers if not p.get("is_self")), None)
    alt_name = alt_peer["name"] if alt_peer else ""
    alt_pe_str = f'{alt_peer["pe"]:.1f}' if alt_peer and alt_peer.get("pe") else "—"
    alt_roce_str = f'{alt_peer["roce"]:.1f}%' if alt_peer and alt_peer.get("roce") is not None else "—"

    # Sector median P/E from peers
    peer_pes = [p["pe"] for p in peers if p.get("pe") and p["pe"] > 0 and not p.get("is_self")]
    sector_median_pe = sorted(peer_pes)[len(peer_pes) // 2] if peer_pes else None

    opm_str = f"{opm_pct:.0f}%" if opm_pct is not None else "N/A"
    roce_val = screener.get("roce")
    roce_str_dm = f"{roce_val:.0f}%" if roce_val else "N/A"

    # Build payoff cells
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
        buy_reasons.append(f"Analyst upside of {upside:.1f}% with mean target of ₹{target_mean:,.0f}")
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
    if alt_peer and not best_peer.get("is_self", True) if best_peer else False:
        bp = best_peer
        bp_pe = f"P/E {bp['pe']:.1f}" if bp.get("pe") else ""
        bp_roce = f"ROCE {bp['roce']:.1f}%" if bp.get("roce") is not None else ""
        bp_metrics = ", ".join(filter(None, [bp_pe, bp_roce]))
        competitor_line = f'<br><br>Within <strong>{industry_name}</strong>, <strong>{bp["name"]}</strong> ({bp_metrics}) ranks higher on techno-fundamental metrics and may be worth considering.'

    verdict_text = f'''<strong>{company_name}</strong> trades at ₹{current_price:,.2f} with a composite risk score of {composite}/100.
    The stock scores {scores["valuation"]}/25 on valuation, {scores["financial"]}/25 on financial health, {scores["growth"]}/25 on growth, and {scores["technical"]}/25 on technicals.
    The company is currently {profit_status} with {"strong" if roe and roe > 0.15 else "moderate" if roe and roe > 0 else "negative"} return on equity.
    <br><br>
    {"Analyst consensus suggests upside of " + f"{upside:.1f}%" + f" with a mean target of ₹{target_mean:.0f}." if target_mean and upside > 0 else "The stock is trading near or above analyst consensus targets."}
    Revenue growth is at {rev_growth*100:.1f}%{" — a strong positive signal" if rev_growth and rev_growth > 0.15 else "" if rev_growth and rev_growth > 0 else " — a concern"}.
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
  .sh-range-track {{ flex:1; height:5px; background:linear-gradient(90deg,rgba(0,229,160,0.15),rgba(245,166,35,0.15),rgba(255,77,109,0.15)); border-radius:3px; position:relative; min-width:80px; }}
  .sh-range-fill {{ height:100%; border-radius:3px; background:linear-gradient(90deg,#00e5a0,#f5a623,#ff4d6d); }}
  .sh-range-dot {{ position:absolute; top:50%; width:10px; height:10px; border-radius:50%; border:2px solid var(--bg); transform:translate(-50%,-50%); }}
  .sh-range-zone {{ font-family:var(--mono); font-size:8px; font-weight:600; letter-spacing:0.5px; text-transform:uppercase; width:62px; text-align:left; flex-shrink:0; }}
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
  .src-link {{ display:inline-block; margin-top:6px; font-size:9px; color:var(--blue); text-decoration:none; font-family:var(--mono); opacity:0.7; transition:opacity 0.2s; }}
  .src-link:hover {{ opacity:1; text-decoration:underline; }}
  .src-link-header {{ float:right; font-size:10px; color:var(--blue); text-decoration:none; font-family:var(--mono); font-weight:400; letter-spacing:0; text-transform:none; opacity:0.6; transition:opacity 0.2s; }}
  .src-link-header:hover {{ opacity:1; text-decoration:underline; }}
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
  .exp-parent {{ user-select:none; }} .exp-parent:hover {{ color:#3d9cf5!important; }}
  .exp-icon {{ display:inline-block;width:16px;height:16px;line-height:16px;text-align:center;font-size:12px;font-weight:700;color:#3d9cf5;background:rgba(61,156,245,0.12);border-radius:4px;margin-left:4px;vertical-align:middle;transition:transform 0.2s; }}
  .sub-row td {{ border-bottom-color:rgba(255,255,255,0.02)!important; }}
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
      <div class="sh-ticker"><span>NSE:{ticker_symbol}</span><span class="badge badge-nse">NSE</span><span class="badge badge-sector">{sector}</span></div>
      <div class="sh-name">{company_name}</div>
      <div class="sh-meta"><span>📊 {industry}</span></div>
      {corp_actions_html}
      <div class="sh-ranges">
        <div class="sh-range">
          <span class="sh-range-label">Day</span>
          <span class="sh-range-val">₹{day_low:,.0f}</span>
          <div class="sh-range-track"><div class="sh-range-fill" style="width:{day_pct:.1f}%"></div><div class="sh-range-dot" style="left:{day_pct:.1f}%;background:{day_dot_color};box-shadow:0 0 6px {day_dot_color}80;"></div></div>
          <span class="sh-range-val">₹{day_high:,.0f}</span>
          <span class="sh-range-zone" style="color:{day_dot_color}">{day_zone}</span>
        </div>
        <div class="sh-range">
          <span class="sh-range-label">52W</span>
          <span class="sh-range-val">₹{low_52w:,.0f}</span>
          <div class="sh-range-track"><div class="sh-range-fill" style="width:{w52_pct:.1f}%"></div><div class="sh-range-dot" style="left:{w52_pct:.1f}%;background:{w52_dot_color};box-shadow:0 0 6px {w52_dot_color}80;"></div></div>
          <span class="sh-range-val">₹{high_52w:,.0f}</span>
          <span class="sh-range-zone" style="color:{w52_dot_color}">{w52_zone}</span>
        </div>
      </div>
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
        VAL:{scores["valuation"]}/25 · FIN:{scores["financial"]}/25 · GRO:{scores["growth"]}/25 · TECH:{scores["technical"]}/25
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
    <div class="section-title">🎯 Fair Value Analysis · CMP vs Analyst Targets <a href="{yahoo_analysis_url}" target="_blank" class="src-link-header">Source: Yahoo Finance Analyst Targets ↗</a></div>
    {fair_value_svg}
    <div style="font-family:var(--mono);font-size:9px;color:var(--text3);margin-top:8px;line-height:1.6;">
      Fair value zone = Analyst consensus price target range · Low ₹{fair_value_low:,.0f} · Mean ₹{fair_value_mid:,.0f} · High ₹{fair_value_high:,.0f}
      {"" if target_mean else " · <span style='color:var(--amber);'>No analyst targets available — using ±25% of CMP as placeholder</span>"}
    </div>
  </div>

  {pe_pb_section_html}

  <div class="section">
    <div class="section-title">💎 Valuation & Financial Metrics</div>
    <div class="card-grid">
      <div class="metric-card {pe_cls}" data-tip="{pe_tip}"><div class="mc-label">P/E RATIO</div><div class="mc-value">{pe_ratio:.1f}x</div><div class="mc-bench">Trailing twelve months</div></div>
      <div class="metric-card {pb_cls}" data-tip="{pb_tip}"><div class="mc-label">P/B RATIO</div><div class="mc-value">{pb_ratio:.1f}x</div><div class="mc-bench">Price to Book value</div></div>
      <div class="metric-card {roe_cls}" data-tip="{roe_tip}"><div class="mc-label">ROE</div><div class="mc-value">{roe*100:.1f}%</div><div class="mc-bench">Return on Equity</div></div>
      <div class="metric-card {pm_cls}" data-tip="{pm_tip}"><div class="mc-label">PROFIT MARGIN</div><div class="mc-value">{profit_margin*100:.1f}%</div><div class="mc-bench">Net profit margin</div></div>
      <div class="metric-card {opm_cls}" data-tip="{opm_tip}"><div class="mc-label">OPM</div><div class="mc-value">{f"{opm_pct:.1f}%" if opm_pct is not None else "N/A"}</div><div class="mc-bench">Operating profit margin</div></div>
      <div class="metric-card {tgt_cls}" data-tip="{tgt_tip}"><div class="mc-label">ANALYST TARGET</div><div class="mc-value">₹{target_mean:,.0f}</div><div class="mc-bench">Range: ₹{fair_value_low:,.0f} - ₹{fair_value_high:,.0f}</div><a href="{yahoo_analysis_url}" target="_blank" class="src-link">Yahoo Finance ↗</a></div>
      <div class="metric-card {peg_cls}" data-tip="{peg_tip}"><div class="mc-label">PEG RATIO</div><div class="mc-value">{f"{peg_ratio:.2f}" if peg_ratio else "N/A"}</div><div class="mc-bench">Price/Earnings to Growth</div></div>
      <div class="metric-card {eve_cls}" data-tip="{eve_tip}"><div class="mc-label">EV/EBITDA</div><div class="mc-value">{f"{ev_ebitda:.1f}x" if ev_ebitda else "N/A"}</div><div class="mc-bench">Enterprise value ratio</div></div>
      <div class="metric-card {cr_cls}" data-tip="{cr_tip}"><div class="mc-label">CURRENT RATIO</div><div class="mc-value">{f"{current_ratio:.2f}" if current_ratio else "N/A"}</div><div class="mc-bench">Liquidity measure</div></div>
      <div class="metric-card {dy_cls}" data-tip="{dy_tip}"><div class="mc-label">DIVIDEND YIELD</div><div class="mc-value">{f"{dy_pct:.2f}%" if dy_pct is not None else "N/A"}</div><div class="mc-bench">Annual yield</div></div>
      <div class="metric-card {roa_cls}" data-tip="{roa_tip}"><div class="mc-label">ROA</div><div class="mc-value">{f"{roa*100:.1f}%" if roa else "N/A"}</div><div class="mc-bench">Return on Assets</div></div>
      <div class="metric-card {gm_cls}" data-tip="{gm_tip}"><div class="mc-label">GROSS MARGIN</div><div class="mc-value">{f"{gross_margin*100:.1f}%" if gross_margin else "N/A"}</div><div class="mc-bench">Gross profit margin</div></div>
    </div>
    {"" if not industry_name else f"""<div style="margin-top:14px;padding:14px 16px;background:rgba(255,255,255,0.02);border:1px solid var(--border2);border-radius:8px;">
      <div style="font-family:var(--mono);font-size:9px;letter-spacing:1.5px;color:var(--text3);margin-bottom:10px;">INDUSTRY AVERAGES — {industry_name.upper()}</div>
      <div style="display:flex;flex-wrap:wrap;gap:20px;">
        <div style="font-family:var(--mono);font-size:11px;"><span style="color:var(--text3);">P/E</span> <span style="color:#fff;font-weight:600;">{f'{ind_pe:.1f}x' if ind_pe else '—'}</span>{f' <span style="color:{"#00e5a0" if pe_ratio and ind_pe and pe_ratio < ind_pe else "#ff4d6d" if pe_ratio and ind_pe and pe_ratio > ind_pe * 1.1 else "#f5a623"};font-size:9px;">({("below" if pe_ratio < ind_pe else "above")} avg)</span>' if pe_ratio and ind_pe else ''}</div>
        <div style="font-family:var(--mono);font-size:11px;"><span style="color:var(--text3);">P/B</span> <span style="color:#fff;font-weight:600;">{f'{bench["pb"][1]:.1f}x' if bench else '—'}</span> <span style="color:var(--text3);font-size:9px;">(sector fair)</span></div>
        <div style="font-family:var(--mono);font-size:11px;"><span style="color:var(--text3);">ROCE</span> <span style="color:#fff;font-weight:600;">{f'{ind_roce:.1f}%' if ind_roce else '—'}</span>{f' <span style="color:{"#00e5a0" if roce_val and ind_roce and roce_val > ind_roce else "#ff4d6d" if roce_val and ind_roce and roce_val < ind_roce * 0.8 else "#f5a623"};font-size:9px;">({("above" if roce_val > ind_roce else "below")} avg)</span>' if roce_val and ind_roce else ''}</div>
        <div style="font-family:var(--mono);font-size:11px;"><span style="color:var(--text3);">ROE</span> <span style="color:#fff;font-weight:600;">{f'{bench["roe"][1]*100:.0f}%' if bench else '—'}</span> <span style="color:var(--text3);font-size:9px;">(sector good)</span></div>
        <div style="font-family:var(--mono);font-size:11px;"><span style="color:var(--text3);">OPM</span> <span style="color:#fff;font-weight:600;">{f'{bench["margin"][1]*100:.0f}%' if bench else '—'}</span> <span style="color:var(--text3);font-size:9px;">(sector good)</span></div>
        <div style="font-family:var(--mono);font-size:11px;"><span style="color:var(--text3);">Div Yield</span> <span style="color:#fff;font-weight:600;">{f'{ind_dy:.2f}%' if ind_dy else '—'}</span></div>
        <div style="font-family:var(--mono);font-size:11px;"><span style="color:var(--text3);">D/E</span> <span style="color:#fff;font-weight:600;">&lt;{bench["de"][0]:.0f}</span> <span style="color:var(--text3);font-size:9px;">(sector comfort)</span></div>
      </div>
    </div>"""}
  </div>

  <div class="breakdown-grid">
    <div class="breakdown-card">
      <div class="bc-header"><div><div class="bc-title">VALUATION</div><div class="bc-score" style="color:{val_color}">{scores["valuation"]}<span class="bc-max">/25</span></div></div><div style="font-family:var(--mono);font-size:10px;color:var(--text3);">25% WEIGHT</div></div>
      <div class="bc-bar-track"><div class="bc-bar-fill" style="width:{scores['valuation']/25*100:.0f}%;background:{val_color};box-shadow:0 0 8px {val_color}44;"></div></div>
      <ul class="bc-items">
        <li>P/E at {pe_ratio:.0f}x</li>
        <li>P/B at {pb_ratio:.1f}x</li>
        <li>Analyst target: ₹{target_mean:.0f} ({upside:+.1f}%)</li>
        <li>1Y return: {return_1y:+.1f}%</li>
      </ul>
    </div>
    <div class="breakdown-card">
      <div class="bc-header"><div><div class="bc-title">FINANCIAL HEALTH</div><div class="bc-score" style="color:{fin_color}">{scores["financial"]}<span class="bc-max">/25</span></div></div><div style="font-family:var(--mono);font-size:10px;color:var(--text3);">25% WEIGHT</div></div>
      <div class="bc-bar-track"><div class="bc-bar-fill" style="width:{scores['financial']/25*100:.0f}%;background:{fin_color};box-shadow:0 0 8px {fin_color}44;"></div></div>
      <ul class="bc-items">
        <li>ROE: {roe*100:.1f}%</li>
        <li>Profit margin: {profit_margin*100:.1f}%</li>
        <li>Revenue growth: {rev_growth*100:.1f}%</li>
        <li>Debt/Equity: {debt_equity:.0f}%</li>
      </ul>
    </div>
    <div class="breakdown-card">
      <div class="bc-header"><div><div class="bc-title">GROWTH</div><div class="bc-score" style="color:{growth_color}">{scores["growth"]}<span class="bc-max">/25</span></div></div><div style="font-family:var(--mono);font-size:10px;color:var(--text3);">25% WEIGHT</div></div>
      <div class="bc-bar-track"><div class="bc-bar-fill" style="width:{scores['growth']/25*100:.0f}%;background:{growth_color};box-shadow:0 0 8px {growth_color}44;"></div></div>
      <ul class="bc-items">
        <li>Revenue growth: {rev_growth*100:.1f}%</li>
        <li>Earnings growth: {earnings_growth*100:.1f}%</li>
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

  {rt_section_html}

  {growth_html}

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

  {"" if not peers_html else f"""<div class="section">
    <div class="section-title">🏭 Industry Peers — {industry_name}</div>
    {peers_html}
    {peers_note_html}
  </div>"""}

  <div class="section">
    <div class="section-title">🎯 Decision Matrix</div>
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
    RISK SCORE REPORT · NSE:{ticker_symbol} · GENERATED {datetime.now().strftime("%b %d, %Y %H:%M IST").upper()} · DATA VIA YAHOO FINANCE + SCREENER.IN<br>
    DISCLAIMER: THIS IS NOT FINANCIAL ADVICE. DATA MAY BE DELAYED. ALWAYS VERIFY WITH OFFICIAL SOURCES BEFORE INVESTING.
  </div>

</div>
</div>

<button class="copy-btn" onclick="copyReport()" id="copyBtn">📋 COPY REPORT</button>
<script>
function toggleGroup(gid) {{
  const rows = document.querySelectorAll('.sub-' + gid);
  const icon = document.getElementById('icon-' + gid);
  const visible = rows.length > 0 && rows[0].style.display !== 'none';
  rows.forEach(r => {{ r.style.display = visible ? 'none' : 'table-row'; }});
  if (icon) icon.textContent = visible ? '+' : '−';
}}
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

/* ── Interactive price & candlestick charts ────────────────────── */
const CHART_DATA = {chart_json};

function _setupCanvas(id) {{
  const c = document.getElementById(id);
  if (!c) return null;
  const ctx = c.getContext('2d');
  const dpr = window.devicePixelRatio || 1;
  const w = c.clientWidth, h = c.clientHeight;
  if (w === 0 || h === 0) {{ console.warn('Canvas ' + id + ' has zero dimensions:', w, h); return null; }}
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
  const pad = {{ t:18, b:24, l:55, r:12 }};
  const cw = w - pad.l - pad.r, ch = h - pad.t - pad.b;

  const ret = ((closes[n-1] - closes[0]) / closes[0] * 100);
  const retEl = document.getElementById('tf-line-ret');
  if (retEl) {{
    retEl.textContent = (ret >= 0 ? '+' : '') + ret.toFixed(2) + '%';
    retEl.className = 'tf-ret ' + (ret >= 0 ? 'up' : 'dn');
  }}

  ctx.strokeStyle = 'rgba(255,255,255,0.06)';
  ctx.lineWidth = 1;
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
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.8;
  ctx.lineJoin = 'round';
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

  // Panel separator lines
  function drawSep(y, label) {{
    ctx.strokeStyle = 'rgba(255,255,255,0.08)'; ctx.lineWidth = 0.5;
    ctx.beginPath(); ctx.moveTo(L, y); ctx.lineTo(w - R, y); ctx.stroke();
    ctx.fillStyle = '#5c5d6e'; ctx.font = '8px "Fira Code",monospace'; ctx.textAlign = 'left';
    ctx.fillText(label, L + 4, y + 10);
  }}

  // ── Candle panel ──
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
  if (ema50) {{ const e = ema50.filter(v=>v!==null).pop(); ctx.fillStyle='#9b7fff'; ctx.fillText('── 50 EMA'+(e?' ('+e.toLocaleString('en-IN',{{maximumFractionDigits:0}})+')':''), lx, ly); ly+=11; }}
  if (sma200) {{ const sv = sma200.filter(v=>v!==null).pop(); ctx.fillStyle='#f5a623'; ctx.fillText('╌╌ 200 DMA'+(sv?' ('+sv.toLocaleString('en-IN',{{maximumFractionDigits:0}})+')':''), lx, ly); }}

  // ── Volume panel ──
  drawSep(pVol.t, 'VOLUME');
  const maxVol = Math.max(...d.v);
  for (let i = 0; i < n; i++) {{
    const x = xPos(i);
    const vH = (d.v[i] / maxVol) * pVol.h * 0.85;
    const bull = d.c[i] >= d.o[i];
    ctx.fillStyle = bull ? 'rgba(0,229,160,0.3)' : 'rgba(255,77,109,0.3)';
    ctx.fillRect(x - barW/2, pVol.t + pVol.h - vH, barW, vH);
  }}

  // ── RSI panel ──
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

  // ── MACD panel ──
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
      // zero line
      ctx.strokeStyle = 'rgba(255,255,255,0.08)'; ctx.lineWidth = 0.5;
      ctx.beginPath(); ctx.moveTo(L, pMacd.t + pMacd.h/2); ctx.lineTo(w-R, pMacd.t + pMacd.h/2); ctx.stroke();
      // histogram
      for (let i = 0; i < n; i++) {{
        const hv = d.macd_hist[i];
        if (hv === null) continue;
        const x = xPos(i);
        const zY = pMacd.t + pMacd.h/2;
        const bY = mScale(hv);
        ctx.fillStyle = hv >= 0 ? 'rgba(0,229,160,0.35)' : 'rgba(255,77,109,0.35)';
        ctx.fillRect(x - barW/2, Math.min(zY, bY), barW, Math.abs(bY - zY));
      }}
      // MACD line
      ctx.strokeStyle = '#3d9cf5'; ctx.lineWidth = 1.2; ctx.beginPath();
      let ms = false;
      d.macd.forEach((v,i) => {{ if (v===null) return; const x=xPos(i), y=mScale(v); if(!ms){{ctx.moveTo(x,y);ms=true;}}else ctx.lineTo(x,y); }});
      ctx.stroke();
      // Signal line
      ctx.strokeStyle = '#f5a623'; ctx.lineWidth = 1; ctx.setLineDash([3,2]); ctx.beginPath();
      let ss = false;
      d.macd_sig.forEach((v,i) => {{ if (v===null) return; const x=xPos(i), y=mScale(v); if(!ss){{ctx.moveTo(x,y);ss=true;}}else ctx.lineTo(x,y); }});
      ctx.stroke(); ctx.setLineDash([]);
    }}
  }}

  // Date labels at bottom
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
// Defer all canvas drawing until after layout is computed
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
  // grid
  ctx.strokeStyle = 'rgba(255,255,255,0.05)'; ctx.lineWidth = 0.5;
  ctx.font = '8px "Fira Code",monospace'; ctx.fillStyle = '#5c5d6e'; ctx.textAlign = 'right';
  for (let i = 0; i <= 4; i++) {{
    const val = barMx - (i / 4) * barRng;
    const y = pad.t + (i / 4) * ch;
    ctx.beginPath(); ctx.moveTo(pad.l, y); ctx.lineTo(W - pad.r, y); ctx.stroke();
    ctx.fillText(val >= 1000 ? (val/1000).toFixed(0)+'K' : val.toFixed(0), pad.l - 5, y + 3);
  }}
  // zero line
  if (barMn < 0) {{
    const zy = yBar(0);
    ctx.strokeStyle = 'rgba(255,255,255,0.12)'; ctx.lineWidth = 0.5;
    ctx.beginPath(); ctx.moveTo(pad.l, zy); ctx.lineTo(W - pad.r, zy); ctx.stroke();
  }}
  // bars
  const groupW = cw / n;
  const bw = Math.max(4, groupW * 0.3);
  for (let i = 0; i < n; i++) {{
    const cx = pad.l + (i + 0.5) * groupW;
    // Revenue bar
    const ry1 = yBar(revs[i]), ry0 = yBar(0);
    ctx.fillStyle = 'rgba(61,156,245,0.55)';
    ctx.fillRect(cx - bw - 1, Math.min(ry0, ry1), bw, Math.abs(ry1 - ry0));
    // Profit bar
    const py1 = yBar(profs[i]), py0 = yBar(0);
    ctx.fillStyle = profs[i] >= 0 ? 'rgba(0,229,160,0.55)' : 'rgba(255,77,109,0.55)';
    ctx.fillRect(cx + 1, Math.min(py0, py1), bw, Math.abs(py1 - py0));
    // Label
    ctx.fillStyle = '#5c5d6e'; ctx.font = '8px "Fira Code",monospace'; ctx.textAlign = 'center';
    ctx.fillText(items[i].label, cx, H - 6);
  }}
  // EPS line (right axis)
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
    // right axis labels
    ctx.fillStyle = '#f5a623'; ctx.font = '7px "Fira Code",monospace'; ctx.textAlign = 'left';
    for (let i = 0; i <= 3; i++) {{
      const val = eMx - (i / 3) * eRng;
      const y = pad.t + (i / 3) * ch;
      ctx.fillText('₹'+val.toFixed(1), W - pad.r + 4, y + 3);
    }}
  }}
  // Legend
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
// fin-toggle button binding (drawing is triggered from DOMContentLoaded)
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
// eps-toggle button binding
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

// EPS Estimate vs Actual chart
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
    // EPS trend from financial data
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
    // grid
    ctx.strokeStyle = 'rgba(255,255,255,0.05)'; ctx.lineWidth = 0.5;
    ctx.font = '8px "Fira Code",monospace'; ctx.fillStyle = '#5c5d6e'; ctx.textAlign = 'right';
    for (let i = 0; i <= 4; i++) {{
      const val = mx - (i / 4) * rng;
      const y = pad.t + (i / 4) * ch;
      ctx.beginPath(); ctx.moveTo(pad.l, y); ctx.lineTo(W - pad.r, y); ctx.stroke();
      ctx.fillText('₹'+val.toFixed(1), pad.l - 5, y + 3);
    }}
    const groupW = cw / n;
    const barW = Math.max(12, Math.min(40, groupW * 0.5));
    const zeroY = yV(0);
    // bars + value labels
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
      // EPS value above bar
      ctx.fillStyle = '#e8e9f0'; ctx.font = '9px "Fira Code",monospace'; ctx.textAlign = 'center';
      ctx.fillText('₹' + d.eps.toFixed(1), x, ey - 8);
      // x-axis quarter/year label
      ctx.fillStyle = '#9899a8'; ctx.font = '9px "Fira Code",monospace'; ctx.textAlign = 'center';
      ctx.fillText(d.label, x, H - 10);
    }});
    // Legend
    ctx.font = '9px "Fira Code",monospace'; ctx.textAlign = 'left'; ctx.fillStyle = '#9899a8';
    ctx.fillText(mode === 'quarterly' ? 'Quarterly EPS (₹/share)' : 'Annual EPS (₹/share)', pad.l + 4, pad.t - 14);
    return;
  }}

  // Estimates mode (default)
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
  // grid
  ctx.strokeStyle = 'rgba(255,255,255,0.05)'; ctx.lineWidth = 0.5;
  ctx.font = '8px "Fira Code",monospace'; ctx.fillStyle = '#5c5d6e'; ctx.textAlign = 'right';
  for (let i = 0; i <= 4; i++) {{
    const val = mx - (i / 4) * rng;
    const y = pad.t + (i / 4) * ch;
    ctx.beginPath(); ctx.moveTo(pad.l, y); ctx.lineTo(W - pad.r, y); ctx.stroke();
    ctx.fillText('₹'+val.toFixed(1), pad.l - 5, y + 3);
  }}
  const groupW = cw / n;
  const dotR = 6;
  // Thin vertical connector between estimate and actual
  EPS_EST.forEach((d, i) => {{
    if (d.estimate === null || d.actual === null) return;
    const x = pad.l + (i + 0.5) * groupW;
    ctx.strokeStyle = 'rgba(255,255,255,0.08)'; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(x, yV(d.estimate)); ctx.lineTo(x, yV(d.actual)); ctx.stroke();
  }});
  // Dots + EPS values + surprise %
  EPS_EST.forEach((d, i) => {{
    const x = pad.l + (i + 0.5) * groupW;
    const hasEst = d.estimate !== null;
    const hasAct = d.actual !== null;
    const beat = hasAct && hasEst && d.actual >= d.estimate;
    // Estimate dot (left offset)
    if (hasEst) {{
      const ex = x - 8;
      const ey = yV(d.estimate);
      ctx.beginPath(); ctx.arc(ex, ey, dotR, 0, Math.PI*2);
      ctx.fillStyle = '#9b7fff'; ctx.fill();
      ctx.strokeStyle = '#08090d'; ctx.lineWidth = 1.5; ctx.stroke();
      ctx.fillStyle = '#9b7fff'; ctx.font = '8px "Fira Code",monospace'; ctx.textAlign = 'right';
      ctx.fillText('₹' + d.estimate.toFixed(1), ex - 9, ey + 3);
    }}
    // Actual dot (right offset)
    if (hasAct) {{
      const ax = x + 8;
      const ay = yV(d.actual);
      ctx.beginPath(); ctx.arc(ax, ay, dotR, 0, Math.PI*2);
      ctx.fillStyle = beat ? '#00e5a0' : '#ff4d6d'; ctx.fill();
      ctx.strokeStyle = '#08090d'; ctx.lineWidth = 1.5; ctx.stroke();
      ctx.fillStyle = beat ? '#00e5a0' : '#ff4d6d'; ctx.font = '8px "Fira Code",monospace'; ctx.textAlign = 'left';
      ctx.fillText('₹' + d.actual.toFixed(1), ax + 9, ay + 3);
    }}
    // Surprise % below the pair
    if (d.surprise !== null) {{
      ctx.font = '9px "Fira Code",monospace'; ctx.textAlign = 'center';
      ctx.fillStyle = d.surprise >= 0 ? '#00e5a0' : '#ff4d6d';
      const bottomY = Math.max(hasEst ? yV(d.estimate) : 0, hasAct ? yV(d.actual) : 0);
      ctx.fillText((d.surprise >= 0 ? '+' : '') + d.surprise.toFixed(1) + '%', x, bottomY + 18);
    }}
    // x label
    ctx.fillStyle = '#5c5d6e'; ctx.font = '7px "Fira Code",monospace'; ctx.textAlign = 'center';
    ctx.fillText(d.label, x, H - 8);
  }});
  // Legend
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

GITHUB_REPORT_BASE = "https://htmlpreview.github.io/?https://github.com/nageshnnazare/recos/blob/main/reports"


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
        row = f"| {ticker} | ₹{current:,.2f} | {scores['composite']}/100 | {signal} | {upside:+.1f}% | [Report]({report_url}) |"
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
    parser.add_argument("--delay", type=int, default=5, help="Seconds to wait between stocks to avoid rate-limiting (default: 5)")

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

    # Clean up reports older than 15 days
    removed = cleanup_old_reports(reports_root, keep_days=15)
    if removed:
        print(f"🧹 Cleaned up {removed} report folder(s) older than 15 days")

    print("=" * 62)
    print("  NSE Stock Risk Score Report Generator")
    print("  No API Key Required · Powered by yfinance")
    print(f"  Stocks: {', '.join(tickers)}")
    print(f"  Date:   {today_str}")
    print(f"  Output: {os.path.abspath(output_dir)}/")
    print("=" * 62)
    print()

    results = []
    delay = args.delay

    for i, ticker in enumerate(tickers, 1):
        # Throttle between stocks to avoid Screener.in rate-limiting
        if i > 1 and delay > 0:
            jitter = random.uniform(0, delay * 0.4)
            wait = delay + jitter
            print(f"  ⏳ Waiting {wait:.1f}s before next stock...")
            time.sleep(wait)

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
    print(f"  📅 Keeping last 15 days of reports")
    print(f"{'=' * 62}\n")


if __name__ == "__main__":
    main()
