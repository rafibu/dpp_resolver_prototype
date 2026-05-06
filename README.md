# DPP Resolver Prototype

A complete prototype for a decentralized Digital Product Passport (DPP) resolution system.

## Project Structure

- `dpp_resolver/`: Centralized registry for DPP platform mappings and schemas. (Java/Spring Boot)
- `generic_dpp_platform_java/`: Template for a DPP platform using Java and Spring Boot.
- `generic_dpp_platform_python/`: Template for a DPP platform using Python and FastAPI.
- `factory/`: Orchestration service to manage the lifecycle of the whole federation. (Python/FastAPI)
- `workload-generator/`: CLI tool to generate synthetic workloads and measure system performance. (Python)

## Getting Started

### Prerequisites

- Java 21
- Python 3.12+
- Docker & Docker Compose

### Quick Start with Factory

The easiest way to run the whole system is using the Factory:

```bash
docker compose up factory
```

This will:
1. Start the Factory.
2. Bootstrap a DPP Resolver and its database.
3. Spawn a set of default DPP platforms (Java and Python versions).
4. Register them with the Resolver.

The system is then accessible at:
- Frontend UI: `http://localhost:4200`
- Factory API: `http://localhost:8000`
- Resolver API: `http://localhost:8080`
- Default Platforms: Starting from `http://localhost:8081`

## Frontend UI

The Frontend is an Angular 21 single-page application that provides a visual dashboard for the federation.

### Features

- **Federation Map**: Interactive topology visualization using `ngx-graph`.
- **Platform Management**: Lifecycle controls (pause, resume, reset, delete) and real-time logs.
- **DPP Browser**: Inspect logical DPPs and their revision histories.
- **JSON Editor**: Integrated Monaco editor with AJV schema validation for creating and revising DPPs.
- **Scenario Runner**: Trigger and monitor automated research scenarios (S1, S2) with live Markdown reports.

### Development

```bash
cd dpp-resolver-prototype-frontend
npm install
npm run start
```
The UI will be available at `http://localhost:4200`.

### Production (Docker)

The Frontend is included in the root `docker-compose.yml`.
```bash
docker compose up frontend
```

## Factory Orchestration

The `factory/` service provides a REST API to dynamically manage the federation.

- **Spawn new platforms**: `POST /platforms`
- **Pause/Resume**: `POST /platforms/{id}/pause`
- **Reset data**: `POST /platforms/{id}/reset`
- **Teardown**: `DELETE /platforms/{id}`

See [factory/README.md](factory/README.md) for more details.

## Workload Generator

The `workload-generator/` is a CLI tool designed to set up specific federation states and drive automated measurements.

### Usage

```bash
# Install dependencies
cd workload-generator
# Recommended: use uv
uv pip install -e .

# Run the tool
workload --help
```

### Subcommands

- **`workload scenario s1`**: Offline Interpretability scenario. Demonstrates resolution from cache when a platform is unreachable.
- **`workload scenario s2`**: Independent Schema Evolution scenario. Demonstrates major version updates and historical schema availability.
- **`workload measure`**: Runs automated measurement cycles. Supports `depth`, `fanout`, `issue`, and `resolve` workloads.
- **`workload generate-depth --depth N`**: Creates a hierarchical chain of DPPs of length N.
- **`workload generate-fanout --fanout N`**: Creates a parent DPP with N child dependencies.
- **`workload pv-scenario`**: Materializes the paper's running example (PV/Battery/Inverter).
- **`workload schema-evolution`**: Measures the impact of minor (v1.1) and major (v2.0) schema updates.

### Measurement Data

Results are persisted as CSVs in `workload-generator/output/`.

### Scenario Reports

The `workload scenario` commands produce narrative reports in Markdown format. These reports are stored in `workload-generator/output/scenarios/` (or via `WORKLOAD_OUTPUT_DIR` env var).

Each report includes:
- **Run ID and Timestamps**: Unique identifier for the run.
- **Outcome**: Overall status (PASSED/FAILED).
- **Step-by-step Logs**: Expected vs. observed behavior for each scenario step.
- **Formal-model Verification**: Confirmation of invariants (e.g., I4, I5, I7) during the run.

These reports are suitable for inclusion in Section 8.4 of the paper.

| Column | Meaning | Unit |
|--------|---------|------|
| `latency_ms` | End-to-end operation time | milliseconds |
| `bytes_payload` | JSON payload size | bytes |
| `bytes_index` | DB storage overhead | bytes (0 if unsupported) |
| `warmup` | Flag for initial non-recorded runs | boolean |

### Visualizations

Produce plots from CSV results:
```bash
python workload-generator/scripts/plot.py workload-generator/output/results.csv
```

### Limitations & Research Readiness

- **`bytes_index`**: Currently defaults to `0`. Database introspection for exact storage overhead is not yet implemented at the platform level.
- **`query` workload**: Stubbed as regulatory query endpoints (P-9) are not part of this implementation phase.
- **Depth/Fan-out Ranges**: Recommended maximum depth is 15 and fan-out 50 for stable local runs.
- **Docker Dependency**: E2E tests and live federation runs require a running Docker daemon. If Docker is unavailable, tests will skip cleanly.
- **Federation Reset**: The `workload measure` command attempts to reset the federation via the Factory between runs. Ensure the Factory has sufficient permissions to manage containers.

### E2E Testing

To run the complete certification suite (requires Docker):
```bash
cd workload-generator
pytest tests/e2e -m e2e
```

## Testing

The project includes unit, integration, and E2E tests for the Factory.

```bash
# Run unit and integration tests
py -3.14 -m pytest factory/tests

# Run E2E tests (requires Docker)
py -3.14 -m pytest factory/tests/e2e -m e2e
```

## Documentation

- [Task List](factory/factory_implementation_tasks.md)
- [Implementation Log](IMPLEMENTATION_LOG.md)
- [Tech Stack](tech_stack.md)
