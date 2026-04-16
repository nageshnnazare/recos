# 📊 Multi-Market Stock Risk Analysis System

A professional-grade stock reporting and risk scoring system for NSE (India) and US markets. It generates detailed, reasoning-enabled HTML dashboards with technical and fundamental analysis.

## 🚀 Quick Start

### 1. Requirements
Ensure you have Python 3.14+ installed and install the dependencies:
```bash
pip install yfinance pandas
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

## 📅 Latest Recommendations

<!-- RECOMMENDATIONS_START -->
| Market | Stock | Score | Verdict | Upside | Report |
|--------|-------|-------|---------|--------|--------|
| NSE | RELIANCE | 66/100 | BUY | +11.2% | [View Report](https://nageshnnazare.github.io/recos/reports/2026-04-16/RELIANCE_RiskReport.html) |
| US | AAPL | 72/100 | BUY | +15.4% | [View Report](https://nageshnnazare.github.io/recos/us_reports/2026-04-16/AAPL_RiskReport.html) |
<!-- RECOMMENDATIONS_END -->

## 🌐 View Reports Live
GitHub doesn't render HTML files by default. To view the generated reports as interactive websites:
1. Go to the project **Settings** > **Pages**.
2. Set the Source to **GitHub Actions**.
3. The system is configured to automatically deploy the `reports/` folder via the `deploy_reports.yml` workflow.

---
*Disclaimer: This is an automated analysis tool. Not financial advice.*
