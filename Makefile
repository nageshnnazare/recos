all: nse us sectors fno sp500 dashboard

nse:
	python3 report_generator.py --watchlist watchlist.txt --alerts --delay 8 -o ./reports/

us:
	python3 us_report_generator.py --watchlist us_watchlist.txt --alerts -o ./us_reports/

sectors:
	python3 sector_report_generator.py -o ./sector_reports/

fno:
	python3 fno_report_generator.py -o ./fno_reports/

sp500:
	python3 sp500_heatmap_generator.py -o ./sp500_reports/

dashboard:
	python3 dashboard_generator.py -r . -o ./index.html

fno-live:
	python3 fno_report_generator.py --live --port 8787

clean:
	rm -rf ./reports/*
	rm -rf ./us_reports/*
	rm -rf ./sector_reports/*
	rm -rf ./fno_reports/*

.PHONY: all nse us sectors fno sp500 dashboard fno-live clean