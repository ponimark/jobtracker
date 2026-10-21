FROM python:3.12-slim

WORKDIR /app

# Install uv for fast package installs
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files first (layer cache)
COPY pyproject.toml uv.lock* ./

# Install dependencies (no editable install in prod)
RUN uv sync --frozen --no-dev

# Copy source
COPY src/ ./src/
COPY config/ ./config/
COPY migrations/ ./migrations/

# Add src to PYTHONPATH
ENV PYTHONPATH=/app/src

ENTRYPOINT ["uv", "run", "--no-sync"]
CMD ["jobtracker", "--help"]
