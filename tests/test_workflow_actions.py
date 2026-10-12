"""Workflow prepares through real MCP calls, a real CasaApi and a recording client.

The recording client stands in for HTTP only. Every wire body is built by the
sibling SDK itself, so previews are checked against the exact payload sent.
"""

import json
from typing import Any, cast

import pytest
from action_fakes import FakeActions
from casahome import CasaApi, CasaClient, is_unverified
from mcp import Client
from test_actions import harness, token
from test_tools import ENTITY, HOME, MODES, SECRET, Harness, failed, guard_sockets, success
from workflow_cases import WIRE_CASES, WorkflowCase

from casahome_mcp.actions.policy import (
    ACTION_METHODS,
    UNVERIFIED_CONTRACT_WARNING,
    action_unverified,
    gated_action_tools,
)
from casahome_mcp.actions.store import CONSENT_WARNING
from casahome_mcp.config import ConfigurationError, Settings

ID_KEYS = {
    "todo_id",
    "suggestion_id",
    "document_id",
    "availability_request_id",
    "visit_id",
    "recipient_id",
    "mail_item_id",
    "package_id",
    "carrier_id",
    "entity_id",
    "message_id",
    "section",
}
# Route selectors and annotations, not request body fields.
PREVIEW_ONLY_KEYS = ID_KEYS | {"archived", "risk", "contract_warning"}


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    guard_sockets(monkeypatch)


class RecordingClient:
    """Duck-typed CasaClient. Records each write and returns one canned body."""

    def __init__(self, response: object = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.requests: list[tuple[str, str, object]] = []

    async def send(self, method: str, path: str, body: object) -> Any:
        self.requests.append((method, path, body))
        if self.error is not None:
            raise self.error
        return self.response

    async def get(self, path: str, **kwargs: object) -> Any:
        raise AssertionError("Workflow prepares must never read")

    async def post(self, path: str, *, json: Any | None = None, retry_on_401: bool = False) -> Any:
        assert retry_on_401 is False
        return await self.send("POST", path, json)

    async def put(self, path: str, *, json: Any | None = None) -> Any:
        return await self.send("PUT", path, json)

    async def patch(self, path: str, *, json: Any | None = None) -> Any:
        return await self.send("PATCH", path, json)

    async def delete(self, path: str) -> Any:
        return await self.send("DELETE", path, None)


def canned_response(h: Harness, case: WorkflowCase) -> object:
    fixtures: dict[str, Any] = {
        "todo": h.fake.todo_result,
        "document": h.fake.document,
        "schedule": h.fake.schedule,
        "availability": h.fake.availability,
    }
    if isinstance(case.response, str):
        return fixtures[case.response].model_dump(mode="json", by_alias=True)
    return case.response


def sdk_harness(case: WorkflowCase, **flags: bool) -> tuple[Harness, RecordingClient]:
    h = harness(**flags)
    client = RecordingClient(canned_response(h, case))
    h.app.actions = CasaApi(cast(CasaClient, client))
    return h, client


def test_every_new_sdk_write_has_a_wire_case() -> None:
    assert {case.operation for case in WIRE_CASES} <= ACTION_METHODS
    assert len({case.operation for case in WIRE_CASES}) == len(WIRE_CASES) == 26


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("case", WIRE_CASES, ids=lambda case: case.operation)
async def test_preview_is_the_exact_sdk_wire_payload_sent_once(
    mode: str, case: WorkflowCase
) -> None:
    h, recorder = sdk_harness(case)
    async with Client(h.server, mode=mode) as client:
        prepared = success(await client.call_tool("casa_prepare_" + case.operation, case.arguments))
        assert recorder.requests == []
        assert prepared["warning"] == CONSENT_WARNING
        preview = prepared["preview"]
        assert isinstance(preview, dict)
        body = {key: value for key, value in preview.items() if key not in PREVIEW_ONLY_KEYS}
        assert body == (case.body or {})
        for key in (ID_KEYS | {"archived"}) & set(case.arguments):
            assert preview[key] == case.arguments[key]
        call = {"confirmation_token": token(prepared), "confirmed": True}
        completed = success(await client.call_tool("casa_execute_action", call))
        assert completed["outcome"] == "SUCCEEDED"
        assert completed["operation"] == case.operation
        assert recorder.requests == [(case.method, case.path, case.body)]
        failed(await client.call_tool("casa_execute_action", call), "INVALID_CONFIRMATION")
    assert len(recorder.requests) == 1
    assert h.fake.calls == []


@pytest.mark.parametrize("case", WIRE_CASES, ids=lambda case: case.operation)
async def test_unverified_marker_drives_gate_warning_and_description(case: WorkflowCase) -> None:
    unverified = is_unverified(getattr(CasaApi, case.operation))
    assert action_unverified(case.operation) is unverified
    tool = "casa_prepare_" + case.operation
    assert (tool in gated_action_tools(Settings(allow_actions=True))) is unverified
    h, recorder = sdk_harness(case, unverified=False)
    async with Client(h.server) as client:
        listing = {item.name: item for item in (await client.list_tools()).tools}
        text = listing[tool].description or ""
        assert CONSENT_WARNING in text
        response = await client.call_tool(tool, case.arguments)
        if unverified:
            assert "Requires ACTIONS and UNVERIFIED_ACTIONS." in text
            assert UNVERIFIED_CONTRACT_WARNING in text
            failed(response, "UNVERIFIED_ACTIONS_DISABLED")
        else:
            assert "Requires ACTIONS only." in text
            assert "contract_warning" not in json.dumps(success(response)["preview"])
    assert recorder.requests == []
    if unverified:
        h.app.settings = h.app.settings.model_copy(update={"allow_unverified_actions": True})
        async with Client(h.server) as client:
            preview = success(await client.call_tool(tool, case.arguments))["preview"]
        assert isinstance(preview, dict)
        assert preview["contract_warning"] == UNVERIFIED_CONTRACT_WARNING


@pytest.mark.parametrize("case", WIRE_CASES, ids=lambda case: case.operation)
@pytest.mark.parametrize(
    "flags,code",
    [
        ({"actions": False, "unverified": False}, "ACTIONS_DISABLED"),
        # The unverified flag alone never authorizes anything.
        ({"actions": False, "unverified": True}, "ACTIONS_DISABLED"),
    ],
)
async def test_actions_flag_wins_with_zero_sdk_calls(
    case: WorkflowCase, flags: dict[str, bool], code: str
) -> None:
    h, recorder = sdk_harness(case, **flags)
    async with Client(h.server) as client:
        failed(await client.call_tool("casa_prepare_" + case.operation, case.arguments), code)
    assert recorder.requests == []


async def test_home_check_precedes_unverified_gate() -> None:
    case = WIRE_CASES[0]
    h, recorder = sdk_harness(case, unverified=False)
    async with Client(h.server) as client:
        failed(
            await client.call_tool(
                "casa_prepare_" + case.operation,
                {**case.arguments, "home_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"},
            ),
            "HOME_NOT_ALLOWED",
        )
    assert recorder.requests == []


async def test_unverified_gate_precedes_missing_credentials() -> None:
    case = WIRE_CASES[0]
    h, recorder = sdk_harness(case, unverified=False)
    h.app.settings = h.app.settings.model_copy(update={"refresh_token": None})
    async with Client(h.server) as client:
        failed(
            await client.call_tool("casa_prepare_" + case.operation, case.arguments),
            "UNVERIFIED_ACTIONS_DISABLED",
        )
    assert recorder.requests == []


async def test_execute_rechecks_unverified_gate_without_consuming() -> None:
    case = next(case for case in WIRE_CASES if case.operation == "retry_todo")
    h, recorder = sdk_harness(case)
    async with Client(h.server) as client:
        prepared = success(await client.call_tool("casa_prepare_retry_todo", case.arguments))
        call = {"confirmation_token": token(prepared), "confirmed": True}
        h.app.settings = h.app.settings.model_copy(update={"allow_unverified_actions": False})
        failed(await client.call_tool("casa_execute_action", call), "UNVERIFIED_ACTIONS_DISABLED")
        assert recorder.requests == []
        h.app.settings = h.app.settings.model_copy(update={"allow_unverified_actions": True})
        assert success(await client.call_tool("casa_execute_action", call))["outcome"] == (
            "SUCCEEDED"
        )
    assert len(recorder.requests) == 1


async def test_cancel_visit_warns_fees_and_no_undo() -> None:
    case = next(case for case in WIRE_CASES if case.operation == "cancel_vendor_visit")
    h, _ = sdk_harness(case)
    async with Client(h.server) as client:
        listing = {item.name: item for item in (await client.list_tools()).tools}
        prepared = success(
            await client.call_tool("casa_prepare_cancel_vendor_visit", case.arguments)
        )
    preview = prepared["preview"]
    assert isinstance(preview, dict)
    risk = str(preview["risk"])
    assert "cancellation fees" in risk and "not undoable" in risk
    description = listing["casa_prepare_cancel_vendor_visit"].description or ""
    assert "cancellation fees" in description and "Not undoable" in description


@pytest.mark.parametrize("deleted", [True, False])
async def test_update_package_warns_only_when_deleting(deleted: bool) -> None:
    h = harness()
    fake = FakeActions(h.fake)
    h.app.actions = fake
    async with Client(h.server) as client:
        prepared = success(
            await client.call_tool(
                "casa_prepare_update_package", {"package_id": "package-one", "deleted": deleted}
            )
        )
        preview = prepared["preview"]
        assert isinstance(preview, dict)
        assert preview["deleted"] is deleted
        assert ("risk" in preview) is deleted
        if deleted:
            assert "may delete the package" in str(preview["risk"])
        success(
            await client.call_tool(
                "casa_execute_action",
                {"confirmation_token": token(prepared), "confirmed": True},
            )
        )
    assert fake.calls == [("update_package", (HOME, "package-one", {"deleted": deleted}))]


async def test_tracking_validation_returns_status_and_safe_carriers_only() -> None:
    case = next(case for case in WIRE_CASES if case.operation == "validate_package_tracking_number")
    h, _ = sdk_harness(case)
    async with Client(h.server) as client:
        prepared = success(await client.call_tool("casa_prepare_" + case.operation, case.arguments))
        completed = success(
            await client.call_tool(
                "casa_execute_action",
                {"confirmation_token": token(prepared), "confirmed": True},
            )
        )
    assert completed["tracking_number_valid"] is True
    assert completed["carrier_ids"] == ["ups"]
    assert "1Z999AA10123456784" not in json.dumps(completed)


@pytest.mark.parametrize("case", WIRE_CASES, ids=lambda case: case.operation)
async def test_sdk_failure_is_unknown_private_and_not_retried(case: WorkflowCase) -> None:
    h = harness()
    recorder = RecordingClient(error=RuntimeError(SECRET))
    h.app.actions = CasaApi(cast(CasaClient, recorder))
    async with Client(h.server) as client:
        prepared = success(await client.call_tool("casa_prepare_" + case.operation, case.arguments))
        call = {"confirmation_token": token(prepared), "confirmed": True}
        completed = success(await client.call_tool("casa_execute_action", call))
        assert completed["outcome"] == "UNKNOWN"
        assert SECRET not in json.dumps(completed)
        failed(await client.call_tool("casa_execute_action", call), "INVALID_CONFIRMATION")
    assert len(recorder.requests) == 1


async def test_unconfirmed_package_archive_response_is_unknown() -> None:
    case = next(case for case in WIRE_CASES if case.operation == "set_package_auto_archive")
    h, recorder = sdk_harness(case)
    recorder.response = {"success": False, "message": SECRET}
    async with Client(h.server) as client:
        prepared = success(await client.call_tool("casa_prepare_" + case.operation, case.arguments))
        completed = success(
            await client.call_tool(
                "casa_execute_action",
                {"confirmation_token": token(prepared), "confirmed": True},
            )
        )
    assert completed["outcome"] == "UNKNOWN"
    assert SECRET not in json.dumps(completed)


INVALID: tuple[tuple[str, dict[str, object]], ...] = (
    ("update_todo", {"todo_id": "todo-one"}),
    ("update_todo", {"todo_id": "todo-one", "title": "null"}),
    ("update_todo", {"todo_id": "todo-one", "title": "x\n" + SECRET}),
    ("update_todo", {"todo_id": "todo-one", "title": "x", "attachments": {"add_upload_ids": []}}),
    ("reject_suggested_todo", {"suggestion_id": "one", "reason": "declined"}),
    ("confirm_todo_support", {"todo_id": "one", "is_support_question": "true"}),
    ("confirm_todo_support", {"todo_id": "one"}),
    ("update_document", {"document_id": "one"}),
    ("update_document", {"document_id": "one", "document_date": "x", "clear_document_date": True}),
    ("update_document", {"document_id": "one", "document_type": "../" + SECRET}),
    ("analyze_document", {"document_id": "one", "reanalyze": 1}),
    ("update_schedule_preferences", {"selected_days_of_week": [8], "selected_times_of_day": []}),
    (
        "update_schedule_preferences",
        {"selected_days_of_week": [1, 2, 3, 4, 5, 6, 7, 0], "selected_times_of_day": []},
    ),
    ("update_schedule_preferences", {"selected_days_of_week": [1.0], "selected_times_of_day": []}),
    (
        "update_availability_slots",
        {"availability_request_id": "one", "windows": [{"start_time": -1, "end_time": 2}]},
    ),
    (
        "update_availability_slots",
        {"availability_request_id": "one", "windows": [{"start_time": 1}]},
    ),
    (
        "reorder_todo_section",
        {"section": "other", "expected_revision": 1, "ordered_item_ids": ["one"]},
    ),
    (
        "reorder_todo_section",
        {"section": "send_to_concierge", "expected_revision": 1, "ordered_item_ids": []},
    ),
    ("cancel_vendor_visit", {"visit_id": SECRET + "/x"}),
    ("set_mail_item_archived", {"mail_item_id": "one"}),
    ("validate_package_tracking_number", {"tracking_number": SECRET + " x"}),
    (
        "add_tracked_package",
        {"carrier_id": "c", "tracking_number": "T1", "name": "n", "direction": "sideways"},
    ),
    ("update_package", {"package_id": "one"}),
    ("update_package", {"package_id": "one", "deleted": "true"}),
    ("set_package_auto_archive", {}),
    ("set_package_auto_archive", {"package_auto_archive_days": 30.0}),
    ("set_package_auto_archive", {"package_auto_archive_days": 0}),
    ("set_package_auto_archive", {"package_auto_archive_days": True}),
    ("create_inventory_entity", {"room_id": "not-a-uuid"}),
    ("create_inventory_entity", {"room_id": ENTITY, "image_upload_ids": ["one"]}),
    (
        "create_inventory_lighting",
        {"room_id": ENTITY, "fixture_entity_type_id": "t", "bulb_kind": "a b"},
    ),
    ("create_paint_from_library", {"paint_color_id": 1, "room_ids": []}),
    ("create_paint_from_library", {"paint_color_id": "1", "room_ids": [ENTITY]}),
    ("create_paint_from_library", {"paint_color_id": 1, "room_ids": [ENTITY + "0"]}),
    ("update_entity_properties", {"entity_id": ENTITY, "props": []}),
    (
        "update_entity_properties",
        {"entity_id": ENTITY, "props": [{"definition_id": "d"}]},
    ),
    (
        "update_entity_properties",
        {"entity_id": ENTITY, "props": [{"definition_id": "d", "value": "v", "enum_id": "e"}]},
    ),
    (
        "update_access_preferences",
        {
            "general_instructions": None,
            "package_pickup_method": "pickup_spot",
            "package_pickup_spot": None,
        },
    ),
    (
        "update_access_preferences",
        {
            "general_instructions": "null",
            "package_pickup_method": None,
            "package_pickup_spot": None,
            "package_pickup_general_instructions": None,
        },
    ),
    ("clear_ai_message_rating", {"message_id": "one", "rating": None}),
)


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("operation,arguments", INVALID)
async def test_invalid_inputs_refused_privately_before_any_call(
    mode: str,
    operation: str,
    arguments: dict[str, object],
    caplog: pytest.LogCaptureFixture,
) -> None:
    h = harness()
    fake = FakeActions(h.fake)
    h.app.actions = fake
    async with Client(h.server, mode=mode) as client:
        response = await client.call_tool("casa_prepare_" + operation, arguments)
        failed(response, "INVALID_ARGUMENT")
        assert SECRET not in json.dumps(response.model_dump(mode="json"))
    assert fake.calls == h.fake.calls == []
    assert SECRET not in caplog.text
    assert len(h.app.action_store._pending) == 0


SCHEMAS: dict[str, tuple[set[str], set[str]]] = {
    "update_todo": ({"todo_id", "title", "prepared_brief", "emoji"}, {"todo_id"}),
    "reject_suggested_todo": ({"suggestion_id", "reason"}, {"suggestion_id"}),
    "confirm_todo_support": (
        {"todo_id", "is_support_question"},
        {"todo_id", "is_support_question"},
    ),
    "update_document": (
        {"document_id", "name", "document_type", "document_date", "clear_document_date"},
        {"document_id"},
    ),
    "analyze_document": ({"document_id", "reanalyze"}, {"document_id", "reanalyze"}),
    "organize_document": ({"document_id"}, {"document_id"}),
    "update_schedule_preferences": (
        {"selected_days_of_week", "selected_times_of_day"},
        {"selected_days_of_week", "selected_times_of_day"},
    ),
    "update_availability_slots": (
        {"availability_request_id", "windows"},
        {"availability_request_id", "windows"},
    ),
    "reorder_todo_section": (
        {"section", "expected_revision", "ordered_item_ids"},
        {"section", "expected_revision", "ordered_item_ids"},
    ),
    "retry_todo": ({"todo_id"}, {"todo_id"}),
    "cancel_vendor_visit": ({"visit_id"}, {"visit_id"}),
    "remove_mailbox_recipient": ({"recipient_id"}, {"recipient_id"}),
    "mark_mail_item_read": ({"mail_item_id"}, {"mail_item_id"}),
    "mark_mail_item_unread": ({"mail_item_id"}, {"mail_item_id"}),
    "set_mail_item_archived": ({"mail_item_id", "archived"}, {"mail_item_id", "archived"}),
    "validate_package_tracking_number": ({"tracking_number"}, {"tracking_number"}),
    "add_tracked_package": (
        {"carrier_id", "tracking_number", "name", "direction"},
        {"carrier_id", "tracking_number", "name", "direction"},
    ),
    "update_package": ({"package_id", "archive", "deleted", "name", "direction"}, {"package_id"}),
    "requeue_package_pickup": ({"package_id"}, {"package_id"}),
    "set_package_auto_archive": ({"package_auto_archive_days"}, {"package_auto_archive_days"}),
    "create_inventory_entity": ({"room_id"}, {"room_id"}),
    "create_inventory_lighting": (
        {"room_id", "fixture_entity_type_id", "bulb_kind", "bulb_entity_type_id"},
        {"room_id", "fixture_entity_type_id", "bulb_kind"},
    ),
    "create_paint_from_library": (
        {"paint_color_id", "room_ids"},
        {"paint_color_id", "room_ids"},
    ),
    "update_entity_properties": (
        {"entity_id", "props", "make_id", "model_id"},
        {"entity_id", "props"},
    ),
    "clear_ai_message_rating": ({"message_id"}, {"message_id"}),
    "update_access_preferences": (
        {
            "general_instructions",
            "package_pickup_method",
            "package_pickup_spot",
            "package_pickup_general_instructions",
        },
        {
            "general_instructions",
            "package_pickup_method",
            "package_pickup_spot",
            "package_pickup_general_instructions",
        },
    ),
}


@pytest.mark.parametrize("mode", MODES)
async def test_strict_input_schemas_and_annotations(mode: str) -> None:
    assert set(SCHEMAS) == {case.operation for case in WIRE_CASES}
    h = harness()
    async with Client(h.server, mode=mode) as client:
        listing = {tool.name: tool for tool in (await client.list_tools()).tools}
    for operation, (fields, required) in SCHEMAS.items():
        tool = listing["casa_prepare_" + operation]
        schema = tool.input_schema
        assert set(schema["properties"]) == fields | {"home_id"}
        assert set(schema.get("required", [])) == required
        assert tool.annotations is not None
        assert tool.annotations.read_only_hint is False
        assert tool.annotations.destructive_hint is False
        assert tool.annotations.idempotent_hint is False
        assert tool.annotations.open_world_hint is False
        serialized = json.dumps(schema)
        for forbidden in ("ctx", "upload", "attachment", "url", "image"):
            assert forbidden not in serialized.lower()


def test_unverified_actions_flag_parsing_is_strict_and_private() -> None:
    assert Settings.from_env({}).allow_unverified_actions is False
    assert Settings.from_env({"CASA_ALLOW_UNVERIFIED_ACTIONS": "TRUE"}).allow_unverified_actions
    with pytest.raises(ConfigurationError, match="CASA_ALLOW_UNVERIFIED_ACTIONS") as error:
        Settings.from_env({"CASA_ALLOW_UNVERIFIED_ACTIONS": SECRET})
    assert SECRET not in str(error.value)


async def test_status_reports_unverified_action_gate() -> None:
    h = harness(unverified=False)
    async with Client(h.server) as client:
        data = success(await client.call_tool("casa_get_status"))["data"]
    assert isinstance(data, dict)
    assert data["allow_unverified_actions"] is False
    blocked = set(gated_action_tools(h.app.settings))
    assert "casa_prepare_cancel_vendor_visit" in blocked
    assert "casa_prepare_update_access_preferences" not in blocked
    assert blocked <= set(data["disabled_features"])
    h = harness(unverified=True)
    async with Client(h.server) as client:
        data = success(await client.call_tool("casa_get_status"))["data"]
    assert isinstance(data, dict)
    assert data["allow_unverified_actions"] is True
    assert not any(name.startswith("casa_prepare_") for name in data["disabled_features"])
