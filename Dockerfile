# Dockerfile for LedgerMind
FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends 
    git 
    build-essential 
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Create non-root user
RUN useradd -m -u 1000 ledgermind && 
    mkdir -p /app/data && 
    chown -R ledgermind:ledgermind /app

# Copy project files
COPY --chown=ledgermind:ledgermind . .

# Switch to non-root user
USER ledgermind

# Install LedgerMind and all dependencies
RUN pip install --no-cache-dir .[all]

# Environment variables
ENV LEDGERMIND_STORAGE_PATH=/app/data
ENV LEDGERMIND_API_KEY=""

# Expose ports
# REST Gateway / MCP SSE
EXPOSE 8080
# Prometheus Metrics
EXPOSE 9090

# Default entrypoint
ENTRYPOINT ["ledgermind-mcp"]
CMD ["run", "--path", "/app/data"]
