"""Deterministic graph generation for resolve measurements."""

from collections import deque
from collections.abc import Sequence

from .models import BenchmarkNode, PlatformInfo


def reference_count(fanout: int, depth: int) -> int:
    """Return the number of non-root nodes in a full fan-out/depth tree."""
    if fanout < 1:
        raise ValueError("fanout must be >= 1")
    if depth < 1:
        raise ValueError("depth must be >= 1")
    if fanout == 1:
        return depth
    return sum(fanout**level for level in range(1, depth + 1))


def generate_resolve_tree(
    *,
    fanout: int,
    depth: int,
    platforms: Sequence[PlatformInfo],
    run_id: str,
) -> list[BenchmarkNode]:
    """Generate a deterministic hard-reference tree in breadth-first order."""
    if not platforms:
        raise ValueError("at least one platform is required")
    reference_count(fanout, depth)

    platform_count = len(platforms)
    mutable_nodes: list[dict[str, object]] = []
    queue: deque[int] = deque()

    def node_id(index: int, platform: PlatformInfo) -> str:
        suffix = "root" if index == 0 else f"n{index:06d}"
        return f"{platform.issuer_id}-bench-resolve-{run_id}-f{fanout}-d{depth}-{suffix}"

    root_platform = platforms[0]
    mutable_nodes.append(
        {
            "node_id": node_id(0, root_platform),
            "platform_index": 0,
            "depth": 0,
            "children": [],
        }
    )
    queue.append(0)

    while queue:
        parent_index = queue.popleft()
        parent = mutable_nodes[parent_index]
        parent_depth = int(parent["depth"])
        if parent_depth >= depth:
            continue

        for _ in range(fanout):
            child_index = len(mutable_nodes)
            platform_index = child_index % platform_count
            if platform_count > 1 and platform_index == int(parent["platform_index"]):
                platform_index = (platform_index + 1) % platform_count
            platform = platforms[platform_index]
            child = {
                "node_id": node_id(child_index, platform),
                "platform_index": platform_index,
                "depth": parent_depth + 1,
                "children": [],
            }
            mutable_nodes.append(child)
            children = parent["children"]
            if isinstance(children, list):
                children.append(child["node_id"])
            queue.append(child_index)

    nodes: list[BenchmarkNode] = []
    for raw in mutable_nodes:
        platform_index = int(raw["platform_index"])
        platform = platforms[platform_index]
        children = raw["children"]
        nodes.append(
            BenchmarkNode(
                node_id=str(raw["node_id"]),
                subject_type=f"bench-resolve-{run_id}-type-{platform_index}",
                issuer_id=platform.issuer_id,
                platform_id=platform.platform_id,
                depth=int(raw["depth"]),
                children=tuple(children) if isinstance(children, list) else (),
            )
        )

    return nodes

