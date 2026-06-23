"""Platform-local query client.

Sends the validated platform-local predicate query to one DPP platform,
measures the call duration, and records the outcome on the supplied
:class:`PlatformQueryResult`. A platform call never raises: all transport,
status, and parse failures are captured as FAILED/TIMEOUT on the result so that
one bad platform cannot fail the whole federated job.
"""

from __future__ import annotations

import httpx
from datetime import datetime, timezone
from pydantic import ValidationError
from typing import Any

from .config import Config
from .models import (
    PlatformCallStatus,
    PlatformMapping,
    PlatformQueryResponse,
    PlatformQueryResult,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _duration_ms(start: datetime, end: datetime) -> int:
    return int((end - start).total_seconds() * 1000)


async def send_predicate_query(
    client: httpx.AsyncClient,
    platform: PlatformMapping,
    body: dict[str, Any],
    config: Config,
    result: PlatformQueryResult,
) -> PlatformQueryResult:
    """Execute the platform-local query and fill ``result`` in place.

    The same ``result`` object is returned for convenience. Its ``status`` is
    set to RUNNING for the duration of the call so that status polling reflects
    progress, then to SUCCESS, FAILED, or TIMEOUT.
    """
    url = f"{platform.base_url.rstrip('/')}{config.platform_query_path}"
    result.status = PlatformCallStatus.RUNNING
    result.started_at = _now()

    try:
        if config.platform_query_method == "GET":
            response = await client.get(url, params=build_predicate_params(body))
        else:
            # Retained only for deployments that deliberately expose a legacy
            # JSON-body endpoint.  Generic Java/Python platforms use GET.
            response = await client.request(config.platform_query_method, url, json=body)
    except httpx.TimeoutException as exc:
        _finish(result, PlatformCallStatus.TIMEOUT, error=f"Platform call timed out: {exc}")
        return result
    except httpx.HTTPError as exc:
        _finish(result, PlatformCallStatus.FAILED, error=f"Platform call failed: {exc}")
        return result

    result.http_status = response.status_code
    if response.is_error:
        _finish(
            result,
            PlatformCallStatus.FAILED,
            error=f"Platform returned HTTP {response.status_code}: {_safe_text(response)}",
        )
        return result

    try:
        payload = response.json()
    except ValueError:
        _finish(result, PlatformCallStatus.FAILED, error="Platform returned invalid JSON")
        return result

    try:
        parsed = PlatformQueryResponse.model_validate(payload)
    except ValidationError as exc:
        _finish(
            result,
            PlatformCallStatus.FAILED,
            error=f"Platform returned an invalid response shape: {exc.error_count()} error(s)",
        )
        return result

    result.response = parsed
    _finish(result, PlatformCallStatus.SUCCESS)
    return result


def _finish(
    result: PlatformQueryResult,
    status: PlatformCallStatus,
    *,
    error: str | None = None,
) -> None:
    result.status = status
    result.error_message = error
    result.finished_at = _now()
    if result.started_at is not None:
        result.duration_ms = _duration_ms(result.started_at, result.finished_at)


def _safe_text(response: httpx.Response) -> str:
    text = response.text or ""
    return text[:500]


def build_predicate_params(body: dict[str, Any]) -> list[tuple[str, str]]:
    """Encode the generic-platform ``@ModelAttribute`` GET contract.

    The Java controller binds camelCase top-level fields and indexed filter
    properties.  Repeating ``filters[i].value`` represents an ``IN`` list.
    This is intentionally the same shape as the Angular QueryService and the
    workload-generator clients.
    """
    params: list[tuple[str, str]] = [
        ("resultMode", _scalar(body["result_mode"])),
        ("executionMode", _scalar(body["execution_mode"])),
        ("subjectType", _scalar(body["subject_type"])),
    ]
    for index, filter_ in enumerate(body.get("filters", [])):
        params.extend([
            (f"filters[{index}].path", _scalar(filter_["path"])),
            (f"filters[{index}].operator", _scalar(filter_["operator"])),
        ])
        value = filter_.get("value")
        if value is None:
            continue
        values = value if isinstance(value, list) else [value]
        params.extend((f"filters[{index}].value", _scalar(item)) for item in values)
    for field in body.get("return_fields") or []:
        params.append(("returnFields", _scalar(field)))
    if body.get("aggregate_path") is not None:
        params.append(("aggregatePath", _scalar(body["aggregate_path"])))
    return params


def _scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)
