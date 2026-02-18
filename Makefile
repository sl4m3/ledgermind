.PHONY: install test clean help

install:
	pip install -e .[all,dev]

test:
	pytest tests

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".benchmarks" -exec rm -rf {} +

help:
	@echo "Ledgermind Makefile"
	@echo "  install   - Install in editable mode with all dependencies"
	@echo "  test      - Run all tests"
	@echo "  clean     - Remove build artifacts and caches"
