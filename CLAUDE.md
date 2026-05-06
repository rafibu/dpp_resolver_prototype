# CLAUDE.md

Project-level instructions for Claude Code when working in this repository.

## Project context

This repository implements a research prototype for a paper on **federated Digital Product Passport (DPP) architecture**, targeted at the Information Systems journal (Elsevier). The prototype demonstrates a formal data model with identity-revision separation, federated composition through hard and soft dependencies, and schema evolution under regulatory constraints.

The paper's claims rest on this prototype, so implementation correctness against the formal model matters more than feature completeness.

## Specification documents

Read these before starting any non-trivial task. They are the source of truth, not the existing code.

- `prototype_user_stories.md` — backlog of 24 user stories grouped by artefact, each with Given-When-Then acceptance criteria. Stories are identified by codes (R-1 to R-5, P-1 to P-9, F-1 to F-3, W-1 to W-4, I-1 to I-3).
- `tech_stack.md` — definitive technology decisions per artefact. If a tech decision is not in this file, ask before introducing it.
- `additional_tasks.md` — supplementary tasks beyond the user story backlog (containerization, frontend scope, paper-section additions).
- `architecture_overview.svg` — component diagram of the federation.
- `resolution_flow.svg` — sequence diagram of a federated resolution with cache.
- `paper_outline_IS.md` — the paper's structure. Sections 4 (formal model) and 5 (operations) define the invariants that the prototype must enforce.

When working on a story, reference it by code in commits and PRs (e.g. "implement P-5 transitive cycle detection").

## Architecture summary

Seven artefacts:

| Artefact             | Stack                             | Purpose                                       |
|----------------------|-----------------------------------|-----------------------------------------------|
| Resolver             | Java 25, Spring Boot, Postgres    | Identity-to-platform mapping, schema registry |
| DPP-Platform A       | Java 25, Spring Boot, Postgres    | Reference platform, relational + JSON hybrid  |
| DPP-Platform B       | Python 3.14, FastAPI, MongoDB     | Reference platform, document persistence      |
| Factory              | Python 3.14, FastAPI + Docker SDK | Spawns and manages platform containers        |
| Workload Generator   | Python 3.14 CLI                   | Synthetic load for measurements               |
| Interaction Platform | Python 3.14 CLI                   | Drives S1/S2/S3 scenarios                     |
| Frontend             | TypeScript, Angular, SCSS, Vite   | Federation observer and demo UI               |

Two platforms (A and B) implement the **same REST contract** with different stacks and storage. Heterogeneity is the point. Do not converge them.

## Cross-cutting technical decisions

These are locked. Do not change without asking.

- **Hashing:** SHA-256 over JCS-canonicalized (RFC 8785) JSON
- **Schema format:** JSON Schema Draft 2020-12
- **Schema versioning:** `(major, minor)` embedded in `$id` field, e.g. `https://schemas.dpp.eu/pv_module/1.2`
- **Identity format:** `<subject_type>/<issuer>-<local_id>[/<version>]`
- **Reference encoding:** schema-annotated field, instance shape `{"$ref": "...", "version": N?}`. Presence of `version` = hard dependency, absence = soft (matches Definition 6 in the paper)
- **Timestamps:** UTC ISO 8601, millisecond precision
- **Logging:** structured JSON to stdout (SLF4J/Logback for Java, structlog for Python)
- **API style:** REST over HTTP, no GraphQL
- **Container management:** Docker, Docker Compose, Docker SDK for Python (in the Factory)

## Formal model invariants

The prototype must enforce these. Code that touches DPP issuance, revision, or storage should reference the relevant invariant in comments.

| Invariant | Meaning                                           | Where enforced                                   |
|-----------|---------------------------------------------------|--------------------------------------------------|
| I1        | Revision uniqueness per (DPP, version)            | Database PK + application-level check            |
| I2        | Version monotonicity                              | Application logic on revise                      |
| I3        | Schema explicitness on every revision             | DB foreign key + validation                      |
| I4        | Hash matches payload                              | Server-side hash computation, never trust client |
| I5        | Payload validates against referenced schema       | Pre-write JSON Schema validation                 |
| I6        | No cycles in hard-dependency graph                | Resolver level (schema-level cycle prevention)   |
| I7        | Hard references resolvable on the federated union | Resolution check on issue, cache enables offline |

The hash is **always** computed server-side from canonicalized payload. Never accept a hash from a client request body.

## Coding conventions

### Language and style

- All code, comments, and identifiers in English.
- No m-dashes in any string output, log message, error message, or generated user-facing text. Use commas, colons, or rephrase.
- No emojis in code, comments, or output.
- Variable and function names should be descriptive but not verbose. `revision_id` not `r`, but not `unique_identifier_for_a_revision_record`.

### Java (Resolver, Platform A)

- Java 25 features welcome (records, pattern matching, sealed types where useful)
- Spring Boot conventions, constructor injection, no field injection
- Use Lombok Class Annotations
- Use records for DTOs, classes for entities
- Repository interfaces extend `JpaRepository`, no custom implementations unless necessary
- Tests: JUnit 5, Create ControllerTests as Gray box tests for API Verification
- Build: Maven

### Python (Platform B, Factory, Workload Generator, Interaction Platform)

- Python 3.14, type hints throughout
- FastAPI with Pydantic v2 models for all request/response shapes
- Async (`async def`, `httpx.AsyncClient`, `motor` for MongoDB) where it touches I/O
- Tests: pytest, pytest-asyncio, Testcontainers for MongoDB in integration tests
- Project layout: `src/` for code, `tests/` for tests, `pyproject.toml` for config
- Use `uv` or `pip-tools` for dependency management, not bare `pip install`

### TypeScript / Angular (Frontend)

- TypeScript strict mode
- Angular 21 with standalone components, no NgModules unless forced by a library
- Use the new control flow syntax (@if, @for, @switch), not *ngIf/*ngFor
- Signals for component-local reactive state, RxJS at the HttpClient boundary only
- SCSS files
- ngx-graph for the federation map
- ngx-monaco-editor-v2 for the JSON editor
- No animation libraries unless explicitly needed

### Global Styles + Styles Folder
Use the following reusable styles when possible
- `/src/styles/`
    - `reset.scss` --> global, tag- and attribute-based rules
    - `globals.scss` --> global, class-based rules (utilities, layouts, blocks)
    - `overrides.scss` --> all overrides for library rules (material)
    - `_col.scss` --> color variables
    - `_dim.scss` --> dimension variables
    - `_var.scss` --> other variables
    - `_mix.scss` --> reusable, tunable scss mixins
    - `_fun.scss` --> reusable scss functions
    - `_mat.scss` --> when using material, it useful to re-export utility function with applied theme argument\
      e.g. `@function get-theme-color($args...) { @return material.get-theme-color($theme, $args...); }`
    - further file splitting might be appropriate e.g. overrides per mat-component
- `/src/styles.scss`
    - imports of reset + globals + overrides

### General Styling Rules

- Do not use `!important`
- style on classes | elements | pseudo-classes | attributes
- use BEM for rules belonging together [further reading](https://css-tricks.com/bem-101/)
- no margins on base styiling of components / blocks
    - add margin from the using component / from the "outside"
    - use layout gaps instead (flex and grid)
- stop using `@import` - use `@use` instead [read why](https://sass-lang.com/documentation/at-rules/use/)
- use namespaced variables/mixins (which is the case when using `@use`)

### Database conventions

- Postgres: snake_case table and column names. Migrations via Flyway. Each migration is reviewed before applying.
- MongoDB: snake_case field names for consistency with Postgres. TTL indexes for cache collections.
- No raw SQL string concatenation. Use JPA criteria, prepared statements, or Motor's typed queries.

### Tests

- Every user story implementation includes at least one integration test mirroring its Gherkin scenario.
- Unit tests for invariant enforcement (one test per invariant, per artefact that enforces it).
- Tests use the same canonicalization and hashing as production code, not bypasses.
- Test data should reflect the running PV/battery/inverter scenario where possible, for consistency with the paper.

## Constraints and out-of-scope items

### Do not introduce

- Authentication or access control. Out of scope for the paper, mentioned as future work.
- Form generation in the Frontend. Use a raw JSON editor (Monaco) with client-side schema validation.
- Real-time websocket updates in the Frontend. Use polling at 2-second intervals.
- A central log aggregator. The Frontend reads container logs via Docker SDK or simple proxy.
- Redis or other caching layers beyond what is in the tech stack file.
- GraphQL on any service.
- Dependencies not listed in `tech_stack.md` without confirming first.

### Do not change

- The REST contract between platforms. Both Platform A and Platform B expose the same endpoints with the same request and response shapes.
- The cross-cutting decisions listed above (hashing, schema format, identity format, etc.).
- The user story numbering. If a story is split or merged, propose the change first.

### Do not skip

- Hash verification on cache reads. Cache hits must re-verify the hash, defending against cache tampering.
- Schema validation before persistence. Validation runs first, persistence second.
- Cycle detection on issue/revise of a revision with hard dependencies. The detection covers transitive cycles across platforms, not just direct ones.

## Workflow expectations

### Story-by-story implementation

Work one user story at a time. For each story:

1. Read the story's acceptance criteria
2. Identify which existing code is relevant (or note "starting fresh")
3. Implement the minimum code to satisfy the criteria
4. Write the integration test that mirrors the Gherkin scenario
5. Run the test, fix until it passes
6. Note the implementation in `IMPLEMENTATION_LOG.md`

Do not bundle multiple stories into a single change unless they are tightly coupled (e.g. R-3 and R-4 both involve resolution path handling).

### Implementation log

Maintain `IMPLEMENTATION_LOG.md` in the repo root. Each entry: date, story code, what was implemented, anything noteworthy (deviations from spec, manual verifications performed, known limitations).

This log feeds into the paper's reproducibility statement and is useful for tracking what has been audited.

### Verification points that need human review

Flag these explicitly when implementing, do not silently proceed:

- Hash and canonicalization correctness across language boundaries (a SHA-256 of JCS-canonicalized JSON must match between Java and Python implementations for the same payload)
- Cycle detection correctness, especially the transitive cross-platform case
- Schema backward compatibility check (the human is implementing this, do not auto-generate it)
- JSON projection layer in Platform A (which fields project, when projection runs)
- Latency measurement boundaries in the Workload Generator

### Commit messages

Format: `<story-code>: <imperative summary>`

Examples:
- `R-1: register platform endpoint with uniqueness check`
- `P-9: add JSON projection for recycled_content`
- `infra: docker-compose for default federation`

## Repository layout

```
/
├── CLAUDE.md                       (this file)
├── prototype_user_stories.md
├── tech_stack.md
├── paper_outline_IS.md
├── architecture_overview.svg
├── resolution_flow.svg
├── IMPLEMENTATION_LOG.md
├── docker-compose.yml
├── dpp_resolver/                   (Spring Boot)
├── generic_dpp_platform_java/      (Spring Boot)
├── generic_dpp_platform_python/    (FastAPI)
├── dpp_platform_factory/           (FastAPI + Docker SDK)
├── workload-generator/             (Python CLI)
├── interaction-platform/           (Python CLI)
├── dpp-resolver-prototype-frontend/   (Angular)
└── docs/
    └── deployment.md               (operational notes)
```

## When in doubt

If a request is ambiguous, ask before guessing. Specifically:

- If a user story's acceptance criterion is unclear, surface the ambiguity rather than picking an interpretation
- If an implementation choice would deviate from the tech stack file, ask first
- If the formal model and the existing code disagree on what an invariant means, the formal model wins, but flag the disagreement so the paper or the code can be corrected

## What this project is not

- Not a production-ready DPP platform. Performance, security hardening, and operational concerns beyond what the paper claims are out of scope.
- Not a full implementation of the EU ESPR DPP requirements. The prototype demonstrates architectural properties, not regulatory compliance.
- Not a benchmark suite. The Workload Generator produces measurements for the paper, not a general-purpose evaluation tool.
- Not a tutorial codebase. Code clarity matters, but the goal is the paper, not pedagogical perfection.
