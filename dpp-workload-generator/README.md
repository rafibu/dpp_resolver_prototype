# DPP Workload Generator

## Role in the Paper

The Workload Generator drives the quantitative evaluation (Section 8.3) and the three end-to-end scenarios (Section 8.4) of the paper. It is a CLI tool that issues operations against the live prototype federation and records results.

It is not part of the federated DPP ecosystem. It is a measurement harness that exercises the federation from the outside.

| What the generator does                                            | Paper anchor                                  |
|--------------------------------------------------------------------|-----------------------------------------------|
| Generates chains of hard-dependent DPPs at controllable depth      | Section 8.3.3: closure resolution cost O(f^d) |
| Generates DPPs with controllable fan-out                           | Section 8.3.3: per-fan-out constant factors   |
| Materializes the PV/battery/inverter running example               | Sections 4-5 running example                  |
| Measures issuance and resolution latency; writes CSV               | Section 8.3: prototype measurements           |
| Runs scenario S1: offline validation after platform unavailability | Section 8.4.1                                 |
| Runs scenario S2: independent schema evolution                     | Section 8.4.2                                 |
| Runs scenario S3: schema-level cycle rejection (Invariant I6)      | Section 8.4.3                                 |

The generator discovers the live topology by calling `GET /federation` on the Factory. It does not need to be told manually where platforms or the Resolver are.

## Architecture

```
src/workload/
  cli.py              -- Typer CLI entry point
  clients.py          -- ResolverClient, PlatformClient (typed HTTP clients)
  federation.py       -- FederationClient (Factory discovery + lifecycle)
  measurement.py      -- MeasurementRecorder, measure_operation context manager
  payloads.py         -- generate_valid_payload, generate_dpp_id
  schemas/
    generator.py      -- generate_schema (JSON Schema 2020-12 with x-dpp-reference support)
  scenarios/
    depth.py          -- hard-dependency chain fixture
    fanout.py         -- fan-out fixture
    pv.py             -- PV/battery/inverter fixture (paper running example)
    schema_evolution.py -- schema evolution measurement workload
    s1.py             -- Scenario S1: Offline Interpretability
    s2.py             -- Scenario S2: Independent Schema Evolution
    s3.py             -- Scenario S3: Schema-Level Cycle Rejection
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

### Fixture generation

```bash
# Materialize the PV/battery/inverter scenario
workload pv-scenario

# Generate a depth-3 hard-dependency chain
workload generate-depth --depth 3

# Generate a parent DPP with 5 hard-dependent children
workload generate-fanout --fanout 5
```

### Scenario evaluation (Section 8.4)

```bash
workload scenario s1 --output-dir output/scenarios
workload scenario s2 --output-dir output/scenarios
workload scenario s3 --output-dir output/scenarios
```

Each scenario writes a Markdown report to the output directory with per-step expected vs. observed outcomes and a PASSED/FAILED verdict.

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

# End-to-end tests (requires running Factory)
pytest tests/e2e/ -m e2e
```
