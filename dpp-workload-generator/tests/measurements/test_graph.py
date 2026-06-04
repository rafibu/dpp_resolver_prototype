from workload.measurements.graph import generate_resolve_tree, reference_count
from workload.measurements.models import PlatformInfo


def _platforms(count: int) -> list[PlatformInfo]:
    return [
        PlatformInfo(
            platform_id=f"platform-{index}",
            issuer_id=f"issuer{index}",
            subject_types=(f"type-{index}",),
            external_url=f"http://platform-{index}",
        )
        for index in range(count)
    ]


def test_reference_count():
    assert reference_count(fanout=1, depth=1) == 1
    assert reference_count(fanout=1, depth=4) == 4
    assert reference_count(fanout=2, depth=1) == 2
    assert reference_count(fanout=2, depth=2) == 6
    assert reference_count(fanout=3, depth=2) == 12


def test_generate_resolve_tree_is_deterministic_full_tree():
    platforms = _platforms(2)

    first = generate_resolve_tree(fanout=2, depth=2, platforms=platforms, run_id="unit")
    second = generate_resolve_tree(fanout=2, depth=2, platforms=platforms, run_id="unit")

    assert first == second
    assert len(first) == 7

    nodes = {node.node_id: node for node in first}
    root = first[0]
    assert root.depth == 0
    assert root.node_id.startswith("issuer0-bench-resolve-unit-f2-d2-root")
    assert len(root.children) == 2

    level_one = [nodes[child_id] for child_id in root.children]
    assert all(len(node.children) == 2 for node in level_one)

    leaves = [node for node in first if node.depth == 2]
    assert len(leaves) == 4
    assert all(node.children == () for node in leaves)

    known_platform_ids = {platform.platform_id for platform in platforms}
    assert all(node.platform_id in known_platform_ids for node in first)
    assert all(child_id in nodes for node in first for child_id in node.children)

