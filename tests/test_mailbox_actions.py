"""Exact observed mailbox scopes through real MCP calls and explicit SDK fakes."""

import inspect
import json

import pytest
from action_fakes import FakeActions
from casahome import CasaApi, is_unverified
from casahome.mail_workflows import ProvisionalMailMixin
from casahome.models.mail_workflows import MailboxAutoArchiveResponse
from mcp import Client
from test_actions import harness, token
from test_tools import HOME, MODES, SECOND_HOME, SECRET, failed, guard_sockets, settings, success

from casahome_mcp.action_protocol import CasaActionsProtocol
from casahome_mcp.actions.store import CONSENT_WARNING
from casahome_mcp.actions.tools import ACTION_METHODS, ACTION_TOOLS

RECIPIENT_TOOL = "casa_prepare_add_mailbox_recipient"
ARCHIVE_TOOL = "casa_prepare_update_mailbox_auto_archive"
RECIPIENT: dict[str, object] = {"first_name": " Élodie ", "last_name": "O'Fixture"}
MAILBOX_CASES: tuple[tuple[str, dict[str, object], tuple[object, ...]], ...] = (
    (RECIPIENT_TOOL, RECIPIENT, (HOME, " Élodie ", "O'Fixture", None)),
    (ARCHIVE_TOOL, {"mailbox_auto_archive_days": 30}, (HOME, 30)),
    (ARCHIVE_TOOL, {"mailbox_auto_archive_days": None}, (HOME, None)),
)


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    guard_sockets(monkeypatch)


def test_protocol_matches_promoted_sdk_mail_methods() -> None:
    # Pickup creation needs an official upload receipt the SDK can't obtain.
    unexposed = {"create_package_pickup_item"}
    methods = {name for name in vars(ProvisionalMailMixin) if not name.startswith("_")}
    assert methods & ACTION_METHODS == methods - unexposed
    assert methods & {name.removeprefix("casa_prepare_") for name in ACTION_TOOLS} == (
        methods - unexposed
    )
    for name in ("add_mailbox_recipient", "update_mailbox_auto_archive"):
        assert not is_unverified(getattr(CasaApi, name))
    # upload_document deliberately narrows the SDK source to immutable bytes.
    for name in ACTION_METHODS - {"upload_document"}:
        assert inspect.signature(getattr(CasaActionsProtocol, name), eval_str=True) == (
            inspect.signature(getattr(CasaApi, name), eval_str=True)
        )


@pytest.mark.parametrize("mode", MODES)
async def test_canonical_tool_schemas_and_annotations(mode: str) -> None:
    h = harness()
    async with Client(h.server, mode=mode) as client:
        listing = await client.list_tools()
    assert len(listing.tools) == 109
    assert len(ACTION_METHODS) == 50 and len(ACTION_TOOLS) == 52
    for tool in listing.tools:
        if tool.name not in {RECIPIENT_TOOL, ARCHIVE_TOOL}:
            continue
        assert tool.description and CONSENT_WARNING in tool.description
        assert "Requires ACTIONS only." in tool.description
        assert tool.annotations is not None
        assert tool.annotations.read_only_hint is False
        assert tool.annotations.destructive_hint is False
        assert tool.annotations.idempotent_hint is False
        assert tool.annotations.open_world_hint is False
        properties = tool.input_schema["properties"]
        if tool.name == RECIPIENT_TOOL:
            assert set(properties) == {"home_id", "first_name", "last_name"}
            assert set(tool.input_schema["required"]) == {"first_name", "last_name"}
            for name in ("first_name", "last_name"):
                assert properties[name]["type"] == "string"
                assert properties[name]["minLength"] == 1
                assert properties[name]["maxLength"] == 256
        else:
            assert set(properties) == {"home_id", "mailbox_auto_archive_days"}
            assert set(tool.input_schema["required"]) == {"mailbox_auto_archive_days"}
            field = properties["mailbox_auto_archive_days"]
            assert "default" not in field
            assert {branch["type"] for branch in field["anyOf"]} == {"integer", "null"}
            assert (
                next(branch for branch in field["anyOf"] if branch["type"] == "integer")["const"]
                == 30
            )


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("name,arguments,expected", MAILBOX_CASES)
async def test_actions_only_gate_exact_preview_and_status_only_result(
    mode: str,
    name: str,
    arguments: dict[str, object],
    expected: tuple[object, ...],
) -> None:
    h = harness(messages=False, uploads=False)
    fake = FakeActions(h.fake)
    h.app.actions = fake
    async with Client(h.server, mode=mode) as client:
        prepared = success(await client.call_tool(name, arguments))
        assert prepared["warning"] == CONSENT_WARNING
        assert prepared["expires_in_seconds"] == 300
        preview = prepared["preview"]
        assert isinstance(preview, dict)
        assert {key: value for key, value in preview.items() if key != "risk"} == arguments
        if name == RECIPIENT_TOOL:
            assert "may change account mail handling" in str(preview["risk"])
        else:
            assert "Retention and disposal behavior is UNVERIFIED" in str(preview["risk"])
            assert "no effect" in str(preview["risk"])
        assert fake.calls == h.fake.calls == []
        selected = token(prepared)
        call = {"confirmation_token": selected, "confirmed": False}
        assert (
            success(await client.call_tool("casa_execute_action", call))["outcome"]
            == "NOT_EXECUTED"
        )
        assert fake.calls == []
        call["confirmed"] = True
        completed = success(await client.call_tool("casa_execute_action", call))
        assert completed["outcome"] == "SUCCEEDED"
        for forbidden in ("first_name", "last_name", "recipient", "address", "kind", SECRET):
            # Operation names intentionally identify the requested method.
            assert forbidden not in json.dumps(
                {k: v for k, v in completed.items() if k != "operation"}
            )
        assert fake.calls == [(name.removeprefix("casa_prepare_"), expected)]
        failed(await client.call_tool("casa_execute_action", call), "INVALID_CONFIRMATION")
        assert len(fake.calls) == 1
        assert h.fake.calls == []


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("field", ["first_name", "last_name"])
@pytest.mark.parametrize(
    "value",
    [
        "",
        "x" * 257,
        None,
        1,
        True,
        [],
        {},
        SECRET + "\n",
        SECRET + "\t",
        SECRET + "\r",
        SECRET + "\u200b",
        SECRET + "\x00",
    ],
)
async def test_recipient_names_strict_and_private(
    mode: str,
    field: str,
    value: object,
    caplog: pytest.LogCaptureFixture,
) -> None:
    h = harness(actions=False)
    fake = FakeActions(h.fake)
    h.app.actions = fake
    async with Client(h.server, mode=mode) as client:
        failed(
            await client.call_tool(RECIPIENT_TOOL, {**RECIPIENT, field: value}), "INVALID_ARGUMENT"
        )
    assert fake.calls == h.fake.calls == []
    assert SECRET not in caplog.text


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize(
    "value",
    [
        30.0,
        0,
        29,
        31,
        -30,
        True,
        False,
        "30",
        "30.0",
        "null",
        "true",
        "false",
        '"30"',
        {},
        [],
        {"token": SECRET},
        SECRET,
    ],
)
async def test_archive_literal_null_union_rejects_coercion_and_json_string_preparse(
    mode: str,
    value: object,
    caplog: pytest.LogCaptureFixture,
) -> None:
    h = harness(actions=False)
    fake = FakeActions(h.fake)
    h.app.actions = fake
    async with Client(h.server, mode=mode) as client:
        failed(
            await client.call_tool(ARCHIVE_TOOL, {"mailbox_auto_archive_days": value}),
            "INVALID_ARGUMENT",
        )
    assert fake.calls == h.fake.calls == []
    assert SECRET not in caplog.text


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize(
    "name,arguments",
    [
        (RECIPIENT_TOOL, {}),
        (RECIPIENT_TOOL, {"first_name": "one"}),
        (RECIPIENT_TOOL, {"last_name": "two"}),
        (ARCHIVE_TOOL, {}),
        *[
            (RECIPIENT_TOOL, {**RECIPIENT, key: value})
            for key, value in (
                ("business_name", None),
                ("business_name", SECRET),
                ("kind", "person"),
                ("is_primary", False),
                ("always_included", True),
                ("recipient_id", SECRET),
            )
        ],
        (ARCHIVE_TOOL, {"mailbox_auto_archive_days": 30, "package_auto_archive_days": 30}),
        (ARCHIVE_TOOL, {"mailbox_auto_archive_days": None, "allow_actions": True}),
    ],
)
async def test_missing_and_unobserved_fields_rejected_before_policy(
    mode: str,
    name: str,
    arguments: dict[str, object],
) -> None:
    h = harness(actions=False)
    fake = FakeActions(h.fake)
    h.app.actions = fake
    async with Client(h.server, mode=mode) as client:
        failed(await client.call_tool(name, arguments), "INVALID_ARGUMENT")
    assert fake.calls == h.fake.calls == []


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("name,arguments,expected", MAILBOX_CASES)
@pytest.mark.parametrize(
    "update,code",
    [
        ({"allow_actions": False}, "ACTIONS_DISABLED"),
        ({"refresh_token": None}, "AUTH_NOT_CONFIGURED"),
        ({"homes": ()}, "HOME_NOT_ALLOWED"),
    ],
)
async def test_execute_rechecks_action_gate_auth_and_home(
    mode: str,
    name: str,
    arguments: dict[str, object],
    expected: tuple[object, ...],
    update: dict[str, object],
    code: str,
) -> None:
    h = harness(messages=False, uploads=False)
    fake = FakeActions(h.fake)
    h.app.actions = fake
    async with Client(h.server, mode=mode) as client:
        prepared = success(await client.call_tool(name, arguments))
        original = h.app.settings
        h.app.settings = original.model_copy(update=update)
        call = {"confirmation_token": token(prepared), "confirmed": True}
        failed(await client.call_tool("casa_execute_action", call), code)
        assert fake.calls == []
        h.app.settings = original
        assert (
            success(await client.call_tool("casa_execute_action", call))["outcome"] == "SUCCEEDED"
        )
        assert fake.calls == [(name.removeprefix("casa_prepare_"), expected)]


@pytest.mark.parametrize("mode", MODES)
async def test_explicit_home_names_bounds_and_cancel_keep_exact_payload(mode: str) -> None:
    h = harness(messages=False, uploads=False)
    h.app.settings = h.app.settings.model_copy(
        update={"homes": settings(homes=(HOME, SECOND_HOME)).homes}
    )
    fake = FakeActions(h.fake)
    h.app.actions = fake
    names = {"first_name": "x", "last_name": "y" * 256}
    async with Client(h.server, mode=mode) as client:
        failed(await client.call_tool(RECIPIENT_TOOL, names), "HOME_REQUIRED")
        prepared = success(
            await client.call_tool(RECIPIENT_TOOL, {**names, "home_id": SECOND_HOME})
        )
        assert prepared["home_id"] == SECOND_HOME
        selected = token(prepared)
        cancelled = success(
            await client.call_tool("casa_cancel_action", {"confirmation_token": selected})
        )
        assert cancelled["outcome"] == "CANCELLED"
        failed(
            await client.call_tool(
                "casa_execute_action", {"confirmation_token": selected, "confirmed": True}
            ),
            "INVALID_CONFIRMATION",
        )
        assert fake.calls == []
        prepared = success(
            await client.call_tool(RECIPIENT_TOOL, {**names, "home_id": SECOND_HOME})
        )
        await client.call_tool(
            "casa_execute_action", {"confirmation_token": token(prepared), "confirmed": True}
        )
    assert fake.calls == [("add_mailbox_recipient", (SECOND_HOME, "x", "y" * 256, None))]


async def test_archive_unsuccessful_response_is_unknown_not_raw(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    h = harness()
    fake = FakeActions(h.fake)
    h.app.actions = fake

    async def unsuccessful(home: str, days: int | None) -> MailboxAutoArchiveResponse:
        await fake.record("update_mailbox_auto_archive", home, days)
        return MailboxAutoArchiveResponse.model_validate(
            {"success": False, "mailbox_auto_archive_days": days, "message": SECRET}
        )

    monkeypatch.setattr(fake, "update_mailbox_auto_archive", unsuccessful)
    async with Client(h.server) as client:
        prepared = success(
            await client.call_tool(ARCHIVE_TOOL, {"mailbox_auto_archive_days": None})
        )
        call = {"confirmation_token": token(prepared), "confirmed": True}
        assert success(await client.call_tool("casa_execute_action", call))["outcome"] == "UNKNOWN"
        failed(await client.call_tool("casa_execute_action", call), "INVALID_CONFIRMATION")
    assert fake.calls == [("update_mailbox_auto_archive", (HOME, None))]
