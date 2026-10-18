.PHONY: test run report

test:
	python -m unittest discover -s tests -v

report:
	python reports/generate_report.py

run:
	python app.py
