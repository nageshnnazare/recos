all: nse us

nse:
	python3 report_generator.py --watchlist watchlist.txt --alerts -o ./reports/

us:
	python3 us_report_generator.py --watchlist us_watchlist.txt --alerts -o ./us_reports/

clean:
	rm -rf ./reports/*
	rm -rf ./us_reports/*

.PHONY: all nse us clean