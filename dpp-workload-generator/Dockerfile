FROM python:3.14-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1

# Copy project files
# We don't have uv.lock yet, so we just copy pyproject.toml
COPY pyproject.toml ./
COPY src/ ./src/

# Install dependencies (system-wide in the container)
RUN uv pip install --system -e .

# Create output directory and set as volume-ready
RUN mkdir -p output
VOLUME ["/app/output"]

ENTRYPOINT ["workload"]
