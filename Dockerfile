# syntax=docker/dockerfile:1.4
FROM python:3.11-slim as builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first for caching
COPY pyproject.toml .
RUN pip install --no-cache-dir build uv && \
    uv pip install --system -r pyproject.toml

# Copy application code
COPY src/ /app/src/
COPY config/ /app/config/

# ---------------------------------------------------------
FROM python:3.11-slim as runtime

# Install runtime CV dependencies (OpenCV headless still needs some libs)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy python packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages/ /usr/local/lib/python3.11/site-packages/
COPY --from=builder /usr/local/bin/ /usr/local/bin/

# Copy application code
COPY --from=builder /app /app

# Set non-root user for security
RUN useradd -m -u 1000 atved_user
USER atved_user

ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

# Default command runs the API Server
CMD ["python", "api_server.py"]
