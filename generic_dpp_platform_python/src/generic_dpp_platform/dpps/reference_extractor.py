import re

from .models import DependencyType, DppReference

_REF_PATTERN = re.compile(r"^([^/]+)/([^/]+)(?:/(\d+))?$")


def extract_references(node: dict | list, path: str = "$") -> list[DppReference]:
    """Traverse the JSON tree and collect all objects containing a '$ref' field."""
    refs: list[DppReference] = []
    _traverse(node, path, refs)
    return refs


def _traverse(node: dict | list, path: str, refs: list[DppReference]) -> None:
    if isinstance(node, dict):
        if "$ref" in node:
            refs.append(_parse_reference(node, path))
        else:
            for key, value in node.items():
                _traverse(value, f"{path}.{key}", refs)
    elif isinstance(node, list):
        for i, item in enumerate(node):
            _traverse(item, f"{path}[{i}]", refs)


def _parse_reference(node: dict, path: str) -> DppReference:
    raw_ref = node["$ref"]
    if not isinstance(raw_ref, str):
        raise ValueError(f"Invalid reference at {path}: $ref must be a string")
    match = _REF_PATTERN.match(raw_ref)
    if not match:
        raise ValueError(
            f"Invalid DPP reference format at {path}: '{raw_ref}'. "
            "Expected '<subject_type>/<dpp_id>[/<version>]'."
        )

    subject_type = match.group(1)
    dpp_id = match.group(2)
    version_in_path: int | None = int(match.group(3)) if match.group(3) else None

    version_field: int | None = None
    if "version" in node:
        candidate = node["version"]
        # Jackson's ``JsonNode.isInt`` deliberately excludes floats, strings,
        # and booleans. Match it rather than silently coercing values.
        if type(candidate) is not int:
            raise ValueError(f"Invalid reference at {path}: version must be an integer")
        version_field = candidate

    if version_in_path is not None and version_field is not None and version_in_path != version_field:
        raise ValueError(
            f"Conflicting version at {path}: path version {version_in_path} "
            f"vs field version {version_field}."
        )

    version = version_in_path if version_in_path is not None else version_field
    dep_type = DependencyType.HARD if version is not None else DependencyType.SOFT

    return DppReference(
        subject_type=subject_type,
        dpp_id=dpp_id,
        version=version,
        dependency_type=dep_type,
        original_ref=raw_ref,
        json_path=path,
    )
