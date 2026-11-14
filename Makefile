PY ?= python

.PHONY: all fetch offline analyze test freeze clean
# fetch public data (falls back to data/snapshots/ if the network fails), then analyse
all:
	$(PY) -m ledger all
# same, but never touch the network: exactly the frozen snapshots
offline:
	$(PY) -m ledger all --offline
fetch:
	$(PY) -m ledger fetch
analyze:
	$(PY) -m ledger analyze
test:
	$(PY) -m ledger test
# maintainer only: freeze freshly fetched raw files as the committed snapshots
freeze:
	$(PY) -m ledger freeze
clean:
	rm -rf output site data/raw data/cache
