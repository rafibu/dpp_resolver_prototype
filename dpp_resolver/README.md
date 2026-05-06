# DPP Resolver

The Resolver is a central component of the federated DPP prototype. It handles:
1. **Platform Discovery:** Mapping subject types to the platforms that issue them.
2. **Schema Registry:** Storing and serving JSON Schemas for different subject types.
3. **Cycle Prevention:** Ensuring that the schema-level dependency graph remains acyclic (Invariant I6).

## Schema-Level Cycle Prevention (R-8)

The Resolver enforces that published schemas do not introduce cycles in the hard-dependency graph of subject types. An edge `A -> B` exists if any version of schema `A` declares a hard-reference to subject type `B` via the `x-dpp-reference` annotation.

### Annotations

We use the custom `x-dpp-reference` keyword in JSON Schemas to mark hard-reference fields.
See `docs/schema-conventions.md` for details.

### Error Responses

If a schema publication would introduce a cycle or a self-reference, the Resolver returns a `422 Unprocessable Entity` response.

**Cycle Detected:**
```json
{
  "error": "schema_cycle_detected",
  "message": "Publishing schema 'battery' 2.0 would introduce a cycle: battery -> pv_module -> battery",
  "cycle_path": ["battery", "pv_module", "battery"]
}
```

**Self-Reference Detected:**
```json
{
  "error": "schema_self_reference",
  "message": "Schema 'pv_module' 2.0 declares a hard reference to its own subject type",
  "subject_type": "pv_module"
}
```

## Setup

1. Create a Postgres Database named `dpp_resolver`.
2. Configure connection details in `src/main/resources/application.properties`.
3. Run the application via Maven: `./mvnw spring-boot:run`.