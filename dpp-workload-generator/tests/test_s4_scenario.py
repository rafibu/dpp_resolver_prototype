import httpx
import pytest

from workload.scenarios import s4


@pytest.mark.asyncio
async def test_s4_failure_report_keeps_an_empty_transport_error_actionable(monkeypatch):
    async def fail(*args, **kwargs):
        raise httpx.ReadTimeout("", request=httpx.Request("POST", "http://factory:8000/platforms"))

    monkeypatch.setattr(s4, "run_s4", fail)

    result = await s4.run_s4_scenario(factory_url="http://factory:8000", scale="small")

    assert result.success is False
    assert result.steps[0].error == "ReadTimeout (no detail provided)"
    assert "ReadTimeout (no detail provided)" in result.report_md
