"""Catalog/room prepares, SDK wire parity and narrowly classified private rejections."""

import asyncio
import json
from pathlib import Path
from typing import cast

import pytest
from action_fakes import FakeActions
from casahome import CasaApi, CasaApiError, CasaClient, is_unverified
from casahome.models.entity_publish import RenameRoomRequest, SaveAndPublishEntityRequest
from casahome.writes import VerifiedWritesMixin
from jsonschema import Draft202012Validator
from mcp import Client
from mcp.server.mcpserver.exceptions import ToolError
from test_actions import harness, token
from test_tools import (
    ENTITY,
    HOME,
    MODES,
    SECOND_HOME,
    SECRET,
    failed,
    guard_sockets,
    mapping,
    sequence,
    settings,
    success,
)
from test_workflow_actions import RecordingClient

from casahome_mcp.actions.core import execute
from casahome_mcp.actions.inventory_tools import CATALOG_MATCH_RISK
from casahome_mcp.actions.models import CATALOG_REJECTION_WARNING
from casahome_mcp.actions.policy import (
    ACTION_METHODS,
    UNVERIFIED_CONTRACT_WARNING,
    action_unverified,
    gated_action_tools,
)
from casahome_mcp.actions.store import CONSENT_WARNING
from casahome_mcp.config import Settings
from casahome_mcp.tools import READ_METHODS, TOOL_METHODS

ROOM = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"
ROOM_TYPE = "ffffffff-ffff-4fff-8fff-ffffffffffff"
CATALOG_ERROR = "CATALOG_MODEL_UNVERIFIED"
MAKE_MODEL_TOOL = "casa_prepare_update_entity_make_model"
RENAME_TOOL = "casa_prepare_rename_room"
LEGACY_TOOL = "casa_prepare_update_entity_model"
NAMES = {"make_name": " Élodie Fixture ", "model_name": " O'Fixture Model "}
PUBLISHED = {
    "entity_id": ENTITY,
    "status": "published",
    "make": {"id": HOME, "name": SECRET},
    "model": {"id": SECOND_HOME, "name": SECRET},
    "identity": {"state": "verified", "candidates": [{"password": SECRET}]},
    "url": "https://example.invalid/" + SECRET,
}
CATALOG_CASES: tuple[tuple[str, dict[str, object], dict[str, object]], ...] = (
    (LEGACY_TOOL, {"model_name": NAMES["model_name"]}, {"model": {"name": NAMES["model_name"]}}),
    (MAKE_MODEL_TOOL, {"make_id": HOME.upper()}, {"make": {"id": HOME.upper()}}),
    (MAKE_MODEL_TOOL, {"model_id": SECOND_HOME}, {"model": {"id": SECOND_HOME}}),
    (MAKE_MODEL_TOOL, {"make_name": NAMES["make_name"]}, {"make": {"name": NAMES["make_name"]}}),
    (
        MAKE_MODEL_TOOL,
        {"model_name": NAMES["model_name"]},
        {"model": {"name": NAMES["model_name"]}},
    ),
    (
        MAKE_MODEL_TOOL,
        {"make_id": HOME, "model_id": SECOND_HOME},
        {"make": {"id": HOME}, "model": {"id": SECOND_HOME}},
    ),
    (
        MAKE_MODEL_TOOL,
        {**NAMES},
        {"make": {"name": NAMES["make_name"]}, "model": {"name": NAMES["model_name"]}},
    ),
    (
        MAKE_MODEL_TOOL,
        {"make_id": HOME, "model_name": NAMES["model_name"]},
        {"make": {"id": HOME}, "model": {"name": NAMES["model_name"]}},
    ),
    (
        MAKE_MODEL_TOOL,
        {"make_name": NAMES["make_name"], "model_id": SECOND_HOME},
        {"make": {"name": NAMES["make_name"]}, "model": {"id": SECOND_HOME}},
    ),
)


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    guard_sockets(monkeypatch)


def test_sdk_write_coverage_and_read_manifest_stay_separate() -> None:
    sdk_methods = {name for name, value in vars(VerifiedWritesMixin).items() if callable(value)}
    unexposed = {
        "save_and_publish_entity",
        "claim_mailbox",
        "materialize_todo",
        "create_document_upload_sessions",
        "upload_document_content",
        "create_document",
    }
    assert sdk_methods - ACTION_METHODS == unexposed
    assert len(TOOL_METHODS) == 55 and len(READ_METHODS) == 54
    assert not ACTION_METHODS & READ_METHODS
    readme = (Path(__file__).parents[1] / "README.md").read_text()
    assert "104 tools: 57 read/local tools plus 45 action prepares, execute and cancel." in readme
    for operation in ("update_entity_make_model", "rename_room"):
        assert not is_unverified(getattr(CasaApi, operation))
        assert not action_unverified(operation)
        assert "casa_prepare_" + operation not in gated_action_tools(Settings())


@pytest.mark.parametrize("mode", MODES)
async def test_new_schemas_and_consent_descriptions(mode: str) -> None:
    h = harness()
    async with Client(h.server, mode=mode) as client:
        listing = {item.name: item for item in (await client.list_tools()).tools}
    expected = {
        MAKE_MODEL_TOOL: (
            {"entity_id", "home_id", "make_id", "make_name", "model_id", "model_name"},
            {"entity_id"},
        ),
        RENAME_TOOL: (
            {"room_id", "home_id", "room_type_id", "name"},
            {"room_id", "room_type_id", "name"},
        ),
        LEGACY_TOOL: ({"entity_id", "home_id", "model_name"}, {"entity_id", "model_name"}),
    }
    for name, (fields, required) in expected.items():
        tool = listing[name]
        assert set(tool.input_schema["properties"]) == fields
        assert set(tool.input_schema["required"]) == required
        assert tool.description and CONSENT_WARNING in tool.description
        assert tool.annotations is not None
        assert tool.annotations.read_only_hint is False
        assert tool.annotations.destructive_hint is False
        assert tool.annotations.open_world_hint is False
        assert tool.annotations.idempotent_hint is False
        Draft202012Validator.check_schema(tool.input_schema)
    assert "No room creation" in (listing[RENAME_TOOL].description or "")
    assert "complete rollback" in (listing["casa_execute_action"].description or "")


@pytest.mark.parametrize("mode", MODES)
async def test_sdk_name_boundaries_and_scalar_text_preserve_exact_input(mode: str) -> None:
    h = harness()
    recorder = RecordingClient(PUBLISHED)
    h.app.actions = CasaApi(cast(CasaClient, recorder))
    async with Client(h.server, mode=mode) as client:
        for tool in (LEGACY_TOOL, MAKE_MODEL_TOOL):
            for name in ("x", "界" * 256, "123", "true", '"Quoted"'):
                prepared = success(
                    await client.call_tool(tool, {"entity_id": ENTITY, "model_name": name})
                )
                assert mapping(mapping(prepared["preview"])["model"])["name"] == name
                success(
                    await client.call_tool(
                        "casa_execute_action",
                        {"confirmation_token": token(prepared), "confirmed": True},
                    )
                )
                assert recorder.requests[-1][2] == {"model": {"name": name}, "props": []}
        # The legacy required string isn't union-preprocessed into a null clear.
        prepared = success(
            await client.call_tool(LEGACY_TOOL, {"entity_id": ENTITY, "model_name": "null"})
        )
        assert mapping(mapping(prepared["preview"])["model"])["name"] == "null"
        recorder.response = {"message": SECRET}
        prepared = success(
            await client.call_tool(
                RENAME_TOOL, {"room_id": ROOM, "room_type_id": ROOM_TYPE, "name": "界" * 256}
            )
        )
        success(
            await client.call_tool(
                "casa_execute_action",
                {"confirmation_token": token(prepared), "confirmed": True},
            )
        )
        assert recorder.requests[-1][2] == {"room_type_id": ROOM_TYPE, "name": "界" * 256}


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("tool,arguments,selections", CATALOG_CASES)
async def test_catalog_preview_matches_actual_sdk_wire_and_is_immutable(
    mode: str, tool: str, arguments: dict[str, object], selections: dict[str, object]
) -> None:
    h = harness(messages=False, uploads=False, unverified=False)
    recorder = RecordingClient(PUBLISHED)
    h.app.actions = CasaApi(cast(CasaClient, recorder))
    args = {"entity_id": ENTITY.upper(), **arguments}
    async with Client(h.server, mode=mode) as client:
        prepared = success(await client.call_tool(tool, args))
        assert recorder.requests == []
        assert h.fake.calls == []
        assert prepared["warning"] == CONSENT_WARNING
        preview = mapping(prepared["preview"])
        assert preview == {
            "entity_id": ENTITY.upper(),
            **selections,
            "props": [],
            "risk": CATALOG_MATCH_RISK,
        }
        # Validate against the actual SDK codec too, not a fake duplicate body.
        body = {**selections, "props": []}
        assert (
            SaveAndPublishEntityRequest.model_validate(body).model_dump(exclude_none=True) == body
        )
        args.update({"make_name": "changed", "model_name": "changed"})
        preview["props"] = [{"secret": SECRET}]
        preview["model"] = {"name": "changed"}
        call = {"confirmation_token": token(prepared), "confirmed": False}
        assert (
            success(await client.call_tool("casa_execute_action", call))["outcome"]
            == "NOT_EXECUTED"
        )
        assert recorder.requests == []
        call["confirmed"] = True
        completed = success(await client.call_tool("casa_execute_action", call))
        assert completed["outcome"] == "SUCCEEDED"
        assert completed["operation"] == tool.removeprefix("casa_prepare_")
        assert SECRET not in json.dumps(completed)
        assert recorder.requests == [
            (
                "POST",
                f"/protected/member/home/{HOME}/entity/{ENTITY.upper()}/save_and_publish",
                body,
            )
        ]
        failed(await client.call_tool("casa_execute_action", call), "INVALID_CONFIRMATION")
        assert len(recorder.requests) == 1


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("room_type_id", [ROOM_TYPE.upper(), "type-one", "0", "null", "x" * 128])
async def test_rename_room_preview_is_exact_required_sdk_payload(
    mode: str, room_type_id: str
) -> None:
    h = harness(messages=False, uploads=False, unverified=False)
    recorder = RecordingClient({"message": SECRET})
    h.app.actions = CasaApi(cast(CasaClient, recorder))
    args = {"room_id": ROOM.upper(), "room_type_id": room_type_id, "name": " Élodie Room "}
    async with Client(h.server, mode=mode) as client:
        prepared = success(await client.call_tool(RENAME_TOOL, args))
        preview = mapping(prepared["preview"])
        assert {k: v for k, v in preview.items() if k != "risk"} == args
        assert "room type" in str(preview["risk"])
        body = {"room_type_id": room_type_id, "name": args["name"]}
        assert RenameRoomRequest.model_validate(body).model_dump() == body
        assert recorder.requests == []
        assert h.fake.calls == []
        args["name"] = preview["name"] = "changed"
        call = {"confirmation_token": token(prepared), "confirmed": True}
        completed = success(await client.call_tool("casa_execute_action", call))
        assert completed["outcome"] == "SUCCEEDED"
        assert SECRET not in json.dumps(completed)
        assert recorder.requests == [
            ("PATCH", f"/protected/member/home/{HOME}/room/{ROOM.upper()}", body)
        ]
        failed(await client.call_tool("casa_execute_action", call), "INVALID_CONFIRMATION")


@pytest.mark.parametrize("mode", MODES)
async def test_invalid_selections_and_sdk_name_validation_mint_no_token(
    mode: str, caplog: pytest.LogCaptureFixture
) -> None:
    h = harness(actions=False)
    fake = FakeActions(h.fake)
    h.app.actions = fake
    invalid: list[tuple[str, dict[str, object]]] = [
        (MAKE_MODEL_TOOL, {"entity_id": ENTITY}),
        (MAKE_MODEL_TOOL, {"entity_id": ENTITY, "make_id": HOME, "make_name": SECRET}),
        (MAKE_MODEL_TOOL, {"entity_id": ENTITY, "model_id": HOME, "model_name": SECRET}),
        (
            MAKE_MODEL_TOOL,
            {"entity_id": ENTITY, "make_id": HOME, "make_name": SECRET, "model_id": SECOND_HOME},
        ),
        (MAKE_MODEL_TOOL, {"entity_id": ENTITY, "make_name": "Make", "props": []}),
        (MAKE_MODEL_TOOL, {"entity_id": ENTITY, "make": {"name": SECRET}}),
        (LEGACY_TOOL, {"entity_id": ENTITY, "model_name": "Model", "make_id": HOME}),
        (RENAME_TOOL, {"room_id": ROOM, "name": "Room"}),
        (RENAME_TOOL, {"room_id": ROOM, "room_type_id": ROOM_TYPE}),
        (RENAME_TOOL, {"room_type_id": ROOM_TYPE, "name": "Room"}),
        (RENAME_TOOL, {"room_id": ROOM, "room_type_id": ROOM_TYPE, "name": "Room", "create": True}),
    ]
    invalid_scalars: tuple[object, ...] = (None, [], {}, 1, True)
    for field in ("make_id", "model_id", "make_name", "model_name"):
        invalid.extend(
            (MAKE_MODEL_TOOL, {"entity_id": ENTITY, "make_name": "Make", field: value})
            for value in (*invalid_scalars, "null", "[]", '{"secret":"' + SECRET + '"}')
        )
    for tool, field, base in (
        (LEGACY_TOOL, "model_name", {"entity_id": ENTITY}),
        (MAKE_MODEL_TOOL, "make_name", {"entity_id": ENTITY}),
        (MAKE_MODEL_TOOL, "model_name", {"entity_id": ENTITY}),
        (RENAME_TOOL, "name", {"room_id": ROOM, "room_type_id": ROOM_TYPE}),
    ):
        invalid.extend(
            (tool, {**base, field: value})
            for value in (
                "",
                "   ",
                "界" * 257,
                SECRET + "\n",
                SECRET + "\t",
                SECRET + "\x00",
                SECRET + "\u200b",
                SECRET + "\u202e",
            )
        )
    for field in ("make_id", "model_id"):
        invalid.extend(
            (MAKE_MODEL_TOOL, {"entity_id": ENTITY, field: value})
            for value in (
                "",
                "make-one",
                HOME.replace("-", ""),
                "{" + HOME + "}",
                "123",
                '"' + HOME + '"',
                "../" + SECRET,
                SECRET + "\n",
            )
        )
    for field in ("room_id", "room_type_id", "name"):
        invalid.extend(
            (
                RENAME_TOOL,
                {"room_id": ROOM, "room_type_id": ROOM_TYPE, "name": "Room", field: value},
            )
            for value in (*invalid_scalars, SECRET + "\r", SECRET + "\x7f", SECRET + "\u2028")
        )
    for value in (
        "",
        "x" * 129,
        "a/b",
        "https://example.invalid/" + SECRET,
        "www.example.invalid",
        "type~one",
        "type.one",
        "../" + SECRET,
    ):
        invalid.append((RENAME_TOOL, {"room_id": ROOM, "room_type_id": value, "name": "Room"}))
    async with Client(h.server, mode=mode) as client:
        for tool, arguments in invalid:
            failed(await client.call_tool(tool, arguments), "INVALID_ARGUMENT")
            assert h.app.action_store._pending == {}
    assert fake.calls == h.fake.calls == []
    assert SECRET not in caplog.text


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize(
    "operation", ["update_entity_model", "update_entity_make_model", "rename_room", "delete_todo"]
)
async def test_catalog_rejection_is_narrow_status_only_and_token_consumed(
    mode: str, operation: str, caplog: pytest.LogCaptureFixture
) -> None:
    h = harness()
    fake = FakeActions(h.fake)
    h.app.actions = fake
    arguments: dict[str, object] = (
        {"room_id": ROOM, "room_type_id": ROOM_TYPE, "name": "Room"}
        if operation == "rename_room"
        else {"todo_id": "todo-one"}
        if operation == "delete_todo"
        else {"entity_id": ENTITY, "model_name": "Unknown"}
    )
    errors = [
        CasaApiError(400, CATALOG_ERROR, SECRET, SECRET, SECRET),
        CasaApiError(401, CATALOG_ERROR, SECRET, SECRET, SECRET),
        CasaApiError(403, CATALOG_ERROR, SECRET, SECRET, SECRET),
        CasaApiError(404, CATALOG_ERROR, SECRET, SECRET, SECRET),
        CasaApiError(409, CATALOG_ERROR, SECRET, SECRET, SECRET),
        CasaApiError(500, CATALOG_ERROR, SECRET, SECRET, SECRET),
        CasaApiError(400, CATALOG_ERROR.lower(), SECRET, SECRET, SECRET),
        CasaApiError(400, CATALOG_ERROR + " ", SECRET, SECRET, SECRET),
        CasaApiError(400, SECRET, SECRET, SECRET, SECRET),
        ValueError(CATALOG_ERROR + SECRET),
        TimeoutError(SECRET),
    ]
    async with Client(h.server, mode=mode) as client:
        output_schema = next(
            item.output_schema
            for item in (await client.list_tools()).tools
            if item.name == "casa_execute_action"
        )
        assert output_schema is not None
        for error in errors:
            fake.error = error
            prepared = success(await client.call_tool("casa_prepare_" + operation, arguments))
            call = {"confirmation_token": token(prepared), "confirmed": True}
            completed = success(await client.call_tool("casa_execute_action", call))
            rejected = operation.startswith("update_entity_") and error is errors[0]
            assert completed["outcome"] == ("REJECTED_UNKNOWN_PRODUCT" if rejected else "UNKNOWN")
            assert completed["warning"] == (CATALOG_REJECTION_WARNING if rejected else None)
            Draft202012Validator(output_schema).validate(completed)
            assert SECRET not in json.dumps(completed)
            assert CATALOG_ERROR not in json.dumps(completed)
            failed(await client.call_tool("casa_execute_action", call), "INVALID_CONFIRMATION")
    assert len(fake.calls) == len(errors)
    assert h.fake.calls == []
    assert SECRET not in caplog.text


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("tool", [LEGACY_TOOL, MAKE_MODEL_TOOL])
async def test_catalog_rejection_through_actual_sdk_is_attempted_once(mode: str, tool: str) -> None:
    h = harness()
    recorder = RecordingClient(error=CasaApiError(400, CATALOG_ERROR, SECRET, SECRET, SECRET))
    h.app.actions = CasaApi(cast(CasaClient, recorder))
    async with Client(h.server, mode=mode) as client:
        prepared = success(
            await client.call_tool(tool, {"entity_id": ENTITY, "model_name": "Unknown"})
        )
        call = {"confirmation_token": token(prepared), "confirmed": True}
        completed = success(await client.call_tool("casa_execute_action", call))
        assert completed["outcome"] == "REJECTED_UNKNOWN_PRODUCT"
        assert completed["warning"] == CATALOG_REJECTION_WARNING
        assert SECRET not in json.dumps(completed)
        failed(await client.call_tool("casa_execute_action", call), "INVALID_CONFIRMATION")
    assert recorder.requests == [
        (
            "POST",
            f"/protected/member/home/{HOME}/entity/{ENTITY}/save_and_publish",
            {"model": {"name": "Unknown"}, "props": []},
        )
    ]
    assert h.fake.calls == []


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("operation", ["update_entity_make_model", "rename_room"])
async def test_new_action_gate_auth_home_rechecks_and_cancel(mode: str, operation: str) -> None:
    h = harness(messages=False, uploads=False, unverified=False)
    fake = FakeActions(h.fake)
    h.app.actions = fake
    arguments: dict[str, object] = (
        {"entity_id": ENTITY, "make_name": "Make"}
        if operation == "update_entity_make_model"
        else {"room_id": ROOM, "room_type_id": ROOM_TYPE, "name": "Room"}
    )
    tool = "casa_prepare_" + operation
    async with Client(h.server, mode=mode) as client:
        for update, code in (
            ({"allow_actions": False}, "ACTIONS_DISABLED"),
            ({"refresh_token": None}, "AUTH_NOT_CONFIGURED"),
            ({"homes": ()}, "HOME_NOT_ALLOWED"),
        ):
            prepared = success(await client.call_tool(tool, arguments))
            original = h.app.settings
            h.app.settings = original.model_copy(update=update)
            call = {"confirmation_token": token(prepared), "confirmed": True}
            failed(await client.call_tool("casa_execute_action", call), code)
            assert fake.calls == []
            h.app.settings = original
            cancelled = success(
                await client.call_tool(
                    "casa_cancel_action", {"confirmation_token": token(prepared)}
                )
            )
            assert cancelled["outcome"] == "CANCELLED"
            failed(await client.call_tool("casa_execute_action", call), "INVALID_CONFIRMATION")
        h.app.settings = original.model_copy(
            update={"homes": settings(homes=(HOME, SECOND_HOME)).homes}
        )
        failed(await client.call_tool(tool, arguments), "HOME_REQUIRED")
        prepared = success(
            await client.call_tool(tool, {**arguments, "home_id": SECOND_HOME.upper()})
        )
        completed = success(
            await client.call_tool(
                "casa_execute_action", {"confirmation_token": token(prepared), "confirmed": True}
            )
        )
        assert completed["home_id"] == SECOND_HOME
    assert len(fake.calls) == 1
    assert fake.calls[0][1][0] == SECOND_HOME
    assert h.fake.calls == []


@pytest.mark.parametrize("operation", ["update_entity_make_model", "rename_room"])
async def test_sdk_marker_controls_unverified_warning_and_gate(
    operation: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(getattr(CasaApi, operation), "__casa_unverified__", True, raising=False)
    # Use the SDK's own marker lookup, not a hardcoded MCP confidence list.
    assert action_unverified(operation)
    h = harness(unverified=False)
    fake = FakeActions(h.fake)
    h.app.actions = fake
    arguments = (
        {"entity_id": ENTITY, "make_name": "Make"}
        if operation == "update_entity_make_model"
        else {"room_id": ROOM, "room_type_id": ROOM_TYPE, "name": "Room"}
    )
    async with Client(h.server) as client:
        tool = next(
            item
            for item in (await client.list_tools()).tools
            if item.name == "casa_prepare_" + operation
        )
        assert tool.description and UNVERIFIED_CONTRACT_WARNING in tool.description
        failed(
            await client.call_tool("casa_prepare_" + operation, arguments),
            "UNVERIFIED_ACTIONS_DISABLED",
        )
        h.app.settings = h.app.settings.model_copy(update={"allow_unverified_actions": True})
        prepared = success(await client.call_tool("casa_prepare_" + operation, arguments))
        assert mapping(prepared["preview"])["contract_warning"] == UNVERIFIED_CONTRACT_WARNING
        h.app.settings = h.app.settings.model_copy(update={"allow_unverified_actions": False})
        failed(
            await client.call_tool(
                "casa_execute_action", {"confirmation_token": token(prepared), "confirmed": True}
            ),
            "UNVERIFIED_ACTIONS_DISABLED",
        )
    assert fake.calls == h.fake.calls == []


async def test_rejection_consumes_before_concurrent_execution() -> None:
    h = harness()
    fake = FakeActions(h.fake)
    fake.error = CasaApiError(400, CATALOG_ERROR, display_message=SECRET)
    fake.release = asyncio.Event()
    h.app.actions = fake
    async with Client(h.server) as client:
        prepared = success(
            await client.call_tool(MAKE_MODEL_TOOL, {"entity_id": ENTITY, "model_name": "Unknown"})
        )
        selected = token(prepared)
        first = asyncio.create_task(execute(h.app, selected, True))
        await fake.entered.wait()
        with pytest.raises(ToolError, match="INVALID_CONFIRMATION"):
            await execute(h.app, selected, True)
        fake.release.set()
        assert (await first).outcome == "REJECTED_UNKNOWN_PRODUCT"
    assert len(fake.calls) == 1


@pytest.mark.parametrize("mode", MODES)
async def test_projected_room_type_id_round_trips_without_uuid_only_mismatch(mode: str) -> None:
    h = harness(unverified=False)
    fake = FakeActions(h.fake)
    h.app.actions = fake
    room = h.fake.inventory.home.stories[0].rooms[0]
    room.id = ROOM
    async with Client(h.server, mode=mode) as client:
        for value in (ROOM_TYPE.upper(), "type-one", "0", "null", "x" * 128):
            room.room_type_id = value
            listed = success(await client.call_tool("casa_list_inventory", {"kind": "rooms"}))
            item = mapping(sequence(mapping(mapping(listed["data"])["page"])["items"])[0])
            assert item["room_type_id"] == value
            args = {"room_id": item["id"], "room_type_id": item["room_type_id"], "name": "Renamed"}
            RenameRoomRequest.model_validate({"room_type_id": value, "name": "Renamed"})
            prepared = success(await client.call_tool(RENAME_TOOL, args))
            completed = success(
                await client.call_tool(
                    "casa_execute_action",
                    {"confirmation_token": token(prepared), "confirmed": True},
                )
            )
            assert completed["outcome"] == "SUCCEEDED"
    assert len(fake.calls) == 5
