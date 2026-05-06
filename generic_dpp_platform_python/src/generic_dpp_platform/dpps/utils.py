import hashlib

import jcs
import jsonschema

from .exceptions import SchemaValidationException


def validate_dpp_document(payload: dict, schema_document: dict) -> dict:
    """Validate payload against JSON Schema Draft 2020-12. Invariant I5."""
    validator_cls = jsonschema.validators.validator_for(schema_document)
    validator = validator_cls(schema_document)
    errors = sorted(validator.iter_errors(payload), key=lambda e: str(e.path))
    if errors:
        raise SchemaValidationException([e.message for e in errors])
    return payload


def hash_document(document: dict) -> bytes:
    """SHA-256 over JCS-canonicalized JSON. Invariant I4."""
    canonical: bytes = jcs.canonicalize(document)
    return hashlib.sha256(canonical).digest()


def hash_to_hex(hash_bytes: bytes | None) -> str | None:
    if hash_bytes is None:
        return None
    return hash_bytes.hex()


def hex_to_hash(hex_str: str | None) -> bytes | None:
    if hex_str is None:
        return None
    if len(hex_str) % 2 != 0 or not all(c in "0123456789abcdef" for c in hex_str.lower()):
        raise ValueError(f"Invalid hex string: {hex_str}")
    return bytes.fromhex(hex_str)


def verify_hash_integrity(document: dict, stored_hash_hex: str) -> bool:
    """Recompute hash from document and compare with stored hex. Invariant I4."""
    return hash_document(document).hex() == stored_hash_hex
