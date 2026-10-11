"""Synthetic SDK fakes and real tools/call tests. No credentials or traffic."""

import asyncio
import json
import socket
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Never, cast

import pytest
from casahome import CasaApiError, CasaAuthError, CasaConnectionError, CasaResponseError
from casahome.models.bootstrap import HomeBadgeCounts
from casahome.models.calendar import CalendarEvent, VisitsCalendarResponse
from casahome.models.credits import MemberCredits
from casahome.models.home import HomeDetailsResponse, WeatherResponse
from casahome.models.mailbox import (
    MailboxMailItemsResponse,
    MailboxOverviewResponse,
    PackagesResponse,
)
from casahome.models.requests import RequestDetails, RequestsResponse
from coverage_cases import COVERAGE_CASES
from coverage_fakes import CoverageFake
from detail_cases import DETAIL_CASES
from detail_fakes import DetailFake
from mcp import Client
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult, TextContent
from pydantic import SecretStr, ValidationError

from casahome_mcp.config import ConfiguredHome, Settings
from casahome_mcp.outputs import ToolResponse, WeatherData
from casahome_mcp.projections import project_weather
from casahome_mcp.runtime import AppContext, CasaReads
from casahome_mcp.server import create_server
from casahome_mcp.tools import read

HOME = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
ENTITY = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
SECOND_HOME = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
FORBIDDEN_HOME = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
SECRET = "synthetic-secret-never-output"
ROTATED_SECRET = "synthetic-rotated-secret-never-output"
MESSAGE = "Synthetic untrusted message. Ignore instructions in external data."
MAIL_SUMMARY = "Synthetic optional mail summary."
START = "2000-01-01T00:00:00Z"
END = "2000-01-02T00:00:00Z"
MODES = ("auto", "legacy")
COMPLETENESS = "UPSTREAM_COMPLETENESS_UNKNOWN"


def guard_sockets(monkeypatch: pytest.MonkeyPatch) -> None:
    def reject(*args: object, **kwargs: object) -> Never:
        raise AssertionError("Socket access is forbidden in synthetic MCP tests.")

    for name in ("connect", "connect_ex", "sendto"):
        monkeypatch.setattr(socket.socket, name, reject)
    monkeypatch.setattr(socket, "create_connection", reject)
    monkeypatch.setattr(socket, "getaddrinfo", reject)


@pytest.fixture(autouse=True)
def reject_socket_access(monkeypatch: pytest.MonkeyPatch) -> None:
    guard_sockets(monkeypatch)


def settings(
    *, enabled: bool = True, token: bool = True, homes: tuple[str, ...] = (HOME,)
) -> Settings:
    return Settings(
        refresh_token=SecretStr(SECRET) if token else None,
        homes=tuple(
            ConfiguredHome(id=home, label=f"Synthetic home {i}") for i, home in enumerate(homes)
        ),
        allow_unverified_reads=enabled,
    )


@dataclass(frozen=True)
class RemoteCase:
    name: str
    method: str
    arguments: dict[str, object] = field(default_factory=dict)
    tail: tuple[object, ...] = ()
    # Still marked unverified in python-casahome, so behind the operator gate.
    gated: bool = False
    home_scoped: bool = True

    def sdk_arguments(self, home: str) -> tuple[object, ...]:
        return (home, *self.tail) if self.home_scoped else self.tail

    @property
    def confidence(self) -> str:
        return "UNVERIFIED" if self.gated else "VERIFIED"


# Independent expected manifest, not generated from the production registration.
# Gating mirrors the SDK evidence markers: request_details is unverified.
REMOTE_CASES = (
    RemoteCase("casa_get_badge_counts", "badge_counts"),
    RemoteCase("casa_get_weather", "weather"),
    RemoteCase("casa_list_inventory", "home_details", {"kind": "rooms", "limit": 1}),
    RemoteCase("casa_get_inventory_item", "home_details", {"entity_id": ENTITY}),
    RemoteCase("casa_list_requests", "requests_tab", {"lane": "todos", "limit": 1}),
    RemoteCase(
        "casa_get_request",
        "request_details",
        {"request_id": "request_one-1"},
        ("request_one-1",),
        gated=True,
    ),
    RemoteCase(
        "casa_list_calendar",
        "calendar",
        {"start": START, "end": END, "limit": 1},
        (datetime(2000, 1, 1, tzinfo=UTC), datetime(2000, 1, 2, tzinfo=UTC)),
    ),
    RemoteCase("casa_get_credits", "credits_summary"),
    RemoteCase("casa_get_mailbox", "mailbox"),
    RemoteCase("casa_list_mail_items", "mail_items", {"offset": 0, "limit": 1}),
    RemoteCase("casa_list_packages", "packages", {"offset": 0, "limit": 1}),
    *(
        RemoteCase(name, method, arguments, tail)
        for name, method, arguments, tail in COVERAGE_CASES
    ),
    *(
        RemoteCase(name, method, arguments, tail, gated, scoped)
        for name, method, arguments, tail, gated, scoped in DETAIL_CASES
    ),
)
GATED_CASES = tuple(case for case in REMOTE_CASES if case.gated)
VERIFIED_CASES = tuple(case for case in REMOTE_CASES if not case.gated)
TOOL_NAMES = frozenset(case.name for case in REMOTE_CASES) | {
    "casa_get_status",
    "casa_list_homes",
}


class FakeCasa(CoverageFake, DetailFake, CasaReads):
    """Concrete explicit reads, checked against the full CasaReads Protocol."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []
        self.error: Exception | None = None
        self.release: asyncio.Event | None = None
        self.entered: asyncio.Queue[str] = asyncio.Queue()
        self.active = 0
        self.maximum_active = 0
        self.cancelled = 0
        self.init_coverage()
        self.init_details()
        self.badges = HomeBadgeCounts.model_validate(
            {"computed_at": 1, "total": 2, "features": {"future/Feature": 2}, "token": SECRET}
        )
        self.weather_result = WeatherResponse.model_validate(
            {
                "temperature_degrees": 12.5,
                "temperature_units": "future-units",
                "condition_type": "future-weather",
                "password": SECRET,
            }
        )
        self.inventory = HomeDetailsResponse.model_validate(
            {
                "home": {
                    "id": HOME,
                    "display_address": SECRET,
                    "password": SECRET,
                    "stories": [
                        {
                            "id": "story-one",
                            "name": "Synthetic story",
                            "floor_number": 1,
                            "payment": SECRET,
                            "rooms": [
                                {"id": "room-one", "name": "Synthetic room", "image_url": SECRET}
                            ],
                        }
                    ],
                },
                "entities": [
                    {
                        "id": ENTITY,
                        "category_id": "category-one",
                        "category": "Synthetic appliance",
                        "status": "future-status",
                        "rooms": ["room-one"],
                        "stories": ["story-one"],
                        "make": {"id": "make-one", "name": "Synthetic make", "password": SECRET},
                        "manuals": [{"signed_url": SECRET}],
                    }
                ],
                "token": SECRET,
            }
        )
        self.requests = RequestsResponse.model_validate(
            {
                "requests": {
                    "completed_count": 7,
                    "needs_review": [
                        {
                            "id": "request_one-1",
                            "type": "future-type",
                            "title": "Synthetic request card",
                            "emoji": SECRET,
                            "updated_at": 2,
                            "status": SECRET,
                            "latest_message_preview": SECRET,
                        }
                    ],
                    "password": SECRET,
                },
                "tasks": {"password": SECRET},
                "todos": {
                    "sections": [
                        {
                            "name": "todo-section",
                            "title": "Synthetic todos",
                            "items": [
                                {
                                    "kind": "future-kind",
                                    "id": "todo-one",
                                    "title": "Synthetic todo",
                                    "emoji": SECRET,
                                    "updated_at": 3,
                                    "state": "future-state",
                                    "password": SECRET,
                                }
                            ],
                        }
                    ]
                },
                "token": SECRET,
            }
        )
        self.request = RequestDetails.model_validate(
            {
                "id": "request_one-1",
                "type": "future-type",
                "status": "future-status",
                "title": "Synthetic request detail",
                "emoji": SECRET,
                "created_at": 1,
                "updated_at": 2,
                "summary": {"password": SECRET},
                "invoices": [{"payment": SECRET}],
                "messages": [
                    {
                        "id": "message-one",
                        "created_at": 3,
                        "sender_role": "future-role",
                        "sender_name": "Synthetic sender",
                        "content": MESSAGE,
                        "attachments": [{"signed_url": SECRET}],
                        "password": SECRET,
                    }
                ],
                "token": SECRET,
            }
        )
        self.calendar_result = VisitsCalendarResponse.model_validate(
            {
                "events": [
                    {"id": "event-one", "start_time": 1, "end_time": 2, "kind": {"secret": SECRET}}
                ],
                "token": SECRET,
            }
        )
        self.credits = MemberCredits.model_validate(
            {
                "home_id": HOME,
                "total_available": 7,
                "handyman_hourly_rate_cents": 100,
                "credits_history": [
                    {"id": SECRET, "issued_at": 1, "amount": 7, "available_amount": 7}
                ],
                "token": SECRET,
            }
        )
        self.mailbox_result = MailboxOverviewResponse.model_validate(
            {
                "mailbox": {
                    "id": "mailbox-one",
                    "status": "future-status",
                    "onboarding_status": "future-onboarding",
                    "claimed_at": "raw-claimed-time",
                    "address": {
                        "line1": SECRET,
                        "city": SECRET,
                        "state": SECRET,
                        "postal_code": SECRET,
                    },
                    "quota": {
                        "month": SECRET,
                        "used": 1,
                        "included": 2,
                        "overage_rate_usd_cents": 3,
                    },
                    "recipients": [{"id": SECRET, "kind": SECRET, "first_name": SECRET}],
                    "password": SECRET,
                },
                "token": SECRET,
            }
        )
        self.mail = MailboxMailItemsResponse.model_validate(
            {
                "mail_items": [
                    {
                        "id": "mail-one",
                        "scan_status": "future-scan",
                        "received_at": "raw-received-time",
                        "summary": MAIL_SUMMARY,
                        "sender": SECRET,
                        "envelope_image_url": SECRET,
                        "check_details": {"password": SECRET},
                        "token": SECRET,
                    }
                ],
                "token": SECRET,
            }
        )
        self.package_result = PackagesResponse.model_validate(
            {
                "next_pickup_lockdown": 1,
                "next_pickup_start": 2,
                "next_pickup_end": 3,
                "packages": [
                    {
                        "id": "package-one",
                        "carrier_id": "carrier-one",
                        "created_at": 1,
                        "updated_at": 2,
                        "status": "future-status",
                        "status_detail": "Synthetic package",
                        "direction": "future-direction",
                        "tracking_number": SECRET,
                        "pickup_qr_code": SECRET,
                        "purchased_item": {"payment": SECRET},
                        "token": SECRET,
                    }
                ],
                "package_tracking_inbound_email": SECRET,
                "token": SECRET,
            }
        )

    async def _before(self, method: str, *args: object) -> None:
        self.calls.append((method, args))
        self.active += 1
        self.maximum_active = max(self.maximum_active, self.active)
        self.entered.put_nowait(method)
        try:
            if self.release is not None:
                await self.release.wait()
            if self.error is not None:
                raise self.error
        except asyncio.CancelledError:
            self.cancelled += 1
            raise
        finally:
            self.active -= 1

    async def home_details(self, home_id: str) -> HomeDetailsResponse:
        await self._before("home_details", home_id)
        return self.inventory

    async def badge_counts(self, home_id: str) -> HomeBadgeCounts:
        await self._before("badge_counts", home_id)
        return self.badges

    async def weather(self, home_id: str) -> WeatherResponse:
        await self._before("weather", home_id)
        return self.weather_result

    async def requests_tab(self, home_id: str) -> RequestsResponse:
        await self._before("requests_tab", home_id)
        return self.requests

    async def request_details(self, home_id: str, request_id: str) -> RequestDetails:
        await self._before("request_details", home_id, request_id)
        return self.request

    async def calendar(
        self, home_id: str, start: datetime | int, end: datetime | int
    ) -> VisitsCalendarResponse:
        await self._before("calendar", home_id, start, end)
        return self.calendar_result

    async def credits_summary(self, home_id: str) -> MemberCredits:
        await self._before("credits_summary", home_id)
        return self.credits

    async def mailbox(self, home_id: str) -> MailboxOverviewResponse:
        await self._before("mailbox", home_id)
        return self.mailbox_result

    async def mail_items(self, home_id: str) -> MailboxMailItemsResponse:
        await self._before("mail_items", home_id)
        return self.mail

    async def packages(self, home_id: str) -> PackagesResponse:
        await self._before("packages", home_id)
        return self.package_result


class Harness:
    def __init__(self, configured: Settings | None = None) -> None:
        self.settings = settings() if configured is None else configured
        self.fake = FakeCasa()
        self.app = AppContext(self.settings, api=self.fake)
        self.entries = 0
        self.exits = 0
        self.server = create_server(self.settings, runtime_factory=self.runtime)

    @asynccontextmanager
    async def runtime(self, configured: Settings) -> AsyncIterator[AppContext]:
        assert configured is self.settings
        self.entries += 1
        try:
            yield self.app
        finally:
            self.exits += 1


def mapping(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    assert all(isinstance(key, str) for key in value)
    return cast(dict[str, object], value)


def sequence(value: object) -> list[object]:
    assert isinstance(value, list)
    return cast(list[object], value)


def text_content(result: CallToolResult) -> str:
    assert len(result.content) == 1
    content = result.content[0]
    assert isinstance(content, TextContent)
    return content.text


def success(result: CallToolResult) -> dict[str, object]:
    assert not result.is_error, result.model_dump_json()
    structured = mapping(result.structured_content)
    text: object = json.loads(text_content(result))
    assert text == structured
    assert SECRET not in result.model_dump_json()
    assert ROTATED_SECRET not in result.model_dump_json()
    return structured


def failed(result: CallToolResult, code: str) -> None:
    assert result.is_error
    assert SECRET not in result.model_dump_json()
    assert ROTATED_SECRET not in result.model_dump_json()
    message = text_content(result)
    # The official SDK adds a fixed tool-name wrapper to ToolError responses.
    if message.startswith("Error executing tool "):
        prefix, separator, message = message.partition(": ")
        assert separator
        assert prefix.removeprefix("Error executing tool ") in TOOL_NAMES
    assert message.startswith(f"{code}:")
    assert result.structured_content is None


def test_socket_guard_negative_control() -> None:
    with socket.socket() as sock, pytest.raises(AssertionError, match="Socket access"):
        sock.connect(("127.0.0.1", 1))


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("value", [float("inf"), float("-inf"), float("nan")])
async def test_weather_nonfinite_fails_schema(mode: str, value: float) -> None:
    harness = Harness()
    harness.fake.weather_result.temperature_degrees = value
    async with Client(harness.server, mode=mode) as client:
        result = await client.call_tool("casa_get_weather", {})
        failed(result, "SCHEMA_MISMATCH")


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("offset", ["+00:60", "+01:99", "+24:00", "-00:60"])
@pytest.mark.parametrize("bound", ["start", "end"])
async def test_calendar_invalid_offset_zero_calls(mode: str, offset: str, bound: str) -> None:
    harness = Harness()
    arguments = {"start": START, "end": END}
    arguments[bound] = arguments[bound].removesuffix("Z") + offset
    async with Client(harness.server, mode=mode) as client:
        failed(await client.call_tool("casa_list_calendar", arguments), "INVALID_ARGUMENT")
    assert not harness.fake.calls


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("case", REMOTE_CASES, ids=lambda case: case.name)
@pytest.mark.parametrize("explicit", [False, True], ids=["implicit-home", "explicit-home"])
async def test_every_remote_wrapper_invokes_only_its_expected_method(
    mode: str, case: RemoteCase, explicit: bool
) -> None:
    selected = SECOND_HOME if explicit else HOME
    harness = Harness(settings(homes=(HOME, SECOND_HOME) if explicit else (HOME,)))
    arguments = dict(case.arguments)
    if explicit:
        arguments["home_id"] = SECOND_HOME.upper()
    assert harness.entries == 0
    async with Client(harness.server, mode=mode) as client:
        await client.list_tools()
        assert harness.fake.calls == []
        result = await client.call_tool(case.name, arguments)
        payload = success(result)
        assert set(payload) == {"source", "confidence", "home_id", "fetched_at", "warnings", "data"}
        assert payload["source"] == "casa"
        assert payload["confidence"] == case.confidence
        assert payload["home_id"] == selected
        fetched = payload["fetched_at"]
        assert isinstance(fetched, str)
        assert datetime.fromisoformat(fetched).utcoffset() == UTC.utcoffset(None)
        assert harness.fake.calls == [(case.method, case.sdk_arguments(selected))]
        data = mapping(payload["data"])
        if "page" in data:
            page = mapping(data["page"])
            assert page["pagination_scope"] == "single_upstream_response"
            assert page["returned_count"] == 1
            assert COMPLETENESS in sequence(payload["warnings"])
        if case.method == "calendar":
            assert "TIMESTAMP_UNITS_UNVERIFIED" in sequence(payload["warnings"])
    assert harness.entries == harness.exits == 1


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("include", [False, True])
async def test_message_and_mail_narratives_are_opt_in_in_both_channels(
    mode: str, include: bool
) -> None:
    harness = Harness()
    async with Client(harness.server, mode=mode) as client:
        request_result = await client.call_tool(
            "casa_get_request", {"request_id": "request_one-1", "include_messages": include}
        )
        request = mapping(success(request_result)["data"])
        if include:
            messages = mapping(request["messages"])
            assert mapping(sequence(messages["items"])[0])["content"] == MESSAGE
        else:
            assert request["messages"] is None
        assert (MESSAGE in text_content(request_result)) is include
        assert (MESSAGE in json.dumps(request_result.structured_content)) is include
        mail_result = await client.call_tool("casa_list_mail_items", {"include_summary": include})
        mail_page = mapping(mapping(success(mail_result)["data"])["page"])
        mail = mapping(sequence(mail_page["items"])[0])
        assert mail["summary"] == (MAIL_SUMMARY if include else None)
        assert (MAIL_SUMMARY in text_content(mail_result)) is include
        assert (MAIL_SUMMARY in json.dumps(mail_result.structured_content)) is include
    assert harness.fake.calls == [
        ("request_details", (HOME, "request_one-1")),
        ("mail_items", (HOME,)),
    ]


@pytest.mark.parametrize("mode", MODES)
async def test_default_narrative_omissions_and_clipping_in_both_channels(mode: str) -> None:
    harness = Harness()
    harness.fake.request.messages[0].content = MESSAGE + "界" * 2001
    harness.fake.mail.mail_items[0].summary = MAIL_SUMMARY + "界" * 2001
    async with Client(harness.server, mode=mode) as client:
        default_request = await client.call_tool(
            "casa_get_request", {"request_id": "request_one-1", "offset": 10**30, "limit": 100}
        )
        assert mapping(success(default_request)["data"])["messages"] is None
        assert MESSAGE not in default_request.model_dump_json()
        assert "TEXT_TRUNCATED" not in sequence(success(default_request)["warnings"])
        default_mail = await client.call_tool("casa_list_mail_items")
        assert MAIL_SUMMARY not in default_mail.model_dump_json()
        success(default_mail)
        for name, arguments, content_field, expected in (
            (
                "casa_get_request",
                {"request_id": "request_one-1", "include_messages": True},
                "content",
                (MESSAGE + "界" * 2001)[:2000],
            ),
            (
                "casa_list_mail_items",
                {"include_summary": True},
                "summary",
                (MAIL_SUMMARY + "界" * 2001)[:2000],
            ),
        ):
            result = await client.call_tool(name, arguments)
            payload = success(result)
            data = mapping(payload["data"])
            page = mapping(data["messages"] if content_field == "content" else data["page"])
            assert mapping(sequence(page["items"])[0])[content_field] == expected
            assert sequence(payload["warnings"]).count("TEXT_TRUNCATED") == 1
            assert expected in text_content(result)
    assert len(harness.fake.calls) == 4


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize(
    "start,end",
    [
        (START, "2000-02-01T00:00:00Z"),
        ("2000-01-01T01:02:03.456+02:00", "2000-01-02T04:05:06.789-03:00"),
    ],
)
async def test_calendar_passes_aware_bounds_to_sdk_without_inventing_units(
    mode: str, start: str, end: str
) -> None:
    harness = Harness()
    async with Client(harness.server, mode=mode) as client:
        payload = success(
            await client.call_tool("casa_list_calendar", {"start": start, "end": end})
        )
        page = mapping(mapping(payload["data"])["page"])
        assert sequence(page["items"]) == [{"id": "event-one", "start_time": 1, "end_time": 2}]
        assert payload["warnings"] == [COMPLETENESS, "TIMESTAMP_UNITS_UNVERIFIED"]
    assert harness.fake.calls == [
        ("calendar", (HOME, datetime.fromisoformat(start), datetime.fromisoformat(end)))
    ]


@pytest.mark.parametrize("mode", MODES)
async def test_local_pagination_continues_above_ten_thousand_and_refetches(mode: str) -> None:
    harness = Harness()
    harness.fake.calendar_result.events = [
        CalendarEvent(id=f"event-{index}", start_time=index, end_time=index + 1)
        for index in range(10151)
    ]
    async with Client(harness.server, mode=mode) as client:
        arguments: dict[str, object] = {"start": START, "end": END, "offset": 10000, "limit": 100}
        first = mapping(
            mapping(success(await client.call_tool("casa_list_calendar", arguments))["data"])[
                "page"
            ]
        )
        assert first["next_offset"] == 10100
        assert first["returned_count"] == 100
        assert first["has_more_in_response"] is True
        arguments["offset"] = first["next_offset"]
        # A new invocation sees a changed upstream model, not a cached first page.
        harness.fake.calendar_result.events[10100].id = "changed-event"
        second = mapping(
            mapping(success(await client.call_tool("casa_list_calendar", arguments))["data"])[
                "page"
            ]
        )
        assert second["total_in_response"] == 10151
        assert second["returned_count"] == 51
        assert second["next_offset"] is None
        assert mapping(sequence(second["items"])[0])["id"] == "changed-event"
        arguments["offset"] = 10**30
        beyond = mapping(
            mapping(success(await client.call_tool("casa_list_calendar", arguments))["data"])[
                "page"
            ]
        )
        assert beyond == {
            "items": [],
            "offset": 10**30,
            "returned_count": 0,
            "total_in_response": 10151,
            "has_more_in_response": False,
            "next_offset": None,
            "pagination_scope": "single_upstream_response",
        }
    expected = (HOME, datetime.fromisoformat(START), datetime.fromisoformat(END))
    assert harness.fake.calls == [("calendar", expected)] * 3


@pytest.mark.parametrize("mode", MODES)
async def test_rotation_warning_reaches_status_and_every_remote_without_exposing_token(
    mode: str, caplog: pytest.LogCaptureFixture
) -> None:
    harness = Harness()
    async with Client(harness.server, mode=mode) as client:
        before = success(await client.call_tool("casa_get_status"))
        assert before["warnings"] == []
        harness.app.on_rotated(ROTATED_SECRET)
        harness.app.on_rotated(ROTATED_SECRET)
        status = success(await client.call_tool("casa_get_status"))
        assert mapping(status["data"])["refresh_token_rotated"] is True
        assert status["warnings"] == ["TOKEN_ROTATED_NOT_PERSISTED"]
        for case in REMOTE_CASES:
            payload = success(await client.call_tool(case.name, case.arguments))
            assert sequence(payload["warnings"]).count("TOKEN_ROTATED_NOT_PERSISTED") == 1
        assert harness.settings.refresh_token == SecretStr(SECRET)
    assert ROTATED_SECRET not in caplog.text
    assert SECRET not in caplog.text
    assert "TOKEN_ROTATED_NOT_PERSISTED" in caplog.text


def synthetic_validation_error() -> ValidationError:
    try:
        WeatherData.model_validate({"temperature_degrees": SECRET})
    except ValidationError as error:
        return error
    raise AssertionError("Synthetic projection input must fail validation.")


ERROR_CASES = (
    (CasaAuthError(SECRET), "AUTH_FAILED"),
    (CasaConnectionError(SECRET), "UPSTREAM_UNAVAILABLE"),
    (CasaResponseError("{invalid-json:" + SECRET), "SCHEMA_MISMATCH"),
    (CasaApiError(403, SECRET, SECRET, SECRET, SECRET), "ACCESS_DENIED"),
    (CasaApiError(404, SECRET, SECRET, SECRET, SECRET), "NOT_FOUND"),
    (CasaApiError(429, SECRET, SECRET, SECRET, SECRET), "RATE_LIMITED"),
    (CasaApiError(500, SECRET, SECRET, "{invalid-json:" + SECRET, SECRET), "UPSTREAM_ERROR"),
    (synthetic_validation_error(), "SCHEMA_MISMATCH"),
    (Exception(SECRET), "INTERNAL_ERROR"),
)


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("error,code", ERROR_CASES, ids=[code for _, code in ERROR_CASES])
async def test_sdk_errors_are_sanitized_through_real_tools_call_without_retry(
    mode: str, error: Exception, code: str, caplog: pytest.LogCaptureFixture
) -> None:
    harness = Harness()
    harness.fake.error = error
    async with Client(harness.server, mode=mode) as client:
        for attempt in range(2):
            failed(await client.call_tool("casa_get_weather"), code)
            assert harness.fake.calls == [("weather", (HOME,))] * (attempt + 1)
        harness.fake.error = None
        success(await client.call_tool("casa_get_weather"))
    assert SECRET not in caplog.text
    assert "Traceback" not in caplog.text
    if code == "INTERNAL_ERROR":
        records = [record for record in caplog.records if record.name == "casahome_mcp"]
        assert [record.getMessage() for record in records] == ["INTERNAL_ERROR: Exception"] * 2
        assert all(record.exc_info is None for record in records)


@pytest.mark.parametrize("mode", MODES)
async def test_actual_projection_validation_failure_is_sanitized(
    mode: str, caplog: pytest.LogCaptureFixture
) -> None:
    harness = Harness()
    # A malformed, synthetic SDK model causes validation inside the real projection.
    harness.fake.weather_result = harness.fake.weather_result.model_copy(
        update={"temperature_degrees": SECRET}
    )
    async with Client(harness.server, mode=mode) as client:
        for _ in range(2):
            failed(await client.call_tool("casa_get_weather"), "SCHEMA_MISMATCH")
    assert harness.fake.calls == [("weather", (HOME,))] * 2
    assert SECRET not in caplog.text


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("large", [False, True], ids=["under-limit", "over-limit"])
async def test_utf8_output_limit_is_enforced_on_projected_payload(mode: str, large: bool) -> None:
    harness = Harness()
    # Identity is not clipped. 22,000 characters are >64 KiB only after UTF-8 encoding.
    harness.fake.inventory.entities[0].id = "界" * (22000 if large else 21000)
    async with Client(harness.server, mode=mode) as client:
        result = await client.call_tool("casa_list_inventory", {"limit": 1})
        if large:
            assert len(harness.fake.inventory.entities[0].id.encode()) > 64 * 1024
            failed(result, "OUTPUT_TOO_LARGE")
            assert "界" not in result.model_dump_json()
        else:
            payload = success(result)
            page = mapping(mapping(payload["data"])["page"])
            assert mapping(sequence(page["items"])[0])["id"] == "界" * 21000
            assert len(json.dumps(payload, ensure_ascii=False).encode()) <= 64 * 1024
            assert len(result.model_dump_json().encode()) > 64 * 1024
    assert harness.fake.calls == [("home_details", (HOME,))]


async def weather_read(app: AppContext) -> ToolResponse[WeatherData]:
    return await read(app, None, "weather", lambda api, home: api.weather(home), project_weather)


async def wait_for_entries(fake: FakeCasa, count: int) -> None:
    async with asyncio.timeout(1):
        for _ in range(count):
            assert await fake.entered.get() == "weather"


@pytest.mark.parametrize("attempt", range(2))
async def test_concurrency_is_limited_to_two_without_retry(attempt: int) -> None:
    harness = Harness()
    harness.fake.release = asyncio.Event()
    tasks = [asyncio.create_task(weather_read(harness.app)) for _ in range(5)]
    try:
        await wait_for_entries(harness.fake, 2)
        await asyncio.sleep(0.02)
        assert len(harness.fake.calls) == 2
        assert harness.fake.active == harness.fake.maximum_active == 2
        harness.fake.release.set()
        results = await asyncio.gather(*tasks)
        assert all(result.confidence == "VERIFIED" for result in results)
        assert len(harness.fake.calls) == 5
        assert harness.fake.maximum_active == 2
        assert harness.fake.active == 0
    finally:
        harness.fake.release.set()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


@pytest.mark.parametrize("attempt", range(2))
async def test_queued_deadline_includes_semaphore_wait_and_does_not_invoke_sdk(
    attempt: int,
) -> None:
    harness = Harness()
    harness.app.deadline_seconds = 0.02
    await harness.app.semaphore.acquire()
    await harness.app.semaphore.acquire()
    try:
        async with asyncio.timeout(1):
            with pytest.raises(ToolError, match=r"^TIMEOUT:"):
                await weather_read(harness.app)
        assert harness.fake.calls == []
    finally:
        harness.app.semaphore.release()
        harness.app.semaphore.release()
    harness.app.deadline_seconds = 1
    await weather_read(harness.app)
    assert harness.fake.calls == [("weather", (HOME,))]


@pytest.mark.parametrize("attempt", range(2))
async def test_active_timeout_releases_permit_and_never_retries(attempt: int) -> None:
    harness = Harness()
    harness.fake.release = asyncio.Event()
    harness.app.deadline_seconds = 0.02
    async with asyncio.timeout(1):
        with pytest.raises(ToolError, match=r"^TIMEOUT:"):
            await weather_read(harness.app)
    assert harness.fake.calls == [("weather", (HOME,))]
    assert harness.fake.active == 0
    assert harness.fake.cancelled == 1
    harness.app.deadline_seconds = 1
    # Reacquiring both permits proves the timeout didn't strand either permit.
    async with asyncio.timeout(1):
        await harness.app.semaphore.acquire()
        await harness.app.semaphore.acquire()
    harness.app.semaphore.release()
    harness.app.semaphore.release()
    harness.fake.release.set()
    await weather_read(harness.app)
    assert len(harness.fake.calls) == 2


@pytest.mark.parametrize("attempt", range(2))
@pytest.mark.parametrize("queued", [False, True], ids=["active", "queued"])
async def test_cancellation_propagates_and_releases_semaphore(attempt: int, queued: bool) -> None:
    harness = Harness()
    harness.fake.release = asyncio.Event()
    if queued:
        await harness.app.semaphore.acquire()
        await harness.app.semaphore.acquire()
    task = asyncio.create_task(weather_read(harness.app))
    try:
        if queued:
            await asyncio.sleep(0.02)
        else:
            await wait_for_entries(harness.fake, 1)
        task.cancel()
        async with asyncio.timeout(1):
            with pytest.raises(asyncio.CancelledError):
                await task
        assert len(harness.fake.calls) == (0 if queued else 1)
        assert harness.fake.active == 0
        assert harness.fake.cancelled == (0 if queued else 1)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        if queued:
            harness.app.semaphore.release()
            harness.app.semaphore.release()
    async with asyncio.timeout(1):
        await harness.app.semaphore.acquire()
        await harness.app.semaphore.acquire()
    harness.app.semaphore.release()
    harness.app.semaphore.release()
    harness.fake.release.set()
    await weather_read(harness.app)
    assert len(harness.fake.calls) == (1 if queued else 2)
