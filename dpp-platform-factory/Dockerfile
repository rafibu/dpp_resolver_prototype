FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install uv
RUN pip install --no-cache-dir uv

# Copy project files needed for installation
COPY pyproject.toml .
COPY src/ src/

# Install the Factory package and dependencies
RUN uv pip install --system .

# Copy runtime data files
COPY seed-schemas/ seed-schemas/
COPY default-federation.yml .

# Factory port
EXPOSE 8000

# Run the Factory
CMD ["uvicorn", "dpp_platform_factory.api.api:app", "--host", "0.0.0.0", "--port", "8000"]
