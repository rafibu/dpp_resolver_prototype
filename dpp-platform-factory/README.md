# DPP Platform Factory

## Role in the Paper

The Factory is the **test harness controller** for the prototype. It is not part of the federated DPP ecosystem. It creates and manages the containers that form that ecosystem.

The paper's formal model defines a federated state (Definition 7) as a resolver plus a set of DPP platforms. In a real deployment these components would be operated independently by different organizations. For the prototype we need them all running in one place and wired together reproducibly. The Factory handles that:

| What the Factory does                                                                           | Paper anchor                                                                        |
|-------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------|
| Brings up the Resolver and registers each platform with it via `POST /admin/platforms/register` | `registerIssuer` and Definition 10 (resolver registry)                              |
| Seeds the authoritative schema set on the Resolver via `POST /schemas`                          | `publishSchema` and Definition 6 (resolver state)                                   |
| Ensures each subject type exists on the Resolver before schemas are published                   | Pre-condition for `publishSchema`                                                   |
| Exposes `GET /federation` so the Frontend and Workload Generator can discover the live topology | Definition 7 (federated state) as an observable snapshot                            |
| Pauses and resumes platform containers to drive offline scenarios (S4)                          | Scenario infrastructure; the pause operation models a platform becoming unreachable |
| Resets platform databases to a known empty state between scenario runs                          | Scenario infrastructure; restores the empty DPP platform state (Definition 5)       |

The Resolver and DPP platforms behave exactly as they would in a real federation. The Factory is invisible to them: the Resolver receives `POST /admin/platforms/register` calls as if a real operator were registering platforms, and the platforms receive their `RESOLVER_URL` as an environment variable as if it were a stable production endpoint.

## Architecture

```
Factory (port 8000)
├── starts and monitors → Resolver (port 8080) + Postgres
├── starts and monitors → Platform A (port 8081) + Postgres
├── starts and monitors → Platform B (port 8082) + MongoDB
├── starts and monitors → Platform C (port 8083) + Postgres
└── exposes GET /federation → consumed by Frontend and Workload Generator
```

Source layout:

- `api/` — FastAPI routes and Pydantic response models
- `core/` — orchestration logic (`platform.py`, `platform_service.py`, `schema_seed_service.py`) and in-memory state (`state.py`)
- `infrastructure/` — Docker SDK wrapper (`docker_client.py`), Resolver container lifecycle (`resolver.py`), Resolver HTTP client (`resolver_client.py`)
- `utils/` — bootstrap, shutdown, orphan recovery, configuration, logging
- `seed-schemas/` — JSON Schema 2020-12 documents for the default PV/battery/inverter federation

## Prerequisites

- Python 3.14+
- Docker Desktop or Docker Engine running
- Pre-built images: `dpp-resolver:latest`, `generic-dpp-platform-java:latest`, `generic-dpp-platform-python:latest`

## Running the Factory

```bash
cd dpp-platform-factory
pip install -e .
python -m dpp_platform_factory
```

Or via Docker Compose from the repository root:

```bash
docker compose up factory
```

## Testing

Three-layered strategy:

| Layer       | What it tests                                                          | How                                             |
|-------------|------------------------------------------------------------------------|-------------------------------------------------|
| Unit        | Pure logic (config validation, state management, Docker label parsing) | Fast, no Docker                                 |
| Integration | Orchestration flow through real service boundaries                     | `FakeDockerClient` + `FakeResolverClient` fakes |
| E2E         | Full lifecycle against real Docker containers                          | Requires pre-built images                       |

```bash
# Unit + Integration (no Docker required)
py -3.14 -m pytest tests

# E2E (requires Docker and pre-built images)
py -3.14 -m pytest tests/e2e -m e2e
```

## Environment Variables

| Variable                   | Description                                                             | Default                            |
|----------------------------|-------------------------------------------------------------------------|------------------------------------|
| `DPP_FACTORY_ORPHANS`      | Action for containers from a previous run (`shutdown`, `reuse`, `fail`) | `fail` (interactive prompt if TTY) |
| `DPP_FACTORY_KEEP_RUNNING` | Skip cascade shutdown on exit                                           | `false`                            |
| `DPP_FACTORY_TESTING`      | Skip bootstrap during unit/integration tests                            | `false`                            |

## API Endpoints

Interactive docs at `http://localhost:8000/docs`.

| Method   | Path                     | Purpose                                                                                                 |
|----------|--------------------------|---------------------------------------------------------------------------------------------------------|
| `GET`    | `/health`                | Liveness probe                                                                                          |
| `GET`    | `/federation`            | Full topology snapshot (resolver URL + all platforms). Entry point for Frontend and Workload Generator. |
| `GET`    | `/platforms`             | List managed platforms                                                                                  |
| `POST`   | `/platforms`             | Spawn a new platform container                                                                          |
| `GET`    | `/platforms/{id}`        | Platform details                                                                                        |
| `POST`   | `/platforms/{id}/pause`  | Stop the platform container (simulates platform going offline)                                          |
| `POST`   | `/platforms/{id}/resume` | Restart a paused platform                                                                               |
| `POST`   | `/platforms/{id}/reset`  | Rebuild the platform database from scratch                                                              |
| `DELETE` | `/platforms/{id}`        | Tear down platform and its database                                                                     |
| `GET`    | `/resolver`              | Resolver URL and status                                                                                 |
| `POST`   | `/resolver/seed-schemas` | Load `seed-schemas/*.json` into the Resolver's authoritative schema set                                 |

## Troubleshooting

- **Docker daemon unavailable**: Ensure Docker is running and the socket is accessible.
- **Port conflicts**: Default ports are 8080-8083. Dynamic platforms start at 8084.
- **Tests hanging**: Set `DPP_FACTORY_TESTING=true` when running tests manually.
- **Orphans found**: Use `DPP_FACTORY_ORPHANS=shutdown` to clean up containers from a previous crashed run.
