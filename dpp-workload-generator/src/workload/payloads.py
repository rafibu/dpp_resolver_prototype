import random
import structlog
from typing import List, Optional, Dict, Any
from pydantic import BaseModel

logger = structlog.get_logger(__name__)

class ReferenceSpec(BaseModel):
    subject_type: str
    dpp_id: str
    version: Optional[int] = None

def generate_dpp_id(issuer: str, subject_type: str, sequence: int) -> str:
    """Return IDs like issuerA-pv-001."""
    # We use a short version of subject_type if it's long, but here we just take it.
    # The requirement used 'pv' for 'pv-module' probably.
    st_short = subject_type.split("_")[0][:2] if "_" in subject_type else subject_type[:2]
    return f"{issuer}-{st_short}-{sequence:03d}"

def generate_valid_payload(schema: dict, dependencies: List[ReferenceSpec] = None, seed: Optional[int] = None) -> dict:
    """Generate a valid DPP payload based on the schema structure from Task 4."""
    rng = random.Random(seed)
    
    # Standard fields
    payload = {
        "manufacturer": f"Manufacturer-{rng.randint(1, 100)}",
        "model": f"Model-{rng.choice(['Alpha', 'Beta', 'Gamma'])}-{rng.randint(100, 999)}",
        "recycled_content": round(rng.uniform(0, 100), 2),
        "serial_number": f"SN-{rng.getrandbits(32):08x}"
    }

    if dependencies:
        payload["dependencies"] = []
        for dep in dependencies:
            ref = {"$ref": f"{dep.subject_type}/{dep.dpp_id}"}
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
