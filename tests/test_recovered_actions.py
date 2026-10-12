"""Provisional prepares with real SDK codecs and a network-free recorder."""

import asyncio
import json
import time
from typing import cast

import pytest
from action_fakes import FakeActions
from casahome import CasaApi, CasaClient, is_unverified
from casahome.models.documents import (
    DocumentDetailsResponse,
    DocumentStructureSuggestionsResponse,
    HomeDocument,
)
from mcp import Client
from pydantic import JsonValue
from test_actions import harness, read_context, token
from test_tools import HOME, MODES, SECRET, failed, guard_sockets, mapping, success
from test_workflow_actions import RecordingClient

from casahome_mcp.actions import recovered_tools
from casahome_mcp.actions.policy import ACTION_METHODS, UNVERIFIED_CONTRACT_WARNING
from casahome_mcp.actions.store import MAX_BYTES, ActionStore, Group, Invocation
from casahome_mcp.coverage_projections import _document
from casahome_mcp.detail_projections import project_document_structure_suggestions

CASES = (
    (
        "update_request_detail",
        {"request_id": "request-one", "title": " New title ", "read_state": "unread"},
        "PATCH",
        "/protected/home/" + HOME + "/requests/request-one",
        {"title": " New title ", "read_state": "unread"},
        {
            "id": "request-one",
            "type": "general",
            "status": "open",
            "title": "New title",
            "emoji": "x",
            "has_unread_messages": False,
        },
    ),
    (
        "update_task",
        {"task_id": "task-one", "description": "New description", "emoji": "x"},
        "PATCH",
        "/protected/home/" + HOME + "/tasks/task-one",
        {"description": "New description", "emoji": "x"},
        {
            "id": "task-one",
            "title": "New",
            "description": "New description",
            "emoji": "x",
            "status": "open",
            "updates": [],
            "can_schedule_handyman_vendor_visit": False,
            "can_chat_with_concierge": False,
            "can_edit": True,
            "can_delete": True,
        },
    ),
    (
        "update_story",
        {"story_id": "story-one", "floor_number": 0},
        "PATCH",
        "/protected/member/home/" + HOME + "/story/story-one",
        {"floor_number": 0},
        {"message": SECRET},
    ),
    (
        "dismiss_document_structure_suggestion",
        {
            "document_id": "doc-one",
            "suggestion_id": "suggestion-one",
        },
        "POST",
        "/protected/home/"
        + HOME
        + "/documents/doc-one/structure_suggestions/suggestion-one/respond",
        {"decision": "dismissed", "expected_values": ["one"]},
        {"saved": True},
    ),
    (
        "delete_document",
        {"document_id": "doc-one"},
        "DELETE",
        "/protected/home/" + HOME + "/documents/doc-one",
        None,
        {"deleted": True},
    ),
)


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    guard_sockets(monkeypatch)


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("operation,args,method,path,body,response", CASES)
async def test_exact_preview_single_attempt_and_replay(
    mode: str,
    operation: str,
    args: dict[str, object],
    method: str,
    path: str,
    body: object,
    response: object,
) -> None:
    assert operation in ACTION_METHODS
    assert is_unverified(getattr(CasaApi, operation))
    h = harness()
    read_context(h, operation)
    recorder = RecordingClient(response)
    h.app.actions = CasaApi(cast(CasaClient, recorder))
    tool = "casa_prepare_" + operation
    async with Client(h.server, mode=mode) as client:
        listing = {item.name: item for item in (await client.list_tools()).tools}
        assert UNVERIFIED_CONTRACT_WARNING in (listing[tool].description or "")
        prepared = success(await client.call_tool(tool, args))
        preview = prepared["preview"]
        assert isinstance(preview, dict)
        if operation in {"dismiss_document_structure_suggestion", "delete_document"}:
            annotations = listing[tool].annotations
            assert annotations is not None and annotations.open_world_hint is True
        assert preview["contract_warning"] == UNVERIFIED_CONTRACT_WARNING
        assert {key: preview[key] for key in args} == args
        if body is not None:
            assert isinstance(body, dict)
            assert all(preview[key] == value for key, value in body.items())
        assert recorder.requests == []
        # The returned preview is a copy, not the immutable execution snapshot.
        if operation == "dismiss_document_structure_suggestion":
            preview["expected_values"] = ["tampered"]
        call = {"confirmation_token": token(prepared), "confirmed": False}
        assert (
            success(await client.call_tool("casa_execute_action", call))["outcome"]
            == "NOT_EXECUTED"
        )
        assert recorder.requests == []
        call["confirmed"] = True
        completed = success(await client.call_tool("casa_execute_action", call))
        assert completed["outcome"] == ("UNKNOWN" if operation == "update_story" else "SUCCEEDED")
        assert SECRET not in json.dumps(completed)
        assert recorder.requests == [(method, path, body)]
        failed(await client.call_tool("casa_execute_action", call), "INVALID_CONFIRMATION")


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("operation,args,method,path,body,response", CASES)
async def test_gates_recheck_and_no_prepare_calls(
    mode: str,
    operation: str,
    args: dict[str, object],
    method: str,
    path: str,
    body: object,
    response: object,
) -> None:
    h = harness(unverified=False)
    read_context(h, operation)
    recorder = RecordingClient(response)
    h.app.actions = CasaApi(cast(CasaClient, recorder))
    async with Client(h.server, mode=mode) as client:
        failed(
            await client.call_tool("casa_prepare_" + operation, args),
            "UNVERIFIED_ACTIONS_DISABLED",
        )
        h.app.settings = h.app.settings.model_copy(update={"allow_unverified_actions": True})
        prepared = success(await client.call_tool("casa_prepare_" + operation, dict(args)))
        call = {"confirmation_token": token(prepared), "confirmed": True}
        h.app.settings = h.app.settings.model_copy(update={"allow_actions": False})
        failed(await client.call_tool("casa_execute_action", call), "ACTIONS_DISABLED")
        h.app.settings = h.app.settings.model_copy(
            update={"allow_actions": True, "allow_unverified_actions": False}
        )
        failed(await client.call_tool("casa_execute_action", call), "UNVERIFIED_ACTIONS_DISABLED")
        assert recorder.requests == []
        h.app.settings = h.app.settings.model_copy(update={"allow_unverified_actions": True})
        assert success(await client.call_tool("casa_execute_action", call))["outcome"] == (
            "UNKNOWN" if operation == "update_story" else "SUCCEEDED"
        )
    assert len(recorder.requests) == 1


@pytest.mark.parametrize("field", ["saved", "deleted"])
@pytest.mark.parametrize("value", [False, None, "false", {}, {"url": SECRET}])
async def test_false_flags_and_malformed_results_are_never_success(
    field: str, value: object
) -> None:
    operation, args, method, path, body, _ = CASES[3 if field == "saved" else 4]
    h = harness()
    read_context(h, operation)
    recorder = RecordingClient({field: value, "url": "https://example.invalid/" + SECRET})
    h.app.actions = CasaApi(cast(CasaClient, recorder))
    async with Client(h.server) as client:
        prepared = success(await client.call_tool("casa_prepare_" + operation, dict(args)))
        call = {"confirmation_token": token(prepared), "confirmed": True}
        completed = success(await client.call_tool("casa_execute_action", call))
        assert completed["outcome"] == ("NOT_APPLIED" if value is False else "UNKNOWN")
        assert SECRET not in json.dumps(completed)
        failed(await client.call_tool("casa_execute_action", call), "INVALID_CONFIRMATION")
    assert recorder.requests == [(method, path, body)]


@pytest.mark.parametrize("operation,args,method,path,body,response", CASES)
async def test_post_write_failure_is_unknown_and_never_retried(
    operation: str,
    args: dict[str, object],
    method: str,
    path: str,
    body: object,
    response: object,
) -> None:
    h = harness()
    read_context(h, operation)
    recorder = RecordingClient(error=RuntimeError(SECRET))
    h.app.actions = CasaApi(cast(CasaClient, recorder))
    async with Client(h.server) as client:
        prepared = success(await client.call_tool("casa_prepare_" + operation, args))
        call = {"confirmation_token": token(prepared), "confirmed": True}
        completed = success(await client.call_tool("casa_execute_action", call))
        assert completed["outcome"] == "UNKNOWN"
        assert SECRET not in json.dumps(completed)
        failed(await client.call_tool("casa_execute_action", call), "INVALID_CONFIRMATION")
    assert recorder.requests == [(method, path, body)]


async def test_inputs_reject_invalid_shapes_without_leaking(
    caplog: pytest.LogCaptureFixture,
) -> None:
    h = harness()
    async with Client(h.server) as client:
        bad = (
            ("update_request_detail", {"request_id": "../" + SECRET, "title": "ok"}),
            ("update_request_detail", {"request_id": "one", "read_state": "other"}),
            ("update_request_detail", {"request_id": "one", "title": None}),
            ("update_request_detail", {"request_id": "one", "title": "  "}),
            ("update_task", {"task_id": "one", "description": None}),
            ("update_task", {"task_id": "one", "emoji": "  "}),
            ("update_task", {"task_id": "one", "attachments": [SECRET]}),
            ("update_story", {"story_id": "one", "floor_number": True}),
            ("update_story", {"story_id": "one", "name": "   "}),
            (
                "dismiss_document_structure_suggestion",
                {"document_id": "one", "suggestion_id": "../" + SECRET},
            ),
            ("delete_document", {"document_id": "../" + SECRET}),
        )
        for operation, args in bad:
            failed(await client.call_tool("casa_prepare_" + operation, args), "INVALID_ARGUMENT")
    assert SECRET not in caplog.text


async def test_reads_have_no_capabilities_and_prepare_refetches_once() -> None:
    h = harness()
    read_context(h, "dismiss_document_structure_suggestion")
    h.app.actions = CasaApi(cast(CasaClient, RecordingClient({"deleted": True})))
    async with Client(h.server) as client:
        details = success(
            await client.call_tool("casa_get_document_details", {"document_id": "doc-one"})
        )
        structures = success(
            await client.call_tool(
                "casa_list_document_structure_suggestions", {"document_id": "doc-one"}
            )
        )
        assert "deletion_guard" not in mapping(details["data"])
        rows = mapping(mapping(structures["data"])["page"])["items"]
        assert isinstance(rows, list)
        assert "dismissal_guard" not in mapping(rows[0])
        assert h.app.action_store.remaining_bytes() == MAX_BYTES
        prepared = success(
            await client.call_tool("casa_prepare_delete_document", {"document_id": "doc-one"})
        )
        metadata = mapping(mapping(prepared["preview"])["read_metadata"])
        assert metadata == {
            "id": "doc-one",
            "name": "Synthetic document",
            "document_type": "warranty",
            "size_bytes": 42,
            "organization_status": "future-status",
        }
        assert mapping(prepared["preview"])["document_metadata_complete"] is True
        accepted = success(
            await client.call_tool(
                "casa_prepare_respond_to_document_structure_suggestion",
                {
                    "document_id": "doc-one",
                    "suggestion_id": "suggestion-one",
                    "decision": "accepted",
                },
            )
        )
        assert mapping(accepted["preview"])["expected_values"] == ["one"]
        listing = {item.name: item for item in (await client.list_tools()).tools}
        for name in (
            "casa_prepare_respond_to_document_structure_suggestion",
            "casa_prepare_dismiss_document_structure_suggestion",
            "casa_prepare_delete_document",
        ):
            annotations = listing[name].annotations
            assert annotations is not None
            assert annotations.read_only_hint is False
            assert annotations.destructive_hint is False
            assert annotations.idempotent_hint is False
            assert annotations.open_world_hint is True
        context = mapping(mapping(accepted["preview"])["suggestion_context"])
        assert context["entity_id"] == "entity-one"
        assert context["definition_id"] == "definition-one"
        assert context["changed_since_analysis"] is False
        assert "expected_values may only guard" in str(mapping(accepted["preview"])["risk"])
    assert h.fake.calls == [
        ("document_details", (HOME, "doc-one")),
        ("document_structure_suggestions", (HOME, "doc-one")),
        ("document_details", (HOME, "doc-one")),
        ("document_structure_suggestions", (HOME, "doc-one")),
    ]
    assert h.fake.retry_flags == [
        ("document_details", True),
        ("document_structure_suggestions", True),
        ("document_details", False),
        ("document_structure_suggestions", False),
    ]


@pytest.mark.parametrize(
    "operation",
    ["dismiss_document_structure_suggestion", "respond_to_document_structure_suggestion"],
)
@pytest.mark.parametrize(
    "reason",
    [
        "missing",
        "accepted",
        "changed",
        "responded",
        "url",
        "control",
        "surrogate",
        "overflow",
        "long",
        "missing_entity",
        "unsafe_definition",
        "unsafe_title",
        "duplicate",
        "oversized_response",
    ],
)
async def test_structure_prepare_refuses_stale_or_unsafe_exact_values(
    operation: str, reason: str
) -> None:
    h = harness()
    read_context(h, operation)
    h.app.actions = FakeActions(h.fake)
    item = h.fake.structure_suggestions.suggestions[0]
    if reason == "missing":
        item.id = "other"
    elif reason == "accepted":
        item.state = "accepted"
    elif reason == "changed":
        item.changed_since_analysis = True
    elif reason == "responded":
        item.responded_at = 42
    elif reason == "url":
        item.current_values = ["https://example.invalid/private"]
    elif reason == "control":
        item.current_values = ["unsafe\u2028value"]
    elif reason == "surrogate":
        item.current_values = ["unsafe\ud800value"]
    elif reason == "overflow":
        item.current_values = ["safe"] * 21
    elif reason == "missing_entity":
        item.entity_id = None
    elif reason == "unsafe_definition":
        item.definition_id = "../unsafe"
    elif reason == "unsafe_title":
        item.title = "https://example.invalid/private"
    elif reason == "duplicate":
        h.fake.structure_suggestions.suggestions.append(item.model_copy())
    elif reason == "oversized_response":
        h.fake.structure_suggestions.suggestions.extend(
            item.model_copy(update={"id": f"other-{i}"}) for i in range(100)
        )
    else:
        item.current_values = ["x" * 10_001]
    args: dict[str, object] = {"document_id": "doc-one", "suggestion_id": "suggestion-one"}
    if operation.startswith("respond"):
        args["decision"] = "accepted"
    async with Client(h.server) as client:
        failed(await client.call_tool("casa_prepare_" + operation, args), "INVALID_ARGUMENT")
    assert h.fake.calls == [("document_structure_suggestions", (HOME, "doc-one"))]
    assert h.app.action_store.remaining_bytes() == MAX_BYTES


@pytest.mark.parametrize(
    "name",
    [None, " ", "https://example.invalid/private", "x" * 257, "bad\u2029value", "bad\ud800value"],
)
async def test_delete_prepare_requires_exact_safe_identity(name: str | None) -> None:
    h = harness()
    h.app.actions = FakeActions(h.fake)
    h.fake.document.document.name = name
    async with Client(h.server) as client:
        failed(
            await client.call_tool("casa_prepare_delete_document", {"document_id": "doc-one"}),
            "INVALID_ARGUMENT",
        )
    assert h.fake.calls == [("document_details", (HOME, "doc-one"))]
    assert h.app.action_store.remaining_bytes() == MAX_BYTES


async def test_prepare_read_timeout_is_sanitized_and_issues_no_token() -> None:
    h = harness()
    h.app.actions = FakeActions(h.fake)
    h.app.deadline_seconds = 0.001
    original = h.fake.document_details

    async def slow(
        home: str, document: str, *, retry_on_401: bool = True
    ) -> DocumentDetailsResponse:
        await asyncio.sleep(0.1)
        return await original(home, document, retry_on_401=retry_on_401)

    h.fake.document_details = slow  # type: ignore[assignment]
    async with Client(h.server) as client:
        failed(
            await client.call_tool("casa_prepare_delete_document", {"document_id": "doc-one"}),
            "TIMEOUT",
        )
    assert h.app.action_store.remaining_bytes() == MAX_BYTES
    assert h.fake.calls == []


@pytest.mark.parametrize("phase", ["selection", "token"])
async def test_deadline_includes_sync_finalization_and_token_allocation(
    monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    h = harness()
    read_context(h, "dismiss_document_structure_suggestion")
    h.app.deadline_seconds = 0.01
    h.app.actions = FakeActions(h.fake)
    if phase == "selection":
        original = recovered_tools.suggestion_context

        def slow_selection(
            response: DocumentStructureSuggestionsResponse, suggestion_id: str
        ) -> tuple[list[str], dict[str, JsonValue]]:
            time.sleep(0.03)
            return original(response, suggestion_id)

        monkeypatch.setattr(recovered_tools, "suggestion_context", slow_selection)
    else:
        original_add = h.app.action_store.add

        def slow_add(
            home_id: str,
            operation: str,
            group: Group,
            preview: dict[str, JsonValue],
            invoke: Invocation,
            *,
            retained_bytes: int = 0,
            snapshot_reservation: object | None = None,
        ) -> dict[str, JsonValue]:
            prepared = original_add(
                home_id,
                operation,
                group,
                preview,
                invoke,
                retained_bytes=retained_bytes,
                snapshot_reservation=snapshot_reservation,
            )
            time.sleep(0.03)
            return prepared

        monkeypatch.setattr(h.app.action_store, "add", slow_add)
    async with Client(h.server) as client:
        failed(
            await client.call_tool(
                "casa_prepare_dismiss_document_structure_suggestion",
                {"document_id": "doc-one", "suggestion_id": "suggestion-one"},
            ),
            "TIMEOUT",
        )
    assert h.fake.calls == [("document_structure_suggestions", (HOME, "doc-one"))]
    assert h.fake.retry_flags == [("document_structure_suggestions", False)]
    assert h.app.action_store.remaining_bytes() == MAX_BYTES


@pytest.mark.parametrize(
    "field,value",
    [
        ("document_type", "https://example.invalid/a"),
        ("document_date", "bad\u2028date"),
        ("size_bytes", -1),
    ],
)
async def test_delete_refuses_any_unsafe_present_metadata(field: str, value: object) -> None:
    h = harness()
    h.app.actions = FakeActions(h.fake)
    setattr(h.fake.document.document, field, value)
    async with Client(h.server) as client:
        failed(
            await client.call_tool("casa_prepare_delete_document", {"document_id": "doc-one"}),
            "INVALID_ARGUMENT",
        )
    assert h.app.action_store.remaining_bytes() == MAX_BYTES


async def test_delete_preview_distinguishes_missing_from_explicit_null_metadata() -> None:
    h = harness()
    h.app.actions = FakeActions(h.fake)
    h.fake.document.document = h.fake.document.document.model_copy(update={"document_date": None})
    async with Client(h.server) as client:
        prepared = success(
            await client.call_tool("casa_prepare_delete_document", {"document_id": "doc-one"})
        )
    metadata = mapping(mapping(prepared["preview"])["read_metadata"])
    assert "document_date" in metadata and metadata["document_date"] is None
    assert "extraction_status" not in metadata


async def test_prepare_read_error_is_private_and_no_token(
    caplog: pytest.LogCaptureFixture,
) -> None:
    h = harness()
    h.app.actions = FakeActions(h.fake)

    async def broken(
        home: str, document: str, *, retry_on_401: bool = True
    ) -> DocumentDetailsResponse:
        raise RuntimeError(SECRET)

    h.fake.document_details = broken  # type: ignore[assignment]
    async with Client(h.server) as client:
        outcome = await client.call_tool("casa_prepare_delete_document", {"document_id": "doc-one"})
        failed(outcome, "INTERNAL_ERROR")
        assert SECRET not in outcome.model_dump_json()
    assert SECRET not in caplog.text
    assert h.app.action_store.remaining_bytes() == MAX_BYTES


async def test_delete_prepare_refuses_unsafe_optional_metadata() -> None:
    h = harness()
    h.app.actions = FakeActions(h.fake)
    document = h.fake.document.document
    document.document_type = "https://example.invalid/private"
    document.document_date = "bad\u2028date"
    assert document.organization is not None
    document.organization.status = "bad\u200bstatus"
    async with Client(h.server) as client:
        outcome = await client.call_tool("casa_prepare_delete_document", {"document_id": "doc-one"})
        failed(outcome, "INVALID_ARGUMENT")
        assert SECRET not in outcome.model_dump_json()
    assert h.app.action_store.remaining_bytes() == MAX_BYTES


def test_store_snapshot_reservation_transfer_is_atomic() -> None:
    from mcp.server.mcpserver.exceptions import ToolError
    from test_actions import noop

    store = ActionStore()
    preview: dict[str, JsonValue] = {"name": "é"}
    size = len(json.dumps(preview, ensure_ascii=False, sort_keys=True).encode("utf-8"))
    reservation = store.reserve_snapshot(MAX_BYTES - size)
    with pytest.raises(ToolError, match="CAPACITY_EXCEEDED"):
        store.add(
            HOME,
            "upload_document",
            "uploads",
            {"name": "éé"},
            noop,
            retained_bytes=MAX_BYTES - size,
            snapshot_reservation=reservation,
        )
    assert store.remaining_bytes() == size
    pending = store.add(
        HOME,
        "upload_document",
        "uploads",
        preview,
        noop,
        retained_bytes=MAX_BYTES - size,
        snapshot_reservation=reservation,
    )
    assert store.remaining_bytes() == 0
    selected = pending["confirmation_token"]
    assert isinstance(selected, str)
    assert store.get(selected).size_bytes == MAX_BYTES
    store.consume(selected)
    assert store.remaining_bytes() == MAX_BYTES


def test_preview_utf8_and_pending_slots_are_charged_without_exposing_bytes() -> None:
    from mcp.server.mcpserver.exceptions import ToolError
    from test_actions import noop

    store = ActionStore()
    tokens = []
    for _ in range(16):
        prepared = store.add(HOME, "delete_todo", "actions", {"value": "é"}, noop)
        assert "size_bytes" not in prepared
        selected = prepared["confirmation_token"]
        assert isinstance(selected, str)
        tokens.append(selected)
    expected = len(json.dumps({"value": "é"}, ensure_ascii=False, sort_keys=True).encode("utf-8"))
    assert store.remaining_bytes() == MAX_BYTES - 16 * expected
    with pytest.raises(ToolError, match="CAPACITY_EXCEEDED"):
        store.add(HOME, "delete_todo", "actions", {"value": "é"}, noop)
    store.consume(tokens[0])
    assert store.remaining_bytes() == MAX_BYTES - 15 * expected
    store.clear()
    assert store.remaining_bytes() == MAX_BYTES


@pytest.mark.parametrize("operation,args,method,path,body,response", CASES)
async def test_expired_token_makes_zero_sdk_calls(
    operation: str,
    args: dict[str, object],
    method: str,
    path: str,
    body: object,
    response: object,
) -> None:
    h = harness()
    read_context(h, operation)
    now = [0.0]
    h.app.action_store = ActionStore(lambda: now[0])
    recorder = RecordingClient(response)
    h.app.actions = CasaApi(cast(CasaClient, recorder))
    async with Client(h.server) as client:
        prepared = success(await client.call_tool("casa_prepare_" + operation, args))
        now[0] = 300.0
        failed(
            await client.call_tool(
                "casa_execute_action", {"confirmation_token": token(prepared), "confirmed": True}
            ),
            "INVALID_CONFIRMATION",
        )
    assert recorder.requests == []


def test_structure_values_never_masquerade_as_exact_guard() -> None:
    original = {
        "id": "suggestion-one",
        "section": "inventory",
        "title": "Example",
        "current_values": ["x" * 257, "https://example.invalid/" + SECRET] + ["v"] * 20,
        "current_label": "Current",
        "proposed_label": "New",
        "reason": "Example",
        "state": "pending",
        "changed_since_analysis": False,
        "citations": [],
    }
    model = DocumentStructureSuggestionsResponse.model_validate({"suggestions": [original]})
    data, warnings = project_document_structure_suggestions(model)
    item = data.page.items[0]
    assert item.current_values_complete is False
    assert "INCOMPLETE_CURRENT_VALUES_NOT_SAFE_AS_GUARD" in warnings
    assert SECRET not in data.model_dump_json()
    original["current_values"] = ["Exact", "Other"]
    model = DocumentStructureSuggestionsResponse.model_validate({"suggestions": [original]})
    data, warnings = project_document_structure_suggestions(model)
    assert data.page.items[0].current_values_complete is True


@pytest.mark.parametrize(
    "unsafe", ["x" * 257, "https://example.invalid/a", "bad\x00value", "bad\u2028value"]
)
async def test_unsafe_structure_read_is_advisory_only(unsafe: str) -> None:
    h = harness()
    h.fake.structure_suggestions.suggestions[0].current_values = [unsafe]
    async with Client(h.server) as client:
        read = success(
            await client.call_tool(
                "casa_list_document_structure_suggestions", {"document_id": "doc-one"}
            )
        )
    rows = mapping(mapping(read["data"])["page"])["items"]
    assert isinstance(rows, list)
    item = mapping(rows[0])
    assert item["current_values_complete"] is False
    assert h.app.action_store.remaining_bytes() == MAX_BYTES


async def test_structure_read_does_not_consume_action_capacity() -> None:
    h = harness()
    template = h.fake.structure_suggestions.suggestions[0]
    h.fake.structure_suggestions.suggestions = [
        template.model_copy(update={"id": f"structure-{index}"}) for index in range(65)
    ]
    async with Client(h.server) as client:
        success(
            await client.call_tool(
                "casa_list_document_structure_suggestions", {"document_id": "doc-one", "limit": 1}
            )
        )
    assert h.app.action_store.remaining_bytes() == MAX_BYTES


def test_document_status_has_no_workflow_counts_or_private_fields() -> None:
    document = HomeDocument.model_validate(
        {
            "id": "doc-one",
            "original_filename": SECRET,
            "uploaded_by_name": SECRET,
            "signed_url": "https://example.invalid/" + SECRET,
            "extraction": {
                "status": "completed",
                "pending_count": 2,
                "pending_structure_count": 3,
                "accepted_count": 4,
                "dismissed_count": 5,
                "already_handled_count": 6,
            },
        }
    )
    projected = _document(document, [])
    assert "pending_count" not in projected.model_dump_json()
    assert "dismissed_count" not in projected.model_dump_json()
    assert SECRET not in projected.model_dump_json()
