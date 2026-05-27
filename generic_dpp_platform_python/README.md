# Generic DPP Platform Python

This project is a FastAPI/MongoDB implementation of the **DPP platform** role in a federated
Digital Product Passport (DPP) ecosystem.

It implements the platform-side parts of the paper's model:

- logical DPP identity and revision history,
- immutable DPP revisions,
- schema-pinned validation,
- payload hashing,
- hard and soft DPP references,
- hard-reference resolution through a resolver,
- local schema caching,
- local caching of externally referenced revisions.

This platform implements the **same REST contract** as the Java/PostgreSQL platform
(`generic_dpp_platform_java`). Heterogeneity of stack and storage (FastAPI + MongoDB vs.
Spring Boot + PostgreSQL) is intentional and demonstrates that the federated architecture is
not tied to any single technology.

## Paper-to-implementation map

This section explains where the main definitions, invariants, and operations from the paper are
implemented in this Python platform.

### Definitions implemented by this module

| Paper item                              | Meaning in the paper                                                                              | Python implementation                                                                       |
|-----------------------------------------|---------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------|
| **Definition 1: Logical DPP**           | A stable DPP identity independent of individual revisions.                                        | `logical_dpps` MongoDB collection; `dpp_id` field                                           |
| **Definition 2: Revision**              | An immutable versioned state of a logical DPP, including schema, payload, and hash.               | `dpp_revisions` MongoDB collection; `DppRevisionResponseDTO`                                |
| **Definition 3: Schema artefact**       | A schema with subject type, validator, and major/minor version.                                   | `schemas` MongoDB collection; `DppSchemaDTO`                                                |
| **Definition 4: Revision validity**     | A revision is valid if its hash matches its payload and its payload validates against its schema. | `dpps/utils.py`: `validate_dpp_document`, `hash_document`, `verify_hash_integrity`          |
| **Definition 5: DPP platform state**    | The local revision set and local schema cache of one platform.                                    | MongoDB collections: `logical_dpps`, `dpp_revisions`, `schemas`, `referenced_dpp_revisions` |
| **Definition 8: Federated reference**   | A reference to another DPP independent of its hosting platform.                                   | `DppReference` in `dpps/models.py`                                                          |
| **Definition 9: Reference mode**        | Hard references target exact revisions; soft references target logical DPPs.                      | `DependencyType.HARD`, `DependencyType.SOFT`                                                |
| **Definition 11: Resolution**           | Resolving a reference by consulting the resolver and then the hosting platform.                   | `schemas/resolver_connector.py`: `resolve_dpp_revision`                                     |
| **Definition 12: Reference extraction** | Extracting DPP references from a payload.                                                         | `dpps/reference_extractor.py`: `extract_references`                                         |

### Invariants implemented by this module

| Paper item                                         | Meaning                                                                  | Implementation                                                                                             |
|----------------------------------------------------|--------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------|
| **Invariant I1: Revision uniqueness**              | A logical DPP cannot have two different revisions with the same version. | Unique compound index on `(dpp_id, dpp_version)` in `dpp_revisions`.                                       |
| **Invariant I2: Version monotonicity and density** | Revision versions form a gap-free sequence starting at 1.                | `dpps/service.py`: `_acquire_next_version` via MongoDB `findOneAndUpdate` with `$inc`                      |
| **Invariant I3: Schema explicitness**              | Every revision explicitly references a schema known to the resolver.     | Implemented locally by requiring the exact schema version to exist in the local cache before issue/revise. |
| **Invariant I4: Payload integrity**                | Stored hash equals the hash of the payload.                              | `dpps/utils.py`: `hash_document` (SHA-256 over JCS-canonicalized JSON)                                     |
| **Invariant I5: Schema conformance**               | Payload validates against the pinned schema.                             | `dpps/utils.py`: `validate_dpp_document` (JSON Schema Draft 2020-12)                                       |
| **Invariant I7: Hard resolvability**               | Every hard reference resolves to an existing concrete revision.          | `dpps/service.py`: `_resolve_and_cache_hard_reference`                                                     |

### Operations implemented by this module

| Paper operation | Meaning                                                                      | Python implementation                                                                      |
|-----------------|------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------|
| **issue**       | Create a new logical DPP and its first revision.                             | `POST /dpps/issue`, `dpps/service.py`: `create_new_dpp`                                    |
| **revise**      | Append a new revision to an existing logical DPP.                            | `POST /dpps/{dpp_id}/revise`, `dpps/service.py`: `create_dpp_revision_for_existing`        |
| **cacheSchema** | Fetch schemas from the resolver into the local platform cache.               | `POST /schemas/{subjectType}/cacheSchema`, `schemas/resolver_connector.py`: `cache_schema` |
| **resolve**     | Resolve a hard reference through the resolver and fetch the target revision. | `schemas/resolver_connector.py`: `resolve_dpp_revision`                                    |

## Implementation overview

The platform stores logical DPPs and append-only revisions in MongoDB. Each revision is bound
to one exact cached schema version and one validated payload hash.

The main lifecycle is:

1. cache schemas from the resolver,
2. issue a logical DPP,
3. append revisions over time,
4. validate every revision against its pinned schema,
5. hash every validated payload,
6. extract references from the payload,
7. require every hard reference to resolve before committing the revision.

Soft references are extracted but not resolved during commit.

## Operational guarantees

### Persistent logical identity

A logical DPP represents the stable identity of a product passport. In the paper this
corresponds to **Definition 1**.

The implementation stores the issuer-qualified identity as a single `dpp_id` string using
the convention:
```
issuerId-localId
```
For generated DPP IDs, the platform uses:
```
issuerId-UUID
```

### Append-only revisions

A revision represents one immutable state of a logical DPP. This corresponds to
**Definition 2**.

Each revision stores:

- DPP ID,
- version,
- schema version,
- payload,
- payload hash,
- creation timestamp.

The first revision must be version 1. Every later revision must be exactly one greater than
the current maximum version. This implements **Invariant I2**.

Version acquisition is atomic: MongoDB `findOneAndUpdate` with `$inc` on the `current_version`
counter in `logical_dpps` replaces the pessimistic row lock used by the Java platform.

### Revision uniqueness

The pair `(dpp_id, dpp_version)` uniquely identifies a revision. This implements
**Invariant I1**. Enforced by a unique compound index in MongoDB.

### Schema-pinned validation

Each revision references one exact schema version. The schema is not selected dynamically
after issuance. This implements the local platform part of **Invariant I3** and
**Invariant I5**.

Validation uses JSON Schema Draft 2020–12 via the `jsonschema` library.

### Payload integrity

Every revision stores a SHA-256 hash of the validated payload. This implements
**Invariant I4**.

The implementation:

1. serializes the validated payload,
2. canonicalizes it using JSON Canonicalization Scheme (JCS) via the `jcs` library,
3. computes a SHA-256 digest,
4. stores the digest as a lowercase hex string,
5. verifies the digest before persistence.

### Hard-reference resolvability

Hard references identify concrete revisions. They must resolve before the new revision is
committed. This implements **Invariant I7**.

Resolution order:

1. check whether the referenced revision is local,
2. check whether it is already cached in `referenced_dpp_revisions`,
3. ask the resolver for the current hosting platform,
4. fetch the revision from that platform,
5. cache the fetched revision locally.

### Soft references

Soft references identify logical DPPs without naming a concrete revision. They correspond to
**Definition 9**.

The implementation extracts soft references but does not resolve them during issue or revise.

## Main components

### `dpps/router.py`

Exposes the DPP HTTP API.

| Method | Path                                | Paper operation or concept                    | Purpose                                                                         |
|--------|-------------------------------------|-----------------------------------------------|---------------------------------------------------------------------------------|
| `GET`  | `/dpps`                             | Current local platform state                  | Lists locally hosted DPPs.                                                      |
| `GET`  | `/dpps/{dpp_id}`                    | Logical DPP and revision history              | Returns one DPP and all its revisions.                                          |
| `GET`  | `/dpps/{dpp_id}/{revision_version}` | **Definition 11: Resolution** target endpoint | Returns one exact revision. Used by other platforms after resolver indirection. |
| `POST` | `/dpps/issue`                       | **issue** operation                           | Creates a logical DPP and first revision.                                       |
| `POST` | `/dpps/{dpp_id}/revise`             | **revise** operation                          | Appends the next immutable revision.                                            |

### `dpps/service.py`

Contains the core implementation of the platform-side transition system.

Responsibilities:

- implements **issue**,
- implements **revise**,
- enforces **Invariant I1** through the unique compound index,
- enforces **Invariant I2** through atomic version acquisition,
- checks the local platform part of **Invariant I3** by requiring a cached exact schema,
- triggers **Invariant I5** validation,
- triggers **Invariant I4** hashing,
- triggers **Invariant I7** hard-reference resolution,
- converts documents to API DTOs.

### `dpps/utils.py`

Implements **Definition 4: Revision validity**.

- `validate_dpp_document`: JSON Schema Draft 2020-12 validation (Invariant I5).
- `hash_document`: SHA-256 over JCS-canonicalized JSON (Invariant I4).
- `verify_hash_integrity`: re-computes and compares hash for tamper detection.

### `dpps/reference_extractor.py`

Implements **Definition 12: Reference extraction**.

Extracts `$ref` objects from DPP payloads. A versioned reference is hard; an unversioned
reference is soft.

### `dpps/cache_service.py`

Caches external hard-reference targets fetched from other platforms.

Cached revisions support **Invariant I7** checks. MongoDB TTL index on `fetched_at` handles
periodic eviction (7-day TTL), replacing the Java platform's scheduled daily cleanup.

### `dpps/cycle_detection.py`

Deprecated.

This module contains a bounded BFS over hard dependencies and relates to **Definition 14**
(instance hard-dependency graph). It is retained only to document an earlier instance-level
approach. It is not called during normal issue/revise processing.

As in the Java platform, cycle prevention at the schema level (**Invariant I6**) is the resolver's
responsibility.

### `schemas/router.py`

Exposes and reads the local schema cache.

| Endpoint                                        | Paper operation or concept | Purpose                                                      |
|-------------------------------------------------|----------------------------|--------------------------------------------------------------|
| `GET /schemas/{subjectType}`                    | Schema cache lookup        | Returns the newest locally cached schema for a subject type. |
| `GET /schemas/{subjectType}/{major}/{minor}`    | Schema cache lookup        | Returns an exact locally cached schema version.              |
| `POST /schemas/{subjectType}/cacheSchema`       | **cacheSchema** operation  | Fetches resolver-published schemas into the local cache.     |

### `schemas/resolver_connector.py`

Implements communication with the resolver.

- `cache_schema`: fetches schemas from the resolver into the local cache,
- `resolve_dpp_revision`: asks the resolver where a hard-reference target is hosted, follows
  the 302 redirect, and fetches the concrete revision from the resolved platform.

## Data model overview

| Collection                 | Paper item               | Purpose                                                         |
|----------------------------|--------------------------|-----------------------------------------------------------------|
| `logical_dpps`             | **Definition 1**         | Stable identity of a DPP plus current version counter.          |
| `dpp_revisions`            | **Definition 2**         | Immutable revision of a DPP.                                    |
| `schemas`                  | **Definition 3**         | Locally cached schema artefacts.                                |
| `referenced_dpp_revisions` | **Invariant I7** support | Cache entries for external hard-reference targets.              |
| `subject_types`            | **Definition 3** support | Product/domain types governed by schemas.                       |
| `platform_config`          | Configuration            | Single-document platform configuration (name, URLs, issuer ID). |

## Revision lifecycle

### Issue

Implements the paper's **issue** operation.

Issuing a DPP:

1. validates the DPP ID belongs to this platform's issuer,
2. checks no logical DPP with the same ID already exists,
3. checks the subject type exists locally,
4. checks the exact schema version exists in the local schema cache, synchronizing from the resolver if needed,
5. validates the payload against the schema,
6. resolves all hard references,
7. computes the payload hash,
8. persists the logical DPP and revision 1 in a MongoDB transaction.

### Revise

Implements the paper's **revise** operation.

Revising a DPP:

1. checks the logical DPP exists,
2. checks the exact schema version exists in the local schema cache, synchronizing from the resolver if needed,
3. checks the schema subject type matches the DPP subject type,
4. validates the payload against the schema,
5. resolves all hard references,
6. computes the payload hash,
7. atomically acquires the next version number and persists the new revision in a MongoDB transaction.

Version acquisition and revision insertion are transactionally coupled. If revision insertion fails, the version counter is rolled back, preserving **Invariant I2**.

## Schema handling

Schemas are managed by the resolver and cached by the platform.

This platform implements the **cacheSchema** operation:

- fetch schemas from the resolver,
- store schemas locally,
- retrieve the newest cached schema for a subject type,
- retrieve an exact cached schema version,
- validate DPP payloads against cached schemas.

Manual schema-cache endpoint:
```
POST /schemas/{subjectType}/cacheSchema
```

Read endpoints:
```
GET /schemas/{subjectType}
GET /schemas/{subjectType}/{major}/{minor}
```

## Differences between the Java model and this implementation

### 1. Storage technology

The Java platform uses PostgreSQL with JPA. This platform uses MongoDB with Motor (async).
Both implement the same REST contract and the same formal invariants.

### 2. Atomic version increment

The Java platform uses a JPA `PESSIMISTIC_WRITE` row lock to prevent concurrent revise
requests from assigning the same version. This platform uses MongoDB's `findOneAndUpdate`
with `$inc` on the `current_version` counter in `logical_dpps`. Behavior is equivalent.

### 3. Hash storage format

Java stores the hash as `BYTEA` (binary). Python stores the hash as a lowercase hex string.
The hex string is `payload_hash` in API responses in both cases, so the API contract is
identical.

### 4. TTL eviction for external revision cache

Java schedules a daily cleanup task to evict stale cache entries. Python uses a MongoDB TTL
index on `fetched_at` with a 7-day TTL. Both prevent the cache from growing unbounded.

## API examples

### Issue a DPP
```bash
curl -X POST http://localhost:8082/dpps/issue \
  -H "Content-Type: application/json" \
  -d '{
    "dpp_id": "issuerA-product-001",
    "version": 1,
    "schema_version": {
      "subject_type": "battery",
      "major_version": 1,
      "minor_version": 0
    },
    "dpp_payload": {
      "serial_number": "BAT-001",
      "manufacturer": "Example Manufacturer"
    }
  }'
```

### Revise a DPP
```bash
curl -X POST http://localhost:8082/dpps/issuerA-product-001/revise \
  -H "Content-Type: application/json" \
  -d '{
    "version": 2,
    "schema_version": {
      "subject_type": "battery",
      "major_version": 1,
      "minor_version": 0
    },
    "dpp_payload": {
      "serial_number": "BAT-001",
      "manufacturer": "Example Manufacturer",
      "status": "updated"
    }
  }'
```

### Get DPP details
```bash
curl http://localhost:8082/dpps/issuerA-product-001
```

### Get exact revision
```bash
curl http://localhost:8082/dpps/issuerA-product-001/2
```

### Cache schemas for a subject type
```bash
curl -X POST http://localhost:8082/schemas/battery/cacheSchema
```

## Configuration

| Environment variable | Description                                                | Example                     |
|----------------------|------------------------------------------------------------|-----------------------------|
| `PLATFORM_NAME`      | Human-readable name of the platform                        | `Platform B`                |
| `BASE_URL`           | Public base URL of this platform                           | `http://localhost:8082`     |
| `ISSUER_ID`          | Issuer identifier used for DPP IDs issued by this platform | `issuerB`                   |
| `RESOLVER_BASE_URL`  | Base URL of the DPP resolver                               | `http://localhost:8080`     |
| `MONGODB_URI`        | MongoDB connection URI                                     | `mongodb://localhost:27017` |
| `MONGODB_DB_NAME`    | MongoDB database name                                      | `dpp_platform`              |
| `LOG_LEVEL`          | Logging level                                              | `INFO`                      |

## Running locally

```bash
export PLATFORM_NAME="Generic DPP Platform"
export BASE_URL="http://localhost:8082"
export ISSUER_ID="issuerB"
export RESOLVER_BASE_URL="http://localhost:8080"
export MONGODB_URI="mongodb://localhost:27017"
export MONGODB_DB_NAME="dpp_platform"

uvicorn generic_dpp_platform.main:app --host 0.0.0.0 --port 8082
```

## Running with Docker

```bash
docker run \
  -e PLATFORM_NAME="Platform B" \
  -e BASE_URL="http://localhost:8082" \
  -e ISSUER_ID="issuerB" \
  -e RESOLVER_BASE_URL="http://localhost:8080" \
  -e MONGODB_URI="mongodb://mongo:27017" \
  -e MONGODB_DB_NAME="dpp_platform" \
  generic-dpp-platform-python
```

## Prerequisites

- Python 3.14
- MongoDB
- a running resolver service
- resolver-published schemas for the subject types this platform should issue
- local schema cache populated before issuing or revising DPPs

## Development

### Install dependencies
```bash
uv sync
# or: pip install -e ".[dev]"
```

### Run tests
```bash
pytest tests/
```

Tests use Testcontainers to spin up a real MongoDB instance. Docker must be available.

### Common setup sequence

1. Start MongoDB.
2. Start the resolver.
3. Start this DPP platform with a unique `ISSUER_ID` and `BASE_URL`.
4. Register the issuer in the resolver.
5. Publish schemas through the resolver.
6. Cache schemas on this platform.
7. Issue DPPs.
8. Revise DPPs.
9. Resolve hard references through the resolver when issuing revisions that depend on
   external DPPs.
