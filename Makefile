.PHONY: install install-core install-multi test clean

install: install-core install-multi

install-core:
	pip install -e ./core

install-multi:
	pip install -e ./multi

test:
	cd core && pytest tests
	cd multi && pytest tests

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
