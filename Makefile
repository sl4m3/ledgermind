.PHONY: install install-core install-server install-adapters test clean

install: install-core install-server install-adapters

install-core:
	pip install -e ./core

install-server:
	pip install -e ./mcp_server

install-adapters:
	pip install -e ./adapters

test:
	cd core && pytest tests
	cd mcp_server && pytest tests

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
