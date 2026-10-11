"""Official MCP Client(server) discovery and result contracts in both modes."""

import json

import pytest
from jsonschema import Draft202012Validator
from mcp import Client
from test_tools import (
    HOME,
    MODES,
    REMOTE_CASES,
    TOOL_NAMES,
    Harness,
    guard_sockets,
    mapping,
    sequence,
    settings,
    success,
)

INPUT_FIELDS = {
    "casa_get_status": set(),
    "casa_list_homes": set(),
    "casa_get_badge_counts": {"home_id"},
    "casa_get_weather": {"home_id"},
    "casa_list_inventory": {"home_id", "kind", "offset", "limit"},
    "casa_list_requests": {"home_id", "lane", "offset", "limit"},
    "casa_get_request": {"home_id", "request_id", "include_messages", "offset", "limit"},
    "casa_list_calendar": {"home_id", "start", "end", "offset", "limit"},
    "casa_get_credits": {"home_id"},
    "casa_get_mailbox": {"home_id"},
    "casa_list_mail_items": {"home_id", "include_summary", "offset", "limit"},
    "casa_list_packages": {"home_id", "offset", "limit"},
}
REQUIRED_FIELDS = {
    "casa_get_request": {"request_id"},
    "casa_list_calendar": {"start", "end"},
}


@pytest.fixture(autouse=True)
def reject_socket_access(monkeypatch: pytest.MonkeyPatch) -> None:
    guard_sockets(monkeypatch)


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("enabled", [False, True])
async def test_exact_twelve_tool_manifest_schemas_and_annotations(mode: str, enabled: bool) -> None:
    harness = Harness(settings(enabled=enabled, token=False))
    async with Client(harness.server, mode=mode) as client:
        listing = await client.list_tools()
        assert listing.next_cursor is None
        assert len(listing.tools) == 12
        assert {tool.name for tool in listing.tools} == TOOL_NAMES
        for tool in listing.tools:
            remote = tool.name not in {"casa_get_status", "casa_list_homes"}
            assert tool.description
            if remote:
                assert "Experimental Casa read" in tool.description
                assert "CASA_ALLOW_UNVERIFIED_READS" in tool.description
                assert "UNVERIFIED" in tool.description
            annotations = tool.annotations
            assert annotations is not None
            assert annotations.read_only_hint is True
            assert annotations.destructive_hint is False
            assert annotations.idempotent_hint is True
            assert annotations.open_world_hint is remote
            schema = mapping(tool.input_schema)
            Draft202012Validator.check_schema(schema)
            assert schema["type"] == "object"
            properties = mapping(schema["properties"])
            assert set(properties) == INPUT_FIELDS[tool.name]
            assert set(sequence(schema.get("required", []))) == REQUIRED_FIELDS.get(
                tool.name, set()
            )
            serialized = json.dumps(schema)
            for forbidden in ("ctx", "Context", "refresh_token", "base_url", "allow_unverified"):
                assert forbidden not in serialized
            if remote:
                home = mapping(properties["home_id"])
                assert home["default"] is None
                variants = [mapping(value) for value in sequence(home["anyOf"])]
                assert {value["type"] for value in variants} == {"string", "null"}
                assert (
                    next(value for value in variants if value["type"] == "string")["maxLength"]
                    == 64
                )
            if "offset" in properties:
                offset = mapping(properties["offset"])
                assert offset["type"] == "integer"
                assert offset["minimum"] == 0
                assert offset["default"] == 0
                assert "maximum" not in offset
                limit = mapping(properties["limit"])
                assert limit["type"] == "integer"
                assert limit["minimum"] == 1
                assert limit["maximum"] == 100
                assert limit["default"] == 25
            for name in ("include_messages", "include_summary"):
                if name in properties:
                    boolean = mapping(properties[name])
                    assert boolean["type"] == "boolean"
                    assert boolean["default"] is False
            if "kind" in properties:
                assert mapping(properties["kind"])["enum"] == ["entities", "rooms"]
                assert mapping(properties["kind"])["default"] == "entities"
            if "lane" in properties:
                assert mapping(properties["lane"])["enum"] == ["requests", "todos"]
                assert mapping(properties["lane"])["default"] == "requests"
            if "request_id" in properties:
                assert mapping(properties["request_id"])["pattern"] == r"^[A-Za-z0-9_-]{1,128}$"
            output = mapping(tool.output_schema)
            Draft202012Validator.check_schema(output)
            assert output["type"] == "object"
            assert output["additionalProperties"] is False
            assert set(mapping(output["properties"])) == {
                "source",
                "confidence",
                "home_id",
                "fetched_at",
                "warnings",
                "data",
            }
        assert harness.fake.calls == []
    assert harness.entries == harness.exits == 1


@pytest.mark.parametrize("mode", MODES)
async def test_all_successes_match_advertised_output_schema_and_text(mode: str) -> None:
    harness = Harness()
    async with Client(harness.server, mode=mode) as client:
        listing = await client.list_tools()
        schemas = {tool.name: mapping(tool.output_schema) for tool in listing.tools}
        cases: list[tuple[str, dict[str, object]]] = [
            ("casa_get_status", {}),
            ("casa_list_homes", {}),
        ]
        cases.extend((case.name, case.arguments) for case in REMOTE_CASES)
        for name, arguments in cases:
            result = await client.call_tool(name, arguments)
            payload = success(result)
            Draft202012Validator(schemas[name]).validate(payload)
    assert len(harness.fake.calls) == 10


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("token", [False, True])
@pytest.mark.parametrize("homes", [(), (HOME,)])
async def test_local_tools_never_authenticate_or_discover_homes(
    mode: str, enabled: bool, token: bool, homes: tuple[str, ...]
) -> None:
    harness = Harness(settings(enabled=enabled, token=token, homes=homes))
    async with Client(harness.server, mode=mode) as client:
        await client.list_tools()
        status = success(await client.call_tool("casa_get_status"))
        assert status["source"] == "runtime"
        assert status["confidence"] == "LOCAL"
        assert status["home_id"] is status["fetched_at"] is None
        data = mapping(status["data"])
        assert data["token_configured"] is token
        assert data["configured_home_count"] == len(homes)
        assert data["allow_unverified_reads"] is enabled
        assert data["refresh_token_rotated"] is False
        assert "authenticated" not in data
        disabled = sequence(data["disabled_features"])
        assert set(disabled) == (set() if enabled else {case.name for case in REMOTE_CASES})
        assert len(disabled) == (0 if enabled else 10)
        listed = success(await client.call_tool("casa_list_homes"))
        assert listed["source"] == "configuration"
        assert listed["confidence"] == "LOCAL"
        assert listed["home_id"] is listed["fetched_at"] is None
        assert mapping(listed["data"]) == {
            "homes": [{"id": home, "label": f"Synthetic home {i}"} for i, home in enumerate(homes)]
        }
        assert harness.fake.calls == []
    assert harness.entries == harness.exits == 1
