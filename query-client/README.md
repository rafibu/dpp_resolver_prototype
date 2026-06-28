# Federated Predicate Query Client

This is a Python-based **federated predicate-query orchestration prototype**.
It is not a DPP platform or resolver and is not part of the formal federation
state. It does not evaluate DPP payloads or implement predicate logic. Each DPP
platform remains responsible for local predicate retrieval over the revisions it
hosts. The client:

1. validates a federated query request,
2. retrieves the registered platform mappings from the resolver,
3. sends a well-formed platform-local query to each registered platform,
4. records per-platform execution time, failures, and timeouts, and
5. merges the per-platform responses into one federation-level result.

It treats the resolver and DPP platforms as **external HTTP services** and never
modifies their state.

## Relation to the paper and current scope

The paper's derived-query realization distributes subject-type and payload
queries to registered platforms, keeps predicate evaluation local, and merges
the returned results. It also includes reverse traversal over references using
schema-level source scopes supplied by the resolver.

This module implements only the predicate-retrieval part of that orchestration:

| Paper query concern | This module |
|---|---|
| Platform-local predicate retrieval | Forwards `SELECT`, `COUNT`, and `SUM` requests and merges successful responses. |
| Federation routing | Discovers resolver registry entries and queries each distinct platform once. |
| Reverse traversal | Not implemented. The S4 workload uses `dpp-workload-generator`'s `PlatformClient` for the generic platforms' `/query/traverse` endpoint. |
| Schema-level source scope | Not derived or consumed because this module has no reverse-traversal API. |
| Source-revision traceability | Preserved only when platform responses include stable revision identity fields. Current generic-platform query responses return payload projections or source documents, so this client cannot add that identity itself. |

### Generic-platform compatibility

The generic Java and Python platforms expose `GET /query/predicate` and bind
flattened query parameters such as `resultMode` and `filters[0].path`. This
client now uses that contract by default, including repeated
`subjectTypes` parameters and repeated `filters[i].value` parameters for `IN`
filters. A non-GET method remains an explicit legacy override for deployments
that expose a JSON-body endpoint.

## Requirements

- Python 3.11+
- FastAPI, Pydantic v2, httpx, uvicorn (installed via `pyproject.toml`)

## Install

```bash
cd query-client
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"   # Windows
# source .venv/bin/activate && pip install -e ".[dev]"  # POSIX
```

## Configuration

Configuration is read from environment variables (see `.env.example`):

| Variable                  | Default                       | Purpose                                         |
| ------------------------- | ----------------------------- | ----------------------------------------------- |
| `RESOLVER_BASE_URL`       | `http://localhost:8080`       | Resolver base URL (`GET /admin/platforms`)      |
| `PLATFORM_QUERY_PATH`     | `/query/predicate`            | Path appended to each platform base URL         |
| `PLATFORM_QUERY_METHOD`   | `GET`                         | HTTP method for the platform-local query        |
| `DEFAULT_TIMEOUT_MS`      | `120000`                      | Federation timeout when a request omits one     |
| `HTTP_CONNECT_TIMEOUT_MS` | `5000`                        | Per-platform connect timeout                    |
| `HTTP_READ_TIMEOUT_MS`    | `120000`                      | Per-platform read timeout                       |
| `CORS_ALLOW_ORIGINS`      | `*`                           | Comma-separated CORS origins for the frontend   |

The resolver registry maps **issuers** to platforms; the client derives each
platform `base_url` from the registry's `resolution_url` (the origin, i.e.
`scheme://host:port`) and **deduplicates** so each platform is queried once.

## Run the HTTP service

```bash
.venv/Scripts/python -m uvicorn query_client.main:app --host 0.0.0.0 --port 8090
```

OpenAPI docs are then available at `http://localhost:8090/docs`.

### API

| Method & path                                          | Description                                         |
| ------------------------------------------------------ | --------------------------------------------------- |
| `POST /api/v1/federated-queries/predicate`             | Start a job; returns `job_id` immediately (202)     |
| `GET  /api/v1/federated-queries/{job_id}`              | Poll job status / per-platform progress             |
| `GET  /api/v1/federated-queries/{job_id}/result`       | Full result (partial with `RUNNING` while in flight)|
| `DELETE /api/v1/federated-queries/{job_id}`            | Cancel a running job (optional)                     |

#### Request body

```json
{
  "result_mode": "SELECT | COUNT | SUM",
  "execution_mode": "INDEXED | ON_DEMAND",
  "subject_types": ["battery"],
  "filters": [{ "path": "status", "operator": "EQ", "value": "active" }],
  "return_fields": ["status"],
  "aggregate_path": "material_composition.mass_kg",
  "timeout_ms": 120000
}
```

- `result_mode` is required.
- `execution_mode` defaults to `INDEXED`.
- `subject_types` is optional. Omitted, `null`, or `[]` means all DPP subject
  types. One value restricts the query to one type; several values restrict it
  to that set. Legacy input named `subject_type` is accepted, but `subject_types`
  takes precedence and new requests are serialized with `subject_types`.
- `filters` is optional; empty matches all current revisions in the selected
  subject-type scope. Filters are AND-combined by the platform (the client never
  adds OR semantics).
- `return_fields` is valid only for `SELECT`.
- `aggregate_path` is required for `SUM`, forbidden for `SELECT`/`COUNT`.
- Operators: `EQ, NEQ, EXISTS, NOT_EXISTS, IN, GT, GTE, LT, LTE`.
  - `EXISTS`/`NOT_EXISTS` must not carry a value.
  - `EQ`/`NEQ` require one scalar; `GT/GTE/LT/LTE` one numeric or date scalar;
    `IN` a non-empty array.
  - `BETWEEN`/`CONTAINS` are not supported.
- Predicate paths refer to projected facts, not arbitrary raw payload paths.

The forwarded **platform-local** JSON body contains only `result_mode`,
`execution_mode`, `subject_types`, `filters`, `return_fields`, `aggregate_path`
(snake_case JSON), omitting `subject_types` for all-type queries. See the
compatibility note above before using it with the generic platforms.

#### Copyable request examples

All subject types from one factory in a date range:

```json
{
  "result_mode": "SELECT",
  "execution_mode": "INDEXED",
  "filters": [
    { "path": "manufacturing.facilityId", "operator": "EQ", "value": "factory-a" },
    { "path": "manufacturing.date", "operator": "GTE", "value": "2024-01-01" },
    { "path": "manufacturing.date", "operator": "LTE", "value": "2024-12-31" }
  ],
  "return_fields": ["manufacturing.facilityId", "manufacturing.date"]
}
```

Several factories in a date range:

```json
{
  "result_mode": "COUNT",
  "filters": [
    { "path": "manufacturing.facilityId", "operator": "IN", "value": ["factory-a", "factory-b", "factory-c"] },
    { "path": "manufacturing.date", "operator": "GTE", "value": "2024-01-01" },
    { "path": "manufacturing.date", "operator": "LTE", "value": "2024-12-31" }
  ]
}
```

Factories supplying a store, DPPs containing lead, and total lead mass use the
same projected-fact model:

```json
{ "result_mode": "SELECT", "filters": [
  { "path": "logistics.destinationStoreId", "operator": "EQ", "value": "store-17" },
  { "path": "logistics.deliveryDate", "operator": "GTE", "value": "2024-01-01" },
  { "path": "logistics.deliveryDate", "operator": "LTE", "value": "2024-12-31" }
] }
```

```json
{ "result_mode": "SELECT", "subject_types": ["pv_module", "battery_pack"], "filters": [
  { "path": "materialComposition.materialId", "operator": "EQ", "value": "Pb" }
] }
```

```json
{ "result_mode": "SUM", "subject_types": ["pv_module", "battery_pack"], "filters": [
  { "path": "materialComposition.materialId", "operator": "EQ", "value": "Pb" }
], "aggregate_path": "materialComposition.mass" }
```

## CLI (reproducible runs)

```bash
.venv/Scripts/python -m query_client.run_query --request examples/query.json
```

Loads the JSON request, runs the federated query to completion, and prints the
full result as JSON.

## Use from the workload generator (importable API)

```python
from query_client import FederatedPredicateQueryRequest, run_federated_query

request = FederatedPredicateQueryRequest.model_validate({
    "result_mode": "COUNT",
    "subject_types": ["battery"],
    "filters": [{"path": "status", "operator": "EQ", "value": "active"}],
})
result = await run_federated_query(request)
print(result.status, result.combined_result.count)
```

For background execution + polling (as the frontend does), use
`FederatedQueryService.start(request)` and read jobs from `service.store`.

## Merging semantics

- **SELECT** — concatenate `matches`, enrich each match with its `platform_id`,
  deduplicate on `platform_id + logical DPP id + revision` when those keys are
  present (otherwise emit a warning and keep all).
- **COUNT** — sum per-platform `count`.
- **SUM** — sum per-platform `aggregate` using `Decimal`. A missing aggregate is
  treated as zero only for an empty result set; otherwise that platform result is
  demoted to `FAILED`.

`complete` is `true` only when every contacted platform succeeded. If some
platforms fail or time out the job is `PARTIAL` (or `FAILED`/`TIMEOUT` if none
succeed, by dominant reason).

## Tests

```bash
.venv/Scripts/python -m pytest
```

Covers request validation, the three merge modes, resolver normalization /
deduplication, and full orchestration (success, partial failure, timeout, and
resolver-down) via a mock transport.
