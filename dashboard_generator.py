#!/usr/bin/env python3
"""
Dashboard Generator — top-level index.html that links to every report.

Scans reports/, us_reports/, sector_reports/, fno_reports/ and builds a
responsive dark-themed landing page with cards for each section, per-stock
links, daily summaries, and date navigation.
"""

from __future__ import annotations

import argparse
import html as html_mod
import os
import re
import sys
from datetime import datetime
from glob import glob
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

BASE_URL = ""

REPORT_DIRS = {
    "nse": {"dir": "reports", "label": "NSE Stocks", "icon": "🇮🇳", "suffix": "_RiskReport.html", "color": "#3d9cf5"},
    "us": {"dir": "us_reports", "label": "US Stocks", "icon": "🇺🇸", "suffix": "_RiskReport.html", "color": "#a855f7"},
    "sectors": {"dir": "sector_reports", "label": "Sector Rotation", "icon": "🔄", "file": "SectorRotation_Report.html", "color": "#f5a623"},
    "fno": {"dir": "fno_reports", "label": "F&O Index Outlook", "icon": "📊", "file": "FNO_IndexOutlook_Report.html", "color": "#00e5a0"},
}


def _esc(s: str) -> str:
    return html_mod.escape(s)


def _scan_dates(base: str) -> list[str]:
    dates = []
    if not os.path.isdir(base):
        return dates
    for entry in sorted(os.listdir(base), reverse=True):
        if re.match(r"\d{4}-\d{2}-\d{2}$", entry) and os.path.isdir(os.path.join(base, entry)):
            dates.append(entry)
    return dates


def _scan_stock_reports(base: str, date: str, suffix: str) -> list[dict[str, str]]:
    folder = os.path.join(base, date)
    if not os.path.isdir(folder):
        return []
    reports = []
    for f in sorted(os.listdir(folder)):
        if f.endswith(suffix):
            ticker = f.replace(suffix, "")
            reports.append({"ticker": ticker, "path": f"{base}/{date}/{f}"})
    return reports


def _parse_summary(base: str, date: str) -> dict[str, str]:
    path = os.path.join(base, date, "DAILY_SUMMARY.md")
    if not os.path.isfile(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()

    info: dict[str, str] = {}

    buy_section = re.findall(r"Value Buy Opportunities", text)
    if buy_section:
        info["has_alerts"] = "1"

    buy = len(re.findall(r"Signal:.*?(?:STRONG )?BUY", text))
    hold = len(re.findall(r"Signal:.*?HOLD", text))
    sell = len(re.findall(r"Signal:.*?SELL", text, re.I))
    # fallback: also check pipe-table format
    buy += len(re.findall(r"\|\s*(?:STRONG )?BUY\s*\|", text))
    hold += len(re.findall(r"\|\s*HOLD\s*\|", text))
    sell += len(re.findall(r"\|\s*SELL\s*\|", text))

    if buy + hold + sell > 0:
        info["buy"] = str(buy)
        info["hold"] = str(hold)
        info["sell"] = str(sell)
        info["total"] = str(buy + hold + sell)
    if info.get("has_alerts"):
        info["buy_alerts"] = str(buy)
    return info


def _build_stock_grid(reports: list[dict[str, str]], color: str) -> str:
    if not reports:
        return '<div class="empty">No reports found for this date.</div>'
    items = ""
    for r in reports:
        items += (
            f'<a class="stock-chip" href="{_esc(r["path"])}" style="--chip-color:{color}">'
            f'{_esc(r["ticker"])}</a>'
        )
    return f'<div class="stock-grid">{items}</div>'


def _build_summary_badges(info: dict[str, str]) -> str:
    if not info:
        return ""
    parts = []
    if "total" in info:
        parts.append(f'<span class="sum-badge">{info["total"]} stocks</span>')
    if info.get("buy", "0") != "0":
        parts.append(f'<span class="sum-badge buy">BUY {info["buy"]}</span>')
    if info.get("hold", "0") != "0":
        parts.append(f'<span class="sum-badge hold">HOLD {info["hold"]}</span>')
    if info.get("sell", "0") != "0":
        parts.append(f'<span class="sum-badge sell">SELL {info["sell"]}</span>')
    if info.get("buy_alerts"):
        parts.append(f'<span class="sum-badge alert">🔔 {info["buy_alerts"]} alerts</span>')
    return '<div class="sum-badges">' + "".join(parts) + '</div>'


def generate_dashboard(root: str) -> str:
    now = datetime.now(IST)
    gen_at = now.strftime("%Y-%m-%d %H:%M IST")

    sections: list[str] = []

    for key in ("nse", "us", "sectors", "fno"):
        cfg = REPORT_DIRS[key]
        base = os.path.join(root, cfg["dir"])
        dates = _scan_dates(base)
        color = cfg["color"]

        if key in ("sectors", "fno"):
            latest_file = cfg["file"]
            latest_path = os.path.join(base, latest_file)
            has_latest = os.path.isfile(latest_path)

            date_links = ""
            for d in dates[:10]:
                fpath = f'{cfg["dir"]}/{d}/{latest_file}'
                if os.path.isfile(os.path.join(root, fpath)):
                    date_links += f'<a class="date-link" href="{fpath}">{d}</a>'

            latest_btn = ""
            if has_latest:
                latest_btn = f'<a class="card-btn" href="{cfg["dir"]}/{latest_file}" style="--btn-color:{color}">View latest report →</a>'

            sections.append(f"""
<div class="card" style="--card-accent:{color}">
  <div class="card-head">
    <span class="card-icon">{cfg["icon"]}</span>
    <div>
      <div class="card-title">{_esc(cfg["label"])}</div>
      <div class="card-sub">{len(dates)} report{'s' if len(dates)!=1 else ''} available</div>
    </div>
  </div>
  {latest_btn}
  <div class="date-nav">{date_links or '<span class="empty">No reports yet</span>'}</div>
</div>""")
        else:
            latest_date = dates[0] if dates else None
            stock_reports = _scan_stock_reports(base, latest_date, cfg["suffix"]) if latest_date else []
            summary_info = _parse_summary(base, latest_date) if latest_date else {}

            date_options = ""
            for d in dates[:15]:
                sel = " selected" if d == latest_date else ""
                date_options += f'<option value="{d}"{sel}>{d}</option>'

            grid_html = _build_stock_grid(stock_reports, color)
            badges_html = _build_summary_badges(summary_info)

            summary_link = ""
            if latest_date:
                md_path = f'{cfg["dir"]}/{latest_date}/DAILY_SUMMARY.md'
                if os.path.isfile(os.path.join(root, md_path)):
                    summary_link = f'<a class="card-btn secondary" href="{md_path}">Daily summary (MD)</a>'

            sections.append(f"""
<div class="card" style="--card-accent:{color}">
  <div class="card-head">
    <span class="card-icon">{cfg["icon"]}</span>
    <div>
      <div class="card-title">{_esc(cfg["label"])}</div>
      <div class="card-sub">{len(stock_reports)} stocks · {latest_date or 'no data'}</div>
    </div>
    <select class="date-sel" onchange="switchDate(this, '{key}', '{cfg["dir"]}', '{cfg["suffix"]}')">{date_options}</select>
  </div>
  {badges_html}
  <div class="stock-grid-wrap" id="grid-{key}">
    {grid_html}
  </div>
  <div class="card-actions">{summary_link}</div>
</div>""")

    sections_html = "\n".join(sections)

    return _TEMPLATE.format(
        gen_at=_esc(gen_at),
        sections=sections_html,
        today=now.strftime("%A, %B %d %Y"),
    )


_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Market Analysis Dashboard</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;600;700&family=DM+Sans:ital,opsz,wght@0,9..40,400..700;1,9..40,400..700&display=swap" rel="stylesheet">
<style>
:root {{
  --bg:#08090d; --bg2:#0d0e14; --bg3:#12131a; --bg4:#181922;
  --border:rgba(255,255,255,0.07); --border2:rgba(255,255,255,0.12);
  --text:#e8e9f0; --text2:#9899a8; --text3:#5c5d6e;
  --green:#00e5a0; --red:#ff4d6d; --amber:#f5a623; --blue:#3d9cf5; --purple:#a855f7;
  --mono:'Fira Code',monospace; --sans:'DM Sans',sans-serif;
}}
*,*::before,*::after {{ box-sizing:border-box; margin:0; padding:0; }}
body {{ background:var(--bg); color:var(--text); font-family:var(--sans); font-size:13px; line-height:1.6; -webkit-font-smoothing:antialiased; }}
.page {{ max-width:1100px; margin:0 auto; padding:32px 22px 60px; }}

.hero {{ text-align:center; padding:40px 20px 32px; position:relative; }}
.hero::before {{ content:''; position:absolute; top:50%; left:50%; width:400px; height:400px; transform:translate(-50%,-50%);
  background:radial-gradient(circle, rgba(61,156,245,0.06) 0%, transparent 70%); pointer-events:none; }}
.hero-badge {{ font-family:var(--mono); font-size:10px; font-weight:600; color:var(--blue); letter-spacing:2.5px; text-transform:uppercase; }}
.hero-title {{ font-family:var(--mono); font-size:28px; font-weight:700; color:#fff; margin-top:8px; letter-spacing:-0.5px; }}
.hero-sub {{ font-family:var(--mono); font-size:11px; color:var(--text3); margin-top:8px; max-width:640px; margin-left:auto; margin-right:auto; line-height:1.7; }}
.hero-date {{ font-family:var(--mono); font-size:12px; color:var(--text2); margin-top:14px; }}

.grid {{ display:grid; grid-template-columns:repeat(2,1fr); gap:18px; margin-top:28px; }}
@media(max-width:800px) {{ .grid {{ grid-template-columns:1fr; }} }}

.card {{ background:var(--bg2); border:1px solid var(--border); border-radius:16px; padding:22px 24px; position:relative; overflow:hidden; transition:border-color .2s; }}
.card:hover {{ border-color:var(--card-accent, var(--border2)); }}
.card::before {{ content:''; position:absolute; top:0; left:0; right:0; height:2px; background:linear-gradient(90deg, transparent, var(--card-accent, var(--blue)), transparent); opacity:.4; }}

.card-head {{ display:flex; align-items:center; gap:14px; margin-bottom:14px; }}
.card-icon {{ font-size:28px; }}
.card-title {{ font-family:var(--mono); font-size:16px; font-weight:700; color:#fff; }}
.card-sub {{ font-family:var(--mono); font-size:10px; color:var(--text3); margin-top:2px; }}
.date-sel {{ margin-left:auto; background:var(--bg4); color:var(--text); border:1px solid var(--border2); border-radius:6px; padding:4px 8px; font-family:var(--mono); font-size:10px; cursor:pointer; }}

.sum-badges {{ display:flex; flex-wrap:wrap; gap:6px; margin-bottom:12px; }}
.sum-badge {{ font-family:var(--mono); font-size:9px; padding:3px 10px; border-radius:5px; background:var(--bg4); color:var(--text2); border:1px solid var(--border); }}
.sum-badge.buy {{ color:var(--green); border-color:rgba(0,229,160,.25); background:rgba(0,229,160,.08); }}
.sum-badge.hold {{ color:var(--amber); border-color:rgba(245,166,35,.25); background:rgba(245,166,35,.08); }}
.sum-badge.sell {{ color:var(--red); border-color:rgba(255,77,109,.25); background:rgba(255,77,109,.08); }}
.sum-badge.alert {{ color:var(--amber); border-color:rgba(245,166,35,.3); background:rgba(245,166,35,.1); }}

.stock-grid {{ display:flex; flex-wrap:wrap; gap:6px; max-height:180px; overflow-y:auto; padding-right:4px; }}
.stock-grid::-webkit-scrollbar {{ width:4px; }}
.stock-grid::-webkit-scrollbar-thumb {{ background:var(--border2); border-radius:2px; }}
.stock-chip {{ font-family:var(--mono); font-size:10px; font-weight:600; padding:5px 11px; border-radius:6px;
  background:rgba(255,255,255,0.03); border:1px solid var(--border); color:var(--text2);
  text-decoration:none; transition:all .15s; white-space:nowrap; }}
.stock-chip:hover {{ color:var(--chip-color, var(--blue)); border-color:var(--chip-color, var(--blue)); background:rgba(255,255,255,0.06); transform:translateY(-1px); }}

.card-btn {{ display:inline-block; font-family:var(--mono); font-size:11px; font-weight:600; padding:8px 18px;
  border-radius:8px; text-decoration:none; margin-bottom:12px; transition:all .15s;
  background:var(--btn-color, var(--blue)); color:#08090d; }}
.card-btn:hover {{ filter:brightness(1.15); transform:translateY(-1px); }}
.card-btn.secondary {{ background:var(--bg4); color:var(--text2); border:1px solid var(--border2); }}
.card-btn.secondary:hover {{ border-color:var(--text3); color:var(--text); }}

.card-actions {{ display:flex; gap:8px; margin-top:10px; }}

.date-nav {{ display:flex; flex-wrap:wrap; gap:6px; margin-top:10px; }}
.date-link {{ font-family:var(--mono); font-size:10px; padding:4px 10px; border-radius:5px;
  background:var(--bg4); border:1px solid var(--border); color:var(--text3); text-decoration:none; transition:all .15s; }}
.date-link:hover {{ color:var(--text); border-color:var(--border2); }}

.empty {{ font-family:var(--mono); font-size:11px; color:var(--text3); padding:12px 0; }}

.footer {{ text-align:center; margin-top:40px; padding:20px; font-family:var(--mono); font-size:9px; color:var(--text3); line-height:1.8; }}
.footer a {{ color:var(--blue); text-decoration:none; }}
.footer a:hover {{ text-decoration:underline; }}

.quick-links {{ display:flex; justify-content:center; gap:12px; margin-top:20px; flex-wrap:wrap; }}
.ql {{ font-family:var(--mono); font-size:10px; padding:6px 16px; border-radius:8px;
  background:var(--bg3); border:1px solid var(--border); color:var(--text2); text-decoration:none; transition:all .15s; }}
.ql:hover {{ color:#fff; border-color:var(--border2); background:var(--bg4); }}
</style>
</head>
<body>
<div class="page">
  <div class="hero">
    <div class="hero-badge">Multi-Market Analysis Hub</div>
    <div class="hero-title">Market Analysis Dashboard</div>
    <div class="hero-sub">
      NSE &amp; US stock risk reports · Sector rotation analysis · F&amp;O option chain outlook ·
      All reports generated automatically via GitHub Actions.
    </div>
    <div class="hero-date">{today} · Updated {gen_at}</div>
    <div class="quick-links">
      <a class="ql" href="#nse">🇮🇳 NSE</a>
      <a class="ql" href="#us">🇺🇸 US</a>
      <a class="ql" href="#sectors">🔄 Sectors</a>
      <a class="ql" href="#fno">📊 F&amp;O</a>
    </div>
  </div>

  <div class="grid" id="nse">
    {sections}
  </div>

  <div class="footer">
    Generated {gen_at}<br>
    <a href="https://github.com/nageshnnazare/recos">github.com/nageshnnazare/recos</a> ·
    Not financial advice · Data from NSE, Yahoo Finance, Groww
  </div>
</div>

<script>
function switchDate(sel, key, dir, suffix) {{
  const date = sel.value;
  const wrap = document.getElementById('grid-'+key);
  if(!wrap) return;
  wrap.innerHTML = '<div class="empty">Loading…</div>';
  /* We generate static HTML so we can't truly fetch dynamically here.
     Instead redirect to the dated folder. */
  const base = dir + '/' + date + '/';
  window.location.href = base;
}}

/* Anchor-based scrolling for quick links */
document.querySelectorAll('.ql').forEach(a => {{
  a.addEventListener('click', e => {{
    const id = a.getAttribute('href').slice(1);
    const cards = document.querySelectorAll('.card');
    const idx = {{'nse':0,'us':1,'sectors':2,'fno':3}}[id];
    if(idx !== undefined && cards[idx]) {{
      e.preventDefault();
      cards[idx].scrollIntoView({{ behavior:'smooth', block:'center' }});
      cards[idx].style.borderColor = 'var(--card-accent)';
      setTimeout(() => cards[idx].style.borderColor = '', 1500);
    }}
  }});
}});
</script>
</body>
</html>"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate top-level dashboard index.html")
    parser.add_argument("-r", "--root", default=".", help="Root directory containing reports/, us_reports/, etc.")
    parser.add_argument("-o", "--output", default="./index.html", help="Output path for dashboard HTML")
    args = parser.parse_args()

    root = os.path.abspath(args.root)
    html = generate_dashboard(root)

    out = os.path.abspath(args.output)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"  ✅ Dashboard: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
