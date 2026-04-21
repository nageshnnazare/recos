# 📊 Multi-Market Stock Risk Analysis System

A professional-grade stock reporting and risk scoring system for NSE (India) and US markets. It generates detailed, reasoning-enabled HTML dashboards with technical and fundamental analysis, plus a daily sector rotation report.

## 🚀 Quick Start

### 1. Requirements
Ensure you have Python 3.14+ installed and install the dependencies:
```bash
pip install yfinance pandas numpy requests beautifulsoup4 lxml
```

### 2. Generate Reports

#### 🇮🇳 NSE Stocks
```bash
# Single ticker
python3 report_generator.py RELIANCE

# Multiple tickers
python3 report_generator.py INFY TCS

# From a watchlist file
python3 report_generator.py --watchlist watchlist.txt --alerts
```

#### 🇺🇸 US Stocks
```bash
# Single ticker
python3 us_report_generator.py AAPL

# Multiple tickers
python3 us_report_generator.py MSFT TSLA

# From a watchlist file
python3 us_report_generator.py --watchlist us_watchlist.txt --alerts
```

#### 🔄 NSE Sector Rotation Report
```bash
python3 sector_report_generator.py -o ./sector_reports/
```

#### Run Everything
```bash
make all   # Runs NSE stocks, US stocks, and sector report
```

## 📈 Sector Rotation Report

Daily sector rotation analysis covering all tradable NSE sector indices with:
- **RRG Scatter Plot** — Relative Rotation Graph showing sector positioning (Leading / Improving / Weakening / Lagging)
- **Rotation Trail Plot** — How sectors moved over the past weeks
- **Market Breadth** — Cap-wise index performance (Nifty 50, 100, 200, Midcap 100/150)
- **Sector Leaders** — Top 3 stocks per sector with 1W/1M/1Y returns
- **Detailed Analysis** — Per-quadrant breakdown with reasons and outlook

👉 [**View Latest Sector Report**](https://htmlpreview.github.io/?https://github.com/nageshnnazare/recos/blob/main/sector_reports/SectorRotation_Report.html)

## 📅 Latest Recommendations

<!-- RECOMMENDATIONS_START -->
| Market | Stock | Score | Verdict | Upside | Report |
|--------|-------|-------|---------|--------|--------|
| NSE | RELIANCE | 66/100 | BUY | +11.2% | [View Report](https://nageshnnazare.github.io/recos/reports/2026-04-16/RELIANCE_RiskReport.html) |
| US | AAPL | 72/100 | BUY | +15.4% | [View Report](https://nageshnnazare.github.io/recos/us_reports/2026-04-16/AAPL_RiskReport.html) |
<!-- RECOMMENDATIONS_END -->

## 🌐 View Reports Live

| Report | Link |
|--------|------|
| Sector Rotation | [View](https://htmlpreview.github.io/?https://github.com/nageshnnazare/recos/blob/main/sector_reports/SectorRotation_Report.html) |
| NSE Stock Reports | [Browse](https://nageshnnazare.github.io/recos/reports/) |
| US Stock Reports | [Browse](https://nageshnnazare.github.io/recos/us_reports/) |

GitHub doesn't render HTML files by default. The links above use [htmlpreview.github.io](https://htmlpreview.github.io) for the sector report and GitHub Pages for stock reports.

---
*Disclaimer: This is an automated analysis tool. Not financial advice.*
