import random
import structlog
from pydantic import BaseModel
from typing import List, Optional, Dict, Any

logger = structlog.get_logger(__name__)

class ReferenceSpec(BaseModel):
    subject_type: str
    dpp_id: str
    version: Optional[int] = None

def generate_dpp_id(issuer: str, subject_type: str, sequence: int) -> str:
    """Return IDs like issuerA-pv-001."""
    st_short = subject_type.split("_")[0][:2] if "_" in subject_type else subject_type[:2]
    return f"{issuer}-{st_short}-{sequence:03d}"

def generate_seed_payload(subject_type: str, seed: Optional[int] = None,
                          hard_refs: Optional[Dict[str, ReferenceSpec]] = None) -> dict:
    """Generate a payload conforming to the federation's seed schemas.

    Used for the three canonical subject types (battery, inverter, pv_module) whose
    schemas are seeded by the Factory and have domain-specific required fields.
    The pv_module schema encodes hard references inside components.<subject_type>
    using the x-dpp-reference annotation (Definition 12), not a dependencies array.
    """
    rng = random.Random(seed)

    if subject_type == "battery":
        return {
            "manufacturer": f"Manufacturer-{rng.randint(1, 100)}",
            "serial_number": f"SN-{rng.getrandbits(32):08x}",
            "capacity_kwh": round(rng.uniform(10, 100), 2),
            "chemistry": rng.choice(["Li-ion", "LFP", "NMC"])
        }

    if subject_type == "inverter":
        return {
            "manufacturer": f"Manufacturer-{rng.randint(1, 100)}",
            "serial_number": f"SN-{rng.getrandbits(32):08x}",
            "max_ac_power_watts": float(rng.choice([3000, 5000, 7000, 10000])),
            "efficiency": round(rng.uniform(95.0, 99.0), 1)
        }

    if subject_type == "pv_module":
        # The factory-seeded pv_module schema declares additionalProperties: false and only
        # permits manufacturer, model, serial_number, recycled_content, and dependencies.
        # Emit exactly those allowed fields so the payload validates (I5).
        payload: dict = {
            "manufacturer": f"Manufacturer-{rng.randint(1, 100)}",
            "model": f"Model-{rng.choice(['Alpha', 'Beta', 'Gamma'])}-{rng.randint(100, 999)}",
            "serial_number": f"SN-{rng.getrandbits(32):08x}",
            "recycled_content": round(rng.uniform(0, 100), 2)
        }
        if hard_refs:
            # Use a flat dependencies array rather than the components.{type}.$ref structure.
            # The pv_module seed schema uses "$ref" as a property name inside components.battery,
            # which networknt json-schema-validator 1.5.5 mishandles in Draft 2020-12 mode
            # (treating it as a $ref keyword rather than a plain property name). The seeded schema
            # allows a top-level "dependencies" array, and DppReferenceExtractor scans recursively
            # for any
            # object with a "$ref" key regardless of where it appears in the payload.
            payload["dependencies"] = []
            for st, ref in hard_refs.items():
                entry: dict = {"$ref": f"{st}/{ref.dpp_id}"}
                if ref.version is not None:
                    entry["version"] = ref.version
                payload["dependencies"].append(entry)
        return payload

    # Unknown seed type — fall back to generic
    return generate_valid_payload({}, seed=seed)

def generate_valid_payload(schema: dict, dependencies: List[ReferenceSpec] = None,
                           seed: Optional[int] = None) -> dict:
    """Generate a valid DPP payload for workload-generator-owned schemas.

    Used for custom subject types (link_N, parent, child, evolve_*) whose schemas
    are published by the workload generator itself. References go in a dependencies
    array, matching the x-dpp-reference layout in generate_schema.
    """
    rng = random.Random(seed)

    payload = {
        "manufacturer": f"Manufacturer-{rng.randint(1, 100)}",
        "model": f"Model-{rng.choice(['Alpha', 'Beta', 'Gamma'])}-{rng.randint(100, 999)}",
        "recycled_content": round(rng.uniform(0, 100), 2),
        "serial_number": f"SN-{rng.getrandbits(32):08x}"
    }

    if dependencies:
        payload["dependencies"] = []
        for dep in dependencies:
            ref: dict = {"$ref": f"{dep.subject_type}/{dep.dpp_id}"}
            if dep.version is not None:
                ref["version"] = dep.version
            payload["dependencies"].append(ref)

    return payload

def generate_invalid_payload(schema: dict, violation_kind: str, seed: Optional[int] = None) -> dict:
    """Generate an invalid DPP payload by violating specific schema constraints."""
    payload = generate_valid_payload(schema, seed=seed)
    rng = random.Random(seed)
    
    if violation_kind == "missing_required_field":
        field = rng.choice(["manufacturer", "model", "serial_number"])
        if field in payload:
            del payload[field]
    elif violation_kind == "wrong_type":
        payload["recycled_content"] = "not a number"
    elif violation_kind == "out_of_range":
        payload["recycled_content"] = 150.0 # Max is 100
    else:
        raise ValueError(f"Unknown violation kind: {violation_kind}")
        
    return payload
