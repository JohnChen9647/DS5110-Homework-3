PYTHON ?= python3
RAW_DIR := data/raw/ml-100k
DATABASE := data/movielens.db

.PHONY: all download clean FORCE

all: $(DATABASE)

# First record strict-load rejections, then rebuild fully without overwriting the report.
$(DATABASE): FORCE src/download.py src/load.py src/reload.py sql/schema.sql
	$(PYTHON) src/download.py
	$(PYTHON) src/load.py $(RAW_DIR) $@
	$(PYTHON) src/reload.py $(RAW_DIR) $@

download:
	$(PYTHON) src/download.py

clean:
	rm -f $(DATABASE) output/rejected.csv

FORCE:
