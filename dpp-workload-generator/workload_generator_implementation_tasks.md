# Workload Generator Implementation Tasks

Sequential task list for implementing the Workload Generator. Tasks are ordered so each builds on the previous, with verification checkpoints at natural integration points.

## Prerequisites

Before starting these tasks, the following must be in place:

- Factory implementation complete and dockerized. `GET /federation` returns Resolver URL and platform URLs
- Resolver complete (R-1 through R-7), schema publication and resolution work end-to-end
- Both DPP-Platforms complete (P-1 through P-9) and exposing the agreed REST contract
- A clean federation can be brought up via `docker compose up factory` and produces a known PV/battery/inverter scenario via factory's seed-schemas endpoint

If any of these are missing, complete them before starting on the Workload Generator.

## Scope reminder

The Workload Generator is a CLI tool, not a long-running service. It exists for two distinct purposes:

1. **Setup**: build specific federation states (depth chains, fan-out structures, the PV scenario) for measurements and scenarios
2. **Measurement**: drive operations against the federation while recording timing and storage data to CSV

This is a research instrument, not a load tester. Throughput and concurrency are not goals. Determinism, reproducibility, and clean output are.

---

## Task 1: Project scaffolding

Create the Workload Generator project structure.

**Subtasks:**

- Create directory `workload-generator/` at the repository root
- Initialize a Python 3.14 project with `pyproject.toml` and `uv.lock`
- Add dependencies: `httpx`, `pydantic>=2`, `typer` (for CLI), `structlog`, `pyyaml`, `rich` (for nicer CLI output), `jcs`
- Add dev dependencies: `pytest`, `pytest-asyncio`, `pytest-httpx`
- Create `src/workload/` package directory with `__init__.py`
- Create `tests/` directory
- Create entry point in `pyproject.toml`: `workload = "workload.cli:app"`
- Create `.gitignore` excluding `.venv`, `__pycache__`, `output/`, `*.csv`

**Verification:**

- `uv pip install -e .` succeeds
- `workload --help` runs and shows the Typer help screen with no commands yet

---

## Task 2: Federation discovery client

Create a client that talks to the Factory to discover platform URLs.

**Subtasks:**

- Create `src/workload/federation.py`
- Define Pydantic models matching Factory's `GET /federation` response: `FederationOverview`, `ResolverInfo`, `PlatformInfo`
- Implement `FederationClient` class wrapping `httpx.AsyncClient`
- Methods:
  - `async def discover(factory_url: str) -> FederationOverview`
  - `async def find_platform_for_subject_type(subject_type: str) -> PlatformInfo`
  - `async def all_platforms() -> list[PlatformInfo]`
  - `async def resolver_url() -> str`
- Cache the federation overview for the duration of a CLI invocation (1 fetch per run)
- Add structured logging for every Factory call

**Verification:**

- Unit tests with `pytest-httpx` mocking Factory responses
- Manual test against a running Factory: `python -c "import asyncio; from workload.federation import FederationClient; print(asyncio.run(FederationClient().discover('http://localhost:8000')))"` returns the running federation

---

## Task 3: Platform and Resolver clients

Wrap the platform and Resolver REST APIs.

**Subtasks:**

- Create `src/workload/clients.py`
- Implement `PlatformClient` class:
  - `async def issue_dpp(spec: IssueDppSpec) -> DppResponse`
  - `async def revise_dpp(dpp_id: str, spec: ReviseDppSpec) -> DppResponse`
  - `async def get_revision(dpp_id: str, version: int | None = None) -> DppResponse`
  - `async def get_schema(subject_type: str, major: int, minor: int) -> dict`
- Implement `ResolverClient` class:
  - `async def publish_schema(subject_type: str, major: int, minor: int, document: dict) -> None`
  - `async def get_schema(subject_type: str, major: int, minor: int) -> dict`
  - `async def list_platforms() -> list[dict]`
  - `async def resolve(subject_type: str, dpp_id: str, version: int | None = None) -> str`  (returns the resolved URL after following redirects)
- All methods raise typed exceptions for 4xx/5xx responses (e.g. `DppNotFoundError`, `SchemaValidationError`, `CycleDetectedError`)
- All methods record latency for the measurement layer (Task 8) to capture
- Include retry logic only for transient connection errors (not for 4xx)

**Verification:**

- Unit tests with `pytest-httpx` for each method, including error paths
- Integration test against a running federation: issue a DPP, retrieve it, verify hash matches

---

## Task 4: Schema generation

Generate JSON Schemas for synthetic DPP types used in workloads.

**Subtasks:**

- Create `src/workload/schemas/` directory
- Implement `generate_schema(subject_type: str, with_dependencies: bool, dependency_count: int = 0) -> dict`
- Generate a minimal but realistic JSON Schema 2020-12 document with:
  - Standard fields: `manufacturer`, `model`, `recycled_content` (number 0-100), `serial_number`
  - Optional `dependencies` field as an array of reference objects when `with_dependencies=True`
  - Each reference object shape: `{"$ref": "<identity>", "version": <int>}` (presence of version makes it hard)
- Provide pre-defined schemas for the running scenario: `pv_module`, `battery`, `inverter`, `junction_box`
- Implement `seed_resolver_schemas(resolver: ResolverClient, subject_types: list[str]) -> None`

**Verification:**

- Unit tests verifying generated schemas are valid JSON Schema 2020-12 documents
- Integration test: seed schemas via Resolver, then retrieve them and verify content matches

---

## Task 5: Payload generation

Generate valid and invalid DPP payloads for given schemas.

**Subtasks:**

- Create `src/workload/payloads.py`
- Implement `generate_valid_payload(schema: dict, dependencies: list[ReferenceSpec] = []) -> dict`
- Implement `generate_invalid_payload(schema: dict, violation_kind: str) -> dict`
  - Violation kinds: `missing_required_field`, `wrong_type`, `out_of_range`
- Implement `generate_dpp_id(issuer: str, sequence: int) -> str` returning IDs like `issuerA-pv-001`
- Use deterministic but varied data: same seed produces same payload, different seeds produce different ones
- Take a `seed: int | None = None` parameter on each generator for reproducibility
- Do not depend on faker or similar libraries; use `random.Random(seed)` directly to keep dependencies minimal

**Verification:**

- Unit tests: same seed produces identical payloads across calls
- Unit tests: each `violation_kind` produces a payload that fails JSON Schema validation
- Unit tests: valid payloads pass validation against their schema

---

## Task 6: Story W-1, depth chain generator

Generate a chain of DPPs with controllable hard-dependency depth.

**Subtasks:**

- Create `src/workload/scenarios/depth.py`
- Implement `async def generate_depth_chain(federation: FederationOverview, depth: int, seed: int | None = None) -> DepthChainResult`
- `DepthChainResult` contains the root DPP identity, the full chain of DPPs created, and the platform mapping
- Algorithm:
  1. Seed schemas for `link_<i>` subject types (i = 1..depth) via Resolver
  2. Issue DPPs leaf-first (link_depth has no dependencies, link_1 depends on link_2 which depends on link_3, etc.)
  3. Distribute DPPs across at least 3 platforms in round-robin fashion
  4. Each link's hard dependency points to the next link's specific revision
- Validate depth is in range 1..10
- Log progress at INFO level: "Created link 3/5 on platform-b"

**Verification:**

- Integration test: generate depth chain of 5, verify chain via resolver traversal
- Verify all DPPs exist on their assigned platforms
- Verify hard-dependency closure depth from the root equals the requested depth

---

## Task 7: Story W-2, fan-out generator

Generate a parent DPP with N hard dependencies.

**Subtasks:**

- Create `src/workload/scenarios/fanout.py`
- Implement `async def generate_fanout(federation, fanout: int, root_platform: str | None = None, seed: int | None = None) -> FanoutResult`
- Algorithm:
  1. Seed schemas for `parent` and `child` subject types
  2. Issue `fanout` distinct child DPPs distributed across platforms (excluding the root platform if it would create a same-platform-only test)
  3. Issue parent DPP on root_platform with hard dependencies on all children
- Validate fanout is in range 1..20
- Children are real DPPs, not stubs (they go through proper P-1)

**Verification:**

- Integration test: generate fanout=10, verify parent has 10 distinct hard dependencies
- Verify children are distributed across at least 2 platforms

---

## Task 8: Story W-3, PV scenario generator

Materialize the PV/battery/inverter scenario from the paper's running example.

**Subtasks:**

- Create `src/workload/scenarios/pv.py`
- Implement `async def generate_pv_scenario(federation: FederationOverview, seed: int | None = None) -> PvScenarioResult`
- Algorithm:
  1. Verify the federation has platforms supporting `pv_module`, `battery`, `inverter`
  2. Seed all three schemas at version 1.0 via Resolver
  3. Issue battery DPP on the platform handling `battery`
  4. Issue inverter DPP on the platform handling `inverter`
  5. Issue PV-module DPP on the platform handling `pv_module`, with hard dependencies on the battery and inverter (pinned to their version 1)
- Result contains all three DPP identities and their versions
- Match the structure depicted in the paper's Figure 1

**Verification:**

- Integration test: generate PV scenario, verify three DPPs exist
- Verify PV's payload contains hard refs to battery and inverter
- Verify resolution of PV's references works end-to-end

---

## Task 9: Measurement infrastructure

Provide timing and bytes-per-operation capture used by all measurement runs.

**Subtasks:**

- Create `src/workload/measurement.py`
- Implement `MeasurementRecorder` class
- Methods:
  - `start_run(run_id: str, workload_kind: str)`
  - `record(operation: str, parameter_value: int, latency_ms: float, bytes_payload: int, bytes_index: int, success: bool, error: str | None, warmup: bool)`
  - `end_run() -> Path` (writes the CSV and returns the path)
- CSV columns exactly: `run_id, workload_kind, parameter_value, operation, latency_ms, bytes_payload, bytes_index, success, error, warmup`
- One row per measured operation; do not aggregate
- Output directory is `output/` in the working directory by default, configurable via env var `WORKLOAD_OUTPUT_DIR`
- Filenames: `<workload_kind>-<timestamp>.csv`
- Add a context manager `measure_operation(recorder, operation, parameter_value, warmup=False)` that times the block and records on exit

**Verification:**

- Unit tests for the recorder: timing precision, CSV format, file naming
- Test that errors are captured (operation marked success=False, error message recorded)

---

## Task 10: Story W-4, measure command

The CLI subcommand that runs a parameterized measurement.

**Subtasks:**

- Create `src/workload/cli.py`
- Add Typer app with subcommands
- Implement `workload measure` command:
  - Args: `--workload {depth,fanout,issue,resolve,query}`, `--range "1-10"`, `--runs N`, `--warmup-runs N`, `--output PATH`, `--seed N`, `--factory-url URL`
- Each measurement run:
  1. Discover federation via Factory
  2. Reset all platforms via Factory (each measurement starts from clean state)
  3. Execute warmup runs without recording
  4. For each parameter value in range, for each run:
     - Build the workload structure (depth chain, fanout, etc.)
     - Capture latency for the operation under test
     - Capture payload bytes from request body, index bytes via platform-specific introspection (or skip and put 0 for now if introspection is not available; document limitation)
     - Record via MeasurementRecorder
  5. Write CSV
- Operations measured per workload type:
  - `depth`: resolve_root_closure (full traversal latency from root)
  - `fanout`: resolve_all_children (parallel resolution of all children)
  - `issue`: issue_simple (single DPP issuance, no dependencies)
  - `resolve`: resolve_single (single DPP retrieval by identity)
  - `query`: query_payload_field (regulatory query if implemented; skip if P-9 projection not done)

**Verification:**

- Run `workload measure --workload depth --range 1-3 --runs 2 --warmup-runs 1` end-to-end, verify CSV output is produced and well-formed
- Verify reset between runs leaves no stale state
- Verify warmup rows are flagged correctly

---

## Task 11: Generate command (W-1, W-2, W-3 wiring)

CLI subcommands for generating fixtures without measurements.

**Subtasks:**

- Implement `workload generate-depth --depth N --seed S` running Task 6
- Implement `workload generate-fanout --fanout N --root-platform P1 --seed S` running Task 7
- Implement `workload pv-scenario --seed S` running Task 8
- Each command prints a summary of what was created (root DPP identity, list of dependencies, platform assignments)
- Each command exits 0 on success, 1 on failure with a clear error message

**Verification:**

- End-to-end: run each command against a real federation, verify the fixture exists by querying platforms

---

## Task 12: Schema evolution measurement

Implement the schema evolution measurement workload mentioned in tech_stack.md.

**Subtasks:**

- Create `src/workload/scenarios/schema_evolution.py`
- Implement `async def run_schema_evolution(federation, n_revisions: int, update_kind: str, recorder: MeasurementRecorder) -> None`
- Algorithm:
  1. Seed schema v1.0
  2. Issue N revisions of a single DPP under v1.0 (recorded as baseline)
  3. Publish schema v1.1 (minor) or v2.0 (major) via Resolver
  4. Issue one revision under the new schema (recorded; major updates require payload changes)
  5. Capture latency of schema publication and the cost of issuing under the new schema
- Add CLI subcommand `workload schema-evolution --revisions N --update-kind minor|major`

**Verification:**

- Run minor and major variants, verify CSV output reflects the operations
- For major updates, verify old revisions remain intact (P-2 invariant)

---

## Task 13: Plot helpers (optional but recommended)

A small companion script for producing plots from the CSV output.

**Subtasks:**

- Create `scripts/plot.py` (note: scripts directory, not in the package)
- Add matplotlib as a dev dependency
- Implement helpers:
  - `plot_latency_vs_depth(csv_path, output_path)`
  - `plot_latency_vs_fanout(csv_path, output_path)`
  - `plot_storage_overhead(csv_path, output_path)`
- Each plot reads the raw CSV, computes mean and std-dev across runs, plots with error bars
- Excludes warmup rows from aggregation
- Output: PNG files at 150 DPI suitable for inclusion in the paper

**Verification:**

- Generate a CSV from Task 10, run a plot helper, verify the output PNG renders correctly
- Verify warmup rows are excluded from the plot

---

## Task 14: Containerize the Workload Generator

Allow running the Workload Generator from a container in addition to the host.

**Subtasks:**

- Create `Dockerfile` based on `python:3.14-slim`
- Install via uv
- Set entrypoint to `workload`
- Mount `output/` as a volume so CSVs persist outside the container
- Document the Docker invocation: `docker run --rm --network dpp-net -v $(pwd)/output:/app/output dpp-workload measure ...`

**Verification:**

- Build image, run measure command from container against the running federation, verify CSV is written to host

---

## Task 15: End-to-end smoke test

Verify the Workload Generator works as a system.

**Subtasks:**

- Create `tests/e2e/test_workload_lifecycle.py`
- Test scenarios:
  1. Cold start: factory running with default federation, run `workload pv-scenario`, verify the three DPPs exist
  2. Run `workload generate-depth --depth 5`, verify chain
  3. Run `workload generate-fanout --fanout 10`, verify fanout structure
  4. Run `workload measure --workload depth --range 1-3 --runs 2 --warmup-runs 1`, verify CSV is produced and rows are present
  5. Run `workload measure --workload fanout --range 1-5 --runs 2`, verify CSV
  6. Run `workload schema-evolution --revisions 5 --update-kind minor`, verify CSV
- All tests run against a real Docker federation, not mocks

**Verification:**

- All E2E tests pass
- Output CSVs contain the expected number of rows per parameter value (runs minus warmups)

---

## Task 16: Documentation

**Subtasks:**

- Update repository README with Workload Generator section
- Document the CLI subcommands and their flags
- Document the CSV schema (column meanings, units)
- Document the relationship to the Factory: how discovery works, why platforms are reset between runs
- Document known limitations (e.g. index bytes may be 0 if platform introspection is not implemented)
- Add a troubleshooting section for common issues (factory unreachable, schema seed conflicts, port conflicts)

**Verification:**

- A fresh developer can clone, run the federation via Factory, and reproduce a measurement run from the README alone

---

## Suggested execution

Tasks 1 to 5 are sequential (foundations). Tasks 6 to 8 (the three generators) can be parallelized. Tasks 9 to 12 build on the generators. Tasks 13 to 16 are finalization.

Realistic time estimate, with Claude Code or Junie assistance:

- Tasks 1 to 5 (foundations and clients): 1 day
- Tasks 6 to 8 (generators): 1 day
- Tasks 9 to 12 (measurement + commands): 1.5 days
- Tasks 13 to 16 (plots, container, tests, docs): 0.5 day

Total: roughly 4 days. Without AI assistance, double this.

## Quality gates

After each task, before moving to the next:

- All tests for the task pass
- The acceptance criteria for the corresponding user story (if any) are demonstrably met
- Implementation is logged in `IMPLEMENTATION_LOG.md` with date, task number, and any notable decisions
- Commit message follows the convention: `workload/T<num>: <imperative summary>` (e.g. `workload/T6: depth chain generator`)

## Things to watch for

A few specific things that will save debugging time:

**Determinism is the point.** Every generator takes a `seed` parameter. Without it, you cannot reproduce a measurement that surprised you. If you find yourself adding non-deterministic behavior (random selection of platforms, timestamps in payloads, etc.), step back and seed it.

**Factory reset between runs is non-negotiable.** Stale state across measurement runs is a silent way to get wrong numbers. Every measurement command starts with `Factory.reset_all_platforms()`. Document this in the CSV via a `run_id` that changes per run.

**Latency measurement boundary matters.** Pick one and document it: from request submission to response received? Including TLS handshake? Including JSON parsing on the client? The choice affects what your numbers mean. The simplest defensible choice is "from `await client.post(...)` start to response body fully received." Stick to it.

**Bytes accounting needs a defensible methodology.** `bytes_payload` is the size of the JSON request body. `bytes_index` requires platform introspection (table size after insert). If introspection is not implemented, set `bytes_index = 0` and document the limitation in Section 8.2 of the paper. Do not estimate or fake.

**The Workload Generator is not the Interaction Platform.** The two are similar but separate. Workload Generator produces statistical data (lots of operations, recorded as CSV rows). Interaction Platform produces narrative scenario reports (specific steps, recorded as Markdown). Do not let the Workload Generator grow to handle scenarios.
