# DPP Workload Generator

## Role in the Paper

The Workload Generator drives the end-to-end evaluation scenarios and supplemental scenario checks. It is a CLI tool that issues operations against the live prototype federation and records results.

It is not part of the federated DPP ecosystem. It is a measurement harness that exercises the federation from the outside.

| What the generator does                                                                     |
|---------------------------------------------------------------------------------------------|
| Generates chains of hard-dependent DPPs at controllable depth                               |
| Generates DPPs with controllable fan-out                                                    |
| Materializes the PV/battery/inverter running example                                        |
| Measures issuance and resolution latency; writes CSV                                        |
| Benchmarks resolver fan-out/depth latency; prints CLI summary                               |
| Runs scenario S1: federated reference stability under target evolution and issuer migration |
| Runs scenario S2: independent schema evolution                                              |
| Runs scenario S3: schema-level cycle rejection (Invariant I6)                               |
| Runs scenario S4: indexed versus on-demand predicate-query evaluation                        |
| Runs scenario S5: offline validation after platform unavailability                          |

The generator discovers the live topology by calling `GET /federation` on the Factory. It does not need to be told manually where platforms or the Resolver are.

## Architecture

```
src/workload/
  cli.py              -- Typer CLI entry point
  clients.py          -- ResolverClient, PlatformClient (typed HTTP clients)
  federation.py       -- FederationClient (Factory discovery + lifecycle)
  measurement.py      -- MeasurementRecorder, measure_operation context manager
  measurements/       -- summary-oriented benchmark mechanisms
    cli.py            -- measurement command group
    graph.py          -- deterministic resolve tree generation
    resolve_fanout.py -- resolver fan-out/depth benchmark
    stats.py          -- latency statistics
  payloads.py         -- generate_valid_payload, generate_dpp_id
  schemas/
    generator.py      -- generate_schema (JSON Schema 2020-12 with x-dpp-reference support)
  scenarios/
    depth.py          -- hard-dependency chain fixture
    fanout.py         -- fan-out fixture
    pv.py             -- PV/battery/inverter fixture (paper running example)
    schema_evolution.py -- schema evolution measurement workload
    s1.py             -- Scenario S1: Federated Reference Stability
    s2.py             -- Scenario S2: Independent Schema Evolution
    s3.py             -- Scenario S3: Schema-Level Cycle Rejection
    s4.py             -- Scenario S4: Predicate-Query Workload Evaluation
    s5.py             -- Scenario S5: Offline Interpretability Supplement
    reporter.py       -- Markdown report writer for scenarios
scripts/
  plot.py             -- Matplotlib plots from CSV output
  sweep.ps1           -- PowerShell wrapper for full measurement sweeps
```

## Prerequisites

- Python 3.14+
- Factory running at `http://localhost:8000` (default)

## Setup

```bash
cd dpp-workload-generator
pip install -e ".[dev]"
```

Or with `uv`:

```bash
uv pip install -e ".[dev]"
```

## CLI Commands

### Measurement workloads

```bash
# Measure closure resolution cost over depth 1-10, 5 runs each
workload measure --workload depth --range 1-10 --runs 5 --output output/depth.csv

# Measure fan-out (parent with N children)
workload measure --workload fanout --range 1-20 --runs 5 --output output/fanout.csv

# Measure single-revision issuance
workload measure --workload issue --range 1-1 --runs 10

# Measure single-reference resolution
workload measure --workload resolve --range 1-1 --runs 10

# Measure schema evolution impact
workload schema-evolution --revisions 5 --update-kind minor
workload schema-evolution --revisions 5 --update-kind major
```

### Resolve fan-out benchmark

The resolve fan-out benchmark measures how long one Resolver takes to resolve a single root DPP revision whose payload contains hard references arranged as a deterministic tree across multiple DPP platforms. It answers:

```
What is the median resolve latency, in milliseconds, for fan-out f and depth d?
```

Run it after the Factory is already running:

```bash
workload measure resolve-fanout \
  --factory-url http://localhost:8000 \
  --fanout 2 \
  --depth 3 \
  --max-resolved-depth 3 \
  --payload-entries 4 \
  --platforms 4 \
  --samples 100 \
  --warmup 20
```

The command discovers the Resolver and current platforms from the Factory, creates missing benchmark platforms if fewer than `--platforms` are running, registers benchmark subject types and resolver routes, publishes the generated DPP revisions leaf-first, then performs sequential warmup and measured closure calls for the root revision.

The number of revisions is the number of nodes in the generated full reference tree:

```text
total revisions = 1 + fanout + fanout^2 + ... + fanout^depth
```

The root is level `0`; `depth` is the number of reference levels below the root. For example, `--fanout 4 --depth 4` creates:

```text
1 + 4 + 16 + 64 + 256 = 341 revisions
```

For `fanout > 1`, this is equivalent to:

```text
total revisions = (fanout^(depth + 1) - 1) / (fanout - 1)
```

For `fanout = 1`, the tree is a chain and creates `depth + 1` revisions.

The generated tree depth and resolved closure depth are separate controls. `--depth` controls how deep the generated hard-reference tree is. `--max-resolved-depth` controls how far the platform `/closure` endpoint traverses that tree during measurement. If `--max-resolved-depth` is omitted, it defaults to the generated `--depth`.

`--payload-entries` controls the target number of top-level entries in each generated DPP payload. For non-leaf DPPs, the `dependencies` array counts as one entry and the remaining entries are deterministic benchmark data fields. For leaf DPPs, all entries are benchmark data fields.

Examples:

```bash
# Generate a depth-4 tree and resolve the full closure
workload measure resolve-fanout --fanout 2 --depth 4

# Generate a depth-4 tree, but resolve only direct hard references from the root
workload measure resolve-fanout --fanout 2 --depth 4 --max-resolved-depth 1
```

Useful options:

| Option                 | Default                 | Description                                                       |
|------------------------|-------------------------|-------------------------------------------------------------------|
| `--factory-url`        | `http://localhost:8000` | URL of the running Factory                                        |
| `--fanout`             | `2`                     | Number of hard references per non-leaf node                       |
| `--depth`              | `2`                     | Number of reference levels below the root                         |
| `--max-resolved-depth` | generated depth         | Maximum closure depth sent as `max_depth` to the platform         |
| `--payload-entries`    | `4`                     | Target number of top-level entries in each generated DPP payload  |
| `--platforms`          | `4`                     | Number of running DPP platforms to use or create                  |
| `--samples`            | `100`                   | Measured resolve calls included in the statistics                 |
| `--warmup`             | `20`                    | Resolve calls run before measurement and excluded from statistics |
| `--timeout`            | `30`                    | HTTP timeout in seconds                                           |
| `--seed`               | generated timestamp     | Deterministic run ID for DPP IDs and subject types                |
| `-v`, `--verbose`      | `false`                 | Show individual API calls instead of the progress bar             |
| `--verbose-errors`     | `false`                 | Print fuller error payloads when setup or resolve calls fail      |

By default, the benchmark hides individual API request logs and shows a progress bar for setup, publication, warmup calls, and measured calls. Use `-v` or `--verbose` to show individual calls instead. In verbose mode, each measured closure resolution is wrapped in a marker such as `=== closure sample 14/100 ... ===`, so the API calls that follow can be attributed to that specific closure request. The benchmark prints only a concise CLI summary and does not write CSV files.

Example output:

```text
Resolve fan-out benchmark

Configuration
  Factory URL:       http://localhost:8000
  Fan-out:           2
  Generated depth:   3
  Max resolved depth:3
  Payload entries:   4
  Required platforms:4
  Total revisions:   15
  Warmup calls:      20
  Samples:           100

Setup
  Resolver:          http://localhost:8080
  Existing platforms:2
  Created platforms: 2
  Subject types:     4
  Root revision:     issuerA-bench-resolve-20260604123000-f2-d3-root
  Max resolved depth:3
  Payload entries:   4

Result
  Successful calls:  100 / 100
  Errors:            0
  Median:            41.73 ms
  Mean:              43.18 ms
  Min:               35.22 ms
  Max:               82.90 ms
  P90:               55.13 ms
  P95:               61.49 ms
  P99:               80.21 ms
```

### Fixture generation

```bash
# Materialize the PV/battery/inverter scenario
workload pv-scenario

# Generate a depth-3 hard-dependency chain
workload generate-depth --depth 3

# Generate a parent DPP with 5 hard-dependent children
workload generate-fanout --fanout 5
```

### Scenario evaluation and supplement

```bash
workload scenario s1 --output-dir output/scenarios
workload scenario s2 --output-dir output/scenarios
workload scenario s3 --output-dir output/scenarios
workload scenario s4 --scale medium --output-dir output/scenarios

# Supplemental only; not part of the actual evaluation.
workload scenario s5 --output-dir output/scenarios
```

S1, S2, S3, and S4 are evaluation scenarios. S4 exports raw and summarized predicate-query benchmark results. S5 writes a Markdown report and is retained only as a supplement to check whether offline validation may be interesting for future work; it is not part of the actual evaluation.

S4 creates or reuses six role-specific platforms identified by deterministic `s4-*` issuers, without resetting or modifying unrelated platforms. Its scale presets are `small` (300 DPPs), `medium` (5,000 DPPs, the default), and `large` (25,000 DPPs). It writes `*-predicate-results.json` and `*-predicate-summary.json`, containing the per-query INDEXED and ON_DEMAND measurements, semantic equivalence checks, and speedup factors. Re-running with the same seed and scale reuses the S4 dataset; a conflicting deterministic dataset is rejected rather than overwritten.

### Plotting

```bash
python scripts/plot.py output/depth.csv
```

## Output Format

CSV columns written by `measure` and `schema-evolution`:

```
run_id, workload_kind, parameter_value, operation, latency_ms, bytes_payload, bytes_index, success, error, warmup
```

Warmup runs are recorded with `warmup=True` and excluded from paper plots.

## Schema Conventions

`generate_schema` produces JSON Schema Draft 2020-12 documents. When `hard_reference_targets` is provided, it adds a property per target annotated with `"x-dpp-reference": "<target>"`. The Resolver's `HardReferenceExtractor` reads these annotations to build the schema dependency graph (Definition 13) and enforce Invariant I6 (acyclicity). Scenario S3 relies on this convention to trigger cycle detection.

## Environment Variables

| Variable              | Default  | Description                                           |
|-----------------------|----------|-------------------------------------------------------|
| `WORKLOAD_OUTPUT_DIR` | `output` | Default output directory for CSV and scenario reports |

## Testing

```bash
# Unit + integration tests (no live federation required)
pytest tests/

# End-to-end tests (requires running Factory & DOCKER_AVAILABLE variable = true)
env:DOCKER_AVAILABLE="true"
pytest tests/e2e/ -m e2e
```
