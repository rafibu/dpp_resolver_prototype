# DPP Resolver Prototype

This repository is the reference prototype for a research paper on **federated Digital Product Passport (DPP) architecture**. It is the concrete realization of the formal data model (paper Section 4) and its transition system (Section 5): a federation of independently operated platforms that share no governance authority, tied together by a thin resolver that holds the authoritative schema set and an issuer-to-platform registry.

The prototype exists to demonstrate three things the paper argues for:

- **Substrate-agnosticism.** The same operation semantics and federation protocol are implemented twice, on a relational stack (Java, Spring Boot, PostgreSQL) and a document stack (Python, FastAPI, MongoDB). Heterogeneity is the point, the two platforms are interoperable through the resolver.
- **Invariant preservation.** The seven structural invariants of the model (I1 to I7: revision uniqueness, version monotonicity, schema explicitness, payload integrity, schema conformance, schema-graph acyclicity, hard resolvability) are enforced by the running code, not just on paper.
- **Behavior in regulatory-relevant situations.** The end-to-end evaluation scenarios exercise federated reference stability under target evolution and issuer migration (S1), independent schema evolution with historical revisions remaining valid (S2), and schema-level cycle rejection (S3). Offline validation of cached hard-dependency closures remains available as S4, a supplemental check only; it is not part of the actual evaluation.

The prototype demonstrates architectural properties. It is not a production DPP platform, not a full implementation of EU ESPR requirements, and not a general-purpose benchmark suite. Authentication, access control, and transport security are deliberately out of scope, their absence does not affect the invariants the prototype verifies.

## Modules

| Module             | Folder                                                                          | What it is                                                                                                                                                                                                               | Details                                             |
|--------------------|---------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|-----------------------------------------------------|
| Resolver           | [`dpp-resolver/`](dpp-resolver/README.md)                                       | Java 25, Spring Boot, PostgreSQL. The federation's authoritative schema registry and issuer-to-platform registry (Definitions 6 and 10). Enforces schema-graph acyclicity (I6).                                          | [README](dpp-resolver/README.md)                    |
| DPP Platform A     | [`generic_dpp_platform_java/`](generic_dpp_platform_java/README.md)             | Java 25, Spring Boot, PostgreSQL. Reference platform on a relational substrate with JSON column support (hybrid relational-document pattern).                                                                            | [README](generic_dpp_platform_java/README.md)       |
| DPP Platform B     | [`generic_dpp_platform_python/`](generic_dpp_platform_python/README.md)         | Python 3.14, FastAPI, MongoDB. Reference platform on a document substrate. Same REST contract as Platform A, invariants enforced in application code.                                                                    | [README](generic_dpp_platform_python/README.md)     |
| Factory            | [`dpp-platform-factory/`](dpp-platform-factory/README.md)                       | Python 3.14, FastAPI + Docker SDK. Test-harness controller: spawns and manages the resolver and platform containers, seeds schemas, exposes `GET /federation` for topology discovery. Not part of the federation itself. | [README](dpp-platform-factory/README.md)            |
| Workload Generator | [`dpp-workload-generator/`](dpp-workload-generator/README.md)                   | Python 3.14 CLI. Drives the the end-to-end evaluation scenarios S1, S2, S3 (Section 7), and supplemental S4.                                                                                                             | [README](dpp-workload-generator/README.md)          |
| Frontend           | [`dpp-resolver-prototype-frontend/`](dpp-resolver-prototype-frontend/README.md) | TypeScript, Angular 21, SCSS. Federation observer, DPP browser and JSON editor, scenario runner.                                                                                                                         | [README](dpp-resolver-prototype-frontend/README.md) |

The Interaction Platform described as a separate artefact in `tech_stack.md` is implemented as the `workload scenario` subcommands of the Workload Generator.

## Formal model vs. implementation

The formal model is deliberately abstract. The prototype makes concrete choices where the model leaves them open, and approximates where the model is undecidable. The differences below do not weaken any invariant.

| Model concept                                                      | Implementation                                                                                                                                                                                                 |
|--------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Hash function `H` (abstract, collision-resistant)                  | SHA-256 over JCS-canonicalized (RFC 8785) payload, always computed server-side, never accepted from a client (I4).                                                                                             |
| Validator predicate `Val(s)` (any decidable predicate)             | JSON Schema Draft 2020-12 (`networknt/json-schema-validator` in Java, `jsonschema` in Python).                                                                                                                 |
| Backward compatibility `⊑` (Definition 15, undecidable in general) | A sound but incomplete syntactic check over a restricted JSON Schema fragment. Conservative: it may force a publisher to declare a minor update as major, but never accepts an incompatible minor update.      |
| Resolution function (Definition 11, returns a revision)            | Over HTTP: the Resolver returns a `302` redirect to the hosting platform, which then serves the revision. The Resolver never proxies payloads.                                                                 |
| Reference extraction (Definition 12)                               | Schema-annotated fields. Reference fields carry an `x-dpp-reference` annotation; instance shape is `{"$ref": "...", "version": N?}`. Presence of `version` is a hard dependency, absence is a soft dependency. |
| Revision tuple omits a timestamp                                   | Platforms additionally record a UTC ISO-8601 issuance time for audit only. Ordering still comes from version numbers (I2), not time.                                                                           |
| Federated state over `N` generic platforms (Definition 7)          | Ships two heterogeneous reference platforms by default (A: PV modules, B: batteries) plus a third Java platform (inverters). More can be spawned on demand via the Factory.                                    |
| Schema cache (Definition 5)                                        | Implemented with a TTL. The stored hash is re-verified on every cache read, so a tampered cache entry is rejected.                                                                                             |
| Resolver, platforms only                                           | The Factory, Workload Generator, and Frontend are prototype scaffolding and observability. They are not part of the formal model.                                                                              |

## Running the federation and the scenarios

### Prerequisites

- **Docker** (Desktop or Engine) with Docker Compose. This is the only requirement to run the federation.
- **Python 3.14+** to run the Workload Generator CLI (the scenarios).
- **Node.js + npm** only if you want to run the Frontend in development mode rather than via Docker.
- **Java 25 + Maven** only if you want to build the platform and resolver images locally rather than from a registry.

### 1. Build the platform images

The Factory does not build images, it expects them to exist. Build the three images once from the repository root:

```bash
docker build -t dpp-resolver:latest ./dpp-resolver
docker build -t generic-dpp-platform-java:latest ./generic_dpp_platform_java
docker build -t generic-dpp-platform-python:latest ./generic_dpp_platform_python
```

The database images (`postgres:16`, `mongo:7`) are pulled automatically.

### 2. Start the Factory and Frontend

From the repository root:

```bash
docker compose up
```

This starts the Factory (host port `8000`) and the Frontend (host port `4200`). On startup the Factory:

1. Brings up the Resolver and its PostgreSQL database (port `8080`).
2. Spawns the default federation: Platform A / PV modules (port `8081`), Platform B / batteries (port `8082`), Platform C / inverters (port `8083`), each with its own database.
3. Registers each platform with the Resolver and seeds the authoritative schema set.

The Factory mounts the Docker socket so it can manage sibling containers. To run the Factory alone without the Frontend, use `docker compose up factory`.

### 3. Open the Frontend

Navigate to `http://localhost:4200`. The Frontend discovers the whole topology by calling `GET /federation` on the Factory, then talks to the Resolver and platforms directly for federation-level operations. It provides:

- **Federation map** showing the Resolver, platforms, and their links.
- **Per-platform DPP browser** with revision histories and a live log viewer.
- **Online/offline toggle** per platform (drives the Factory pause/resume, used to simulate a platform becoming unreachable).
- **JSON editor** (Monaco) for issuing and revising DPP payloads, with client-side schema validation.
- **Scenario runner** for triggering S1, S2, S3, and supplemental S4 and viewing their Markdown reports.

Polling at a 2-second interval keeps the views current, there are no websockets.

### 4. Run the scenarios from the CLI

With the federation running, install and run the Workload Generator. From the repository root:

```bash
cd dpp-workload-generator
pip install -e .          # or: uv pip install -e .
```

Then run each scenario. They discover the live topology through the Factory, so no URLs need to be supplied:

```bash
workload scenario s1 --output-dir output/scenarios   # reference stability under target evolution and issuer migration
workload scenario s2 --output-dir output/scenarios   # independent schema evolution
workload scenario s3 --output-dir output/scenarios   # schema-level cycle rejection
workload scenario s4 --output-dir output/scenarios   # supplemental offline-validation check
```

Each command writes a Markdown report with per-step expected-vs-observed outcomes and a PASSED/FAILED verdict. S1, S2, and S3 are the Section 7 evaluation scenarios. S4 is a supplemental check only, not part of the actual evaluation, and is retained to see whether offline validation may be interesting for future work. The same CLI also drives the quantitative measurements (`workload measure ...`); see the [Workload Generator README](dpp-workload-generator/README.md) for the full command set.

## Further documentation

- [Tech Stack](tech_stack.md) — definitive technology decisions per module.
- Per-module READMEs linked in the table above.
