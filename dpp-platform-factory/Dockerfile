FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install uv
RUN pip install --no-cache-dir uv

# Install both packages from the monorepo. Factory S4 imports the reusable
# workload implementation directly; it never shells out to the workload CLI.
COPY dpp-workload-generator/ /app/workload-generator/
COPY dpp-platform-factory/ /app/factory/
RUN uv pip install --system /app/workload-generator /app/factory

WORKDIR /app/factory
RUN mkdir -p output/scenarios

# Factory port
EXPOSE 8000

# Run the Factory
CMD ["uvicorn", "dpp_platform_factory.api.api:app", "--host", "0.0.0.0", "--port", "8000"]
