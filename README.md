# Multi-Market Stock Risk Analysis System

A professional-grade, automated reporting system for NSE (India) and US markets. Generates detailed HTML dashboards with technical and fundamental analysis, sector rotation insights, F&O option chain analysis with strategy recommendations, and a unified dashboard — all powered by GitHub Actions.

## Quick Start

### Requirements

Python 3.12+ and the project dependencies:

```bash
pip install -r requirements.txt
```

### Generate All Reports

```bash
make all
```

This runs NSE stocks, US stocks, sector rotation, F&O outlook, and builds the dashboard (`index.html`).

## Reports

### NSE Stock Risk Reports

Per-stock HTML reports with risk scoring, technical signals, fundamental ratios, and buy/hold/sell verdicts.

```bash
# Single ticker
python3 report_generator.py RELIANCE

# Multiple tickers
python3 report_generator.py INFY TCS

# Full watchlist with alerts
python3 report_generator.py --watchlist watchlist.txt --alerts --delay 8 -o ./reports/
```

Output: `reports/<date>/<TICKER>_RiskReport.html` + `DAILY_SUMMARY.md`

### US Stock Risk Reports

Same risk framework adapted for US equities via Yahoo Finance.

```bash
# Single ticker
python3 us_report_generator.py AAPL

# Full watchlist with alerts
python3 us_report_generator.py --watchlist us_watchlist.txt --alerts -o ./us_reports/
```

Output: `us_reports/<date>/<TICKER>_RiskReport.html` + `DAILY_SUMMARY.md`

### Sector Rotation Report

Daily sector rotation analysis covering all tradable NSE sector indices:

- **RRG Scatter Plot** — Relative Rotation Graph showing sector positioning (Leading / Improving / Weakening / Lagging)
- **Rotation Trail Plot** — How sectors moved over the past weeks
- **Market Breadth** — Cap-wise index performance (Nifty 50, 100, 200, Midcap 100/150)
- **Sector Leaders** — Top 3 stocks per sector with 1W/1M/1Y returns
- **Detailed Analysis** — Per-quadrant breakdown with reasons and outlook

```bash
python3 sector_report_generator.py -o ./sector_reports/
```

Output: `sector_reports/<date>/SectorRotation_Report.html`

### F&O Index Outlook

NIFTY 50 and NIFTY BANK option chain analysis with:

- **OI/IV/Greeks analysis** — Put-call ratio, max pain, ATM positioning
- **Full option chain table** — Scrollable table with OI, Change in OI, IV, LTP, Delta, Gamma, Theta, Vega for both Calls and Puts
- **Strategy recommendation** — Bull/Bear spreads, Iron Condor, Straddles based on verdict + IV + OI
- **Interactive P&L simulator** — Canvas-based chart with breakeven markers, max profit/loss boundaries, and a price slider

```bash
# Static report
python3 fno_report_generator.py -o ./fno_reports/

# Live server with auto-refreshing option chain (polls Groww every 30s)
python3 fno_report_generator.py --live --port 8787
```

Output: `fno_reports/<date>/FNO_IndexOutlook_Report.html`

### Dashboard

Top-level `index.html` that links to every report across all sections:

```bash
python3 dashboard_generator.py -r . -o ./index.html
```

## Make Targets

| Target | Description |
|--------|-------------|
| `make all` | Generate all reports + dashboard |
| `make nse` | NSE stock reports only |
| `make us` | US stock reports only |
| `make sectors` | Sector rotation report only |
| `make fno` | F&O index outlook only |
| `make dashboard` | Rebuild the dashboard index |
| `make fno-live` | Start F&O live server on port 8787 |
| `make clean` | Delete all generated reports |

## GitHub Actions

### Daily Reports (`daily-reports.yml`)

Runs Mon–Fri at 9:30 AM IST. Generates all reports, builds the dashboard, commits them to the repo, and opens a GitHub Issue if value-buy alerts are found.

### Dashboard & F&O Live Pages (`fno-live.yml`)

Runs every 15 minutes during NSE market hours (9:00 AM – 3:45 PM IST). Regenerates the F&O report with fresh option chain data and deploys the full dashboard + all reports to GitHub Pages.

**Setup:** Go to repo Settings → Pages → set Source to **GitHub Actions**.

## View Reports Live

| Report | Link |
|--------|------|
| Dashboard | [View](https://nageshnnazare.github.io/recos/) |
| Sector Rotation | [View](https://nageshnnazare.github.io/recos/sector_reports/SectorRotation_Report.html) |
| F&O Outlook | [View](https://nageshnnazare.github.io/recos/fno_reports/FNO_IndexOutlook_Report.html) |
| NSE Stock Reports | [Browse](https://nageshnnazare.github.io/recos/reports/) |
| US Stock Reports | [Browse](https://nageshnnazare.github.io/recos/us_reports/) |

## Project Structure

```
recos/
├── report_generator.py          # NSE stock risk reports
├── us_report_generator.py       # US stock risk reports
├── sector_report_generator.py   # NSE sector rotation & RRG
├── fno_report_generator.py      # F&O option chain & strategy
├── dashboard_generator.py       # Top-level dashboard builder
├── watchlist.txt                # NSE tickers
├── us_watchlist.txt             # US tickers
├── requirements.txt             # Python dependencies
├── Makefile                     # Build targets
├── .github/workflows/
│   ├── daily-reports.yml        # Daily report generation
│   └── fno-live.yml             # Pages deployment + F&O refresh
├── reports/                     # NSE reports (git-ignored, CI-only)
├── us_reports/                  # US reports (git-ignored, CI-only)
├── sector_reports/              # Sector reports (git-ignored, CI-only)
├── fno_reports/                 # F&O reports (git-ignored, CI-only)
└── index.html                   # Dashboard (git-ignored, CI-only)
```

Report directories are gitignored locally. Only the GitHub Actions bot commits generated reports via `git add -f`.

## Data Sources

| Data | Source |
|------|--------|
| NSE stock prices & fundamentals | Yahoo Finance (via yfinance) |
| US stock prices & fundamentals | Yahoo Finance (via yfinance) |
| NSE sector indices | Yahoo Finance |
| F&O option chain | Groww.in SSR pages |
| NSE index breadth | NSE equity-stockIndices API |
| Market news | Google News RSS, Economic Times RSS |

---

*Disclaimer: This is an automated analysis tool for educational purposes. Not financial advice.*
