# Schema Conventions

This document defines the conventions for JSON Schemas used in the federated DPP prototype.

## Hard-Reference Annotation: `x-dpp-reference`

The Resolver and DPP Platforms need to identify which fields in a schema represent hard references to other DPPs and what subject type they target.

### Convention

We use a custom JSON Schema keyword `x-dpp-reference`. Its value must be a string representing the target subject type.

### Usage

The `x-dpp-reference` annotation can appear in any object property definition. It indicates that the property is a reference to a DPP of the specified subject type.

Example schema fragment:

```json
{
  "$id": "https://schemas.dpp.eu/pv_module/1.0",
  "type": "object",
  "properties": {
    "battery": {
      "type": "object",
      "x-dpp-reference": "battery",
      "properties": {
        "$ref": {"type": "string"},
        "version": {"type": "integer"}
      }
    },
    "inverter": {
      "type": "object",
      "x-dpp-reference": "inverter",
      "properties": {
        "$ref": {"type": "string"},
        "version": {"type": "integer"}
      }
    }
  }
}
```

### Implications

- **For the Resolver:** The Resolver parses this annotation during schema publication to build a schema-level dependency graph. This graph is used to prevent cycles (Invariant I6).
- **For DPP Platforms:** Platforms use this annotation during DPP issuance and revision to extract instance-level references, resolve them, and perform cycle detection (if applicable at instance level, though schema-level detection at the Resolver is the primary defense).
- **JSON Schema Validation:** This is a custom annotation and does not affect standard JSON Schema validation. Validators will ignore it unless explicitly configured to handle it.

## Standard Subject Types

The following subject types are used in the running example:

- `pv_module`
- `battery`
- `inverter`
- `junction_box`
