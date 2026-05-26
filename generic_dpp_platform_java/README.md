# Generic DPP Platform Java

This project is a Spring Boot implementation of the **DPP platform** role in a federated Digital Product Passport (DPP)
ecosystem.

It implements the platform-side parts of the paper's model:

— logical DPP identity and revision history,
— immutable DPP revisions,
— schema-pinned validation,
— payload hashing,
— hard and soft DPP references,
— hard-reference resolution through a resolver,
— local schema caching,
— local caching of externally referenced revisions.

## Paper-to-implementation map

This section explains where the main definitions, invariants, and operations from the paper are implemented in this Java
platform.

### Definitions implemented by this module

| Paper item                              | Meaning in the paper                                                                              | Java implementation                                                                                     |
|-----------------------------------------|---------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------|
| **Definition 1: Logical DPP**           | A stable DPP identity independent of individual revisions.                                        | `LogicalDpp`                                                                                            |
| **Definition 2: Revision**              | An immutable versioned state of a logical DPP, including schema, payload, and hash.               | `DppRevision`, `DppRevisionId`                                                                          |
| **Definition 3: Schema artifact**       | A schema with subject type, validator, and major/minor version.                                   | `DppSchema`, `DppSchemaId`                                                                              |
| **Definition 4: Revision validity**     | A revision is valid if its hash matches its payload and its payload validates against its schema. | `DppUtil.validateDppDocument(...)`, `DppUtil.hashDocument(...)`, `DppRevision.verifyHashIntegrity(...)` |
| **Definition 5: DPP platform state**    | The local revision set and local schema cache of one platform.                                    | Local database tables for `LogicalDpp`, `DppRevision`, `DppSchema`, and `ReferencedDppRevision`         |
| **Definition 8: Federated reference**   | A reference to another DPP independent of its hosting platform.                                   | `DppReference`                                                                                          |
| **Definition 9: Reference mode**        | Hard references target exact revisions; soft references target logical DPPs.                      | `DppReference.DependencyType.HARD`, `DppReference.DependencyType.SOFT`                                  |
| **Definition 11: Resolution**           | Resolving a reference by consulting the resolver and then the hosting platform.                   | `ResolverConnector.resolveDppRevisionUrl(...)`, `ResolverConnector.resolveDppRevision(...)`             |
| **Definition 12: Reference extraction** | Extracting DPP references from a payload.                                                         | `DppReferenceExtractor`                                                                                 |

### Invariants implemented by this module

| Paper item                                         | Meaning                                                                  | Implementation                                                                                                                                        |
|----------------------------------------------------|--------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Invariant I1: Revision uniqueness**              | A logical DPP cannot have two different revisions with the same version. | `DppRevisionId` is a composite key of DPP ID and version.                                                                                             |
| **Invariant I2: Version monotonicity and density** | Revision versions form a gap-free sequence starting at `1`.              | `DppRevisionService.checkAndGetNextVersionNumber(...)`                                                                                                |
| **Invariant I3: Schema explicitness**              | Every revision explicitly references a schema known to the resolver.     | Implemented locally by requiring the exact schema version to exist in the local schema cache before issue/revise. The resolver remains the authority. |
| **Invariant I4: Payload integrity**                | Stored hash equals the hash of the payload.                              | `DppUtil.hashDocument(...)` and `DppRevision.verifyHashIntegrity(...)`                                                                                |
| **Invariant I5: Schema conformance**               | Payload validates against the pinned schema.                             | `DppUtil.validateDppDocument(...)`                                                                                                                    |
| **Invariant I7: Hard resolvability**               | Every hard reference resolves to an existing concrete revision.          | `DppRevisionService.resolveAndCacheHardReference(...)`                                                                                                |

### Operations implemented by this module

| Paper operation | Meaning                                                                      | Java implementation                                                                                |
|-----------------|------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------|
| **issue**       | Create a new logical DPP and its first revision.                             | `DppController` endpoint `POST /dpps/issue`, `DppRevisionService.issueDpp(...)`                    |
| **revise**      | Append a new revision to an existing logical DPP.                            | `DppController` endpoint `POST /dpps/{dpp_id}/revise`, `DppRevisionService.reviseExistingDpp(...)` |
| **cacheSchema** | Fetch schemas from the resolver into the local platform cache.               | `DppSchemaController.cacheSchemaManually(...)`, `ResolverConnector.cacheSchema(...)`               |
| **resolve**     | Resolve a hard reference through the resolver and fetch the target revision. | `ResolverConnector.resolveDppRevisionUrl(...)`, `ResolverConnector.resolveDppRevision(...)`        |

## Implementation overview

The platform stores logical DPPs and append-only revisions. Each revision is bound to one exact cached schema version
and one validated payload hash.

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

A logical DPP represents the stable identity of a product passport. In the paper this corresponds to **Definition 1**.

In this implementation, the logical identity is stored in `LogicalDpp`.

The formal identity is issuer-qualified. The implementation encodes it as a single string:
```
text
issuerId-localId
```
For generated DPP IDs, the platform uses:
```
text
issuerId-UUID
```
This means each platform can generate IDs independently as long as its configured `ISSUER_ID` is unique in the resolver.

### Append-only revisions

A revision represents one immutable state of a logical DPP. This corresponds to **Definition 2**.

In this implementation, revisions are stored as `DppRevision`.

Each revision has:

- DPP ID,
- version,
- schema version,
- payload,
- payload hash,
- creation timestamp.

The first revision must be version `1`. Every later revision must be exactly one greater than the current maximum version. This implements **Invariant I2**.

### Revision uniqueness

The pair `(dppId, version)` uniquely identifies a revision. This implements **Invariant I1**.

In code, this is represented by `DppRevisionId`.

### Schema-pinned validation

Each revision references one exact schema version. The schema is not selected dynamically after issuance. This implements the local platform part of **Invariant I3** and **Invariant I5**.

Validation is performed by:
```
text
DppUtil.validateDppDocument(...)
```
The implementation uses JSON Schema 2020–12.

### Payload integrity

Every revision stores a SHA-256 hash of the validated payload. This implements **Invariant I4**.

The implementation:

1. serializes the validated payload,
2. canonicalizes it using JSON Canonicalization Scheme,
3. computes a SHA-256 digest,
4. stores the digest,
5. verifies the digest before persistence.

Hashing is performed by:
```
text
DppUtil.hashDocument(...)
```
### Hard-reference resolvability

Hard references identify concrete revisions. They must resolve before the new revision is committed. This implements **Invariant I7**.

The implementation checks hard references in:
```
text
DppRevisionService.resolveAndCacheHardReference(...)
```
Resolution order:

1. check whether the referenced revision is local,
2. check whether it is already cached as `ReferencedDppRevision`,
3. ask the resolver for the current hosting platform,
4. fetch the revision from that platform,
5. cache the fetched revision locally.

### Soft references

Soft references identify logical DPPs without naming a concrete revision. They correspond to **Definition 9**.

The implementation extracts soft references but does not resolve them during issue or revise. This is intentional: soft references are informational and do not contribute to the hard-dependency closure.

## Main components

### `DppController`

Exposes the DPP HTTP API.

| Method | Path                                | Paper operation or concept                    | Purpose                                                                         |
|--------|-------------------------------------|-----------------------------------------------|---------------------------------------------------------------------------------|
| `GET`  | `/dpps`                             | Current local platform state                  | Lists locally hosted DPPs.                                                      |
| `GET`  | `/dpps/{dpp_id}`                    | Logical DPP and revision history              | Returns one DPP and all its revisions.                                          |
| `GET`  | `/dpps/{dpp_id}/{revision_version}` | **Definition 11: Resolution** target endpoint | Returns one exact revision. Used by other platforms after resolver indirection. |
| `POST` | `/dpps/issue`                       | **issue** operation                           | Creates a logical DPP and first revision.                                       |
| `POST` | `/dpps/{dpp_id}/revise`             | **revise** operation                          | Appends the next immutable revision.                                            |

### `DppRevisionService`

Contains the core implementation of the platform-side transition system.

Responsibilities:

- implements **issue**,
- implements **revise**,
- enforces **Invariant I1** through revision IDs,
- enforces **Invariant I2** through consecutive version assignment,
- checks the local platform part of **Invariant I3** by requiring a cached exact schema,
- triggers **Invariant I5** validation,
- triggers **Invariant I4** hashing,
- triggers **Invariant I7** hard-reference resolution,
- converts entities to API DTOs.

### `LogicalDpp`

Implements **Definition 1: Logical DPP**.

It stores:

- the issuer-qualified `dppId`,
- the subject type,
- the associated revisions.

The implementation encodes the formal issuer-qualified identity into one string using:
```
text
issuerId-localId
```
### `DppRevision`

Implements **Definition 2: Revision**.

It stores:

- composite revision identity,
- logical DPP reference,
- pinned schema reference,
- JSON payload,
- hash of the payload,
- creation timestamp.

The timestamp is implementation metadata only. Revision ordering is determined by the integer version, not by time.

### `DppSchema`

Implements the platform-local cache representation of **Definition 3: Schema artefact**.

This platform does not publish schemas. It only stores resolver-published schemas locally so that payloads can be validated during issue and revise.

### `DppSchemaController` and `DppSchemaService`

Expose and read the local schema cache.

| Endpoint                                     | Paper operation or concept | Purpose                                                      |
|----------------------------------------------|----------------------------|--------------------------------------------------------------|
| `GET /schemas/{subjectType}`                 | Schema cache lookup        | Returns the newest locally cached schema for a subject type. |
| `GET /schemas/{subjectType}/{major}/{minor}` | Schema cache lookup        | Returns an exact locally cached schema version.              |
| `POST /schemas/{subjectType}/cacheSchema`    | **cacheSchema** operation  | Fetches resolver-published schemas into the local cache.     |

### `ResolverConnector`

Implements communication with the resolver.

It supports:

- **cacheSchema**: fetches schemas from the resolver,
- **resolve**: asks the resolver where a hard-reference target is hosted,
- fetches the concrete target revision from the resolved platform URL.

This corresponds to the platform-side use of **Definition 11: Resolution**.

### `DppReferenceExtractor`

Implements **Definition 12: Reference extraction**, with a prototype-specific convention.

The paper defines reference extraction abstractly. The implementation uses `$ref` objects in JSON payloads.

Supported formats:
```
text
subject_type/issuer-local_id
subject_type/issuer-local_id/version
```
A versioned reference is hard. An unversioned reference is soft.

Alternative hard-reference encoding:
```
json
{
"$ref": "battery/issuerA-123",
"version": 2
}
```
### `DppReference`

Implements **Definition 8: Federated reference** and **Definition 9: Reference mode**.

A reference contains:

- subject type,
- DPP ID,
- optional version,
- dependency type,
- original reference string,
- JSON path.

### `ReferencedDppRevision`

Caches external hard-reference targets fetched from other platforms.

These cached revisions support **Invariant I7** checks but are not part of this platform's own issued revision history.

### `DppCycleDetectionService`

Deprecated.

This was an earlier bounded instance-level implementation related to **Definition 14: Instance hard-dependency graph**. It is not used in the normal issue/revise flow because cycle prevention is now treated as resolver-side schema governance through **Invariant I6**.

## Data model overview

| Entity                  | Paper item               | Purpose                                                           |
|-------------------------|--------------------------|-------------------------------------------------------------------|
| `LogicalDpp`            | **Definition 1**         | Stable identity of a DPP.                                         |
| `DppRevision`           | **Definition 2**         | Immutable revision of a DPP.                                      |
| `DppRevisionId`         | **Invariant I1**         | Composite key for DPP ID and revision version.                    |
| `DppSchema`             | **Definition 3**         | Locally cached schema artefact.                                   |
| `DppSchemaId`           | **Definition 3**         | Composite key for subject type, major version, and minor version. |
| `DppReference`          | **Definitions 8 and 9**  | Hard or soft DPP reference extracted from a payload.              |
| `ReferencedDppRevision` | **Invariant I7** support | Cache entry for external hard-reference targets.                  |
| `SubjectType`           | **Definition 3** support | Product/domain type governed by schemas.                          |

## Revision lifecycle

### Issue

Implements the paper's **issue** operation.

Issuing a DPP creates:

1. a new `LogicalDpp`,
2. revision `1` for that DPP.

The platform checks:

1. the DPP ID belongs to this platform's issuer,
2. no logical DPP with the same ID already exists,
3. the subject type exists locally,
4. the exact schema version exists in the local schema cache,
5. the payload validates against the schema,
6. all hard references resolve,
7. the payload hash is computed and stored.

Related paper items:

- **Definition 1: Logical DPP**
- **Definition 2: Revision**
- **Definition 4: Revision validity**
- **Invariant I1: Revision uniqueness**
- **Invariant I2: Version monotonicity and density**
- **Invariant I3: Schema explicitness**
- **Invariant I4: Payload integrity**
- **Invariant I5: Schema conformance**
- **Invariant I7: Hard resolvability**

If no DPP ID is supplied, the platform generates one:
```
text
issuerId-UUID
```
### Revise

Implements the paper's **revise** operation.

Revising a DPP appends a new immutable revision.

The platform checks:

1. the logical DPP exists,
2. the next version is exactly current maximum version + 1,
3. the exact schema version exists in the local schema cache,
4. the schema subject type matches the DPP subject type,
5. the payload validates against the schema,
6. all hard references resolve,
7. the payload hash is computed and stored.

Related paper items:

- **Definition 2: Revision**
- **Invariant I1: Revision uniqueness**
- **Invariant I2: Version monotonicity and density**
- **Invariant I3: Schema explicitness**
- **Invariant I4: Payload integrity**
- **Invariant I5: Schema conformance**
- **Invariant I7: Hard resolvability**

The revise path locks the logical DPP before computing the next version. This prevents concurrent revise requests from assigning the same version.

## Schema handling

Schemas are managed by the resolver and cached by the platform.

This platform implements the **cacheSchema** operation. It can:

- fetch schemas from the resolver,
- store schemas locally,
- retrieve the newest cached schema for a subject type,
- retrieve an exact cached schema version,
- validate DPP payloads against cached schemas.

This platform does not implement:

- **publishSchema**,
- **Definition 15: Backward compatibility** checks,
- **Definition 16: Schema update** governance,
- **Invariant I6: Schema-graph acyclicity** enforcement.

Those are resolver-side responsibilities.

Manual schema-cache endpoint:
```
text
POST /schemas/{subjectType}/cacheSchema
```
Read endpoints:
```
text
GET /schemas/{subjectType}
GET /schemas/{subjectType}/{major}/{minor}
```
## Reference handling

DPP payloads may contain references to other DPPs.

This corresponds to:

- **Definition 8: Federated reference**
- **Definition 9: Reference mode**
- **Definition 11: Resolution**
- **Definition 12: Reference extraction**
- **Invariant I7: Hard resolvability**

Example soft reference:
```
json
{
"$ref": "battery/issuerB-456"
}
```
Example hard reference:
```
json
{
"$ref": "battery/issuerB-456/3"
}
```
Alternative hard-reference encoding:
```
json
{
"$ref": "battery/issuerB-456",
"version": 3
}
```
Reference modes:

| Format                                 | Mode | Meaning                                                      |
|----------------------------------------|------|--------------------------------------------------------------|
| `subject_type/issuer-local_id`         | Soft | Refers to the logical DPP. Not resolved during issuance.     |
| `subject_type/issuer-local_id/version` | Hard | Refers to one concrete revision. Must resolve before commit. |
| `$ref` plus sibling `version`          | Hard | Equivalent to including the version in the reference path.   |

Hard-reference processing:

1. The platform extracts references from the validated payload.
2. Hard references are identified by the presence of a version.
3. Local hard references are checked directly in the local revision repository.
4. External hard references are checked in the local referenced-revision cache.
5. If not cached, the platform asks the resolver for the current host platform.
6. The platform fetches the exact revision from the resolved platform URL.
7. The fetched revision is cached locally.
8. If any hard reference cannot be resolved, the new revision is rejected.

Soft-reference processing:

1. Soft references are extracted.
2. They are not resolved during issue or revise.
3. They do not affect revision validity.
4. They may be resolved later by clients if needed.

## Integrity and hashing

Payload integrity implements **Invariant I4**.

The implementation:

1. converts the validated payload to JSON,
2. canonicalizes it using JSON Canonicalization Scheme,
3. computes a SHA-256 digest,
4. stores the digest as `hashedDocument`,
5. exposes the hash as lowercase hexadecimal in DTOs.

This ensures that semantically identical JSON documents with different key order or whitespace produce the same hash.

## Differences between the paper model and this implementation

This implementation intentionally differs from the abstract model in several places.

### 1. Logical DPP identity encoding

In the paper, **Definition 1: Logical DPP** separates issuer, subject type, and local identifier.

This implementation stores a single `dppId` string and enforces the convention:
```
text
issuerId-localId
```
The subject type is stored separately through `LogicalDpp.subjectType`.

### 2. Schema authority is external

The paper's resolver state is described by **Definition 6: Resolver state**.

This platform only stores a local schema cache. It trusts the resolver to expose valid schemas and to enforce resolver-side rules.

### 3. Schema publication is not implemented here

The paper's **publishSchema** operation is resolver-side.

This module only implements **cacheSchema** and schema lookup.

### 4. Backward compatibility checking is not implemented here

The paper defines **Definition 15: Backward compatibility** and **Definition 16: Schema update**.

These checks belong to the resolver. This platform validates payloads against exact cached schema versions but does not decide whether one schema version is backward-compatible with another.

### 5. Schema-dependency cycle prevention is not implemented here

The paper's **Invariant I6: Schema-graph acyclicity** is resolver-side.

The platform does not perform schema-graph cycle checks. The deprecated `DppCycleDetectionService` shows an earlier instance-level experiment related to **Definition 14**, but it is not used in the normal issue/revise flow.

### 6. Reference extraction uses a `$ref` convention

The paper's **Definition 12: Reference extraction** is schema-parameterized.

This implementation uses a convention-based approach: any JSON object containing a textual `$ref` field is treated as a DPP reference.

### 7. Soft references are not resolved during commit

The paper allows soft references to remain unresolved.

The implementation follows this behavior by extracting soft references but not resolving them during issue or revise.

### 8. Timestamps are implementation metadata

The paper's **Definition 2: Revision** does not use timestamps to define revision order.

This implementation stores `createdAt` for auditing and logging. Revision order is still defined by the integer version.

### 9. External referenced revisions are cached separately

The paper's federated state is described by **Definition 7: Federated state**.

This implementation stores fetched external revisions in `ReferencedDppRevision`, separate from locally issued `DppRevision` records. The cache improves performance and supports hard-reference validation, but cached external revisions are not part of this platform's own logical DPP histories.

### 10. Migration and registration are resolver-side

The paper's **migrate** and **registerIssuer** operations are resolver-side.

This DPP platform does not implement them. It remains compatible with resolver-based migration because references do not encode platform URLs.

## API examples

### Issue a DPP
```
bash
curl -X POST http://localhost:8081/dpps/issue \
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
"serialNumber": "BAT-001",
"manufacturer": "Example Manufacturer"
}
}'
```
### Revise a DPP
```
bash
curl -X POST http://localhost:8081/dpps/issuerA-product-001/revise \
-H "Content-Type: application/json" \
-d '{
"version": 2,
"schema_version": {
"subject_type": "battery",
"major_version": 1,
"minor_version": 0
},
"dpp_payload": {
"serialNumber": "BAT-001",
"manufacturer": "Example Manufacturer",
"status": "updated"
}
}'
```
### Get DPP details
```
bash
curl http://localhost:8081/dpps/issuerA-product-001
```
### Get exact revision
```
bash
curl http://localhost:8081/dpps/issuerA-product-001/2
```
### Cache schemas for a subject type
```
bash
curl -X POST http://localhost:8081/schemas/battery/cacheSchema
```
## Configuration

The platform is configured via environment variables.

| Environment variable | Description                                                | Example                 |
|----------------------|------------------------------------------------------------|-------------------------|
| `PLATFORM_NAME`      | Human-readable name of the platform                        | `Platform A`            |
| `BASE_URL`           | Public base URL of this platform                           | `http://localhost:8081` |
| `ISSUER_ID`          | Issuer identifier used for DPP IDs issued by this platform | `issuerA`               |
| `RESOLVER_BASE_URL`  | Base URL of the DPP resolver                               | `http://localhost:8080` |

### Database configuration

| Environment variable         | Description               | Default                                             |
|------------------------------|---------------------------|-----------------------------------------------------|
| `SPRING_DATASOURCE_URL`      | JDBC URL for the database | `jdbc:postgresql://localhost:5432/dpp_generic_java` |
| `SPRING_DATASOURCE_USERNAME` | Database username         | `postgres`                                          |
| `SPRING_DATASOURCE_PASSWORD` | Database password         | `postgres`                                          |

## Running locally

Set the required environment variables and start the application:
```
bash
export PLATFORM_NAME="Generic DPP Platform"
export BASE_URL="http://localhost:8081"
export ISSUER_ID="issuerA"
export RESOLVER_BASE_URL="http://localhost:8080"
export SPRING_DATASOURCE_URL="jdbc:postgresql://localhost:5432/dpp_generic_java"
export SPRING_DATASOURCE_USERNAME="postgres"
export SPRING_DATASOURCE_PASSWORD="postgres"

./mvnw spring-boot:run
```
## Running with Docker
```
bash
docker run \
-e PLATFORM_NAME="Platform A" \
-e BASE_URL="http://localhost:8081" \
-e ISSUER_ID="issuerA" \
-e RESOLVER_BASE_URL="http://localhost:8080" \
-e SPRING_DATASOURCE_URL="jdbc:postgresql://db:5432/dpp_generic_java" \
-e SPRING_DATASOURCE_USERNAME="postgres" \
-e SPRING_DATASOURCE_PASSWORD="password" \
generic-dpp-platform-java
```
## Prerequisites

- Java 25 or newer
- PostgreSQL
- a running resolver service
- resolver-published schemas for the subject types this platform should issue
- local schema cache populated before issuing or revising DPPs

## Development notes

### Build
```
bash
./mvnw clean package
```
### Run tests
```
bash
./mvnw test
```
### Common setup sequence

1. Start PostgreSQL.
2. Start the resolver.
3. Start this DPP platform with a unique `ISSUER_ID` and `BASE_URL`.
4. Register the issuer in the resolver.
5. Publish schemas through the resolver.
6. Cache schemas on this platform.
7. Issue DPPs.
8. Revise DPPs.
9. Resolve hard references through the resolver when issuing revisions that depend on external DPPs.