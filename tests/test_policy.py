"""Denied inputs and policy precedence must produce zero fake SDK calls."""

import asyncio

import pytest
from mcp import Client
from mcp.server.mcpserver.exceptions import ToolError
from test_tools import (
    END,
    FORBIDDEN_HOME,
    HOME,
    MODES,
    REMOTE_CASES,
    SECOND_HOME,
    SECRET,
    START,
    Harness,
    RemoteCase,
    failed,
    guard_sockets,
    settings,
)

from casahome_mcp.config import Settings
from casahome_mcp.projections import project_weather
from casahome_mcp.tools import READ_METHODS, read


@pytest.fixture(autouse=True)
def reject_socket_access(monkeypatch: pytest.MonkeyPatch) -> None:
    guard_sockets(monkeypatch)


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("case", REMOTE_CASES, ids=lambda case: case.name)
@pytest.mark.parametrize("token", [False, True])
async def test_every_remote_is_disabled_by_default_even_without_credentials(
    mode: str, case: RemoteCase, token: bool
) -> None:
    # Use the actual Settings default rather than a separately supplied False flag.
    supplied = settings(token=token)
    configured = Settings(homes=supplied.homes, refresh_token=supplied.refresh_token)
    assert not configured.allow_unverified_reads
    harness = Harness(configured)
    if not token:
        harness.app.api = None
    async with Client(harness.server, mode=mode) as client:
        result = await client.call_tool(case.name, case.arguments)
        failed(result, "UNVERIFIED_DISABLED")
        assert "CASA_ALLOW_UNVERIFIED_READS" in result.model_dump_json()
        assert harness.fake.calls == []


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("case", REMOTE_CASES, ids=lambda case: case.name)
@pytest.mark.parametrize(
    "homes,explicit,enabled,token,api_present,code",
    [
        ((), None, False, False, False, "NO_HOMES_CONFIGURED"),
        ((), None, True, True, True, "NO_HOMES_CONFIGURED"),
        ((HOME, SECOND_HOME), None, False, False, False, "HOME_REQUIRED"),
        ((HOME, SECOND_HOME), None, True, True, True, "HOME_REQUIRED"),
        ((HOME,), FORBIDDEN_HOME, False, False, False, "HOME_NOT_ALLOWED"),
        ((HOME,), FORBIDDEN_HOME, True, True, True, "HOME_NOT_ALLOWED"),
        ((HOME,), None, False, False, False, "UNVERIFIED_DISABLED"),
        ((HOME,), None, True, False, True, "AUTH_NOT_CONFIGURED"),
        ((HOME,), None, True, True, False, "AUTH_NOT_CONFIGURED"),
    ],
)
async def test_home_then_gate_then_credentials_precedence_without_sdk_access(
    mode: str,
    case: RemoteCase,
    homes: tuple[str, ...],
    explicit: str | None,
    enabled: bool,
    token: bool,
    api_present: bool,
    code: str,
) -> None:
    harness = Harness(settings(homes=homes, enabled=enabled, token=token))
    if not api_present:
        harness.app.api = None
    arguments = dict(case.arguments)
    if explicit is not None:
        arguments["home_id"] = explicit
    async with Client(harness.server, mode=mode) as client:
        for _ in range(2):
            failed(await client.call_tool(case.name, arguments), code)
        assert harness.fake.calls == []


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("case", REMOTE_CASES, ids=lambda case: case.name)
@pytest.mark.parametrize("enabled", [False, True])
async def test_unknown_arguments_cannot_bypass_operator_gate(
    mode: str, case: RemoteCase, enabled: bool, caplog: pytest.LogCaptureFixture
) -> None:
    harness = Harness(settings(enabled=enabled))
    async with Client(harness.server, mode=mode) as client:
        for key, value in (
            ("allow_unverified", True),
            ("allow_unverified_reads", True),
            ("ctx", SECRET),
            ("refresh_token", SECRET),
            ("base_url", SECRET),
            ("unknown", {"password": SECRET}),
        ):
            failed(
                await client.call_tool(case.name, {**case.arguments, key: value}),
                "INVALID_ARGUMENT",
            )
        assert harness.fake.calls == []
    assert SECRET not in caplog.text


INVALID_ARGUMENTS: tuple[tuple[str, dict[str, object]], ...] = (
    ("casa_get_request", {}),
    ("casa_get_request", {"request_id": ""}),
    ("casa_get_request", {"request_id": "x" * 129}),
    ("casa_get_request", {"request_id": "../" + SECRET}),
    ("casa_get_request", {"request_id": "%2f" + SECRET}),
    ("casa_get_request", {"request_id": SECRET + "?token=hidden"}),
    ("casa_get_request", {"request_id": SECRET + "#fragment"}),
    ("casa_get_request", {"request_id": " " + SECRET}),
    ("casa_get_request", {"request_id": "non-ascii-é"}),
    ("casa_get_request", {"request_id": 123}),
    ("casa_get_request", {"request_id": None}),
    ("casa_get_weather", {"home_id": SECRET}),
    ("casa_get_weather", {"home_id": 123}),
    ("casa_get_weather", {"home_id": SECRET * 10}),
    ("casa_list_inventory", {"kind": SECRET}),
    ("casa_list_requests", {"lane": SECRET}),
    ("casa_list_calendar", {}),
    ("casa_list_calendar", {"start": START}),
    ("casa_list_calendar", {"end": END}),
    ("casa_list_calendar", {"start": 123, "end": END}),
    ("casa_list_calendar", {"start": SECRET, "end": END}),
    ("casa_list_calendar", {"start": "2000-01-01", "end": END}),
    ("casa_list_calendar", {"start": "2000-01-01T00:00:00", "end": END}),
    ("casa_list_calendar", {"start": "2000-01-01 00:00:00Z", "end": END}),
    ("casa_list_calendar", {"start": START, "end": START}),
    ("casa_list_calendar", {"start": END, "end": START}),
    ("casa_list_calendar", {"start": START, "end": "2000-02-02T00:00:00Z"}),
    ("casa_list_calendar", {"start": START, "end": "2000-02-01T00:00:00.001Z"}),
    ("casa_list_calendar", {"start": "2000-13-01T00:00:00Z", "end": END}),
    ("casa_list_calendar", {"start": "2000-01-01T00:00:00+24:00", "end": END}),
    ("casa_list_calendar", {"start": START, "end": "2000-01-02T00:00:00"}),
    ("casa_get_status", {"unexpected": SECRET}),
    ("casa_list_homes", {"unexpected": SECRET}),
)


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("name,arguments", INVALID_ARGUMENTS)
async def test_invalid_inputs_win_before_home_gate_and_auth_and_never_leak(
    mode: str,
    enabled: bool,
    name: str,
    arguments: dict[str, object],
    caplog: pytest.LogCaptureFixture,
) -> None:
    # No home or token proves argument validation precedes later policy failures.
    harness = Harness(settings(enabled=enabled, token=False, homes=()))
    harness.app.api = None
    async with Client(harness.server, mode=mode) as client:
        failed(await client.call_tool(name, arguments), "INVALID_ARGUMENT")
        assert harness.fake.calls == []
    assert SECRET not in caplog.text


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("enabled", [False, True])
async def test_newline_request_id_cannot_escape_value_safe_validation(
    mode: str, enabled: bool, caplog: pytest.LogCaptureFixture
) -> None:
    # Python JSON Schema regex permits a final newline before '$'. The SDK's
    # Pydantic validator doesn't. This differential must never expose values.
    harness = Harness(settings(enabled=enabled))
    async with Client(harness.server, mode=mode) as client:
        result = await client.call_tool("casa_get_request", {"request_id": SECRET + "\n"})
    assert harness.fake.calls == []
    assert SECRET not in caplog.text
    failed(result, "INVALID_ARGUMENT")


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize(
    "case", [case for case in REMOTE_CASES if "limit" in case.arguments] + [REMOTE_CASES[4]]
)
async def test_every_paginated_tool_rejects_bad_bounds_and_types_before_fetch(
    mode: str, case: RemoteCase, caplog: pytest.LogCaptureFixture
) -> None:
    harness = Harness()
    async with Client(harness.server, mode=mode) as client:
        for name, value in (
            ("offset", -1),
            ("offset", True),
            ("offset", 1.5),
            ("offset", "1"),
            ("offset", SECRET),
            ("limit", 0),
            ("limit", 101),
            ("limit", False),
            ("limit", 1.5),
            ("limit", "25"),
            ("limit", None),
        ):
            failed(
                await client.call_tool(case.name, {**case.arguments, name: value}),
                "INVALID_ARGUMENT",
            )
        assert harness.fake.calls == []
    assert SECRET not in caplog.text


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize(
    "name,base,field",
    [
        ("casa_get_request", {"request_id": "request_one-1"}, "include_messages"),
        ("casa_list_mail_items", {}, "include_summary"),
    ],
)
async def test_boolean_opt_ins_require_actual_json_booleans(
    mode: str, name: str, base: dict[str, object], field: str, caplog: pytest.LogCaptureFixture
) -> None:
    harness = Harness()
    invalid: tuple[object, ...] = (0, 1, "true", "false", SECRET, None, [], {})
    async with Client(harness.server, mode=mode) as client:
        for value in invalid:
            failed(await client.call_tool(name, {**base, field: value}), "INVALID_ARGUMENT")
        assert harness.fake.calls == []
    assert SECRET not in caplog.text


@pytest.mark.parametrize("mode", MODES)
async def test_unknown_and_write_tool_names_are_refused_without_calls(
    mode: str, caplog: pytest.LogCaptureFixture
) -> None:
    harness = Harness()
    async with Client(harness.server, mode=mode) as client:
        for name in (
            "bootstrap",
            "casa_bootstrap",
            "casa_create_todo",
            "casa_send_message",
            SECRET,
        ):
            failed(await client.call_tool(name, {"password": SECRET}), "INVALID_ARGUMENT")
        assert harness.fake.calls == []
    assert SECRET not in caplog.text


async def test_read_allowlist_cannot_authorize_bootstrap_or_unregistered_writes() -> None:
    assert {case.method for case in REMOTE_CASES} == READ_METHODS
    harness = Harness()
    for method in ("bootstrap", "create_todo", "send_message", "onboarding_details", SECRET):
        async with asyncio.timeout(1):
            with pytest.raises(ToolError, match=r"^INTERNAL_ERROR:"):
                await read(
                    harness.app,
                    None,
                    method,
                    lambda api, home: api.weather(home),
                    project_weather,
                )
        assert harness.fake.calls == []
