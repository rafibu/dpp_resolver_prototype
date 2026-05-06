# DPP Platform Factory

The Factory is an orchestration service for the DPP Resolver Prototype. It manages the lifecycle of the Resolver and multiple DPP Platforms using Docker.

## Features

- **Automated Bootstrap**: Brings up the Resolver and a default set of platforms on startup.
- **Dynamic Spawning**: Create new DPP platforms (Spring or FastAPI) on demand.
- **Lifecycle Management**: Pause, resume, reset, and teardown platforms via REST API.
- **Resolver Integration**: Automatically registers new platforms with the Resolver.
- **Schema Seeding**: Bulk-load JSON schemas into the Resolver from local files.
- **Orphan Handling**: Detects and handles containers from previous runs (shutdown, reuse, or fail) and can reconstruct state from running containers on startup.
- **Graceful Cascade Shutdown**: Stops all managed containers in the correct order on exit.

## Prerequisites

- Python 3.14+
- Docker Desktop or Docker Engine running
- (Optional) `uv` for fast dependency management

## Local Installation

```bash
cd dpp-platform-factory
pip install -e .
```

## Running the Factory

### Locally

```bash
# From the dpp-platform-factory directory
python -m factory
```

Or with uvicorn directly:

```bash
uvicorn factory.api:app --host 0.0.0.0 --port 8000
```

### With Docker Compose

```bash
# From the repository root
docker compose up factory
```

## Testing

The project uses a three-layered testing strategy:

### 1. Unit Tests
Fast tests for pure logic using mocks where necessary.
Located in `tests/`.

### 2. Service-level Integration Tests
High-fidelity tests using realistic fakes (`FakeDockerClient`, `FakeResolverClient`) instead of broad mocks. These exercise the real orchestration logic through public service boundaries.
Located in `tests/`.

### 3. E2E Tests
Tests that use real Docker containers to exercise the full system lifecycle.
Located in `tests/e2e/`.

#### Running Tests

Normal tests (Unit + Integration):
```bash
py -3.14 -m pytest tests
```

E2E tests (Requires Docker and pre-built images):
```bash
py -3.14 -m pytest tests/e2e -m e2e
```

## Environment Variables

| Variable                   | Description                                                  | Default                            |
|----------------------------|--------------------------------------------------------------|------------------------------------|
| `DPP_FACTORY_ORPHANS`      | Action for orphaned containers (`shutdown`, `reuse`, `fail`) | `fail` (interactive prompt if TTY) |
| `DPP_FACTORY_KEEP_RUNNING` | If `true`, skip cascade shutdown on exit                     | `false`                            |
| `DPP_FACTORY_TESTING`      | If `true`, skip bootstrap during tests                       | `false`                            |

## API Endpoints

The API is available at `http://localhost:8000`. Interactive documentation can be found at `http://localhost:8000/docs`.

### Key Endpoints

- `GET /federation`: Overview of the whole federation.
- `POST /platforms`: Spawn a new platform.
- `POST /platforms/{id}/pause`: Stop a platform container.
- `POST /platforms/{id}/resume`: Start a paused platform.
- `POST /platforms/{id}/reset`: Reset a platform's database.
- `DELETE /platforms/{id}`: Teardown a platform.
- `POST /resolver/seed-schemas`: Seed schemas into the resolver.

## Architecture

The Factory is built with FastAPI and is organized into the following components:

- `api/`: Route declarations and API models.
- `core/`: Core business logic, including platform lifecycle and state management.
- `infrastructure/`: Clients for external services like Docker and the Resolver.
- `utils/`: Configuration, logging, and lifecycle utilities.

## Pre-built Images

To run E2E tests or the full Factory, ensure the following images are built:
- `dpp-resolver:latest`
- `dpp-platform-spring:latest`
- `dpp-platform-fastapi:latest`
- `dpp-factory:latest`

## Troubleshooting

- **Docker daemon unavailable**: Ensure Docker is running and the socket is accessible. On Linux/macOS, you might need `sudo` or to be in the `docker` group.
- **Port conflicts**: The factory starts allocating ports from `8084`. Ensure these ports are not used by other services.
- **Tests hanging**: Ensure `DPP_FACTORY_TESTING=true` is set when running tests manually to avoid accidental Docker orchestration.
- **Orphans found**: If the factory crashed, it might leave containers. Use `DPP_FACTORY_ORPHANS=shutdown` to clean them up on next start.
