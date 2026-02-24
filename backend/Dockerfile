FROM python:3.11-slim-bookworm

LABEL version="4.0.0"
LABEL description="Talos v4.0 Ironclad — Backend"

# Install tini (PID 1 / zombie reaper) and runtime deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    tini \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r -g 1000 talos && useradd -r -u 1000 -g talos -s /bin/bash talos

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY --chown=talos:talos . .

# Runtime directories
RUN mkdir -p /talos/skills/quarantine /talos/skills/active /talos/skills/deprecated \
             /talos/logs/tier1 /talos/logs/tier2 /talos/logs/tier3 \
             /talos/tmp \
    && chown -R talos:talos /talos

USER talos

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -sf http://localhost:8080/health || exit 1

# tini as PID 1 ensures proper signal handling and zombie reaping
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
