import pytest

from workload.clients import DppNotFoundError
from workload.scenarios import s2


class FakeResolver:
    def __init__(self, schemas):
        self.schemas = dict(schemas)
        self.published = []

    async def get_schema(self, subject_type: str, major: int, minor: int) -> dict:
        try:
            return self.schemas[(subject_type, major, minor)]
        except KeyError as exc:
            raise DppNotFoundError("missing") from exc

    async def publish_schema(self, subject_type: str, major: int, minor: int, document: dict) -> None:
        self.published.append((subject_type, major, minor, document))
        self.schemas[(subject_type, major, minor)] = document


@pytest.mark.asyncio
async def test_s2_seed_schema_skips_incompatible_existing_version():
    resolver = FakeResolver({
        ("pv_module", 1, 0): {
            "type": "object",
            "properties": {"workload_s4": {"type": "object"}},
            "required": ["workload_s4"],
        }
    })

    version = await s2._ensure_compatible_seed_schema(resolver, "pv_module")

    assert version.subject_type == "pv_module"
    assert version.major_version == 2
    assert resolver.published[0][:3] == ("pv_module", 2, 0)


@pytest.mark.asyncio
async def test_s2_battery_breaking_schema_uses_next_free_major():
    resolver = FakeResolver({
        ("battery", 1, 0): {
            "type": "object",
            "properties": {"capacity_kwh": {"type": "number"}, "chemistry": {"type": "string"}},
            "required": ["capacity_kwh", "chemistry"],
        },
        ("battery", 2, 0): {"type": "object", "properties": {"other": {"type": "string"}}},
    })

    version = await s2._ensure_battery_schema_with_cell_chemistry(
        resolver,
        s2.DppSchemaVersion(subject_type="battery", major_version=1, minor_version=0),
    )

    assert version.major_version == 3
    published_schema = resolver.schemas[("battery", 3, 0)]
    assert "cell_chemistry" in published_schema["required"]
