import httpx
import pytest
from datetime import datetime

from workload.federation import PlatformInfo, PlatformStatus
from workload.scenarios import s1


def _platform() -> PlatformInfo:
    return PlatformInfo(
        platform_id="platform-c",
        stack="spring-postgres",
        issuer_id="issuerB_s1_successor",
        subject_types=["s1_inverter"],
        external_url="http://platform-c:8080",
        status=PlatformStatus.RUNNING,
        created_at=datetime.now(),
    )


@pytest.mark.asyncio
async def test_wait_for_revision_import_retries_transient_probe(monkeypatch):
    calls = 0
    sleeps: list[float] = []

    async def probe(platform: PlatformInfo) -> bool:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ConnectError("platform still starting")
        return True

    async def sleep(delay_seconds: float) -> None:
        sleeps.append(delay_seconds)

    monkeypatch.setattr(s1, "_supports_revision_import", probe)
    monkeypatch.setattr(s1.asyncio, "sleep", sleep)

    supported = await s1._wait_for_revision_import(_platform(), attempts=2, delay_seconds=0.25)

    assert supported is True
    assert calls == 2
    assert sleeps == [0.25]
