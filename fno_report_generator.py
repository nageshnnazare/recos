#!/usr/bin/env python3
"""
NSE F&O Index Outlook Report (NIFTY 50 & NIFTY BANK)
-----------------------------------------------------
Fetches option chain data (OI, IV, greeks, LTP) from Groww's SSR page and index
breadth from NSE's equity-stockIndices API.  Derives PCR, max-pain, ATM
positioning, recommends a strategy with interactive P&L simulation, and scrapes
market headlines from public RSS.

Not investment advice.
"""

from __future__ import annotations

import argparse
import html as html_mod
import json
import math
import os
import re
import shutil
import sys
import time
import urllib.parse
import xml.etree.ElementTree as ET

import requests
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

EQUITY_STOCK_INDICES = "https://www.nseindia.com/api/equity-stockIndices"

GROWW_OC_URLS: dict[str, str] = {
    "NIFTY": "https://groww.in/options/nifty",
    "BANKNIFTY": "https://groww.in/options/nifty-bank",
}

INDEX_PROFILES: dict[str, dict[str, str]] = {
    "NIFTY": {"label": "NIFTY 50", "chain_symbol": "NIFTY", "breadth_index": "NIFTY 50"},
    "BANKNIFTY": {"label": "NIFTY BANK", "chain_symbol": "BANKNIFTY", "breadth_index": "NIFTY BANK"},
}

NEWS_FEEDS = [
    ("Google News", "https://news.google.com/rss/search?q=NIFTY+OR+Bank+Nifty+OR+NSE+index+options&hl=en-IN&gl=IN&ceid=IN:en"),
    ("Economic Times", "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms"),
]

NEWS_KW = re.compile(r"\b(nifty|bank\s*nifty|sensex|nse|fno|f&o|future|option|call|put|derivative|index)\b", re.I)


# ─── Data structures ────────────────────────────────────────────────────────

@dataclass
class ChainRow:
    strike: float
    ce_oi: float = 0; ce_chg_oi: float = 0; ce_iv: float = 0; ce_ltp: float = 0
    ce_change: float = 0; ce_change_pct: float = 0
    ce_delta: float = 0; ce_gamma: float = 0; ce_theta: float = 0; ce_vega: float = 0
    pe_oi: float = 0; pe_chg_oi: float = 0; pe_iv: float = 0; pe_ltp: float = 0
    pe_change: float = 0; pe_change_pct: float = 0
    pe_delta: float = 0; pe_gamma: float = 0; pe_theta: float = 0; pe_vega: float = 0


@dataclass
class StrategyLeg:
    kind: str  # "CE" or "PE"
    strike: float
    action: str  # "BUY" or "SELL"
    premium: float
    lots: int = 1


@dataclass
class Strategy:
    name: str
    bias: str
    legs: list[StrategyLeg] = field(default_factory=list)
    lot_size: int = 1
    spot: float = 0
    max_profit: float | None = None
    max_loss: float | None = None
    breakevens: list[float] = field(default_factory=list)
    reasoning: str = ""


@dataclass
class IndexReport:
    label: str
    chain_symbol: str
    spot: float = 0; spot_source: str = ""
    index_change_pct: float = 0
    advances: int = 0; declines: int = 0; unchanged: int = 0
    chain_ok: bool = False
    expiry: str = ""
    lot_size: int = 1
    chain_rows: list[ChainRow] = field(default_factory=list)
    total_ce_oi: float = 0; total_pe_oi: float = 0
    total_ce_oi_chg: float = 0; total_pe_oi_chg: float = 0
    pcr_oi: float | None = None
    max_pain: float | None = None; max_pain_dist_pct: float | None = None
    atm_strike: float = 0
    verdict: str = "Neutral"; verdict_tone: str = "neutral"; confidence: str = "Low"
    reasoning: list[str] = field(default_factory=list)
    strategy: Strategy | None = None
    data_notes: list[str] = field(default_factory=list)


# ─── Data fetching ──────────────────────────────────────────────────────────

def fetch_index_breadth(index_name: str) -> dict[str, Any] | None:
    q = urllib.parse.quote(index_name, safe="")
    try:
        r = requests.get(
            f"{EQUITY_STOCK_INDICES}?index={q}",
            headers={"user-agent": UA, "accept": "application/json", "referer": "https://www.nseindia.com/"},
            timeout=20,
        )
        data = r.json() if r.ok else None
    except (requests.RequestException, ValueError):
        data = None
    if not data or "data" not in data or not data["data"]:
        return None
    row = data["data"][0]
    adv = data.get("advance") or {}
    return {
        "last": float(row.get("lastPrice") or 0),
        "pchange": float(row.get("pChange") or 0),
        "advances": int(adv.get("advances") or 0),
        "declines": int(adv.get("declines") or 0),
        "unchanged": int(adv.get("unchanged") or 0),
    }


_NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


def fetch_groww_chain(key: str) -> dict[str, Any] | None:
    url = GROWW_OC_URLS.get(key)
    if not url:
        return None
    try:
        r = requests.get(url, headers={"user-agent": UA}, timeout=25)
        if not r.ok:
            return None
        m = _NEXT_DATA_RE.search(r.text)
        if not m:
            return None
        return json.loads(m.group(1))
    except (requests.RequestException, json.JSONDecodeError, ValueError):
        return None


def _f(x: Any) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def parse_groww_chain(nd: dict[str, Any]) -> tuple[list[ChainRow], str, int]:
    data = nd.get("props", {}).get("pageProps", {}).get("data", {})
    oc = data.get("optionChain", {})
    contracts = oc.get("optionContracts") or []
    agg = oc.get("aggregatedDetails") or {}
    expiry = agg.get("currentExpiry") or ""
    lot_size = int(agg.get("lotSize") or 1)
    rows: list[ChainRow] = []
    for c in contracts:
        strike = _f(c.get("strikePrice")) / 100.0
        ce = c.get("ce") or {}
        pe = c.get("pe") or {}
        cl = ce.get("liveData") or {}
        pl = pe.get("liveData") or {}
        cg = ce.get("greeks") or {}
        pg = pe.get("greeks") or {}
        rows.append(ChainRow(
            strike=strike,
            ce_oi=_f(cl.get("oi")), ce_chg_oi=_f(cl.get("oi")) - _f(cl.get("prevOI")),
            ce_iv=_f(cg.get("iv")), ce_ltp=_f(cl.get("ltp")),
            ce_change=_f(cl.get("dayChange")), ce_change_pct=_f(cl.get("dayChangePerc")),
            ce_delta=_f(cg.get("delta")), ce_gamma=_f(cg.get("gamma")),
            ce_theta=_f(cg.get("theta")), ce_vega=_f(cg.get("vega")),
            pe_oi=_f(pl.get("oi")), pe_chg_oi=_f(pl.get("oi")) - _f(pl.get("prevOI")),
            pe_iv=_f(pg.get("iv")), pe_ltp=_f(pl.get("ltp")),
            pe_change=_f(pl.get("dayChange")), pe_change_pct=_f(pl.get("dayChangePerc")),
            pe_delta=_f(pg.get("delta")), pe_gamma=_f(pg.get("gamma")),
            pe_theta=_f(pg.get("theta")), pe_vega=_f(pg.get("vega")),
        ))
    return rows, expiry, lot_size


# ─── Analysis ───────────────────────────────────────────────────────────────

def compute_max_pain(rows: list[ChainRow]) -> float | None:
    strikes = sorted({r.strike for r in rows if r.strike > 0})
    if not strikes:
        return None
    best, best_pain = strikes[0], float("inf")
    for s in strikes:
        pain = sum(r.ce_oi * max(0, s - r.strike) + r.pe_oi * max(0, r.strike - s) for r in rows)
        if pain < best_pain:
            best_pain, best = pain, s
    return best


def analyze(key: str, breadth: dict[str, Any] | None, gw: dict[str, Any] | None) -> IndexReport:
    prof = INDEX_PROFILES[key]
    rpt = IndexReport(label=prof["label"], chain_symbol=prof["chain_symbol"])
    if breadth:
        rpt.spot = breadth["last"]
        rpt.spot_source = "NSE cash index"
        rpt.index_change_pct = breadth["pchange"]
        rpt.advances = breadth["advances"]
        rpt.declines = breadth["declines"]
        rpt.unchanged = breadth["unchanged"]

    if gw:
        rows, expiry, lot = parse_groww_chain(gw)
        if rows:
            rpt.chain_ok = True
            rpt.chain_rows = rows
            rpt.expiry = expiry
            rpt.lot_size = lot

    if not rpt.chain_ok:
        rpt.data_notes.append("Option chain data unavailable. Analysis uses only cash index breadth.")
        _breadth_verdict(rpt)
        return rpt

    for r in rpt.chain_rows:
        rpt.total_ce_oi += r.ce_oi
        rpt.total_pe_oi += r.pe_oi
        rpt.total_ce_oi_chg += r.ce_chg_oi
        rpt.total_pe_oi_chg += r.pe_chg_oi

    if rpt.total_ce_oi > 0:
        rpt.pcr_oi = rpt.total_pe_oi / rpt.total_ce_oi

    rpt.max_pain = compute_max_pain(rpt.chain_rows)
    if rpt.max_pain and rpt.spot:
        rpt.max_pain_dist_pct = (rpt.spot - rpt.max_pain) / rpt.max_pain * 100

    if rpt.spot:
        atm = min(rpt.chain_rows, key=lambda r: abs(r.strike - rpt.spot))
        rpt.atm_strike = atm.strike

    _fno_reasoning(rpt)
    _fno_verdict(rpt)
    rpt.strategy = recommend_strategy(rpt)
    return rpt


def _ad_ratio(rpt: IndexReport) -> float | None:
    return rpt.advances / max(1, rpt.declines) if rpt.declines > 0 else None


def _breadth_verdict(rpt: IndexReport):
    pc = rpt.index_change_pct
    ar = _ad_ratio(rpt)
    if pc and pc > 0.35 and (ar is None or ar >= 1.0):
        rpt.verdict, rpt.verdict_tone, rpt.confidence = "Mildly constructive (breadth)", "up", "Low"
    elif pc and pc < -0.35 and (ar is None or ar <= 1.0):
        rpt.verdict, rpt.verdict_tone, rpt.confidence = "Mildly cautious (breadth)", "down", "Low"
    else:
        rpt.verdict, rpt.verdict_tone, rpt.confidence = "Neutral (limited data)", "neutral", "Low"
    if pc is not None:
        rpt.reasoning.append(f"Cash index change {pc:+.2f}%.")
    if ar is not None:
        rpt.reasoning.append(f"Breadth A/D ≈ {ar:.2f} ({rpt.advances} up / {rpt.declines} down).")


def _fno_reasoning(rpt: IndexReport):
    if rpt.pcr_oi is not None:
        rpt.reasoning.append(
            f"Put–call ratio (OI) = {rpt.pcr_oi:.3f}. "
            "Low PCR suggests crowded calls (mean-reversion risk); high PCR indicates hedging/bearish positioning."
        )
    if rpt.max_pain is not None and rpt.spot:
        d = rpt.max_pain_dist_pct or 0
        rpt.reasoning.append(
            f"Max pain ≈ {rpt.max_pain:,.0f} vs spot ≈ {rpt.spot:,.0f} ({d:+.2f}%). "
            "Near expiry, price tends to gravitate toward max pain."
        )
    rpt.reasoning.append(
        f"Session ΔOI: calls {rpt.total_ce_oi_chg:+,.0f}, puts {rpt.total_pe_oi_chg:+,.0f}. "
        "Fresh OI in the direction of the move implies trend conviction; against the move implies hedging."
    )
    atm_row = None
    if rpt.spot and rpt.chain_rows:
        atm_row = min(rpt.chain_rows, key=lambda r: abs(r.strike - rpt.spot))
    if atm_row:
        rpt.reasoning.append(
            f"ATM ({atm_row.strike:,.0f}): CE OI {atm_row.ce_oi:,.0f} vs PE OI {atm_row.pe_oi:,.0f}, "
            f"CE IV {atm_row.ce_iv:.1f}% / PE IV {atm_row.pe_iv:.1f}%."
        )
    ar = _ad_ratio(rpt)
    if ar is not None:
        rpt.reasoning.append(f"Cash index breadth: {rpt.advances} up / {rpt.declines} down (A/D ≈ {ar:.2f}).")


def _fno_verdict(rpt: IndexReport):
    score, n = 0.0, 0
    if rpt.pcr_oi is not None:
        n += 1
        if rpt.pcr_oi < 0.75:
            score -= 0.7
        elif rpt.pcr_oi > 1.45:
            score += 0.4
        elif 0.85 <= rpt.pcr_oi <= 1.25:
            pass
        else:
            score += 0.15 if rpt.pcr_oi > 1 else -0.15
    if rpt.max_pain_dist_pct is not None:
        n += 1
        if rpt.max_pain_dist_pct > 0.4:
            score -= 0.35
        elif rpt.max_pain_dist_pct < -0.4:
            score += 0.35
    net = rpt.total_ce_oi_chg - rpt.total_pe_oi_chg
    if abs(net) > 1:
        n += 1
        score += -0.25 if net > 0 else 0.25
    if rpt.index_change_pct:
        n += 1
        score += 0.4 if rpt.index_change_pct > 0.2 else (-0.4 if rpt.index_change_pct < -0.2 else 0)
    ar = _ad_ratio(rpt)
    if ar is not None:
        n += 1
        score += 0.35 if ar >= 1.2 else (-0.35 if ar <= 0.85 else 0)
    conf = "Medium" if n >= 4 else "Low"
    if score > 0.45:
        rpt.verdict, rpt.verdict_tone, rpt.confidence = "Bias: upward drift (F&O + breadth)", "up", conf
    elif score < -0.45:
        rpt.verdict, rpt.verdict_tone, rpt.confidence = "Bias: downward drift (F&O + breadth)", "down", conf
    else:
        rpt.verdict, rpt.verdict_tone, rpt.confidence = "Neutral / two-sided (mixed signals)", "neutral", conf


# ─── Strategy recommendation ────────────────────────────────────────────────

def _nearest(rows: list[ChainRow], target: float) -> ChainRow | None:
    return min(rows, key=lambda r: abs(r.strike - target)) if rows else None


def recommend_strategy(rpt: IndexReport) -> Strategy | None:
    if not rpt.chain_ok or not rpt.spot or not rpt.chain_rows:
        return None
    spot = rpt.spot
    rows = [r for r in rpt.chain_rows if r.strike > 0 and (r.ce_ltp > 0 or r.pe_ltp > 0)]
    if len(rows) < 5:
        return None
    atm = _nearest(rows, spot)
    if not atm:
        return None

    avg_iv = atm.ce_iv * 0.5 + atm.pe_iv * 0.5
    high_iv = avg_iv > 25

    step = rows[1].strike - rows[0].strike if len(rows) > 1 else 50.0
    if step <= 0:
        step = 50.0

    if rpt.verdict_tone == "up":
        if high_iv:
            return _bull_put_spread(rpt, rows, atm, step)
        return _bull_call_spread(rpt, rows, atm, step)
    elif rpt.verdict_tone == "down":
        if high_iv:
            return _bear_call_spread(rpt, rows, atm, step)
        return _bear_put_spread(rpt, rows, atm, step)
    else:
        if high_iv:
            return _iron_condor(rpt, rows, atm, step)
        return _long_straddle(rpt, rows, atm)


def _make_strat(name: str, bias: str, legs: list[StrategyLeg], rpt: IndexReport, reasoning: str) -> Strategy:
    s = Strategy(name=name, bias=bias, legs=legs, lot_size=rpt.lot_size, spot=rpt.spot, reasoning=reasoning)
    _compute_pnl_bounds(s)
    return s


def _compute_pnl_bounds(s: Strategy):
    lo = min(l.strike for l in s.legs) - 500
    hi = max(l.strike for l in s.legs) + 500
    pts = [lo + (hi - lo) * i / 500 for i in range(501)]
    pnls = [_pnl_at(s, p) for p in pts]
    s.max_profit = max(pnls)
    s.max_loss = min(pnls)
    bes: list[float] = []
    for i in range(1, len(pnls)):
        if pnls[i - 1] * pnls[i] < 0:
            bes.append(round(pts[i], 2))
    s.breakevens = bes


def _pnl_at(s: Strategy, price: float) -> float:
    total = 0.0
    for l in s.legs:
        if l.kind == "CE":
            intrinsic = max(0, price - l.strike)
        else:
            intrinsic = max(0, l.strike - price)
        if l.action == "BUY":
            total += (intrinsic - l.premium) * l.lots * s.lot_size
        else:
            total += (l.premium - intrinsic) * l.lots * s.lot_size
    return total


def _bull_call_spread(rpt, rows, atm, step):
    buy_k = atm.strike
    sell_row = _nearest(rows, buy_k + 2 * step)
    if not sell_row or sell_row.strike <= buy_k:
        sell_row = _nearest(rows, buy_k + step)
    if not sell_row or sell_row.ce_ltp <= 0:
        return None
    return _make_strat("Bull Call Spread", "Bullish", [
        StrategyLeg("CE", buy_k, "BUY", atm.ce_ltp),
        StrategyLeg("CE", sell_row.strike, "SELL", sell_row.ce_ltp),
    ], rpt, f"Buy {buy_k:,.0f} CE @ {atm.ce_ltp:.2f}, Sell {sell_row.strike:,.0f} CE @ {sell_row.ce_ltp:.2f}. "
       "Net debit strategy that profits from a moderate upside move. Capped risk and reward.")


def _bull_put_spread(rpt, rows, atm, step):
    sell_k = atm.strike
    buy_row = _nearest(rows, sell_k - 2 * step)
    if not buy_row or buy_row.strike >= sell_k:
        buy_row = _nearest(rows, sell_k - step)
    if not buy_row or buy_row.pe_ltp <= 0:
        return None
    return _make_strat("Bull Put Spread", "Bullish (IV-friendly)", [
        StrategyLeg("PE", sell_k, "SELL", atm.pe_ltp),
        StrategyLeg("PE", buy_row.strike, "BUY", buy_row.pe_ltp),
    ], rpt, f"Sell {sell_k:,.0f} PE @ {atm.pe_ltp:.2f}, Buy {buy_row.strike:,.0f} PE @ {buy_row.pe_ltp:.2f}. "
       "Net credit strategy benefiting from time decay and bullish bias. High IV inflates the credit received.")


def _bear_put_spread(rpt, rows, atm, step):
    buy_k = atm.strike
    sell_row = _nearest(rows, buy_k - 2 * step)
    if not sell_row or sell_row.strike >= buy_k:
        sell_row = _nearest(rows, buy_k - step)
    if not sell_row or sell_row.pe_ltp <= 0:
        return None
    return _make_strat("Bear Put Spread", "Bearish", [
        StrategyLeg("PE", buy_k, "BUY", atm.pe_ltp),
        StrategyLeg("PE", sell_row.strike, "SELL", sell_row.pe_ltp),
    ], rpt, f"Buy {buy_k:,.0f} PE @ {atm.pe_ltp:.2f}, Sell {sell_row.strike:,.0f} PE @ {sell_row.pe_ltp:.2f}. "
       "Net debit strategy profiting from downside. Limited risk with defined reward.")


def _bear_call_spread(rpt, rows, atm, step):
    sell_k = atm.strike
    buy_row = _nearest(rows, sell_k + 2 * step)
    if not buy_row or buy_row.strike <= sell_k:
        buy_row = _nearest(rows, sell_k + step)
    if not buy_row or buy_row.ce_ltp <= 0:
        return None
    return _make_strat("Bear Call Spread", "Bearish (IV-friendly)", [
        StrategyLeg("CE", sell_k, "SELL", atm.ce_ltp),
        StrategyLeg("CE", buy_row.strike, "BUY", buy_row.ce_ltp),
    ], rpt, f"Sell {sell_k:,.0f} CE @ {atm.ce_ltp:.2f}, Buy {buy_row.strike:,.0f} CE @ {buy_row.ce_ltp:.2f}. "
       "Net credit strategy benefiting from time decay and bearish bias. High IV benefits the credit leg.")


def _iron_condor(rpt, rows, atm, step):
    sell_ce_row = _nearest(rows, atm.strike + 2 * step)
    buy_ce_row = _nearest(rows, atm.strike + 4 * step)
    sell_pe_row = _nearest(rows, atm.strike - 2 * step)
    buy_pe_row = _nearest(rows, atm.strike - 4 * step)
    if not all([sell_ce_row, buy_ce_row, sell_pe_row, buy_pe_row]):
        return None
    if any(r.ce_ltp <= 0 and r.pe_ltp <= 0 for r in [sell_ce_row, buy_ce_row, sell_pe_row, buy_pe_row]):
        return None
    return _make_strat("Iron Condor", "Neutral (high IV)", [
        StrategyLeg("CE", sell_ce_row.strike, "SELL", sell_ce_row.ce_ltp),
        StrategyLeg("CE", buy_ce_row.strike, "BUY", buy_ce_row.ce_ltp),
        StrategyLeg("PE", sell_pe_row.strike, "SELL", sell_pe_row.pe_ltp),
        StrategyLeg("PE", buy_pe_row.strike, "BUY", buy_pe_row.pe_ltp),
    ], rpt,
        f"Sell {sell_ce_row.strike:,.0f} CE + Sell {sell_pe_row.strike:,.0f} PE, "
        f"Buy {buy_ce_row.strike:,.0f} CE + Buy {buy_pe_row.strike:,.0f} PE. "
        "Net credit strategy that profits if index stays within the sold strikes. High IV maximises the premium collected."
    )


def _long_straddle(rpt, rows, atm):
    if atm.ce_ltp <= 0 or atm.pe_ltp <= 0:
        return None
    return _make_strat("Long Straddle", "Neutral (expects big move)", [
        StrategyLeg("CE", atm.strike, "BUY", atm.ce_ltp),
        StrategyLeg("PE", atm.strike, "BUY", atm.pe_ltp),
    ], rpt,
        f"Buy {atm.strike:,.0f} CE @ {atm.ce_ltp:.2f} + Buy {atm.strike:,.0f} PE @ {atm.pe_ltp:.2f}. "
        "Net debit strategy that profits from a large move in either direction. Low IV makes the entry cheaper."
    )


# ─── News ───────────────────────────────────────────────────────────────────

def fetch_rss_articles(max_per_feed: int = 8) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    hdr = {"user-agent": UA, "accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.8"}
    for source, url in NEWS_FEEDS:
        try:
            r = requests.get(url, headers=hdr, timeout=20)
            if not r.ok:
                continue
            root = ET.fromstring(r.content)
            ch = root.find("channel")
            if ch is None:
                continue
            for item in ch.findall("item")[:max_per_feed]:
                t = (item.findtext("title") or "").strip()
                lnk = (item.findtext("link") or "").strip()
                pub = (item.findtext("pubDate") or "").strip()
                if t and NEWS_KW.search(t):
                    out.append({"source": source, "title": t, "link": lnk, "pub": pub})
        except (ET.ParseError, requests.RequestException, ValueError):
            continue
    seen: set[str] = set()
    deduped: list[dict[str, str]] = []
    for a in out:
        k = a["title"][:120].lower()
        if k not in seen:
            seen.add(k)
            deduped.append(a)
    return deduped[:18]


# ─── HTML generation ────────────────────────────────────────────────────────

def _esc(s: str) -> str:
    return html_mod.escape(s)


def _num(v: float, decimals: int = 0) -> str:
    if decimals == 0:
        return f"{v:,.0f}"
    return f"{v:,.{decimals}f}"


def _strategy_json(s: Strategy) -> str:
    legs = []
    for l in s.legs:
        legs.append({"kind": l.kind, "strike": l.strike, "action": l.action, "premium": l.premium, "lots": l.lots})
    return json.dumps({"legs": legs, "lot_size": s.lot_size, "spot": s.spot}, separators=(",", ":"))


_LIVE_JS = """<script>
(function(){
  const SYMBOLS = ['nifty','banknifty'];
  let interval = 30;
  let timer = null;
  let lastData = {};

  /* Build live control bar */
  const slot = document.getElementById('live-bar-slot');
  if(slot) {
    slot.innerHTML = `
    <div class="live-bar">
      <div class="lb-status"><span class="live-dot"></span> LIVE — auto-refresh every
        <select id="live-interval">
          <option value="15">15s</option>
          <option value="30" selected>30s</option>
          <option value="60">1m</option>
          <option value="120">2m</option>
        </select>
      </div>
      <div><span class="lb-ts" id="live-ts">Waiting for first refresh…</span>
        <button id="live-now">Refresh now</button></div>
    </div>`;
    document.getElementById('live-interval').addEventListener('change', function(){
      interval = parseInt(this.value);
      restart();
    });
    document.getElementById('live-now').addEventListener('click', refreshAll);
  }

  function fmtNum(v, dec){
    if(v==null || isNaN(v)) return '—';
    return dec===0 ? v.toLocaleString('en-IN',{maximumFractionDigits:0})
                   : v.toLocaleString('en-IN',{minimumFractionDigits:dec, maximumFractionDigits:dec});
  }

  function clsFor(v){ return v>=0 ? 'pos' : 'neg'; }

  function buildChainRow(r, spot, stepSize){
    const isAtm = Math.abs(r.strike - spot) < stepSize * 0.6;
    const ac = isAtm ? ' class="atm-row"' : '';
    return `<tr${ac}>` +
      `<td>${fmtNum(r.ce_oi,0)}</td><td class="${clsFor(r.ce_chg_oi)}">${fmtNum(r.ce_chg_oi,0)}</td>` +
      `<td>${r.ce_iv.toFixed(1)}</td><td>${r.ce_ltp.toFixed(2)}</td>` +
      `<td class="${clsFor(r.ce_change)}">${r.ce_change>=0?'+':''}${r.ce_change.toFixed(2)}</td>` +
      `<td>${r.ce_delta.toFixed(4)}</td><td>${r.ce_theta.toFixed(2)}</td>` +
      `<td class="strike-col">${fmtNum(r.strike,0)}</td>` +
      `<td>${r.pe_theta.toFixed(2)}</td><td>${r.pe_delta.toFixed(4)}</td>` +
      `<td class="${clsFor(r.pe_change)}">${r.pe_change>=0?'+':''}${r.pe_change.toFixed(2)}</td>` +
      `<td>${r.pe_ltp.toFixed(2)}</td><td>${r.pe_iv.toFixed(1)}</td>` +
      `<td class="${clsFor(r.pe_chg_oi)}">${fmtNum(r.pe_chg_oi,0)}</td><td>${fmtNum(r.pe_oi,0)}</td>` +
      `</tr>`;
  }

  function updateIndex(slug, d){
    const prev = lastData[slug];
    lastData[slug] = d;

    /* KPIs */
    const grid = document.getElementById('kpi-'+slug);
    if(grid){
      const kv = (sel,val) => { const el=grid.querySelector('[data-kpi="'+sel+'"]'); if(el) el.textContent=val; };
      kv('spot', fmtNum(d.spot,2));
      kv('index_change_pct', (d.index_change_pct>=0?'+':'')+d.index_change_pct.toFixed(2)+'%');
      kv('pcr_oi', d.pcr_oi!=null ? d.pcr_oi.toFixed(3) : '—');
      kv('max_pain', d.max_pain!=null ? fmtNum(d.max_pain,0) : '—');
      kv('max_pain_dist', 'Δ '+(d.max_pain_dist_pct!=null ? (d.max_pain_dist_pct>=0?'+':'')+d.max_pain_dist_pct.toFixed(2)+'%' : '—'));
      kv('ad', d.advances+' / '+d.declines);
      kv('confidence', d.confidence);
    }

    /* Verdict */
    const vb = document.getElementById('verdict-badge-'+slug);
    if(vb){
      vb.textContent = d.verdict;
      vb.className = 'badge ' + ({up:'tone-up',down:'tone-down'}[d.verdict_tone]||'tone-n');
    }

    /* Reasoning */
    const rl = document.getElementById('reasons-'+slug);
    if(rl && d.reasoning){
      rl.innerHTML = d.reasoning.map(r => '<li>'+r.replace(/</g,'&lt;')+'</li>').join('');
    }

    /* Chain table */
    const tbody = document.getElementById('chain-tbody-'+slug);
    if(tbody && d.chain && d.chain.length){
      const spot = d.spot || 0;
      const visible = d.chain.filter(r => Math.abs(r.strike - spot) <= spot * 0.08);
      const rows = visible.length ? visible : d.chain;
      const step = rows.length>1 ? rows[1].strike - rows[0].strike : 50;
      tbody.innerHTML = rows.map(r => buildChainRow(r, spot, step)).join('');

      /* Flash changed cells — compare LTPs */
      if(prev && prev.chain){
        const prevMap = {};
        prev.chain.forEach(r => { prevMap[r.strike] = r; });
        tbody.querySelectorAll('tr').forEach((tr,i) => {
          const r = rows[i];
          const p = prevMap[r.strike];
          if(!p) return;
          if(r.ce_ltp !== p.ce_ltp || r.pe_ltp !== p.pe_ltp){
            const cls = (r.ce_ltp > p.ce_ltp || r.pe_ltp > p.pe_ltp) ? 'flash-up' : 'flash-dn';
            tr.classList.add(cls);
            setTimeout(() => tr.classList.remove(cls), 600);
          }
        });
      }
    }
  }

  function refreshAll(){
    const tsEl = document.getElementById('live-ts');
    if(tsEl) tsEl.textContent = 'Refreshing…';
    SYMBOLS.forEach(slug => {
      fetch('/api/chain/'+slug.toUpperCase())
        .then(r => r.json())
        .then(d => {
          updateIndex(slug, d);
          if(tsEl) tsEl.textContent = 'Last update: '+d.ts;
        })
        .catch(e => { if(tsEl) tsEl.textContent = 'Error: '+e.message; });
    });
  }

  function restart(){
    if(timer) clearInterval(timer);
    timer = setInterval(refreshAll, interval*1000);
  }

  /* Initial refresh after 2s, then on interval */
  setTimeout(refreshAll, 2000);
  restart();
})();
</script>"""


def generate_html(reports: list[IndexReport], news: list[dict[str, str]], gen_at: str, live_mode: bool = False) -> str:
    idx_tabs = ""
    idx_contents = ""
    strategies_json: list[str] = []

    for i, rpt in enumerate(reports):
        slug = rpt.chain_symbol.lower()
        active = " active" if i == 0 else ""
        idx_tabs += f'<button class="idx-tab{active}" data-idx="{slug}">{_esc(rpt.label)}</button>'
        idx_contents += _build_index_block(rpt, slug, active, i)
        if rpt.strategy:
            strategies_json.append(f'"{slug}": {_strategy_json(rpt.strategy)}')

    strat_obj = "{" + ",".join(strategies_json) + "}"

    news_html = ""
    for a in news:
        news_html += (
            f'<div class="news-item"><a class="nw-link" href="{_esc(a["link"])}" target="_blank" rel="noopener">'
            f'{_esc(a["title"])}</a><div class="nw-meta">{_esc(a["source"])} · {_esc(a.get("pub",""))}</div></div>'
        )
    if not news_html:
        news_html = '<div class="note">No headlines matched filters today.</div>'

    live_js = _LIVE_JS if live_mode else ""
    live_badge = '<span class="live-dot"></span> LIVE' if live_mode else ""

    return _HTML_TEMPLATE.format(
        gen_at=_esc(gen_at),
        idx_tabs=idx_tabs,
        idx_contents=idx_contents,
        news_html=news_html,
        strat_json=strat_obj,
        live_js=live_js,
        live_badge=live_badge,
    )


def _build_index_block(rpt: IndexReport, slug: str, active: str, idx: int) -> str:
    tone_cls = {"up": "tone-up", "down": "tone-down"}.get(rpt.verdict_tone, "tone-n")
    notes = "".join(f'<div class="note">{_esc(n)}</div>' for n in rpt.data_notes)
    reasons = "".join(f"<li>{_esc(r)}</li>" for r in rpt.reasoning)

    pcr = f"{rpt.pcr_oi:.3f}" if rpt.pcr_oi is not None else "—"
    mp = _num(rpt.max_pain) if rpt.max_pain else "—"
    mpd = f"{rpt.max_pain_dist_pct:+.2f}%" if rpt.max_pain_dist_pct is not None else "—"

    # Chain table rows
    chain_body = ""
    if rpt.chain_rows and rpt.spot:
        visible = [r for r in rpt.chain_rows if abs(r.strike - rpt.spot) <= rpt.spot * 0.08]
        if not visible:
            visible = rpt.chain_rows
        for r in visible:
            is_atm = abs(r.strike - rpt.spot) < (rpt.chain_rows[1].strike - rpt.chain_rows[0].strike if len(rpt.chain_rows) > 1 else 50) * 0.6
            atm_cls = ' class="atm-row"' if is_atm else ""
            chain_body += (
                f"<tr{atm_cls}>"
                f"<td>{_num(r.ce_oi)}</td><td class=\"{'pos' if r.ce_chg_oi>=0 else 'neg'}\">{_num(r.ce_chg_oi)}</td>"
                f"<td>{r.ce_iv:.1f}</td><td>{r.ce_ltp:.2f}</td><td class=\"{'pos' if r.ce_change>=0 else 'neg'}\">{r.ce_change:+.2f}</td>"
                f"<td>{r.ce_delta:.4f}</td><td>{r.ce_theta:.2f}</td>"
                f"<td class=\"strike-col\">{_num(r.strike)}</td>"
                f"<td>{r.pe_theta:.2f}</td><td>{r.pe_delta:.4f}</td>"
                f"<td class=\"{'pos' if r.pe_change>=0 else 'neg'}\">{r.pe_change:+.2f}</td><td>{r.pe_ltp:.2f}</td>"
                f"<td>{r.pe_iv:.1f}</td><td class=\"{'pos' if r.pe_chg_oi>=0 else 'neg'}\">{_num(r.pe_chg_oi)}</td>"
                f"<td>{_num(r.pe_oi)}</td>"
                f"</tr>"
            )

    # Strategy card
    strat_html = ""
    if rpt.strategy:
        s = rpt.strategy
        legs_html = ""
        for l in s.legs:
            act_cls = "leg-buy" if l.action == "BUY" else "leg-sell"
            legs_html += (
                f'<div class="strat-leg {act_cls}">'
                f'<span class="sl-action">{l.action}</span> '
                f'<span class="sl-strike">{_num(l.strike)} {l.kind}</span> '
                f'<span class="sl-prem">@ {l.premium:.2f}</span></div>'
            )
        mp_txt = f"₹{_num(s.max_profit)}" if s.max_profit is not None else "—"
        ml_txt = f"₹{_num(s.max_loss)}" if s.max_loss is not None else "—"
        be_txt = " / ".join(_num(b) for b in s.breakevens) if s.breakevens else "—"
        strat_html = f"""
<div class="strat-card">
  <div class="sm-title" style="margin-bottom:10px">Recommended strategy</div>
  <div class="strat-name">{_esc(s.name)} <span class="strat-bias badge {tone_cls}">{_esc(s.bias)}</span></div>
  <div class="strat-legs">{legs_html}</div>
  <div class="strat-meta">
    <div><span class="strat-lbl">Lot size</span><span class="strat-val">{s.lot_size}</span></div>
    <div><span class="strat-lbl">Max profit</span><span class="strat-val pos">{mp_txt}</span></div>
    <div><span class="strat-lbl">Max loss</span><span class="strat-val neg">{ml_txt}</span></div>
    <div><span class="strat-lbl">Breakeven(s)</span><span class="strat-val">{be_txt}</span></div>
  </div>
  <div class="strat-reason">{_esc(s.reasoning)}</div>
  <div class="sm-title" style="margin-top:14px; margin-bottom:6px">P&amp;L at expiry — interactive simulator</div>
  <div class="pnl-sim">
    <canvas id="pnl-canvas-{slug}" width="680" height="350"></canvas>
    <div class="pnl-legend">
      <span class="pl-item"><span class="pl-swatch" style="background:#3d9cf5"></span>P&amp;L curve</span>
      <span class="pl-item"><span class="pl-swatch" style="background:#f5a623"></span>Breakeven</span>
      <span class="pl-item"><span class="pl-swatch" style="background:#00e5a0"></span>Buy / Max profit</span>
      <span class="pl-item"><span class="pl-swatch" style="background:#ff4d6d"></span>Sell / Max loss</span>
      <span class="pl-item"><span class="pl-swatch" style="background:rgba(255,255,255,0.3)"></span>Spot price</span>
    </div>
    <div class="pnl-controls">
      <label>Simulated index price:</label>
      <input type="range" id="pnl-slider-{slug}" min="0" max="1" step="0.001" value="0.5">
      <span id="pnl-readout-{slug}" class="pnl-readout"></span>
    </div>
  </div>
</div>"""

    return f"""
<div class="idx-block{active}" data-idx="{slug}">
  <!-- sub-tabs -->
  <div class="sub-tabs">
    <button class="sub-tab active" data-panel="analysis-{slug}">Analysis</button>
    <button class="sub-tab" data-panel="chain-{slug}">Option chain</button>
    <button class="sub-tab" data-panel="strategy-{slug}">Strategy</button>
  </div>

  <!-- ANALYSIS panel -->
  <div class="sub-panel active" id="analysis-{slug}">
    <div class="ic-head">
      <div><div class="ic-label">{_esc(rpt.label)}</div><div class="ic-sub">{_esc(rpt.chain_symbol)} · {_esc(rpt.expiry or 'N/A')}</div></div>
      <div class="ic-badges"><span class="badge" id="chain-badge-{slug}">{'CHAIN OK' if rpt.chain_ok else 'CHAIN N/A'}</span><span class="badge {tone_cls}" id="verdict-badge-{slug}">{_esc(rpt.verdict)}</span></div>
    </div>
    <div class="kpi-grid" id="kpi-{slug}">
      <div class="kpi"><div class="kpi-l">Spot</div><div class="kpi-v" data-kpi="spot">{_num(rpt.spot, 2)}</div></div>
      <div class="kpi"><div class="kpi-l">Index chg</div><div class="kpi-v" data-kpi="index_change_pct">{rpt.index_change_pct:+.2f}%</div></div>
      <div class="kpi"><div class="kpi-l">PCR (OI)</div><div class="kpi-v" data-kpi="pcr_oi">{pcr}</div></div>
      <div class="kpi"><div class="kpi-l">Max pain</div><div class="kpi-v" data-kpi="max_pain">{mp}</div><div class="kpi-s" data-kpi="max_pain_dist">Δ {mpd}</div></div>
      <div class="kpi"><div class="kpi-l">Breadth A/D</div><div class="kpi-v" data-kpi="ad">{rpt.advances} / {rpt.declines}</div></div>
      <div class="kpi"><div class="kpi-l">Confidence</div><div class="kpi-v" data-kpi="confidence">{_esc(rpt.confidence)}</div></div>
    </div>
    <div id="notes-{slug}">{notes}</div>
    <div class="section-mini"><div class="sm-title">Reasoning</div><ol class="reasons" id="reasons-{slug}">{reasons}</ol></div>
  </div>

  <!-- OPTION CHAIN panel -->
  <div class="sub-panel" id="chain-{slug}">
    <div class="sm-title" style="margin-bottom:8px">Full option chain · {_esc(rpt.expiry or '')} · Lot {rpt.lot_size}</div>
    <div class="chain-wrap">
      <table class="chain-tbl">
        <thead><tr>
          <th colspan="7" class="th-calls">CALLS</th>
          <th class="th-strike">STRIKE</th>
          <th colspan="7" class="th-puts">PUTS</th>
        </tr><tr>
          <th>OI</th><th>ΔOI</th><th>IV</th><th>LTP</th><th>Chg</th><th>Delta</th><th>Theta</th>
          <th></th>
          <th>Theta</th><th>Delta</th><th>Chg</th><th>LTP</th><th>IV</th><th>ΔOI</th><th>OI</th>
        </tr></thead>
        <tbody id="chain-tbody-{slug}">{chain_body}</tbody>
      </table>
    </div>
  </div>

  <!-- STRATEGY panel -->
  <div class="sub-panel" id="strategy-{slug}">
    {strat_html or '<div class="note">No strategy available (chain data missing).</div>'}
  </div>
</div>"""


# ─── HTML template ──────────────────────────────────────────────────────────

_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>NSE F&amp;O Index Outlook · {gen_at}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;600&family=DM+Sans:ital,opsz,wght@0,9..40,400..700;1,9..40,400..700&display=swap" rel="stylesheet">
<style>
:root {{
  --bg:#08090d; --bg2:#0d0e14; --bg3:#12131a; --bg4:#181922;
  --border:rgba(255,255,255,0.07); --border2:rgba(255,255,255,0.12);
  --green:#00e5a0; --green-dim:rgba(0,229,160,0.12);
  --red:#ff4d6d; --red-dim:rgba(255,77,109,0.12);
  --amber:#f5a623; --blue:#3d9cf5; --blue-dim:rgba(61,156,245,0.12);
  --text:#e8e9f0; --text2:#9899a8; --text3:#5c5d6e;
  --mono:'Fira Code',monospace; --sans:'DM Sans',sans-serif;
}}
*,*::before,*::after {{ box-sizing:border-box; margin:0; padding:0; }}
body {{ background:var(--bg); color:var(--text); font-family:var(--sans); font-size:13px; line-height:1.6; -webkit-font-smoothing:antialiased; }}
.page {{ max-width:1260px; margin:0 auto; padding:28px 22px 48px; }}

/* Header */
.hdr {{ padding:24px 28px; background:linear-gradient(135deg,#0f1018,#131420 55%,#0d1020); border:1px solid var(--border2); border-radius:16px; position:relative; overflow:hidden; margin-bottom:20px; }}
.hdr::before {{ content:''; position:absolute; top:0; left:0; right:0; height:1px; background:linear-gradient(90deg,transparent,var(--blue),transparent); opacity:.45; }}
.hdr-badge {{ font-family:var(--mono); font-size:10px; font-weight:600; color:var(--blue); letter-spacing:2px; }}
.hdr-badge span {{ background:var(--blue-dim); border:1px solid rgba(61,156,245,.2); border-radius:4px; padding:2px 8px; font-size:9px; margin-left:6px; }}
.hdr-title {{ font-family:var(--mono); font-size:24px; font-weight:700; color:#fff; margin-top:6px; }}
.hdr-sub {{ font-family:var(--mono); font-size:10px; color:var(--text2); margin-top:6px; max-width:900px; line-height:1.7; }}

/* Index tabs */
.idx-tabs {{ display:flex; gap:6px; margin-bottom:16px; }}
.idx-tab {{ font-family:var(--mono); font-size:11px; padding:7px 18px; border:1px solid var(--border2); border-radius:8px; background:var(--bg2); color:var(--text2); cursor:pointer; transition:.15s; }}
.idx-tab:hover {{ background:var(--bg3); color:var(--text); }}
.idx-tab.active {{ background:var(--blue-dim); color:var(--blue); border-color:rgba(61,156,245,.3); }}
.idx-block {{ display:none; background:var(--bg2); border:1px solid var(--border); border-radius:14px; padding:20px; }}
.idx-block.active {{ display:block; }}

/* Sub-tabs */
.sub-tabs {{ display:flex; gap:4px; margin-bottom:14px; border-bottom:1px solid var(--border); padding-bottom:10px; }}
.sub-tab {{ font-family:var(--mono); font-size:10px; letter-spacing:1px; text-transform:uppercase; padding:6px 14px; border:1px solid transparent; border-radius:6px; background:none; color:var(--text3); cursor:pointer; transition:.15s; }}
.sub-tab:hover {{ color:var(--text2); background:var(--bg3); }}
.sub-tab.active {{ color:var(--blue); background:var(--blue-dim); border-color:rgba(61,156,245,.2); }}
.sub-panel {{ display:none; }}
.sub-panel.active {{ display:block; }}

/* KPI grid */
.ic-head {{ display:flex; justify-content:space-between; align-items:flex-start; gap:12px; margin-bottom:14px; }}
.ic-label {{ font-family:var(--mono); font-size:15px; font-weight:700; color:#fff; }}
.ic-sub {{ font-size:11px; color:var(--text3); margin-top:2px; }}
.ic-badges {{ display:flex; flex-wrap:wrap; gap:6px; justify-content:flex-end; }}
.badge {{ font-family:var(--mono); font-size:9px; padding:3px 8px; border-radius:999px; border:1px solid var(--border2); color:var(--text2); white-space:nowrap; }}
.tone-up {{ color:var(--green); border-color:rgba(0,229,160,.35); background:var(--green-dim); }}
.tone-down {{ color:var(--red); border-color:rgba(255,77,109,.35); background:var(--red-dim); }}
.tone-n {{ color:var(--amber); border-color:rgba(245,166,35,.3); background:rgba(245,166,35,.1); }}
.kpi-grid {{ display:grid; grid-template-columns:repeat(6,1fr); gap:10px; margin-bottom:12px; }}
@media(max-width:900px) {{ .kpi-grid {{ grid-template-columns:repeat(3,1fr); }} }}
.kpi {{ background:var(--bg3); border:1px solid var(--border); border-radius:10px; padding:10px 12px; }}
.kpi-l {{ font-family:var(--mono); font-size:8px; letter-spacing:1.2px; text-transform:uppercase; color:var(--text3); }}
.kpi-v {{ font-family:var(--mono); font-size:17px; font-weight:700; margin-top:2px; }}
.kpi-s {{ font-size:9px; color:var(--text3); margin-top:2px; }}
.note {{ font-size:11px; color:var(--amber); background:rgba(245,166,35,.08); border:1px solid rgba(245,166,35,.2); border-radius:8px; padding:10px 12px; margin:10px 0; line-height:1.55; }}
.sm-title {{ font-family:var(--mono); font-size:10px; color:var(--text3); letter-spacing:1.5px; text-transform:uppercase; }}
.reasons {{ margin-left:18px; color:var(--text2); font-size:12px; }}
.reasons li {{ margin-bottom:5px; }}

/* Option chain table */
.chain-wrap {{ max-height:520px; overflow:auto; border:1px solid var(--border); border-radius:10px; }}
.chain-wrap::-webkit-scrollbar {{ width:5px; height:5px; }}
.chain-wrap::-webkit-scrollbar-track {{ background:var(--bg3); }}
.chain-wrap::-webkit-scrollbar-thumb {{ background:var(--border2); border-radius:3px; }}
.chain-tbl {{ width:100%; border-collapse:collapse; font-family:var(--mono); font-size:10px; white-space:nowrap; }}
.chain-tbl thead {{ position:sticky; top:0; z-index:2; }}
.chain-tbl th {{ padding:7px 8px; background:var(--bg4); color:var(--text3); font-weight:500; font-size:9px; letter-spacing:.5px; text-transform:uppercase; border-bottom:2px solid var(--border2); }}
.th-calls {{ text-align:center; color:var(--green); border-bottom:2px solid rgba(0,229,160,.25); background:rgba(0,229,160,.04); }}
.th-puts {{ text-align:center; color:var(--red); border-bottom:2px solid rgba(255,77,109,.25); background:rgba(255,77,109,.04); }}
.th-strike {{ text-align:center; background:var(--bg4); }}
.chain-tbl td {{ padding:5px 8px; text-align:right; border-bottom:1px solid var(--border); }}
.chain-tbl .strike-col {{ text-align:center; font-weight:700; color:#fff; background:var(--bg4); position:sticky; left:0; }}
.chain-tbl .atm-row {{ background:rgba(61,156,245,.06); }}
.chain-tbl .atm-row .strike-col {{ color:var(--blue); background:rgba(61,156,245,.12); }}
.pos {{ color:var(--green); }}
.neg {{ color:var(--red); }}

/* Strategy */
.strat-card {{ background:var(--bg3); border:1px solid var(--border); border-radius:12px; padding:18px 20px; }}
.strat-name {{ font-family:var(--mono); font-size:16px; font-weight:700; color:#fff; margin-bottom:10px; display:flex; align-items:center; gap:10px; flex-wrap:wrap; }}
.strat-bias {{ font-size:9px; }}
.strat-legs {{ display:flex; flex-wrap:wrap; gap:8px; margin-bottom:12px; }}
.strat-leg {{ font-family:var(--mono); font-size:11px; padding:6px 12px; border-radius:8px; border:1px solid var(--border2); }}
.leg-buy {{ background:var(--green-dim); color:var(--green); border-color:rgba(0,229,160,.25); }}
.leg-sell {{ background:var(--red-dim); color:var(--red); border-color:rgba(255,77,109,.25); }}
.sl-action {{ font-weight:700; }}
.strat-meta {{ display:grid; grid-template-columns:repeat(4,1fr); gap:10px; margin-bottom:12px; }}
@media(max-width:700px) {{ .strat-meta {{ grid-template-columns:repeat(2,1fr); }} }}
.strat-lbl {{ display:block; font-family:var(--mono); font-size:8px; letter-spacing:1px; text-transform:uppercase; color:var(--text3); }}
.strat-val {{ font-family:var(--mono); font-size:14px; font-weight:700; }}
.strat-reason {{ font-size:12px; color:var(--text2); line-height:1.65; }}

/* P&L simulator */
.pnl-sim {{ background:var(--bg2); border:1px solid var(--border); border-radius:10px; padding:14px; }}
.pnl-sim canvas {{ width:100%; height:auto; display:block; border-radius:6px; }}
.pnl-legend {{ display:flex; flex-wrap:wrap; gap:14px; margin-top:8px; font-family:var(--mono); font-size:9px; color:var(--text3); }}
.pl-item {{ display:flex; align-items:center; gap:5px; }}
.pl-swatch {{ width:12px; height:3px; border-radius:2px; display:inline-block; }}
.pnl-controls {{ display:flex; align-items:center; gap:12px; margin-top:10px; font-family:var(--mono); font-size:11px; color:var(--text2); }}
.pnl-controls input[type=range] {{ flex:1; accent-color:var(--blue); height:6px; }}
.pnl-readout {{ font-weight:700; min-width:200px; }}

/* News */
.news-wrap {{ background:var(--bg2); border:1px solid var(--border); border-radius:14px; padding:18px 20px; margin-top:18px; }}
.news-item {{ padding:10px 0; border-bottom:1px solid var(--border); }}
.news-item:last-child {{ border-bottom:none; }}
.nw-link {{ color:var(--blue); text-decoration:none; font-size:13px; font-weight:600; }}
.nw-link:hover {{ text-decoration:underline; }}
.nw-meta {{ font-family:var(--mono); font-size:9px; color:var(--text3); margin-top:3px; }}
.report-footer {{ text-align:center; padding:24px 8px 8px; font-family:var(--mono); font-size:9px; color:var(--text3); line-height:1.8; }}

/* Live mode */
.live-dot {{ display:inline-block; width:8px; height:8px; background:#ff4444; border-radius:50%; margin-right:4px; vertical-align:middle; animation:pulse 1.5s ease-in-out infinite; }}
@keyframes pulse {{ 0%,100%{{ opacity:1; }} 50%{{ opacity:.3; }} }}
.live-bar {{ display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:8px; margin-bottom:14px; padding:10px 16px; background:var(--bg3); border:1px solid var(--border); border-radius:10px; font-family:var(--mono); font-size:10px; color:var(--text2); }}
.live-bar .lb-status {{ display:flex; align-items:center; gap:6px; }}
.live-bar .lb-ts {{ color:var(--text3); }}
.live-bar select {{ background:var(--bg4); color:var(--text); border:1px solid var(--border2); border-radius:5px; padding:3px 8px; font-family:var(--mono); font-size:10px; }}
.live-bar button {{ background:var(--blue-dim); color:var(--blue); border:1px solid rgba(61,156,245,.25); border-radius:5px; padding:3px 12px; font-family:var(--mono); font-size:10px; cursor:pointer; }}
.live-bar button:hover {{ background:rgba(61,156,245,.25); }}
.chain-tbl .flash-up {{ animation:flashG .6s; }} .chain-tbl .flash-dn {{ animation:flashR .6s; }}
@keyframes flashG {{ 0%{{ background:rgba(0,229,160,.25); }} 100%{{ background:transparent; }} }}
@keyframes flashR {{ 0%{{ background:rgba(255,77,109,.25); }} 100%{{ background:transparent; }} }}
</style>
</head>
<body>
<div class="page">
  <div class="hdr">
    <div class="hdr-badge">F&amp;O INDEX OUTLOOK <span>NSE INDIA</span> {live_badge}</div>
    <div class="hdr-title">NIFTY 50 &amp; NIFTY BANK — Options positioning &amp; strategy</div>
    <div class="hdr-sub">
      Option chain via Groww · Cash breadth via NSE · Strategy recommended from OI + IV + breadth heuristics ·
      Interactive P&amp;L plot is at-expiry payoff — not investment advice.
    </div>
  </div>

  <div id="live-bar-slot"></div>
  <div class="idx-tabs">{idx_tabs}</div>
  {idx_contents}

  <div class="news-wrap">
    <div class="sm-title" style="margin-bottom:10px">Market headlines</div>
    {news_html}
  </div>
  <div class="report-footer">Generated {gen_at} · IST<br>Option chain from Groww SSR · Cash breadth from NSE equity-stockIndices API · For educational use only.</div>
</div>

<script>
(function() {{
  /* Track slider state per slug so we can re-draw on tab reveal */
  const sliderState = {{}};

  function tryDrawSlug(slug) {{
    const canvas = document.getElementById('pnl-canvas-'+slug);
    if(!canvas || canvas.clientWidth === 0) return;
    const pct = sliderState[slug] !== undefined ? sliderState[slug] : 0.5;
    drawPnl(slug, pct);
  }}

  /* Index tab switching – redraw any visible canvas after switch */
  document.querySelectorAll('.idx-tab').forEach(btn => {{
    btn.addEventListener('click', () => {{
      document.querySelectorAll('.idx-tab').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.idx-block').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const block = document.querySelector('.idx-block[data-idx="'+btn.dataset.idx+'"]');
      if(block) {{
        block.classList.add('active');
        requestAnimationFrame(() => tryDrawSlug(btn.dataset.idx));
      }}
    }});
  }});

  /* Sub-tab switching – draw canvas when Strategy panel becomes visible */
  document.querySelectorAll('.sub-tab').forEach(btn => {{
    btn.addEventListener('click', () => {{
      const parent = btn.closest('.idx-block');
      parent.querySelectorAll('.sub-tab').forEach(b => b.classList.remove('active'));
      parent.querySelectorAll('.sub-panel').forEach(p => p.classList.remove('active'));
      btn.classList.add('active');
      const panel = parent.querySelector('#'+btn.dataset.panel);
      if(panel) {{
        panel.classList.add('active');
        const slug = parent.dataset.idx;
        if(panel.id && panel.id.startsWith('strategy-')) {{
          requestAnimationFrame(() => tryDrawSlug(slug));
        }}
      }}
    }});
  }});

  /* P&L simulator */
  const strategies = {strat_json};
  const green='#00e5a0', red='#ff4d6d', blue='#3d9cf5', text2='#9899a8', bg3='#12131a', border='rgba(255,255,255,0.07)';

  function pnlAt(strat, price) {{
    let total = 0;
    strat.legs.forEach(l => {{
      const intr = l.kind==='CE' ? Math.max(0,price-l.strike) : Math.max(0,l.strike-price);
      total += (l.action==='BUY' ? (intr-l.premium) : (l.premium-intr)) * l.lots * strat.lot_size;
    }});
    return total;
  }}

  function drawPnl(slug, simPct) {{
    const strat = strategies[slug];
    if(!strat) return;
    const canvas = document.getElementById('pnl-canvas-'+slug);
    if(!canvas) return;
    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio||1;
    const W = canvas.clientWidth, H = canvas.clientHeight;
    canvas.width = W*dpr; canvas.height = H*dpr;
    ctx.scale(dpr,dpr);

    const strikes = strat.legs.map(l=>l.strike);
    const spread = Math.max(...strikes) - Math.min(...strikes);
    const pad = Math.max(spread*1.5, strat.spot*0.04);
    const lo = Math.min(...strikes, strat.spot) - pad;
    const hi = Math.max(...strikes, strat.spot) + pad;
    const simPrice = lo + (hi-lo)*simPct;

    const N = 400;
    let pts = [], minP=Infinity, maxP=-Infinity;
    for(let i=0;i<=N;i++) {{
      const px = lo + (hi-lo)*i/N;
      const py = pnlAt(strat, px);
      pts.push({{x:px,y:py}});
      if(py<minP) minP=py; if(py>maxP) maxP=py;
    }}
    const pPad = Math.max(Math.abs(maxP), Math.abs(minP)) * 0.15 || 100;
    const yLo = minP - pPad, yHi = maxP + pPad;

    const mL=58, mR=20, mT=18, mB=44;
    const cW=W-mL-mR, cH=H-mT-mB;
    const toX = v => mL + (v-lo)/(hi-lo)*cW;
    const toY = v => mT + (1 - (v-yLo)/(yHi-yLo))*cH;

    // Background
    ctx.fillStyle=bg3; ctx.fillRect(0,0,W,H);

    // Grid lines
    ctx.strokeStyle=border; ctx.lineWidth=1;
    for(let i=0;i<=5;i++) {{
      const y = mT + cH*i/5;
      ctx.beginPath(); ctx.moveTo(mL,y); ctx.lineTo(W-mR,y); ctx.stroke();
    }}

    // Zero line
    const zeroY = toY(0);
    if(zeroY >= mT && zeroY <= mT+cH) {{
      ctx.strokeStyle='rgba(255,255,255,0.18)'; ctx.lineWidth=1.5;
      ctx.setLineDash([6,4]); ctx.beginPath(); ctx.moveTo(mL,zeroY); ctx.lineTo(W-mR,zeroY); ctx.stroke(); ctx.setLineDash([]);
    }}

    // Fill profit/loss areas
    ctx.save(); ctx.beginPath(); ctx.rect(mL,mT,cW,cH); ctx.clip();
    // Profit fill
    ctx.beginPath(); ctx.moveTo(toX(pts[0].x), Math.min(toY(pts[0].y), zeroY));
    pts.forEach(p => {{ const py=toY(p.y); ctx.lineTo(toX(p.x), Math.min(py, zeroY)); }});
    ctx.lineTo(toX(pts[pts.length-1].x), zeroY); ctx.lineTo(toX(pts[0].x), zeroY); ctx.closePath();
    ctx.fillStyle='rgba(0,229,160,0.08)'; ctx.fill();
    // Loss fill
    ctx.beginPath(); ctx.moveTo(toX(pts[0].x), Math.max(toY(pts[0].y), zeroY));
    pts.forEach(p => {{ const py=toY(p.y); ctx.lineTo(toX(p.x), Math.max(py, zeroY)); }});
    ctx.lineTo(toX(pts[pts.length-1].x), zeroY); ctx.lineTo(toX(pts[0].x), zeroY); ctx.closePath();
    ctx.fillStyle='rgba(255,77,109,0.08)'; ctx.fill();
    ctx.restore();

    // ── Breakeven vertical lines (profit/loss boundary) ──
    const beLines = [];
    for(let i=1;i<pts.length;i++) {{
      if(pts[i-1].y * pts[i].y < 0) {{
        const ratio = Math.abs(pts[i-1].y) / (Math.abs(pts[i-1].y)+Math.abs(pts[i].y));
        beLines.push(pts[i-1].x + (pts[i].x - pts[i-1].x)*ratio);
      }}
    }}
    beLines.forEach(be => {{
      const bx = toX(be);
      ctx.strokeStyle='#f5a623'; ctx.lineWidth=1.5; ctx.setLineDash([5,4]);
      ctx.beginPath(); ctx.moveTo(bx, mT); ctx.lineTo(bx, mT+cH); ctx.stroke(); ctx.setLineDash([]);
      // diamond marker at zero crossing
      ctx.fillStyle='#f5a623';
      ctx.beginPath(); ctx.moveTo(bx, zeroY-6); ctx.lineTo(bx+5, zeroY); ctx.lineTo(bx, zeroY+6); ctx.lineTo(bx-5, zeroY); ctx.closePath(); ctx.fill();
      // label
      ctx.font='700 9px "Fira Code"'; ctx.textAlign='center';
      ctx.fillStyle='#08090d';
      ctx.fillText('BE', bx, zeroY+3);
      ctx.fillStyle='#f5a623';
      ctx.fillText(Math.round(be).toLocaleString(), bx, mT+cH+24);
    }});

    // ── Max profit / max loss horizontal boundary lines ──
    const mpY = toY(maxP), mlY = toY(minP);
    // Max profit line
    if(mpY >= mT && mpY <= mT+cH) {{
      ctx.strokeStyle='rgba(0,229,160,0.45)'; ctx.lineWidth=1; ctx.setLineDash([3,5]);
      ctx.beginPath(); ctx.moveTo(mL, mpY); ctx.lineTo(W-mR, mpY); ctx.stroke(); ctx.setLineDash([]);
      ctx.fillStyle=green; ctx.font='600 9px "Fira Code"'; ctx.textAlign='left';
      ctx.fillText('MAX PROFIT +'+(Math.round(maxP)).toLocaleString(), mL+4, mpY-4);
    }}
    // Max loss line
    if(mlY >= mT && mlY <= mT+cH) {{
      ctx.strokeStyle='rgba(255,77,109,0.45)'; ctx.lineWidth=1; ctx.setLineDash([3,5]);
      ctx.beginPath(); ctx.moveTo(mL, mlY); ctx.lineTo(W-mR, mlY); ctx.stroke(); ctx.setLineDash([]);
      ctx.fillStyle=red; ctx.font='600 9px "Fira Code"'; ctx.textAlign='left';
      ctx.fillText('MAX LOSS '+(Math.round(minP)).toLocaleString(), mL+4, mlY+12);
    }}

    // ── Profit / Loss zone labels ──
    // Place "PROFIT" / "LOSS" labels in the largest profit and loss regions
    if(beLines.length > 0) {{
      // find widest profit zone
      const edges = [lo, ...beLines, hi];
      let bestProfit = null, bestLoss = null;
      for(let j=0; j<edges.length-1; j++) {{
        const mid = (edges[j]+edges[j+1])/2;
        const pnlMid = pnlAt(strat, mid);
        const width = edges[j+1]-edges[j];
        if(pnlMid > 0 && (!bestProfit || width > bestProfit.w)) bestProfit = {{mid, w:width}};
        if(pnlMid < 0 && (!bestLoss || width > bestLoss.w)) bestLoss = {{mid, w:width}};
      }}
      ctx.font='700 11px "Fira Code"'; ctx.globalAlpha=0.18;
      if(bestProfit) {{ ctx.fillStyle=green; ctx.textAlign='center'; ctx.fillText('PROFIT', toX(bestProfit.mid), zeroY-14); }}
      if(bestLoss) {{ ctx.fillStyle=red; ctx.textAlign='center'; ctx.fillText('LOSS', toX(bestLoss.mid), zeroY+18); }}
      ctx.globalAlpha=1;
    }}

    // ── P&L curve (drawn on top) ──
    ctx.beginPath(); ctx.moveTo(toX(pts[0].x), toY(pts[0].y));
    for(let i=1;i<pts.length;i++) ctx.lineTo(toX(pts[i].x), toY(pts[i].y));
    ctx.strokeStyle=blue; ctx.lineWidth=2.5; ctx.stroke();

    // ── Strike markers ──
    strat.legs.forEach(l => {{
      const sx = toX(l.strike);
      ctx.strokeStyle = l.action==='BUY' ? green : red;
      ctx.lineWidth=1; ctx.setLineDash([4,3]);
      ctx.beginPath(); ctx.moveTo(sx,mT); ctx.lineTo(sx,mT+cH); ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = l.action==='BUY' ? green : red;
      ctx.font='600 9px "Fira Code"'; ctx.textAlign='center';
      ctx.fillText(l.action+' '+l.strike.toLocaleString()+' '+l.kind, sx, mT+cH+12);
    }});

    // ── Spot marker ──
    const spotX = toX(strat.spot);
    ctx.strokeStyle='rgba(255,255,255,0.3)'; ctx.lineWidth=1; ctx.setLineDash([2,4]);
    ctx.beginPath(); ctx.moveTo(spotX,mT); ctx.lineTo(spotX,mT+cH); ctx.stroke(); ctx.setLineDash([]);
    ctx.fillStyle=text2; ctx.font='600 9px "Fira Code"'; ctx.textAlign='center';
    ctx.fillText('SPOT '+strat.spot.toLocaleString(), spotX, mT-5);

    // ── Simulation crosshair ──
    const simX = toX(simPrice), simPnl = pnlAt(strat, simPrice), simY = toY(simPnl);
    ctx.strokeStyle='rgba(255,255,255,0.5)'; ctx.lineWidth=1; ctx.setLineDash([3,3]);
    ctx.beginPath(); ctx.moveTo(simX,mT); ctx.lineTo(simX,mT+cH); ctx.stroke();
    // horizontal guide from dot to Y-axis
    ctx.beginPath(); ctx.moveTo(mL, simY); ctx.lineTo(simX, simY); ctx.stroke();
    ctx.setLineDash([]);
    // dot
    ctx.beginPath(); ctx.arc(simX, simY, 6, 0, Math.PI*2);
    ctx.fillStyle = simPnl>=0 ? green : red; ctx.fill();
    ctx.strokeStyle='#fff'; ctx.lineWidth=1.5; ctx.stroke();
    // P&L value next to dot
    ctx.fillStyle = simPnl>=0 ? green : red;
    ctx.font='700 10px "Fira Code"'; ctx.textAlign='left';
    ctx.fillText((simPnl>=0?'+':'')+Math.round(simPnl).toLocaleString(), simX+10, simY+4);

    // ── Y-axis labels ──
    ctx.fillStyle=text2; ctx.font='10px "Fira Code"'; ctx.textAlign='right';
    for(let i=0;i<=5;i++) {{
      const val = yHi - (yHi-yLo)*i/5;
      ctx.fillText((val>=0?'+':'')+Math.round(val).toLocaleString(), mL-6, mT+cH*i/5+4);
    }}

    // ── Readout ──
    const readout = document.getElementById('pnl-readout-'+slug);
    if(readout) {{
      const clr = simPnl>=0 ? green : red;
      const zone = simPnl > 0 ? '<span style="color:'+green+'"> PROFIT</span>' : (simPnl < 0 ? '<span style="color:'+red+'"> LOSS</span>' : ' BREAKEVEN');
      readout.innerHTML = 'Index: <span style="color:#fff">'+simPrice.toFixed(0)+'</span> · P&L: <span style="color:'+clr+'">'+(simPnl>=0?'+':'')+Math.round(simPnl).toLocaleString()+'</span>'+zone;
    }}
  }}

  Object.keys(strategies).forEach(slug => {{
    const slider = document.getElementById('pnl-slider-'+slug);
    if(!slider) return;
    sliderState[slug] = 0.5;
    slider.addEventListener('input', () => {{
      sliderState[slug] = parseFloat(slider.value);
      drawPnl(slug, sliderState[slug]);
    }});
    window.addEventListener('resize', () => tryDrawSlug(slug));
    /* Draw immediately only if canvas is currently visible (first index, strategy tab open) */
    requestAnimationFrame(() => tryDrawSlug(slug));
  }});
}})();
</script>
{live_js}
</body>
</html>"""


# ─── JSON serialisation for live API ────────────────────────────────────────

def _report_to_json(rpt: IndexReport) -> dict[str, Any]:
    rows = []
    for r in rpt.chain_rows:
        rows.append({
            "strike": r.strike,
            "ce_oi": r.ce_oi, "ce_chg_oi": r.ce_chg_oi, "ce_iv": r.ce_iv,
            "ce_ltp": r.ce_ltp, "ce_change": r.ce_change, "ce_change_pct": r.ce_change_pct,
            "ce_delta": r.ce_delta, "ce_gamma": r.ce_gamma, "ce_theta": r.ce_theta, "ce_vega": r.ce_vega,
            "pe_oi": r.pe_oi, "pe_chg_oi": r.pe_chg_oi, "pe_iv": r.pe_iv,
            "pe_ltp": r.pe_ltp, "pe_change": r.pe_change, "pe_change_pct": r.pe_change_pct,
            "pe_delta": r.pe_delta, "pe_gamma": r.pe_gamma, "pe_theta": r.pe_theta, "pe_vega": r.pe_vega,
        })
    strat = None
    if rpt.strategy:
        s = rpt.strategy
        strat = {
            "name": s.name, "bias": s.bias, "lot_size": s.lot_size, "spot": s.spot,
            "max_profit": s.max_profit, "max_loss": s.max_loss,
            "breakevens": s.breakevens, "reasoning": s.reasoning,
            "legs": [{"kind": l.kind, "strike": l.strike, "action": l.action,
                       "premium": l.premium, "lots": l.lots} for l in s.legs],
        }
    return {
        "label": rpt.label, "symbol": rpt.chain_symbol,
        "spot": rpt.spot, "spot_source": rpt.spot_source,
        "index_change_pct": rpt.index_change_pct,
        "advances": rpt.advances, "declines": rpt.declines, "unchanged": rpt.unchanged,
        "chain_ok": rpt.chain_ok, "expiry": rpt.expiry, "lot_size": rpt.lot_size,
        "total_ce_oi": rpt.total_ce_oi, "total_pe_oi": rpt.total_pe_oi,
        "total_ce_oi_chg": rpt.total_ce_oi_chg, "total_pe_oi_chg": rpt.total_pe_oi_chg,
        "pcr_oi": rpt.pcr_oi, "max_pain": rpt.max_pain,
        "max_pain_dist_pct": rpt.max_pain_dist_pct,
        "atm_strike": rpt.atm_strike,
        "verdict": rpt.verdict, "verdict_tone": rpt.verdict_tone, "confidence": rpt.confidence,
        "reasoning": rpt.reasoning, "data_notes": rpt.data_notes,
        "strategy": strat,
        "chain": rows,
        "ts": datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST"),
    }


def _fetch_report(key: str) -> dict[str, Any]:
    prof = INDEX_PROFILES[key]
    br = fetch_index_breadth(prof["breadth_index"])
    gw = fetch_groww_chain(key)
    rpt = analyze(key, br, gw)
    return _report_to_json(rpt)


# ─── Live server ─────────────────────────────────────────────────────────────

import http.server
import threading
import functools
from urllib.parse import urlparse


class _LiveHandler(http.server.BaseHTTPRequestHandler):
    """Serves the static HTML report and a live JSON API."""

    html_content: str = ""

    def log_message(self, fmt, *args):
        ts = datetime.now(IST).strftime("%H:%M:%S")
        print(f"  [{ts}] {args[0]}")

    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")

    def do_GET(self):
        path = urlparse(self.path).path

        if path in ("/", "/index.html"):
            self._serve_html()
        elif path.startswith("/api/chain/"):
            symbol = path.split("/")[-1].upper()
            self._serve_chain(symbol)
        elif path == "/api/all":
            self._serve_all()
        else:
            self.send_error(404)

    def _serve_html(self):
        body = self.__class__.html_content.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_chain(self, symbol: str):
        if symbol not in INDEX_PROFILES:
            self.send_error(404, f"Unknown symbol: {symbol}")
            return
        data = _fetch_report(symbol)
        body = json.dumps(data, separators=(",", ":")).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self._cors_headers()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_all(self):
        result = {}
        for key in INDEX_PROFILES:
            result[key.lower()] = _fetch_report(key)
        body = json.dumps(result, separators=(",", ":")).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self._cors_headers()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _run_live(port: int = 8787):
    print(f"\n  🔴 LIVE MODE — http://localhost:{port}")
    print("  Endpoints:")
    print(f"    GET /              → HTML report (with auto-refresh)")
    print(f"    GET /api/chain/NIFTY     → NIFTY chain + analysis JSON")
    print(f"    GET /api/chain/BANKNIFTY → BANKNIFTY chain + analysis JSON")
    print(f"    GET /api/all       → Both indices JSON")
    print("  Press Ctrl+C to stop.\n")

    reports: list[IndexReport] = []
    for key in ("NIFTY", "BANKNIFTY"):
        prof = INDEX_PROFILES[key]
        print(f"  → initial fetch {prof['label']}...")
        br = fetch_index_breadth(prof["breadth_index"])
        gw = fetch_groww_chain(key)
        reports.append(analyze(key, br, gw))
        time.sleep(0.25)

    news = fetch_rss_articles()
    gen_at = datetime.now(IST).strftime("%Y-%m-%d %H:%M IST")
    html_out = generate_html(reports, news, gen_at, live_mode=True)
    _LiveHandler.html_content = html_out

    server = http.server.HTTPServer(("0.0.0.0", port), _LiveHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Server stopped.")
        server.server_close()


# ─── Cleanup ─────────────────────────────────────────────────────────────────

def cleanup_old_reports(reports_root: str, keep_days: int = 15) -> int:
    """Delete report date-folders older than keep_days."""
    from datetime import timedelta
    cutoff = datetime.now(IST) - timedelta(days=keep_days)
    removed = 0
    if not os.path.isdir(reports_root):
        return 0
    for entry in os.listdir(reports_root):
        if not re.match(r"\d{4}-\d{2}-\d{2}$", entry):
            continue
        dirpath = os.path.join(reports_root, entry)
        if os.path.isdir(dirpath):
            try:
                folder_date = datetime.strptime(entry, "%Y-%m-%d").replace(tzinfo=IST)
                if folder_date < cutoff:
                    shutil.rmtree(dirpath)
                    removed += 1
            except ValueError:
                pass
    return removed


# ─── Main ───────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="NSE F&O index outlook HTML report")
    parser.add_argument("-o", "--output-dir", default="./fno_reports")
    parser.add_argument("--live", action="store_true", help="Start live server with auto-refreshing option chain")
    parser.add_argument("--port", type=int, default=8787, help="Port for live server (default: 8787)")
    args = parser.parse_args()

    if args.live:
        _run_live(port=args.port)
        return 0

    out_root = os.path.abspath(args.output_dir)
    today = datetime.now(IST).strftime("%Y-%m-%d")
    dated = os.path.join(out_root, today)
    os.makedirs(dated, exist_ok=True)

    print("  NSE F&O Index Outlook Report")
    print(f"  Output: {dated}")

    reports: list[IndexReport] = []
    for key in ("NIFTY", "BANKNIFTY"):
        prof = INDEX_PROFILES[key]
        print(f"  → {prof['label']}...")
        br = fetch_index_breadth(prof["breadth_index"])
        time.sleep(0.25)
        gw = fetch_groww_chain(key)
        time.sleep(0.25)
        if gw:
            rows, _, _ = parse_groww_chain(gw)
            print(f"     ✓ {len(rows)} strikes via Groww")
        else:
            print("     ⚠ chain unavailable")
        reports.append(analyze(key, br, gw))

    news = fetch_rss_articles()
    print(f"  → headlines: {len(news)} items")

    gen_at = datetime.now(IST).strftime("%Y-%m-%d %H:%M IST")
    html_out = generate_html(reports, news, gen_at)

    fname = "FNO_IndexOutlook_Report.html"
    p1 = os.path.join(dated, fname)
    p2 = os.path.join(out_root, fname)
    with open(p1, "w", encoding="utf-8") as f:
        f.write(html_out)
    shutil.copy2(p1, p2)
    print(f"  ✅ {p1}")

    removed = cleanup_old_reports(out_root, keep_days=15)
    if removed:
        print(f"  🧹 Cleaned up {removed} report folder(s) older than 15 days")

    return 0


if __name__ == "__main__":
    sys.exit(main())
