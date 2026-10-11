"""Preview and commit security contracts via real MCP v2 calls, synthetic SDK only."""

import ast
import asyncio
import hashlib
import json
import os
from pathlib import Path

import pytest
from action_fakes import FakeActions
from casahome.models.ai import CasaAIMessagesResponse
from mcp import Client
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import JsonValue
from test_tools import (
    ENTITY,
    HOME,
    MODES,
    SECRET,
    Harness,
    failed,
    guard_sockets,
    settings,
    success,
)

from casahome_mcp.action_protocol import CasaActionsProtocol
from casahome_mcp.actions.models import ActionResult
from casahome_mcp.actions.store import MAX_BYTES, MAX_PENDING, ActionStore
from casahome_mcp.actions.tools import ACTION_METHODS, ACTION_TOOLS, execute
from casahome_mcp.actions.uploads import LOCAL_FILE_CAP, snapshot_file
from casahome_mcp.config import ConfigurationError, Settings
from casahome_mcp.coverage_projections import project_ai_history

CASES: tuple[tuple[str, dict[str, object]], ...] = (
    ("move_entity_to_room", {"entity_id": ENTITY, "room_id": HOME}),
    ("rate_ai_message", {"message_id": "message-one", "rating": "good"}),
    ("respond_to_suggested_todo", {"suggestion_id": "suggestion-one", "decision": "accept"}),
    ("send_todo_to_concierge", {"todo_id": "todo-one"}),
    (
        "answer_todo_question",
        {
            "todo_id": "todo-one",
            "round_id": "round-one",
            "question_id": "question-one",
            "answer": {
                "kind": "single_select",
                "selected_option_index": 0,
                "other_text": "Line one\nLine two",
            },
        },
    ),
    (
        "submit_todo_question_round",
        {
            "todo_id": "todo-one",
            "round_id": "round-one",
            "answers": [
                {
                    "question_id": "question-one",
                    "input_kind": "multi_select",
                    "selected_option_indexes": [0, 2],
                }
            ],
        },
    ),
    (
        "update_autopilot_plan",
        {
            "plan_id": "plan-one",
            "enabled": False,
            "selected_cadence": "every_quarter",
            "next_desired_occurrence_date": "2000-01-01",
        },
    ),
    (
        "update_notification_settings",
        {"settings": [{"notification_type": "type-one", "channel": "push", "enabled": False}]},
    ),
    ("send_ai_message", {"text": "Line one\nLine two"}),
    ("send_request_message", {"request_id": "request-one", "content": "Line one\nLine two"}),
    ("create_todo_result", {"content": "Line one\nLine two"}),
    ("delete_todo", {"todo_id": "todo-one"}),
    ("update_entity_model", {"entity_id": ENTITY, "model_name": "New model"}),
    (
        "respond_to_document_structure_suggestion",
        {
            "document_id": "doc-one",
            "suggestion_id": "suggestion-one",
            "decision": "accepted",
            "expected_values": [],
        },
    ),
)


@pytest.fixture(autouse=True)
def deny_network(monkeypatch: pytest.MonkeyPatch) -> None:
    guard_sockets(monkeypatch)


def harness(*, actions: bool = True, messages: bool = True, uploads: bool = True) -> Harness:
    configured = settings().model_copy(
        update={"allow_actions": actions, "allow_messages": messages, "allow_uploads": uploads}
    )
    return Harness(configured)


def token(payload: dict[str, object]) -> str:
    value = payload["confirmation_token"]
    assert isinstance(value, str)
    return value


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("operation,arguments", CASES)
async def test_prepare_then_false_then_execute_then_replay(
    mode: str,
    operation: str,
    arguments: dict[str, object],
) -> None:
    h = harness()
    actions = FakeActions(h.fake)
    h.app.actions = actions
    async with Client(h.server, mode=mode) as client:
        prepared = success(await client.call_tool("casa_prepare_" + operation, arguments))
        assert h.fake.calls == actions.calls == []
        assert prepared["home_id"] == HOME
        assert prepared["expires_in_seconds"] == 300
        assert "NOT proof" in str(prepared["warning"])
        call = {"confirmation_token": token(prepared), "confirmed": False}
        assert (
            success(await client.call_tool("casa_execute_action", call))["outcome"]
            == "NOT_EXECUTED"
        )
        assert actions.calls == []
        call["confirmed"] = True
        completed = success(await client.call_tool("casa_execute_action", call))
        assert completed["outcome"] == "SUCCEEDED"
        assert SECRET not in json.dumps(completed)
        if operation == "create_todo_result":
            assert completed["needs_support_confirmation"] is True
        failed(await client.call_tool("casa_execute_action", call), "INVALID_CONFIRMATION")
        assert [name for name, _ in actions.calls] == [operation]
        assert h.fake.calls == []


@pytest.mark.parametrize("operation,arguments", CASES)
async def test_all_actions_default_deny(operation: str, arguments: dict[str, object]) -> None:
    h = Harness(settings())
    h.app.actions = FakeActions(h.fake)
    async with Client(h.server) as client:
        failed(await client.call_tool("casa_prepare_" + operation, arguments), "ACTIONS_DISABLED")
    assert h.fake.calls == []


@pytest.mark.parametrize("gate", ["allow_actions", "allow_messages"])
async def test_recheck_policy_before_execution(gate: str) -> None:
    h = harness()
    fake = FakeActions(h.fake)
    h.app.actions = fake
    async with Client(h.server) as client:
        prepared = success(
            await client.call_tool("casa_prepare_send_ai_message", {"text": "hello"})
        )
        h.app.settings = h.app.settings.model_copy(update={gate: False})
        failed(
            await client.call_tool(
                "casa_execute_action", {"confirmation_token": token(prepared), "confirmed": True}
            ),
            "ACTIONS_DISABLED" if gate == "allow_actions" else "MESSAGES_DISABLED",
        )
    assert fake.calls == []


async def test_execute_rechecks_home_and_auth() -> None:
    h = harness()
    fake = FakeActions(h.fake)
    h.app.actions = fake
    async with Client(h.server) as client:
        prepared = success(
            await client.call_tool("casa_prepare_delete_todo", {"todo_id": "todo-one"})
        )
        original = h.app.settings
        h.app.settings = original.model_copy(update={"homes": ()})
        failed(
            await client.call_tool(
                "casa_execute_action", {"confirmation_token": token(prepared), "confirmed": True}
            ),
            "HOME_NOT_ALLOWED",
        )
        h.app.settings = original.model_copy(update={"refresh_token": None})
        failed(
            await client.call_tool(
                "casa_execute_action", {"confirmation_token": token(prepared), "confirmed": True}
            ),
            "AUTH_NOT_CONFIGURED",
        )
    assert fake.calls == []


async def test_concurrent_execution_consumes_before_await() -> None:
    h = harness()
    fake = FakeActions(h.fake)
    fake.release = asyncio.Event()
    h.app.actions = fake
    async with Client(h.server) as client:
        prepared = success(
            await client.call_tool("casa_prepare_delete_todo", {"todo_id": "todo-one"})
        )
        selected = token(prepared)
        first = asyncio.create_task(execute(h.app, selected, True))
        await fake.entered.wait()
        with pytest.raises(ToolError, match="INVALID_CONFIRMATION"):
            await execute(h.app, selected, True)
        fake.release.set()
        assert (await first).outcome == "SUCCEEDED"
    assert len(fake.calls) == 1


@pytest.mark.parametrize("error", [TimeoutError(SECRET), ValueError(SECRET)])
async def test_unknown_outcome_no_retry_or_error_values(error: Exception) -> None:
    h = harness()
    fake = FakeActions(h.fake)
    fake.error = error
    h.app.actions = fake
    async with Client(h.server) as client:
        prepared = success(
            await client.call_tool("casa_prepare_delete_todo", {"todo_id": "todo-one"})
        )
        call = {"confirmation_token": token(prepared), "confirmed": True}
        response = success(await client.call_tool("casa_execute_action", call))
        assert response["outcome"] == "UNKNOWN"
        assert SECRET not in json.dumps(response)
        failed(await client.call_tool("casa_execute_action", call), "INVALID_CONFIRMATION")
    assert len(fake.calls) == 1


async def noop(api: CasaActionsProtocol, home: str) -> ActionResult:
    return ActionResult(outcome="SUCCEEDED", operation="delete_todo", home_id=home)


def test_store_expiry_cancel_capacity_and_private_errors() -> None:
    now = [0.0]
    store = ActionStore(lambda: now[0])
    preview: dict[str, JsonValue] = {"todo_id": "todo-one"}
    first = store.add(HOME, "delete_todo", "actions", preview, noop)
    selected = first["confirmation_token"]
    assert isinstance(selected, str)
    now[0] = 300
    with pytest.raises(ToolError, match="INVALID_CONFIRMATION"):
        store.get(selected)
    tokens = [
        store.add(HOME, "delete_todo", "actions", preview, noop)["confirmation_token"]
        for _ in range(MAX_PENDING)
    ]
    assert len(set(tokens)) == MAX_PENDING
    with pytest.raises(ToolError, match="CAPACITY_EXCEEDED"):
        store.add(HOME, "delete_todo", "actions", preview, noop)
    store.clear()
    large = store.add(HOME, "upload_document", "uploads", preview, noop, size_bytes=MAX_BYTES)
    with pytest.raises(ToolError, match="CAPACITY_EXCEEDED"):
        store.add(HOME, "upload_document", "uploads", preview, noop, size_bytes=1)
    large_token = large["confirmation_token"]
    assert isinstance(large_token, str)
    store.consume(large_token)
    store.check_capacity(MAX_BYTES)


@pytest.mark.parametrize("mode", MODES)
async def test_upload_snapshot_bound_to_bytes_not_mutable_path(tmp_path: Path, mode: str) -> None:
    path = tmp_path / "synthetic.txt"
    original = b"synthetic upload bytes"
    path.write_bytes(original)
    h = harness()
    fake = FakeActions(h.fake)
    h.app.actions = fake
    async with Client(h.server, mode=mode) as client:
        prepared = success(
            await client.call_tool(
                "casa_prepare_upload_document",
                {
                    "file_path": str(path),
                    "filename": "arbitrary/fixture.txt",
                    "mimetype": "text/plain",
                    "find_todos": False,
                },
            )
        )
        assert fake.calls == []
        preview = prepared["preview"]
        assert isinstance(preview, dict)
        assert preview["sha256"] == hashlib.sha256(original).hexdigest()
        assert preview["size_bytes"] == len(original)
        assert preview["basename"] == "fixture.txt"
        assert str(path) not in json.dumps(prepared)
        assert original.decode() not in json.dumps(prepared)
        path.write_bytes(b"changed after preview")
        completed = success(
            await client.call_tool(
                "casa_execute_action", {"confirmation_token": token(prepared), "confirmed": True}
            )
        )
        assert completed["outcome"] == "SUCCEEDED"
        assert fake.calls == [
            ("upload_document", (HOME, original, "fixture.txt", "text/plain", False))
        ]


@pytest.mark.parametrize(
    "actions,messages,uploads,code",
    [
        (False, False, False, "ACTIONS_DISABLED"),
        (True, False, False, "UPLOADS_DISABLED"),
    ],
)
async def test_upload_gate_before_file_or_sdk_io(
    actions: bool,
    messages: bool,
    uploads: bool,
    code: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse(*args: object, **kwargs: object) -> bytes:
        raise AssertionError("Must not open any file")

    monkeypatch.setattr("casahome_mcp.actions.tools.snapshot_file", refuse)
    h = harness(actions=actions, messages=messages, uploads=uploads)
    h.app.actions = FakeActions(h.fake)
    async with Client(h.server) as client:
        failed(
            await client.call_tool(
                "casa_prepare_upload_document",
                {
                    "file_path": "/synthetic/no-such-file",
                    "filename": "fixture.txt",
                    "mimetype": "text/plain",
                    "find_todos": True,
                },
            ),
            code,
        )
    assert h.fake.calls == []


def test_source_write_allowlist_and_no_generic_http() -> None:
    import casahome_mcp

    root = Path(casahome_mcp.__file__).parent
    invocations: set[str] = set()
    for path in (root / "actions").glob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "api"
            ):
                invocations.add(node.func.attr)
        for forbidden in (".client", ".post(", ".put(", ".delete(", ".patch(", "getattr(api"):
            assert forbidden not in path.read_text()
    assert invocations == ACTION_METHODS
    assert {
        name for name in vars(CasaActionsProtocol) if not name.startswith("_")
    } == ACTION_METHODS


async def test_manifest_exact_and_action_annotations() -> None:
    assert {"casa_prepare_" + name for name, _ in CASES} | {
        "casa_prepare_upload_document",
        "casa_execute_action",
        "casa_cancel_action",
    } == ACTION_TOOLS
    h = harness()
    async with Client(h.server) as client:
        listing = await client.list_tools()
        for tool in listing.tools:
            if tool.name not in ACTION_TOOLS:
                continue
            assert tool.annotations is not None
            assert tool.annotations.read_only_hint is False
            assert tool.annotations.idempotent_hint is False
            assert tool.annotations.destructive_hint is (tool.name == "casa_execute_action")
            assert tool.description
            if tool.name.startswith("casa_prepare_"):
                assert "specific approval" in tool.description


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize(
    "operation,arguments",
    [
        ("respond_to_suggested_todo", {"suggestion_id": "one", "decision": "decline"}),
        ("rate_ai_message", {"message_id": "one", "rating": "clear"}),
        ("send_ai_message", {"text": "message", "upload_ids": [SECRET]}),
        ("send_request_message", {"request_id": "one", "content": "text", "attachments": []}),
        ("create_todo_result", {"content": "text", "attachments": []}),
        (
            "answer_todo_question",
            {
                "todo_id": "one",
                "round_id": "two",
                "question_id": "three",
                "skip": True,
                "answer": {"kind": "single_select", "selected_option_index": 0},
            },
        ),
        (
            "answer_todo_question",
            {
                "todo_id": "one",
                "round_id": "two",
                "question_id": "three",
                "answer": {"kind": "single_select", "selected_option_index": 1.0},
            },
        ),
        (
            "answer_todo_question",
            {
                "todo_id": "one",
                "round_id": "two",
                "question_id": "three",
                "answer": json.dumps({"kind": "single_select", "selected_option_index": 0}),
            },
        ),
        (
            "respond_to_document_structure_suggestion",
            {"document_id": "one", "suggestion_id": "two", "decision": "accepted"},
        ),
        (
            "respond_to_document_structure_suggestion",
            {
                "document_id": "one",
                "suggestion_id": "two",
                "decision": "accept",
                "expected_values": [],
            },
        ),
        ("update_entity_model", {"entity_id": ENTITY, "model_name": "text", "props": []}),
        (
            "update_notification_settings",
            {"settings": [{"notification_type": "one", "channel": "email", "enabled": True}]},
        ),
        (
            "update_notification_settings",
            {"settings": [{"notification_type": "one\n", "channel": "push", "enabled": True}]},
        ),
        ("send_ai_message", {"text": "private\u200b" + SECRET}),
        ("send_ai_message", {"text": "private\x00" + SECRET}),
    ],
)
async def test_narrow_scope_and_private_prehandler_validation(
    mode: str,
    operation: str,
    arguments: dict[str, object],
    caplog: pytest.LogCaptureFixture,
) -> None:
    h = harness()
    fake = FakeActions(h.fake)
    h.app.actions = fake
    async with Client(h.server, mode=mode) as client:
        failed(await client.call_tool("casa_prepare_" + operation, arguments), "INVALID_ARGUMENT")
    assert fake.calls == h.fake.calls == []
    assert SECRET not in caplog.text


@pytest.mark.parametrize("kind", ["directory", "fifo", "empty", "oversize"])
def test_snapshot_nonregular_or_invalid_files_never_read(tmp_path: Path, kind: str) -> None:
    path = tmp_path / "synthetic"
    if kind == "directory":
        path.mkdir()
    elif kind == "fifo":
        os.mkfifo(path)
    else:
        path.write_bytes(b"" if kind == "empty" else b"oversize")
    with pytest.raises(ToolError, match="INVALID_FILE"):
        snapshot_file(str(path), 3)


def test_snapshot_allows_explicit_symlink_to_regular_fixture(tmp_path: Path) -> None:
    path = tmp_path / "synthetic.txt"
    path.write_bytes(b"fixture")
    symlink = tmp_path / "link.txt"
    symlink.symlink_to(path)
    assert snapshot_file(str(symlink), LOCAL_FILE_CAP) == b"fixture"


async def test_cancel_upload_releases_bytes_and_shutdown_clears_store(tmp_path: Path) -> None:
    path = tmp_path / "synthetic.txt"
    path.write_bytes(b"fixture")
    h = harness()
    fake = FakeActions(h.fake)
    h.app.actions = fake
    async with Client(h.server) as client:
        args = {
            "file_path": str(path),
            "filename": "fixture.txt",
            "mimetype": "text/plain",
            "find_todos": True,
        }
        prepared = success(await client.call_tool("casa_prepare_upload_document", args))
        assert h.app.action_store.remaining_bytes() == MAX_BYTES - 7
        call = {"confirmation_token": token(prepared)}
        cancelled = success(await client.call_tool("casa_cancel_action", call))
        assert cancelled["outcome"] == "CANCELLED"
        assert h.app.action_store.remaining_bytes() == MAX_BYTES
        failed(
            await client.call_tool("casa_execute_action", {**call, "confirmed": True}),
            "INVALID_CONFIRMATION",
        )
        another = success(await client.call_tool("casa_prepare_upload_document", args))
    assert h.app.action_store.remaining_bytes() == MAX_BYTES
    with pytest.raises(ToolError, match="INVALID_CONFIRMATION"):
        h.app.action_store.get(token(another))
    assert fake.calls == []


async def test_upload_rechecks_upload_gate_and_uses_policy_before_file_io(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "synthetic.txt"
    path.write_bytes(b"fixture")
    h = harness()
    fake = FakeActions(h.fake)
    h.app.actions = fake
    async with Client(h.server) as client:
        args = {
            "file_path": str(path),
            "filename": "fixture.txt",
            "mimetype": "text/plain",
            "find_todos": True,
        }
        prepared = success(await client.call_tool("casa_prepare_upload_document", args))
        h.app.settings = h.app.settings.model_copy(update={"allow_uploads": False})
        failed(
            await client.call_tool(
                "casa_execute_action", {"confirmation_token": token(prepared), "confirmed": True}
            ),
            "UPLOADS_DISABLED",
        )
        h.app.settings = h.app.settings.model_copy(update={"allow_uploads": True})

        def refuse(*args: object, **kwargs: object) -> bytes:
            raise AssertionError("Policy rejection must precede file reads")

        monkeypatch.setattr("casahome_mcp.actions.tools.snapshot_file", refuse)
        failed(
            await client.call_tool(
                "casa_prepare_upload_document", {**args, "mimetype": "not/allowed"}
            ),
            "INVALID_FILE",
        )
    assert fake.calls == []


@pytest.mark.parametrize("key", ["CASA_ALLOW_ACTIONS", "CASA_ALLOW_MESSAGES", "CASA_ALLOW_UPLOADS"])
def test_flags_strict_and_default_deny(key: str) -> None:
    default = Settings.from_env({})
    assert not default.allow_actions and not default.allow_messages and not default.allow_uploads
    with pytest.raises(ConfigurationError, match=key):
        Settings.from_env({key: SECRET})
    configured = Settings.from_env({key: "TRUE"})
    assert getattr(configured, key.removeprefix("CASA_").lower()) is True


async def test_expired_protocol_token_and_unknown_token_share_fixed_error() -> None:
    h = harness()
    h.app.actions = FakeActions(h.fake)
    now = [0.0]
    h.app.action_store = ActionStore(lambda: now[0])
    async with Client(h.server) as client:
        prepared = success(await client.call_tool("casa_prepare_delete_todo", {"todo_id": "one"}))
        now[0] = 301
        expired = await client.call_tool(
            "casa_execute_action", {"confirmation_token": token(prepared), "confirmed": True}
        )
        unknown = await client.call_tool(
            "casa_execute_action", {"confirmation_token": "x" * 43, "confirmed": True}
        )
        assert expired.content == unknown.content
        failed(expired, "INVALID_CONFIRMATION")


async def test_question_snapshot_survives_input_and_preview_mutation() -> None:
    h = harness()
    fake = FakeActions(h.fake)
    h.app.actions = fake
    async with Client(h.server) as client:
        arguments = {
            "todo_id": "todo-one",
            "round_id": "round-one",
            "question_id": "question-one",
            "answer": {"kind": "multi_select", "selected_option_indexes": [0, 2]},
        }
        prepared = success(await client.call_tool("casa_prepare_answer_todo_question", arguments))
        arguments["answer"] = {"kind": "single_select", "selected_option_index": 5}
        prepared["preview"] = {"changed": True}
        await client.call_tool(
            "casa_execute_action", {"confirmation_token": token(prepared), "confirmed": True}
        )
    assert fake.calls == [
        (
            "answer_todo_question",
            (
                HOME,
                "todo-one",
                "round-one",
                "question-one",
                {"kind": "multi_select", "selected_option_indexes": [0, 2], "other_text": None},
                False,
            ),
        )
    ]


@pytest.mark.parametrize("mode", MODES)
async def test_confirmed_execution_deadline_is_unknown_and_token_consumed(mode: str) -> None:
    h = harness()
    fake = FakeActions(h.fake)
    fake.release = asyncio.Event()
    h.app.actions = fake
    h.app.deadline_seconds = 0.01
    async with Client(h.server, mode=mode) as client:
        prepared = success(await client.call_tool("casa_prepare_delete_todo", {"todo_id": "one"}))
        call = {"confirmation_token": token(prepared), "confirmed": True}
        assert success(await client.call_tool("casa_execute_action", call))["outcome"] == "UNKNOWN"
        failed(await client.call_tool("casa_execute_action", call), "INVALID_CONFIRMATION")
    assert len(fake.calls) == 1


def test_ai_data_todo_preserves_only_opted_in_allowlisted_fields() -> None:
    model = CasaAIMessagesResponse.model_validate(
        {
            "items": [
                {
                    "id": "message-one",
                    "parts": [
                        {"type": "text", "text": "fixture text"},
                        {
                            "type": "data-todo",
                            "data": {
                                "todo_id": "todo-one",
                                "title": "fixture title",
                                "status": "preparing",
                                "url": "https://example.invalid/" + SECRET,
                                "attachments": [SECRET],
                                "password": SECRET,
                            },
                        },
                        {"type": "future-part", "text": SECRET, "payload": {"token": SECRET}},
                    ],
                }
            ]
        }
    )
    for include in (False, True):
        data, warnings = project_ai_history(model, include_messages=include)
        serialized = data.model_dump_json()
        assert SECRET not in serialized
        assert "OPAQUE_MESSAGE_PARTS_OMITTED" in warnings
        assert ("fixture title" in serialized) is include
        assert ("todo-one" in serialized) is include
        assert ("fixture text" in serialized) is include
        assert ("data-todo" in serialized) is include
        assert "future-part" not in serialized
