# Prototype Tech Stack

Definitive technology decisions and operational specification for each artefact in the DPP prototype. Use this as the implementation reference. This file reflects the technology stack as actually implemented.

## Cross-cutting decisions

These apply to every artefact and are not repeated below.

| Concern                      | Decision                                                                                                                         |
|------------------------------|----------------------------------------------------------------------------------------------------------------------------------|
| Hashing                      | SHA-256                                                                                                                          |
| JSON canonicalization        | JCS (RFC 8785)                                                                                                                   |
| Schema format                | JSON Schema Draft 2020-12                                                                                                        |
| Schema version embedding     | `$id` field, e.g. `https://schemas.dpp.eu/pv_module/1.2`                                                                         |
| Backward compatibility check | Custom function (implemented separately)                                                                                         |
| Identity format              | `<subject_type>/<issuer>-<local_id>[/<version>]`                                                                                 |
| Timestamps                   | UTC, ISO 8601, millisecond precision                                                                                             |
| Logging                      | Structured JSON lines on stdout, captured by Docker                                                                              |
| Container management         | Docker, Docker SDK for Python                                                                                                    |
| Inter-component API style    | REST over HTTP                                                                                                                   |
| Reference encoding           | Schema-annotated field, instance shape `{"$ref": "...", "version": N?}`. Presence of `version` = hard dependency, absence = soft |

## Architectural roles

The Resolver and the Factory have distinct responsibilities that should not blur:

- **Resolver:** federation primitive. Behaves like a real-world DPP resolver. Knows about platforms only because they registered themselves. Has no awareness of the test harness.
- **Factory:** test harness controller. Owns the prototype's runtime: spawns and manages platform containers, tracks their port mappings, drives lifecycle operations (pause, resume, reset). Acts as the primary backend for the Frontend.

The Frontend talks primarily to the Factory. The Factory tells the Frontend where to find the Resolver and the platforms. The Frontend talks to the Resolver and platforms directly only for federation-level operations (resolution, DPP retrieval, schema retrieval).

## Artefact 1: Resolver

The federation's discovery service and authoritative schema registry.

### Stack

| Layer              | Choice                            |
|--------------------|-----------------------------------|
| Language / Runtime | Java 25                           |
| Framework          | Spring Boot 4.0 (latest patch)    |
| Web layer          | Spring MVC, REST controllers      |
| Persistence        | Spring Data JPA, Hibernate        |
| Database           | PostgreSQL 16                     |
| Migrations         | Flyway                            |
| Build              | Maven                             |
| Logging            | SLF4J + Logback, JSON encoder     |
| Container          | Eclipse Temurin JRE 25 base image |

### Responsibilities

- Maintain identity-to-platform mappings: which platform hosts a given logical DPP
- Store and serve schema artefacts as the authoritative source
- Validate platform registrations (unique platform ID, valid endpoint)
- Issue redirects for federated DPP references
- Never proxy DPP payloads; data path is platform-to-platform direct

### REST endpoints

- `POST /platforms` register a platform
- `GET /platforms/{id}` retrieve platform info
- `GET /platforms` list registered platforms
- `POST /schemas` publish a schema artefact (returns 422 if minor update breaks compatibility)
- `GET /schemas/{subject_type}/{major}.{minor}` retrieve a schema
- `GET /<subject_type>/<issuer>-<local_id>[/<version>]` resolve identity, returns 302
- `GET /health` liveness probe

### Operational notes

- Stateless on payload data, only stores identity mappings and schemas
- Schema publication is append-only (Invariant: schemas never modified after publication)
- Returns `Location` header on 302 redirects, including the resolved version when one was specified
- Backward compatibility check on schema publication: if claimed minor update fails the check, returns 422
- The Resolver does not know it is running inside a test harness; it behaves as a real federation Resolver would

### Java 25 notes

- JSpecify null-safety annotations are first-class in Spring Boot 4. Use `@Nullable` and `@NonNull` from `org.jspecify.annotations` consistently
- Records are the default for DTOs
- Pattern matching in switch expressions is welcome where it improves clarity

## Artefact 2: DPP-Platform A

Spring Boot reference platform with relational persistence.

### Stack

| Layer                  | Choice                             |
|------------------------|------------------------------------|
| Language / Runtime     | Java 25                            |
| Framework              | Spring Boot 4.0                    |
| Web layer              | Spring MVC                         |
| Persistence            | Spring Data JPA, Hibernate         |
| Database               | PostgreSQL 16                      |
| Migrations             | Flyway                             |
| JSON Schema validation | networknt/json-schema-validator    |
| JCS canonicalization   | erdtman/java-json-canonicalization |
| Build                  | Maven                              |
| Logging                | SLF4J + Logback, JSON encoder      |

### Responsibilities

- Issue and revise DPPs for its registered subject types
- Store revisions in hybrid relational + JSON model
- Cache external DPP revisions resolved through the Resolver
- Cache schemas for its domain locally (read-through from Resolver)
- Detect hard-dependency cycles before issuance (including transitive across platforms)
- Validate revisions against schema before persistence
- Serve revisions to other platforms and consumers


### REST endpoints

- `POST /dpps` issue first revision
- `POST /dpps/{dpp_id}/revisions` append revision
- `GET /dpps/{dpp_id}` get current revision
- `GET /dpps/{dpp_id}/{version}` get specific revision
- `GET /schemas/{subject_type}/{major}.{minor}` schema lookup, cache-first
- `GET /health` liveness probe

### Operational notes

- Hash is computed server-side from canonicalized payload, never accepted from client
- Schema validation runs before any persistence
- Cycle detection runs synchronously on issue/revise, may call Resolver and other platforms
- External cache hits are verified by hash on every read
- Consider Spring Boot 4's HTTP Service Clients for the Resolver and inter-platform clients (declarative `@HttpExchange` interfaces auto-implemented by the framework)

## Artefact 3: DPP-Platform B

FastAPI reference platform with document persistence.

### Stack

| Layer                  | Choice                                           |
|------------------------|--------------------------------------------------|
| Language / Runtime     | Python 3.14                                      |
| Web framework          | FastAPI                                          |
| ASGI server            | Uvicorn                                          |
| Validation models      | Pydantic v2                                      |
| Database               | MongoDB 7                                        |
| Database driver        | PyMongo Async (>= 4.9), using `AsyncMongoClient` |
| JSON Schema validation | jsonschema                                       |
| JCS canonicalization   | jcs                                              |
| Logging                | structlog, JSON output                           |
| Package manager        | uv                                               |

### Driver decision: PyMongo Async, not Motor

Motor is being deprecated on May 14, 2026. New code must use the PyMongo Async API (`pymongo.AsyncMongoClient`). The API is similar enough to Motor that examples translate directly:

```python
from pymongo import AsyncMongoClient

client = AsyncMongoClient("mongodb://platform-b-db:27017")
db = client.dpp_platform_b
await db.dpp_revisions.insert_one({...})
```

Note: `AsyncMongoClient` is not thread-safe and must be confined to a single asyncio event loop. This matches FastAPI's request handling model.

### Responsibilities

Identical to Platform A. Same REST contract, same behavior. The only differences are storage and language.

### Indexes

- `dpp_revisions`: compound index on `(dpp_id, dpp_version)` unique
- `external_cache`: TTL index on `expires_at`
- `dpp_schemas`: compound index on `(subject_type, major_version, minor_version)`

### REST endpoints

Identical to Platform A. Same paths, same shapes.

### Python 3.14 notes

- Use `from __future__ import annotations` is no longer needed; annotations are lazily evaluated by default (PEP 649)
- Type hints throughout, leveraging deferred evaluation
- Free-threading mode is officially supported but not enabled by default; the prototype uses standard GIL-based Python
- `t-strings` (template string literals, PEP 750) are available; useful for safe URL construction in the resolver client

## Artefact 4: Factory

The test harness controller. Owns the prototype's runtime environment.

### Stack

| Layer                | Choice                                               |
|----------------------|------------------------------------------------------|
| Language / Runtime   | Python 3.14                                          |
| Web framework        | FastAPI                                              |
| Container management | Docker SDK for Python (`docker` package)             |
| Database             | None (in-memory state, persistent via Docker labels) |
| Logging              | structlog                                            |
| Package manager      | uv                                                   |

### Responsibilities

**At startup:**
- Check for orphaned containers from previous runs (filtered by Docker label `managed-by=dpp-factory`)
- If orphans exist, prompt the operator: shut them down or reuse?
- Bring up the Resolver and its database
- Bring up the default federation platforms per config file
- Become the primary backend for the Frontend

**During runtime:**
- Spawn additional platforms on request (F-3, F-4)
- Pause and resume platforms (F-6, F-7)
- Reset platform state (F-5)
- Maintain authoritative mapping of `(platform_id -> external_url)` for the Frontend and other harness consumers
- Expose Resolver location to the Frontend
- Provide platform list and status

**At shutdown:**
- Stop all spawned platform and database containers in parallel
- Stop the Resolver and its database
- Clean up Docker network

### REST endpoints

```
GET    /health                         liveness probe
GET    /federation                     overview: resolver URL, list of platforms with URLs
GET    /platforms                      list all managed platforms with their external URLs
POST   /platforms                      spawn a new platform (F-3, F-4)
GET    /platforms/{id}                 platform details (status, URL, config)
POST   /platforms/{id}/pause           pause platform (F-6)
POST   /platforms/{id}/resume          resume platform (F-7)
POST   /platforms/{id}/reset           reset platform state (F-5)
DELETE /platforms/{id}                 tear down platform
GET    /resolver                       resolver URL and status
POST   /resolver/seed-schemas          load predefined schemas into Resolver (for scenario setup)
```

The `GET /federation` endpoint is the entry point for the Frontend. Single call returns everything the Frontend needs to draw the federation map and route subsequent calls.

### Internal state

In-memory only:

```
platforms: dict[platform_id, PlatformRecord]
  PlatformRecord:
    platform_id, stack, issuer_id, subject_types
    container_id, db_container_id
    external_url, internal_url
    status (running/paused/error)
    created_at

resolver: ResolverRecord
  container_id, db_container_id, external_url
  status, started_at
```

Persistent recovery via Docker labels: `managed-by=dpp-factory`, `dpp-factory-role=platform|database|resolver`, `dpp-factory-platform-id=<id>`. On startup, query Docker for labeled containers and either reconnect or shut down (operator's choice).

### Default federation config

```yaml
# factory/default-federation.yml
resolver:
  port: 8080

default_platforms:
  - id: platform-a
    stack: spring-postgres
    issuer: issuerA
    subject_types: [pv_module]
    port: 8081
  - id: platform-b
    stack: fastapi-mongo
    issuer: issuerB
    subject_types: [battery]
    port: 8082
  - id: platform-c
    stack: spring-postgres
    issuer: issuerC
    subject_types: [inverter]
    port: 8083
```

Additional platforms spawned via `POST /platforms` get ports starting at 8084.

### Container conventions

- Network: `dpp-net` (Factory creates if missing)
- Naming: `dpp-platform-<id>` and `dpp-platform-<id>-db`, `dpp-resolver` and `dpp-resolver-db`
- Labels: `managed-by=dpp-factory`, `dpp-factory-role=...`, `dpp-factory-platform-id=...`
- Health check: poll platform's `/health` for up to 30 seconds with 1-second intervals

### Operational notes

- Single instance: only one Factory runs at a time. No coordination across instances.
- Pre-built images: Factory does not build images. Images must be built before Factory startup via Makefile or CI.
- Atomic operations: spawn either succeeds completely (platform running, registered, healthy) or rolls back fully.

## Artefact 5: Workload Generator

Drives the four end-to-end evaluation scenarios (S1–S4) and the supplemental
offline-interpretability check (S5) against the live federation.

### Stack

| Layer                    | Choice                                       |
|--------------------------|----------------------------------------------|
| Language / Runtime       | Python 3.14                                  |
| Execution                | Typer CLI with subcommands                   |
| HTTP client              | httpx (async)                                |
| Federation discovery     | Calls Factory's `GET /federation`            |
| Measurement output       | CSV files for raw measurements               |
| Scenario output          | Markdown reports per scenario, with outcomes |
| Plotting (separate step) | matplotlib                                   |
| Package manager          | uv                                           |

### Responsibilities

Measurement and fixtures:

- Generate DPPs with controllable hard-dependency depth
- Generate DPPs with controllable fan-out
- Generate the running PV/battery/inverter scenario as a fixture
- Generate valid and invalid DPPs against given schemas
- Drive measurement runs: timing each operation, recording bytes
- Write structured CSV output for analysis

Scenarios:

- Set up the prerequisite federation state for each scenario via the Factory
- Execute the scenario steps in order and capture expected vs observed outcome per step
- Produce a structured Markdown report with a PASSED/FAILED verdict

### CLI subcommands

Measurement and fixtures:

- `workload generate-depth --depth N`
- `workload generate-fanout --fanout N`
- `workload pv-scenario`
- `workload measure --workload depth|fanout|issue|resolve --range 1-10 --runs 5 --output results.csv`
- `workload schema-evolution --revisions N --update-kind minor|major`

Scenarios:

- `workload scenario s1 --output-dir output/scenarios` federated reference stability under target evolution and issuer migration
- `workload scenario s2 --output-dir output/scenarios` independent schema evolution
- `workload scenario s3 --output-dir output/scenarios` schema-level cycle rejection
- `workload scenario s4 --output-dir output/scenarios` derived-query evaluation: indexed and on-demand predicate retrieval and reverse traversal
- `workload scenario s5 --output-dir output/scenarios` supplemental offline-interpretability check; not part of the paper's evaluation

The Workload Generator queries the Factory at startup to discover platform URLs. It does not need to be told manually where platforms are.

### Output format

Measurement CSV columns:

```
run_id, workload_kind, parameter_value, operation, latency_ms, bytes_payload, bytes_index, success, error, warmup
```

## Artefact 6: Frontend

The federation observer, scenario driver, and DPP editor.

### Stack

| Layer             | Choice                                                    |
|-------------------|-----------------------------------------------------------|
| Language          | TypeScript                                                |
| Framework         | Angular 21                                                |
| Styling           | SCSS                                                      |
| Build             | Angular CLI                                               |
| HTTP client       | Angular HttpClient                                        |
| State management  | Angular Signals for UI state, RxJS for HttpClient streams |
| Visualization     | ngx-graph for the federation map                          |
| JSON editor       | monaco-editor with ngx-monaco-editor-v2 wrapper           |
| Schema validation | ajv for client-side validation                            |
| Container         | nginx serving static build                                |

### Backend integration

The Frontend's primary backend is the **Factory**. On load, the Frontend calls `GET /federation` to discover the Resolver URL and the list of platform URLs. All subsequent calls route based on this discovery:

- Platform lifecycle (spawn, pause, resume, reset): Factory
- Federation map data: Factory
- DPP operations on a specific platform: that platform's URL (from Factory's response)
- Resolution operations: Resolver URL (from Factory's response)
- Schema operations: Resolver URL

This design isolates the Frontend from container details and lets the test harness swap implementations without Frontend changes.

### Responsibilities

Keep list (minimum viable):

- Federation map view: platforms, Resolver, links, current state
- Per-platform DPP list and revision history view
- Per-platform log viewer (reads from Docker logs via Factory proxy or a small backend)
- Online/offline toggle per platform (calls Factory pause/resume)
- Trigger-scenario buttons for S1, S2, S3, and S4 (invokes scenarios via the Factory)
- Raw JSON editor for DPP payloads with client-side schema validation
- Display of platform state changes after operations

Cut list (out of scope):

- Schema-driven form generation
- Real-time websocket updates (use polling, 2-second interval)
- Authentication
- Schema editing UI

## Container topology

The Factory is the entry point. On startup, it brings up:

- 1x Resolver + 1x Postgres (resolver-db)
- 3x DPP-Platforms (per default federation config) + their respective databases (postgres or mongodb)

Frontend and Workload Generator are not spawned by the Factory:

- Frontend runs as its own container (nginx), but is started separately via `docker compose up frontend` or run during development with `ng serve`. It discovers everything via the Factory.
- Workload Generator (including the scenario subcommands) is a CLI tool, invoked from the developer's terminal.

### Network

- Single Docker network `dpp-net`
- Service discovery within the network via container names
- Factory exposes its API on host port 8000
- Resolver and platforms expose their APIs via Factory-allocated host ports

## Summary of artefact-to-stack mapping

| Artefact             | Language    | Framework            | Storage                   | Container?  | Spawned by Factory? |
|----------------------|-------------|----------------------|---------------------------|-------------|---------------------|
| Resolver             | Java 25     | Spring Boot 4        | Postgres 16               | Yes         | Yes                 |
| DPP-Platform A       | Java 25     | Spring Boot 4        | Postgres 16               | Yes         | Yes                 |
| DPP-Platform B       | Python 3.14 | FastAPI              | MongoDB 7 (PyMongo Async) | Yes         | Yes                 |
| Factory              | Python 3.14 | FastAPI + Docker SDK | None (in-memory)          | Yes         | No (entry point)    |
| Workload Generator   | Python 3.14 | CLI, httpx           | CSV + Markdown output     | No (CLI)    | No                  |
| Frontend             | TypeScript  | Angular 21           | None                      | Yes (nginx) | No                  |

## Version pinning notes

For reproducibility and supply-chain stability, pin minor versions in build files:

- **Java**: 25 (LTS, released September 2025)
- **Spring Boot**: 4.0.x (latest patch at implementation time, 4.0.6 as of April 2026)
- **Python**: 3.14.x (latest patch, 3.14.4 as of February 2026)
- **PyMongo**: >= 4.9 (the version that introduced production-ready Async API)
- **PostgreSQL**: 16 (`postgres:16` image)
- **MongoDB**: 7 (current production)

Lock file management:

- Java: Maven (`pom.xml`), built via the bundled `mvnw` wrapper
- Python: uv's `uv.lock`
- TypeScript: npm or pnpm `package-lock.json` / `pnpm-lock.yaml`
