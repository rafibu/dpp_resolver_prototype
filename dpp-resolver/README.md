# DPP Resolver

This project is a Spring Boot implementation of the **resolver** role in a federated Digital
Product Passport (DPP) ecosystem.

It implements the resolver-side parts of the paper's model:

- the authoritative schema set and its governance operations,
- the resolver registry mapping issuers to hosting platforms,
- federated reference resolution with HTTP redirects,
- schema-graph cycle prevention,
- schema backward-compatibility enforcement.

## Paper-to-implementation map

This section explains where the main definitions, invariants, and operations from the paper are
implemented in this resolver.

### Definitions implemented by this module

| Paper item                                 | Meaning in the paper                                                                                | Java implementation                                                                 |
|--------------------------------------------|-----------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------|
| **Definition 3: Schema artefact**          | A schema with subject type, validator, and (major, minor) version.                                  | `DppSchema`, `DppSchemaId`                                                          |
| **Definition 6: Resolver state**           | The authoritative schema set and the resolver registry.                                             | `DppSchema` table (schema set) and `Platform` table (registry)                      |
| **Definition 10: Resolver registry**       | A total function from issuer identifiers to hosting platforms.                                      | `Platform` entity; looked up by `PlatformRepository.findByAbbreviation`             |
| **Definition 11: Resolution**              | Two-step lookup: registry to find the hosting platform, then the platform's state for the revision. | `UrlResolverService.resolveUrl(...)` returning a 302 redirect URL                   |
| **Definition 13: Schema dependency graph** | Directed graph over subject types induced by hard-reference declarations in schemas.                | `SchemaDependency` table; `HardReferenceExtractor` builds edges                     |
| **Definition 15: Backward compatibility**  | Every payload valid under the old schema is also valid under the new schema.                        | `JsonUtil.assertIsBackwardsCompatible(...)`                                         |
| **Definition 16: Schema update**           | Minor update requires backward compatibility; major update may break it.                            | `DppSchemaService.assertValidSchema(...)` checks compatibility for minor increments |

### Invariants enforced by this module

| Paper item                                | Meaning                                                                                  | Implementation                                                                                                            |
|-------------------------------------------|------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------|
| **Invariant I3: Schema explicitness**     | Every revision on any DPP platform references a schema present in the authoritative set. | Schemas are never deleted; `DppSchemaRepository` is append-only.                                                          |
| **Invariant I6: Schema-graph acyclicity** | The schema dependency graph contains no cycles.                                          | `SchemaCycleDetector.checkForCycle(...)` called during every `publishSchema`; `SchemaGraphRebuilder` verifies on startup. |

### Operations implemented by this module

| Paper operation         | Meaning                                                                             | Java implementation                                                                  |
|-------------------------|-------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------|
| **publishSchema**       | Add a new schema artefact to the authoritative set, enforcing I6 and compatibility. | `POST /schemas` handled by `DppSchemaController`, `DppSchemaService.save(...)`       |
| **registerIssuer**      | Add a new issuer-to-platform mapping to the resolver registry.                      | `POST /admin/platforms` (upsert: new issuer = register) via `PlatformController`     |
| **migrate**             | Update an existing issuer's platform mapping in the resolver registry.              | `POST /admin/platforms` (upsert: existing issuer = migrate) via `PlatformController` |
| **resolve** (read-only) | Look up the hosting platform for a federated reference and return a redirect URL.   | `GET /{subjectType}/{dppId}[/{revision}]` via `UrlResolverController`                |

## Implementation overview

The resolver state consists of two components (Definition 6):

1. **Authoritative schema set**: all published `DppSchema` artefacts, stored in Postgres. Once
   published, a schema is never removed. DPP platforms cache subsets of this set
   locally and reference exact versions in every revision (Invariant I3).

2. **Resolver registry**: all `Platform` records, each mapping one issuer identifier to a
   hosting platform URL template (Definition 10). The registry is used by the `resolve` operation
   (Definition 11) to route resolution requests.

The main lifecycle:

1. Register subject types.
2. Publish schemas for each subject type (with cycle and compatibility checks).
3. Register issuers and their hosting platform URLs.
4. DPP platforms cache schemas and issue revisions.
5. When a DPP platform needs to verify a hard reference, it calls the resolver's `resolve`
   endpoint, receives a 302 redirect, and fetches the revision from the hosting platform.

## Invariant enforcement

### I3: Schema explicitness (Federated)

Every revision on any DPP platform references a schema present in the authoritative set (Invariant
I3). The resolver enforces the "present in set" half: `DppSchemaService.save(...)` is the only
write path into the schema table, and there is no delete path. The `DppSchema` entity is append-only.

### I6: Schema-graph acyclicity (Resolver)

The schema dependency graph (Definition 13) has subject types as vertices and a directed edge from
type A to type B when any version of a schema for A declares a `x-dpp-reference` field targeting B.
Invariant I6 requires this graph to remain acyclic.

`DppSchemaService.save(...)` checks I6 before every schema publication via
`SchemaCycleDetector.checkForCycle(...)`. By Proposition 1, this single check at schema
publication time is enough to guarantee instance-level acyclicity across the entire federation:
no DPP platform can create a circular hard-reference chain regardless of which specific revisions
they issue, because the schema graph from which their references derive is acyclic.

`SchemaGraphRebuilder` runs at startup and rebuilds the `schema_dependency` table from the stored
schemas if drift is detected.

### I6 error responses

A `422 Unprocessable Entity` response is returned if publication violates I6.

**Cycle detected:**

```json
{
  "error": "schema_cycle_detected",
  "message": "Publishing schema 'battery' 2.0 would introduce a cycle: battery -> pv_module -> battery",
  "cycle_path": [
    "battery",
    "pv_module",
    "battery"
  ]
}
```

**Self-reference detected:**

```json
{
  "error": "schema_self_reference",
  "message": "Schema 'pv_module' 2.0 declares a hard reference to its own subject type",
  "subject_type": "pv_module"
}
```

## Schema compatibility

Schema version increments enforce Definition 16.

For a **minor update** (same major, minor + 1): `JsonUtil.assertIsBackwardsCompatible(...)` checks
that the new schema is backward-compatible with the predecessor (Definition 15). Backward
compatibility means every payload valid under the old schema also validates under the new one.
The check is a sound but not necessarily complete syntactic approximation over the supported JSON
Schema fragment.

For a **major update** (major + 1, minor = 0): no compatibility check is required.

## Main components

### `UrlResolverController`

Exposes the `resolve` operation as HTTP redirect endpoints.

| Method | Path                                       | Paper operation or concept  | Purpose                                             |
|--------|--------------------------------------------|-----------------------------|-----------------------------------------------------|
| `GET`  | `/{subjectType}/{dppId}`                   | **resolve**, soft reference | Returns 302 to hosting platform (current revision). |
| `GET`  | `/{subjectType}/{dppId}/{revisionVersion}` | **resolve**, hard reference | Returns 302 to hosting platform (exact revision).   |

The response includes `X-DPP-Reference-Type: SOFT` or `HARD` to indicate the reference mode
(Definition 9).

### `UrlResolverService`

Implements Definition 11 (Resolution) by looking up the issuer in the registry (Definition 10)
and constructing the redirect URL.

The issuer is extracted as the prefix before the first `-` in the DPP ID. The local identifier
may itself contain `-` (for example when it is a UUID).

### `PlatformController`

Exposes the `registerIssuer` and `migrate` operations via a
single upsert endpoint. A `POST /admin/platforms` request creates a registry entry if the issuer
is new, or updates it if the issuer is already registered.

| Method | Path                    | Paper operation or concept                 | Purpose                                           |
|--------|-------------------------|--------------------------------------------|---------------------------------------------------|
| `GET`  | `/admin/platforms`      | Resolver registry (Definition 10)          | Lists all issuer-to-platform mappings.            |
| `GET`  | `/admin/platforms/{st}` | Resolver registry filtered by subject type | Lists mappings for a given subject type.          |
| `POST` | `/admin/platforms`      | **registerIssuer** or **migrate**          | Creates or updates an issuer-to-platform mapping. |

### `DppSchemaController`

Exposes the `publishSchema` operation and read access to the authoritative schema
set (Definition 6).

| Method | Path                                     | Paper operation or concept  | Purpose                                                                    |
|--------|------------------------------------------|-----------------------------|----------------------------------------------------------------------------|
| `GET`  | `/schemas/{subjectType}`                 | Authoritative schema set    | Returns all published schemas for a subject type.                          |
| `GET`  | `/schemas/{subjectType}/current`         | Authoritative schema set    | Returns the most recent schema version for a subject type.                 |
| `GET`  | `/schemas/{subjectType}/{major}/{minor}` | Authoritative schema set    | Returns an exact schema version (used by DPP platforms for `cacheSchema`). |
| `POST` | `/schemas`                               | **publishSchema** operation | Publishes a new schema artefact, enforces I6 and compatibility.            |

### `DppSchemaService`

Core logic for the `publishSchema` operation. Enforces:

- version monotonicity (major increments by 1, minor increments by 1 within same major),
- backward compatibility for minor updates (Definition 15, Definition 16),
- schema-graph acyclicity (Invariant I6, precondition P4).

### `SchemaCycleDetector`

Implements the acyclicity check for Invariant I6 via an iterative DFS over the candidate graph.
Returns a sealed `CycleCheckResult` with variants `Acyclic`, `CycleDetected`, and `SelfReference`.

### `HardReferenceExtractor`

Extracts hard-reference target subject types from a JSON Schema document by scanning for
`x-dpp-reference` annotations. These annotations drive the schema dependency graph (Definition 13).

### `SchemaGraphRebuilder`

Runs at startup via `@PostConstruct`. Compares the `schema_dependency` table against what would be
derived from the stored schemas and rebuilds the table if drift is detected. This is a self-healing
mechanism for the I6 data structure.

### `SubjectTypeController`

Manages the set of subject types used throughout the formal model. Subject types must exist before
schemas can be published for them or issuers can be registered for them.

### `Platform`

Entity for one resolver registry entry (Definition 10). Fields:

| Field           | Meaning                                                                |
|-----------------|------------------------------------------------------------------------|
| `abbreviation`  | Issuer identifier (prefix of all DPP IDs issued by this platform).     |
| `platformName`  | Human-readable platform name.                                          |
| `resolutionUrl` | URL template used to construct redirect URLs. Must contain `{dppId}`.  |
| `subjectTypes`  | Subject types this issuer declared support for (extension of Def. 10). |

### `DppSchema`

Entity for one schema artefact in the authoritative schema set (Definition 3). Immutable once
published. Fields: `subjectType`, `majorVersion`, `minorVersion`, `schemaDocument` (JSONB),
`publishedAt`.

### `SchemaDependency`

Stores one directed edge in the schema dependency graph (Definition 13). Each edge records
`fromSubjectType`, `toSubjectType`, and the schema version that introduced it. The full set of
edges is maintained by `DppSchemaService` and verified by `SchemaGraphRebuilder`.

## Data model overview

| Entity             | Paper item                                       | Purpose                                                    |
|--------------------|--------------------------------------------------|------------------------------------------------------------|
| `Platform`         | **Definition 10** (resolver registry entry)      | Issuer-to-platform mapping with URL template.              |
| `SubjectType`      | Subject type set (Definitions 1, 3, 13)          | Product domain governed by schemas.                        |
| `DppSchema`        | **Definition 3** (schema artefact)               | Published schema in the authoritative set (Definition 6).  |
| `DppSchemaId`      | **Definition 3** (schema version)                | Composite key: subject type, major version, minor version. |
| `SchemaDependency` | **Definition 13** (schema dependency graph edge) | One hard-reference edge in the schema dependency graph.    |

## Differences between the paper model and this implementation

### 1. Subject-type filtering in the registry

The formal registry (Definition 10) maps issuers to platforms without subject-type constraints.
This implementation adds a subject-type list to each registry entry as a prototype-level guard:
the `resolve` endpoint returns 404 if the registered platform does not declare support for the
requested subject type. This is not part of the formal model.

### 2. Schema publication endpoint path

The `publishSchema` operation is exposed at `POST /schemas`. This path also serves GET requests
for the schema list. The paper treats schema publication and schema reads as distinct operations;
the implementation shares the base path for REST convenience.

### 3. Resolver registry does not handle per-DPP routing

Definition 10 routes by issuer only: all DPPs from a given issuer are co-located on one platform.
This implementation follows that model. There is no per-DPP or per-subject-type routing in the
registry; subject-type filtering is a validation add-on.

### 4. Resolution returns a redirect, not the revision payload

Definition 11 returns the revision directly. This implementation returns a 302 redirect to the
hosting platform so the calling platform fetches the revision itself. This preserves the federated
separation: the resolver does not replicate DPP data.

### 5. Schema backward-compatibility check is a sound approximation

Definition 15 defines backward compatibility as a universal quantification over the payload domain,
which is undecidable in general. `JsonUtil.assertIsBackwardsCompatible(...)` implements a sound
syntactic check over a restricted JSON Schema fragment: it accepts
only if compatibility holds, but may reject some compatible pairs as false negatives.

## Schema annotation convention

The `x-dpp-reference` annotation in JSON Schema documents declares hard-reference targets:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "batteryRef": {
      "type": "object",
      "x-dpp-reference": "battery"
    }
  }
}
```

Any property annotated with `"x-dpp-reference": "subjectType"` tells the resolver that payloads
valid under this schema may contain hard references to the named subject type. The resolver uses
these annotations to build the schema dependency graph. See `docs/schema-conventions.md` for the
full specification.

## API examples

### Register an issuer

```bash
curl -X POST http://localhost:8080/admin/subject-types \
  -H "Content-Type: application/json" \
  -d '{"name": "battery", "description": "EV battery passport"}'

curl -X POST http://localhost:8080/admin/platforms \
  -H "Content-Type: application/json" \
  -d '{
    "platform": "Platform A",
    "issuerId": "issuerA",
    "resolutionUrl": "http://platform-a:8081/dpps/{dppId}",
    "subjectTypes": ["battery"]
  }'
```

### Publish a schema

```bash
curl -X POST http://localhost:8080/schemas \
  -H "Content-Type: application/json" \
  -d '{
    "subjectType": "battery",
    "majorVersion": 1,
    "minorVersion": 0,
    "schemaDocument": {
      "$schema": "https://json-schema.org/draft/2020-12/schema",
      "type": "object",
      "properties": {
        "serialNumber": {"type": "string"},
        "capacityKwh": {"type": "number"}
      },
      "required": ["serialNumber"],
      "additionalProperties": false
    }
  }'
```

### Resolve a soft reference

```bash
# Returns 302 to http://platform-a:8081/dpps/issuerA-product-001
curl -v http://localhost:8080/battery/issuerA-product-001
```

### Resolve a hard reference

```bash
# Returns 302 to http://platform-a:8081/dpps/issuerA-product-001/2
curl -v http://localhost:8080/battery/issuerA-product-001/2
```

## Configuration

The resolver is configured via environment variables.

| Environment variable         | Description               | Default                                         |
|------------------------------|---------------------------|-------------------------------------------------|
| `SPRING_DATASOURCE_URL`      | JDBC URL for the database | `jdbc:postgresql://localhost:5432/dpp_resolver` |
| `SPRING_DATASOURCE_USERNAME` | Database username         | `postgres`                                      |
| `SPRING_DATASOURCE_PASSWORD` | Database password         | `postgres`                                      |

## Running locally

1. Create a Postgres database named `dpp_resolver`.
2. Set the required environment variables:

```bash
export SPRING_DATASOURCE_URL="jdbc:postgresql://localhost:5432/dpp_resolver"
export SPRING_DATASOURCE_USERNAME="postgres"
export SPRING_DATASOURCE_PASSWORD="postgres"
```

3. Start the application:

```bash
./mvnw spring-boot:run
```

## Running with Docker

```bash
docker run \
  -e SPRING_DATASOURCE_URL="jdbc:postgresql://db:5432/dpp_resolver" \
  -e SPRING_DATASOURCE_USERNAME="postgres" \
  -e SPRING_DATASOURCE_PASSWORD="postgres" \
  -p 8080:8080 \
  dpp-resolver
```

## Prerequisites

- Java 25 or newer
- PostgreSQL
- Subject types, schemas, and issuer registrations must be created before DPP platforms can issue
  revisions

## Common setup sequence

1. Start PostgreSQL.
2. Start this resolver.
3. Register subject types.
4. Publish schemas for each subject type.
5. Start DPP platforms.
6. Register each platform's issuer in the resolver.
7. DPP platforms cache schemas.
8. DPP platforms issue and revise DPPs.

## Development notes

### Build

```bash
./mvnw clean package
```

### Run tests

```bash
./mvnw test
```
