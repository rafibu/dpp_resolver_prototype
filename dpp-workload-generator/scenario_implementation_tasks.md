# Scenario Subcommands Implementation Tasks

Sequential task list for adding the two scenario subcommands (S1, S2) to the Workload Generator. These replace the standalone "Interaction Platform" artefact.

## Prerequisites

Before starting these tasks, the following must be in place:

- Workload Generator implementation complete (Tasks 1 through 16 of `workload_generator_implementation_tasks.md`)
- Factory exposes `/platforms/{id}/pause`, `/platforms/{id}/resume`, `/platforms/{id}/reset`, and `/resolver/seed-schemas`
- Resolver supports schema publication including major-version bumps (R-6, R-7)
- Both platforms cache external revisions and verify hashes on cache reads (P-3)

If any of these are missing, complete them before starting on the scenarios.

## Scope

The two scenarios produce **narrative reports**, not statistical data. The output is Markdown with timestamps and outcomes per step, suitable for inclusion in Section 8.4 of the paper.

Each scenario:
1. Sets up federation state (uses Workload Generator primitives)
2. Executes scenario-specific steps in order
3. Captures expected vs observed outcome at each step
4. Writes a Markdown report

Scenarios are deterministic. Same input, same output. No flakiness. If a scenario produces nondeterministic results, that is a prototype bug to fix, not a scenario to retry.

## Note on cycle prevention

The cycle prevention scenario that was previously called S3 has been removed from the scenario set. Cycles are now prevented at schema publication time at the Resolver, not at instance issuance time at the platforms. This behavior is verified via Resolver integration tests (see `schema_cycle_implementation_tasks.md`, task R-8.6), not as a federation-level scenario.

The user stories I-3 and P-5 are deleted as a consequence. Only I-1 (S1) and I-2 (S2) remain.

---

## Task 1: Scenario reporting infrastructure

Provide the shared report-writing utility used by both scenarios.

**Subtasks:**

- Create `src/workload/scenarios/reporter.py`
- Implement `ScenarioReporter` class
- Methods:
  - `__init__(scenario_id: str, scenario_title: str)`
  - `step(description: str, expected: str)` returns a context manager
  - Inside the context manager: `record_observation(observed: str, success: bool, details: dict | None = None)`
  - `finalize() -> Path` (writes Markdown report and returns the path)
- Markdown structure:

```
# Scenario S1: Offline Interpretability

**Run ID:** s1-2026-05-03T14-22-11Z
**Started:** 2026-05-03T14:22:11.456Z
**Completed:** 2026-05-03T14:22:35.012Z
**Outcome:** PASSED

## Setup

- ...

## Steps

### Step 1: Cache hard dependencies on platform-a

**Expected:** All hard refs in PV-module DPP resolve and cache successfully.

**Observed:** 2 references resolved (battery, inverter). Cache contains 2 entries with verified hashes.

**Result:** PASSED

### Step 2: Pause platform-b

...

## Verification of formal-model elements

- I4 (Integrity): cached hashes verified successfully across all reads. PASSED.
- I7 (Hard resolvability): closure remained resolvable on cached snapshot after pause. PASSED.

## Conclusion

Scenario S1 demonstrates the offline interpretability property of the architecture. ...
```

- Output directory: `output/scenarios/` in the working directory by default, configurable via env var `WORKLOAD_OUTPUT_DIR`
- Filename: `<scenario_id>-<timestamp>.md`
- Capture step duration in milliseconds for each step
- If any step fails, the overall outcome is FAILED but the scenario continues to the end (so the report shows where things broke down)

**Verification:**

- Unit tests for the reporter: format correctness, timestamp handling, success/failure aggregation
- Test that exceptions inside a step are captured and recorded

---

## Task 2: Scenario CLI scaffolding

Wire up the `workload scenario` command group with subcommands.

**Subtasks:**

- Add a `scenario` Typer subcommand group to `src/workload/cli.py`
- Two subcommands: `s1`, `s2`
- Common flags for both: `--factory-url URL` (default `http://localhost:8000`), `--seed N` (default 42), `--output-dir PATH`
- Each subcommand currently calls into a stub function and prints "not yet implemented"
- The exit code is 0 if the scenario passed, 1 if any step failed

**Verification:**

- `workload scenario --help` lists both subcommands
- `workload scenario s1 --help` shows expected flags
- Stubs run without errors and return exit code 0

---

## Task 3: Scenario S1, offline interpretability

Drive the offline interpretability scenario end-to-end.

**Subtasks:**

- Create `src/workload/scenarios/s1.py`
- Implement `async def run_s1(factory_url: str, seed: int, output_dir: Path) -> ScenarioResult`
- Steps:

**Setup:**
1. Discover federation via Factory
2. Reset all platforms via Factory (clean state)
3. Seed PV/battery/inverter schemas via Factory's `/resolver/seed-schemas` endpoint
4. Generate PV scenario via Workload Generator's `generate_pv_scenario()` (Task 8 of workload_generator_implementation_tasks)

**Steps:**

5. **Cache dependencies on platform-a**
   - Expected: PV-module DPP's hard refs (battery, inverter) resolve and cache
   - Action: Issue a fresh GET against the PV-module DPP from platform-a, which forces dependency resolution
   - Observation: query platform-a's external_cache, verify it contains 2 entries
   - Verification: each cache entry's hash matches SHA256(JCS(payload))
6. **Verify online resolution works baseline**
   - Expected: GET PV-module DPP from outside the federation returns 200 with payload
   - Action: HTTP GET via Resolver
   - Observation: 200 response, payload validated
7. **Pause platform-b via Factory**
   - Expected: platform-b becomes unreachable
   - Action: POST /platforms/platform-b/pause
   - Observation: HTTP GET to platform-b's external URL fails with connection error
8. **Validate PV-module closure offline**
   - Expected: platform-a can still serve the PV-module DPP because dependencies are cached
   - Action: GET PV-module DPP via platform-a's URL
   - Observation: 200 response with payload, references in payload point to cached battery (verified by hash)
9. **Re-verify hash on cached battery entry**
   - Expected: cached payload still hashes to the stored hash (Invariant I4)
   - Action: read cache row, recompute hash, compare
   - Observation: hashes match
10. **Resume platform-b**
    - Expected: platform-b becomes reachable again
    - Action: POST /platforms/platform-b/resume
    - Observation: GET to platform-b's external URL succeeds with 200

**Verification of formal-model elements:**

- I4 (Integrity): all cached hashes verified successfully
- I7 (Hard resolvability): PV-module's hard-dependency closure remained resolvable from cached snapshot after pause

- Wire up the CLI subcommand `workload scenario s1` to call `run_s1`

**Verification:**

- Run S1 against a real federation, verify Markdown report is produced
- Verify each step's observation matches the expected outcome
- Run S1 a second time after Factory reset, verify identical report (modulo timestamps)
- If platform-b's pause fails, scenario reports the failure clearly

---

## Task 4: Scenario S2, independent schema evolution

Drive the schema evolution scenario.

**Subtasks:**

- Create `src/workload/scenarios/s2.py`
- Implement `async def run_s2(factory_url: str, seed: int, output_dir: Path) -> ScenarioResult`
- Steps:

**Setup:**
1. Discover federation via Factory
2. Reset all platforms via Factory
3. Seed `battery` schema 1.0 and `pv_module` schema 1.0 (PV references battery so both are needed)

**Steps:**

4. **Issue battery DPP under schema 1.0 on platform-b**
   - Expected: battery DPP created with schema (battery, 1, 0)
   - Action: Workload Generator issues a battery DPP
   - Observation: DPP exists, schema reference is (battery, 1, 0)
5. **Issue PV-module DPP on platform-a with hard dep pinned to battery v1**
   - Expected: PV-module DPP created with hard ref to battery's specific revision
   - Action: Workload Generator issues PV-module DPP
   - Observation: PV-module DPP exists, hard dependency is version-pinned
6. **Verify PV-module is valid (baseline)**
   - Expected: GET PV-module returns 200, schema validates
   - Action: HTTP GET via platform-a
   - Observation: 200, payload validates against pv_module 1.0
7. **Publish battery schema 2.0 (major update) via Resolver**
   - Expected: schema published, marked as major (breaking change introduced, e.g. new required field `cell_chemistry`)
   - Action: POST /schemas to Resolver with major version 2 and a breaking change
   - Observation: 201 response, schema retrievable via GET /schemas/battery/2.0
8. **Verify battery schema 1.0 is still retrievable**
   - Expected: historical schemas remain accessible (R-5)
   - Action: GET /schemas/battery/1.0
   - Observation: 200, original schema returned unchanged
9. **Verify existing PV-module DPP remains valid**
   - Expected: PV-module's pinned battery revision is under schema 1.0, still valid
   - Action: GET PV-module DPP, validate against pv_module 1.0
   - Observation: still 200, validation passes
10. **Issue a new battery DPP under schema 2.0 on platform-b**
    - Expected: new battery DPP must satisfy 2.0 constraints (must include `cell_chemistry`)
    - Action: Workload Generator issues a new battery DPP under (battery, 2, 0)
    - Observation: 201, validation passes against 2.0
11. **Try issuing a new battery DPP under 2.0 missing the new required field**
    - Expected: rejected with 422 schema validation error (Invariant I5)
    - Action: issue with payload missing `cell_chemistry`
    - Observation: 422 response, error identifies the missing field

**Verification of formal-model elements:**

- I5 (Validity): rejected payload was correctly rejected
- Definition 9 (Major update): the version bump was treated as major, not subject to backward compatibility check
- R-5 (Historical schema availability): schema 1.0 remained accessible after 2.0 was published

- Wire up the CLI subcommand `workload scenario s2`

**Verification:**

- Run S2 against a real federation, verify Markdown report
- Verify both schemas are accessible at the end
- Verify PV-module's pinned battery is still resolvable

---

## Task 5: End-to-end smoke test for both scenarios

Verify scenarios run cleanly against a real federation.

**Subtasks:**

- Create `tests/e2e/test_scenarios.py`
- Test scenarios:
  1. Run `workload scenario s1` after Factory bootstrap, verify Markdown report exists and outcome is PASSED
  2. Run `workload scenario s2`, verify Markdown report and outcome
  3. Run both sequentially, verify each is independent (Factory reset works correctly between them)
- Test that exit codes match: 0 on success, 1 on any step failure
- Tests run against a real Docker federation, not mocks

**Verification:**

- All E2E tests pass
- Output directory contains two Markdown files after the test run
- Each report's "Outcome: PASSED" line is present

---

## Task 6: Documentation

**Subtasks:**

- Update repository README with scenarios section
- Document the `workload scenario` CLI subcommand and its two variants
- Document the Markdown report format (consumers may parse this for the paper)
- Document the relationship between scenarios and Section 8.4 of the paper
- Note explicitly that schema-level cycle prevention (formerly S3) is verified via Resolver integration tests, not as a scenario
- Add a sample report in `docs/example-scenario-report.md` for reference

**Verification:**

- Reading the README, a fresh developer can run both scenarios and locate their reports

---

## Suggested execution

Tasks 1 and 2 are sequential foundations. Tasks 3 and 4 (the two scenarios) can be parallelized since they share no code beyond what tasks 1 and 2 produce. Tasks 5 and 6 are wrap-up.

Realistic time estimate, with Junie or Claude Code assistance:

- Tasks 1 and 2 (reporter + CLI): half a day
- Tasks 3 and 4 (scenarios): 1 day
- Tasks 5 and 6 (tests + docs): half a day

Total: 2 days. Without AI assistance, double this.

## Quality gates

After each task, before moving to the next:

- All tests for the task pass
- The scenario report renders cleanly in Markdown viewers
- The corresponding user story acceptance criteria (I-1, I-2) are demonstrably met
- Implementation is logged in `IMPLEMENTATION_LOG.md`
- Commit message follows the convention: `workload-scenarios/T<num>: <imperative summary>`

## Things to watch for

A few specific things that will save debugging time and improve the resulting paper:

**Determinism is non-negotiable.** Each scenario must produce identical reports across runs (modulo timestamps). If you find yourself adding randomness, sleep loops, or "wait until X happens" logic, that is hiding a real prototype bug. Find and fix it rather than papering over.

**The scenario IS the test.** Do not write unit tests that mock the Factory, then claim S1 works. The Markdown report is the evidence. If the report says "PASSED" it must reflect actual federation behavior, not mocked behavior.

**The Markdown reports go straight into your paper.** You will copy-paste paragraphs from these reports into Section 8.4. So the writing inside them matters. Use complete sentences. Use the formal-model element names (I4, I5, I7) consistently with the paper. Avoid cute phrasing.

**S2's "breaking change" needs to be a real one.** When publishing schema 2.0 in step 7, the breaking change should be something specific: "added required field `cell_chemistry`". Document the change in the report so reviewers know the major bump was justified.

**Failed steps still continue.** Scenarios do not abort on first failure. They keep going so the report shows the full state. This is more useful for debugging the prototype and for paper reviewers who want to see how the architecture handles partial failures.
