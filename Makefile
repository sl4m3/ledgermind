.PHONY: install test clean lint benchmark docker-build docker-run help

install:
	pip install -e .[all,dev]

test:
	pytest tests

lint:
	ruff check .

benchmark:
	pytest tests/core/performance/test_bench_ops.py --benchmark-json benchmarks/results/latest.json

docker-build:
	docker build -t ledgermind:latest .

docker-run:
	docker run -p 8080:8080 -p 9090:9090 -v $$(pwd)/data:/app/data ledgermind:latest

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".benchmarks" -exec rm -rf {} +

help:
	@echo "Ledgermind Makefile"
	@echo "  install      - Install in editable mode with all dependencies"
	@echo "  test         - Run all tests"
	@echo "  lint         - Run ruff linter"
	@echo "  benchmark    - Run performance benchmarks"
	@echo "  docker-build - Build Docker image"
	@echo "  docker-run   - Run Docker container"
	@echo "  clean        - Remove build artifacts and caches"
