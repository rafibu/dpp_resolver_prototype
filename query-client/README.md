# query-client

A self-contained, Python-based **federated predicate query client** for the DPP
prototype.

The query client is an **orchestration component only**. It does not evaluate DPP
payloads and does not implement predicate logic. Each DPP platform remains
responsible for evaluating a predicate query over the revisions it hosts. The
query client:

1. validates a federated query request,
2. retrieves the registered platform mappings from the resolver,
3. sends a well-formed platform-local query to each registered platform,
4. records per-platform execution time, failures, and timeouts, and
5. merges the per-platform responses into one federation-level result.

It treats the resolver and the DPP platforms as **external services** accessed
through their HTTP APIs. It never modifies resolver or platform state.

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
| `PLATFORM_QUERY_PATH`     | `/api/v1/query/predicate`     | Path appended to each platform base URL         |
| `PLATFORM_QUERY_METHOD`   | `POST`                        | HTTP method for the platform-local query        |
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
  "subject_type": "battery",
  "filters": [{ "path": "status", "operator": "EQ", "value": "active" }],
  "return_fields": ["status"],
  "aggregate_path": "material_composition.mass_kg",
  "timeout_ms": 120000
}
```

- `result_mode` and `subject_type` are required.
- `execution_mode` defaults to `INDEXED`.
- `filters` is optional; empty matches all revisions of the subject type. Filters
  are AND-combined by the platform (the client never adds OR semantics).
- `return_fields` is valid only for `SELECT`.
- `aggregate_path` is required for `SUM`, forbidden for `SELECT`/`COUNT`.
- Operators: `EQ, NEQ, EXISTS, NOT_EXISTS, IN, GT, GTE, LT, LTE`.
  - `EXISTS`/`NOT_EXISTS` must not carry a value.
  - `EQ`/`NEQ` require one scalar; `GT/GTE/LT/LTE` one numeric scalar; `IN` a
    non-empty array.
  - `BETWEEN`/`CONTAINS` are not supported.

The forwarded **platform-local** body contains only `result_mode`,
`execution_mode`, `subject_type`, `filters`, `return_fields`, `aggregate_path`
(snake_case JSON).

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
    "subject_type": "battery",
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
