from copy import deepcopy


_SEED_SCHEMAS: dict[str, dict] = {
    "battery": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://schemas.dpp.eu/battery/1.0",
        "title": "Battery",
        "type": "object",
        "properties": {
            "serial_number": {"type": "string"},
            "manufacturer": {"type": "string"},
            "capacity_kwh": {"type": "number"},
            "capacity_wh": {"type": "number"},
            "chemistry": {"type": "string"},
            "cycles": {"type": "integer"},
        },
        "required": ["capacity_kwh", "chemistry"],
    },
    "inverter": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://schemas.dpp.eu/inverter/1.0",
        "title": "Inverter",
        "type": "object",
        "properties": {
            "serial_number": {"type": "string"},
            "manufacturer": {"type": "string"},
            "max_ac_power_watts": {"type": "number"},
            "efficiency": {"type": "number"},
        },
        "required": ["max_ac_power_watts"],
    },
    "pv_module": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://schemas.dpp.eu/pv_module/1.0",
        "title": "PV Module",
        "type": "object",
        "properties": {
            "serial_number": {"type": "string"},
            "manufacturer": {"type": "string"},
            "model": {"type": "string"},
            "peak_power_watts": {"type": "number"},
            "components": {
                "type": "object",
                "properties": {
                    "battery": {
                        "type": "object",
                        "x-dpp-reference": "battery",
                        "properties": {
                            "$ref": {"type": "string"},
                            "version": {"type": "integer"},
                        },
                        "required": ["$ref"],
                    },
                    "inverter": {
                        "type": "object",
                        "x-dpp-reference": "inverter",
                        "properties": {
                            "$ref": {"type": "string"},
                            "version": {"type": "integer"},
                        },
                        "required": ["$ref"],
                    },
                },
            },
        },
        "required": ["manufacturer", "model"],
    },
}


def canonical_seed_schema(subject_type: str) -> dict:
    """Return the canonical Factory seed schema used by PV workload scenarios."""
    try:
        return deepcopy(_SEED_SCHEMAS[subject_type])
    except KeyError as exc:
        raise ValueError(f"No canonical seed schema for subject type: {subject_type}") from exc
