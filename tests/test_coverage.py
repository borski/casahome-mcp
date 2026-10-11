"""New read contracts, privacy, bounded text and raw-input refusal in both MCP modes."""

import json

import pytest
from casahome import CasaApi
from coverage_cases import COVERAGE_CASES, TARGET
from coverage_fakes import AI_TEXT, BRIEF, EXCERPT, NOTES, OPAQUE_CURSOR, URL
from mcp import Client
from test_tools import (
    FORBIDDEN_HOME,
    HOME,
    MODES,
    SECRET,
    Harness,
    failed,
    guard_sockets,
    mapping,
    sequence,
    settings,
    success,
)

from casahome_mcp.coverage_projections import cursor


@pytest.fixture(autouse=True)
def reject_socket_access(monkeypatch: pytest.MonkeyPatch) -> None:
    guard_sockets(monkeypatch)


OPT_INS: tuple[tuple[str, dict[str, object], str, str], ...] = (
    ("casa_list_suggested_todos", {}, "include_brief", BRIEF),
    ("casa_get_todo", {"todo_id": "todo-one"}, "include_brief", BRIEF),
    ("casa_get_work_document_source", {"todo_id": "todo-one"}, "include_excerpts", EXCERPT),
    ("casa_get_ai_bootstrap", {}, "include_messages", AI_TEXT),
    ("casa_list_ai_history", {}, "include_messages", AI_TEXT),
    ("casa_list_purchases", {}, "include_notes", NOTES),
)


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("name,arguments,opt_in,marker", OPT_INS)
async def test_narratives_are_opt_in_and_both_channels_match(
    mode: str,
    name: str,
    arguments: dict[str, object],
    opt_in: str,
    marker: str,
) -> None:
    harness = Harness()
    async with Client(harness.server, mode=mode) as client:
        for include in (False, True):
            result = await client.call_tool(name, {**arguments, opt_in: include})
            success(result)
            assert (marker in json.dumps(result.structured_content)) is include
            assert (marker in result.content[0].model_dump_json()) is include
            for omitted in (
                SECRET,
                URL,
                "signed?",
                "original_text",
                "question_rounds",
                "attachments",
                "member_payment",
                "payload",
                "purchase_link",
                "event_cursor",
            ):
                assert omitted not in json.dumps(result.structured_content)


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("name,arguments,opt_in,marker", OPT_INS)
async def test_opt_ins_are_strict_and_never_echo_invalid_values(
    mode: str,
    name: str,
    arguments: dict[str, object],
    opt_in: str,
    marker: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    harness = Harness(settings(homes=(), token=False))
    invalid: tuple[object, ...] = (0, 1, "true", "false", SECRET, None, [], {})
    async with Client(harness.server, mode=mode) as client:
        for bad in invalid:
            failed(await client.call_tool(name, {**arguments, opt_in: bad}), "INVALID_ARGUMENT")
    assert not harness.fake.calls
    assert SECRET not in caplog.text


INVALID_FIELDS: tuple[tuple[str, dict[str, object], str], ...] = (
    ("casa_get_todo", {}, "todo_id"),
    ("casa_get_work_document_source", {}, "todo_id"),
    ("casa_list_paint_collections", {}, "brand_id"),
    ("casa_list_paint_colors", {}, "collection_id"),
    ("casa_list_documents", {}, "document_type"),
    ("casa_get_inventory_service_history", {"target_type": "entity"}, "target_id"),
    ("casa_get_room_photo_metadata", {}, "room_id"),
    ("casa_list_documents", {}, "cursor"),
    ("casa_list_ai_history", {}, "before"),
)


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("name,arguments,field", INVALID_FIELDS)
async def test_path_uuid_and_cursor_inputs_refuse_attacks_before_any_sdk_access(
    mode: str,
    name: str,
    arguments: dict[str, object],
    field: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    harness = Harness(settings(homes=(), token=False))
    bad_values: tuple[object, ...] = (
        "",
        "../" + SECRET,
        "%2F" + SECRET,
        SECRET + "?token=" + SECRET,
        SECRET + "#fragment",
        URL,
        SECRET + "\n",
        SECRET + "\u200b",
        '{"token":"' + SECRET + '"}',
        '["' + SECRET + '"]',
        "null",
        [],
        {},
        1.0,
        True,
        "x" * 2049,
    )
    async with Client(harness.server, mode=mode) as client:
        for bad in bad_values:
            failed(await client.call_tool(name, {**arguments, field: bad}), "INVALID_ARGUMENT")
    assert not harness.fake.calls
    assert SECRET not in caplog.text


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("field", ["page", "page_size", "upstream_limit"])
async def test_sdk_integer_controls_are_strict_in_raw_preprocessor(mode: str, field: str) -> None:
    name = "casa_list_completed_requests" if field != "upstream_limit" else "casa_list_documents"
    harness = Harness()
    bad_values: tuple[object, ...] = (0, -1, True, False, 1.0, "1", SECRET, [], {})
    async with Client(harness.server, mode=mode) as client:
        for bad in bad_values:
            failed(await client.call_tool(name, {field: bad}), "INVALID_ARGUMENT")
        if field != "page":
            failed(await client.call_tool(name, {field: 101}), "INVALID_ARGUMENT")
    assert not harness.fake.calls


@pytest.mark.parametrize("mode", MODES)
async def test_exact_selectors_home_target_and_no_extra_ids(mode: str) -> None:
    harness = Harness()
    async with Client(harness.server, mode=mode) as client:
        for args in (
            {},
            {"todo_id": "todo-one", "task_id": "task-one"},
            {"todo_id": "todo-one", "request_id": "request-one"},
            {"task_id": "task-one", "request_id": "request-one"},
        ):
            failed(
                await client.call_tool("casa_get_work_document_source", args), "INVALID_ARGUMENT"
            )
        failed(
            await client.call_tool("casa_get_inventory_service_history", {"target_type": "room"}),
            "INVALID_ARGUMENT",
        )
        failed(
            await client.call_tool(
                "casa_get_inventory_service_history",
                {"target_type": "home", "target_id": FORBIDDEN_HOME},
            ),
            "HOME_NOT_ALLOWED",
        )
        failed(
            await client.call_tool("casa_get_todo", {"todo_id": "todo-one", "entity_id": TARGET}),
            "INVALID_ARGUMENT",
        )
        assert not harness.fake.calls
        for kind, target in (("home", None), ("room", TARGET), ("entity", TARGET)):
            success(
                await client.call_tool(
                    "casa_get_inventory_service_history", {"target_type": kind, "target_id": target}
                )
            )
        assert harness.fake.calls == [
            ("inventory_service_history", (HOME, kind, HOME if target is None else target))
            for kind, target in (("home", None), ("room", TARGET), ("entity", TARGET))
        ]


@pytest.mark.parametrize("mode", MODES)
async def test_sdk_and_local_pagination_are_separate_and_cursors_roundtrip(mode: str) -> None:
    harness = Harness()
    harness.fake.completed.pagination.page = 3
    harness.fake.completed.pagination.page_size = 10
    harness.fake.documents_result.documents *= 3
    async with Client(harness.server, mode=mode) as client:
        completed = mapping(
            success(
                await client.call_tool(
                    "casa_list_completed_requests",
                    {
                        "page": 3,
                        "page_size": 10,
                        "offset": 10000,
                        "limit": 1,
                        "search": "Completed",
                    },
                )
            )["data"]
        )
        assert completed["upstream_pagination"] == {
            "page": 3,
            "page_size": 10,
            "total_count": 300,
            "total_pages": 3,
        }
        assert mapping(completed["page"])["total_in_response"] == 1
        assert mapping(completed["page"])["returned_count"] == 0
        doc = success(await client.call_tool("casa_list_documents", {"offset": 0, "limit": 1}))
        data = mapping(doc["data"])
        assert data["next_cursor"] == OPAQUE_CURSOR
        assert mapping(data["page"])["next_offset"] == 1
        assert "LOCAL_PAGE_TRUNCATED" in sequence(doc["warnings"])
        success(
            await client.call_tool(
                "casa_list_documents",
                {
                    "cursor": data["next_cursor"],
                    "upstream_limit": 10,
                    "offset": 1,
                    "limit": 1,
                    "q": "Warranty",
                    "document_type": "warranty",
                },
            )
        )
        history = mapping(success(await client.call_tool("casa_list_ai_history"))["data"])
        success(
            await client.call_tool(
                "casa_list_ai_history",
                {
                    "before": history["next_cursor"],
                    "upstream_limit": 10,
                },
            )
        )
    assert harness.fake.calls == [
        ("completed_requests", (HOME, 3, 10, "Completed")),
        ("documents", (HOME, None, 30, None, None, None)),
        ("documents", (HOME, OPAQUE_CURSOR, 10, "Warranty", "warranty", None)),
        ("casa_ai_messages", (HOME, None, None)),
        ("casa_ai_messages", (HOME, 10, OPAQUE_CURSOR)),
    ]


@pytest.mark.parametrize("value", [OPAQUE_CURSOR, "a.b.c", "next_cursor-1/+=", None])
def test_opaque_cursor_is_not_confused_with_url_or_auth(value: str | None) -> None:
    warnings: list[str] = []
    assert cursor(value, warnings) == value
    assert warnings == []


@pytest.mark.parametrize(
    "value", [URL, "//example.invalid/path", "www.example.invalid", "null", "x" * 2049, "abc\n"]
)
def test_unsafe_cursor_is_omitted_not_clipped(value: str) -> None:
    warnings: list[str] = []
    assert cursor(value, warnings) is None
    assert warnings == ["UNSAFE_CURSOR_OMITTED"]


@pytest.mark.parametrize("mode", MODES)
async def test_real_onboarding_timestamps_304_and_plan_flags_pricing(mode: str) -> None:
    harness = Harness()
    async with Client(harness.server, mode=mode) as client:
        events = mapping(
            mapping(success(await client.call_tool("casa_list_onboarding_calendar"))["data"])[
                "page"
            ]
        )
        assert sequence(events["items"]) == [
            {"id": "event-one", "start_at": 1700000000, "end_at": 1700003600}
        ]
        slots = mapping(
            mapping(success(await client.call_tool("casa_list_onboarding_availability"))["data"])[
                "page"
            ]
        )
        assert sequence(slots["items"]) == [{"start_time": 1700000000, "vendor_count": 1}]
        harness.fake.onboarding_calendar = None
        unchanged = mapping(
            success(await client.call_tool("casa_list_onboarding_calendar"))["data"]
        )
        assert unchanged == {"not_modified": True, "page": None}
        plans = mapping(
            mapping(success(await client.call_tool("casa_list_autopilot_plans"))["data"])["page"]
        )
        rows = [mapping(item) for item in sequence(plans["items"])]
        assert rows[0]["eligible"] is True and rows[0]["enabled"] is True
        assert rows[1]["eligible"] is False and rows[1]["enabled"] is None
        associations = [mapping(item) for item in sequence(rows[0]["associations"])]
        assert associations[1]["duration_minutes"] == 30
        assert associations[1]["price_usd_cents"] == 2500
        assert associations[1]["enabled"] is False


@pytest.mark.parametrize("mode", MODES)
async def test_new_marker_gate_is_dynamic_and_wins_before_auth(
    mode: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(CasaApi.vehicles, "__casa_unverified__", True, raising=False)
    harness = Harness(settings(enabled=False, token=False))
    async with Client(harness.server, mode=mode) as client:
        failed(await client.call_tool("casa_list_vehicles"), "UNVERIFIED_DISABLED")
        status = mapping(success(await client.call_tool("casa_get_status"))["data"])
        assert "casa_list_vehicles" in sequence(status["disabled_features"])
    assert not harness.fake.calls


@pytest.mark.parametrize("mode", MODES)
async def test_all_new_methods_scrub_sdk_errors(
    mode: str, caplog: pytest.LogCaptureFixture
) -> None:
    harness = Harness()
    harness.fake.error = RuntimeError(URL + SECRET)
    async with Client(harness.server, mode=mode) as client:
        for name, _, arguments, _ in COVERAGE_CASES:
            failed(await client.call_tool(name, arguments), "INTERNAL_ERROR")
    assert len(harness.fake.calls) == 24
    assert SECRET not in caplog.text
    assert URL not in caplog.text


@pytest.mark.parametrize("mode", MODES)
async def test_nested_urls_and_url_after_clip_boundary_never_leak(mode: str) -> None:
    harness = Harness()
    f = harness.fake
    f.suggestions.suggested_todos[0].title = URL
    f.suggestions.suggested_todos[0].prepared_brief = "x" * 2001 + " " + URL
    f.document_source.source = (
        f.document_source.source.model_copy(update={"name": URL})
        if f.document_source.source
        else None
    )
    f.ai_history.items[0].content = "x" * 2001 + " " + URL
    f.vehicles_result.vehicles[0].id = URL
    f.vehicles_result.vehicles[0].powertrain = (
        f.vehicles_result.vehicles[0].powertrain.model_copy(update={"display_name": URL})
        if f.vehicles_result.vehicles[0].powertrain
        else None
    )
    f.notifications.groups[0].types[0].channels[0].channel = URL
    f.plans[0].plans[0].pricing_policies[0].description = "x" * 2001 + " " + URL
    f.plans[0].plans[0].room_associations[0].room_name = URL
    async with Client(harness.server, mode=mode) as client:
        for name, args in (
            ("casa_list_suggested_todos", {"include_brief": True}),
            ("casa_get_work_document_source", {"todo_id": "todo-one", "include_excerpts": True}),
            ("casa_list_ai_history", {"include_messages": True}),
            ("casa_list_vehicles", {}),
            ("casa_get_notification_settings", {}),
            ("casa_list_autopilot_plans", {}),
        ):
            payload = success(await client.call_tool(name, args))
            serialized = json.dumps(payload)
            assert URL not in serialized and SECRET not in serialized
            assert "x" * 2000 not in serialized
            assert "URL_TEXT_OMITTED" in sequence(payload["warnings"])


@pytest.mark.parametrize("mode", MODES)
async def test_narrative_nested_limits_and_utf8_size_guard(mode: str) -> None:
    harness = Harness()
    harness.fake.todo_result.todo.prepared_brief = "界" * 2001
    harness.fake.notifications.groups[0].types *= 21
    harness.fake.plans[0].plans[0].room_associations *= 21
    async with Client(harness.server, mode=mode) as client:
        todo = success(
            await client.call_tool("casa_get_todo", {"todo_id": "todo-one", "include_brief": True})
        )
        assert mapping(mapping(todo["data"])["todo"])["prepared_brief"] == "界" * 2000
        assert "TEXT_TRUNCATED" in sequence(todo["warnings"])
        for name in ("casa_get_notification_settings", "casa_list_autopilot_plans"):
            payload = success(await client.call_tool(name))
            assert "NESTED_COLLECTION_TRUNCATED" in sequence(payload["warnings"])
        harness.fake.suggestions.suggested_todos *= 100
        failed(
            await client.call_tool(
                "casa_list_suggested_todos", {"include_brief": True, "limit": 100}
            ),
            "OUTPUT_TOO_LARGE",
        )
        success(
            await client.call_tool("casa_list_suggested_todos", {"include_brief": True, "limit": 1})
        )


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("value", [float("inf"), float("-inf"), float("nan")])
async def test_new_numeric_projections_fail_finite_validation(mode: str, value: float) -> None:
    harness = Harness()
    harness.fake.utilities.services[0].statements[0].total_amount_usd_due = value
    harness.fake.taxes.reports[0].total_tax_due = value
    async with Client(harness.server, mode=mode) as client:
        for name in ("casa_get_utilities_insights", "casa_get_property_taxes"):
            failed(await client.call_tool(name), "SCHEMA_MISMATCH")


@pytest.mark.parametrize("mode", MODES)
async def test_empty_read_envelopes_do_not_establish_item_shape_or_fabricate_totals(
    mode: str,
) -> None:
    harness = Harness()
    f = harness.fake
    f.suggestions.suggested_todos.clear()
    f.completed.items.clear()
    f.documents_result.documents.clear()
    f.vehicles_result.vehicles.clear()
    f.utilities.services.clear()
    f.taxes.reports.clear()
    f.purchases_result.pending_purchase_approvals.clear()
    f.purchases_result.approved_purchases.clear()
    f.purchases_result.purchased_items.clear()
    f.ai_history.items.clear()
    async with Client(harness.server, mode=mode) as client:
        for name in (
            "casa_list_suggested_todos",
            "casa_list_completed_requests",
            "casa_list_documents",
            "casa_list_vehicles",
            "casa_get_utilities_insights",
            "casa_get_property_taxes",
            "casa_list_purchases",
            "casa_list_ai_history",
        ):
            payload = success(await client.call_tool(name))
            assert payload["confidence"] == "VERIFIED"
            assert "UPSTREAM_COMPLETENESS_UNKNOWN" in sequence(payload["warnings"])
            local = mapping(mapping(payload["data"])["page"])
            assert local["items"] == []
            assert local["total_in_response"] == local["returned_count"] == 0
            assert local["next_offset"] is None
            assert local["pagination_scope"] == "single_upstream_response"


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("name,method,arguments,tail", COVERAGE_CASES)
async def test_each_new_home_input_is_uuid_guarded_before_union_preprocessing(
    mode: str,
    name: str,
    method: str,
    arguments: dict[str, object],
    tail: tuple[object, ...],
    caplog: pytest.LogCaptureFixture,
) -> None:
    harness = Harness()
    invalid: tuple[object, ...] = (
        {"token": SECRET},
        '{"token":"' + SECRET + '"}',
        '["' + SECRET + '"]',
        "null",
        HOME.replace("-", ""),
        HOME + "\n",
        True,
        1.0,
    )
    async with Client(harness.server, mode=mode) as client:
        for bad in invalid:
            failed(await client.call_tool(name, {**arguments, "home_id": bad}), "INVALID_ARGUMENT")
    assert not harness.fake.calls
    assert SECRET not in caplog.text


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("id_value", [0, 12, "12", "0012", "catalog_one-1"])
async def test_catalog_ids_are_not_uuid_coerced_or_normalized(
    mode: str, id_value: int | str
) -> None:
    harness = Harness()
    async with Client(harness.server, mode=mode) as client:
        success(await client.call_tool("casa_list_paint_collections", {"brand_id": id_value}))
    assert harness.fake.calls == [("paint_collections", (HOME, id_value))]


@pytest.mark.parametrize("mode", MODES)
async def test_each_work_document_selector_is_forwarded_exactly_once(mode: str) -> None:
    harness = Harness()
    async with Client(harness.server, mode=mode) as client:
        for key in ("todo_id", "task_id", "request_id"):
            success(await client.call_tool("casa_get_work_document_source", {key: "item_one-1"}))
    assert harness.fake.calls == [
        ("work_document_source", (HOME, "item_one-1", None, None)),
        ("work_document_source", (HOME, None, "item_one-1", None)),
        ("work_document_source", (HOME, None, None, "item_one-1")),
    ]


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("token", [False, True])
async def test_home_history_target_allowlist_precedes_gate_and_credentials(
    mode: str,
    token: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        CasaApi.inventory_service_history, "__casa_unverified__", True, raising=False
    )
    harness = Harness(settings(enabled=False, token=token))
    async with Client(harness.server, mode=mode) as client:
        failed(
            await client.call_tool(
                "casa_get_inventory_service_history",
                {
                    "target_type": "home",
                    "target_id": FORBIDDEN_HOME,
                },
            ),
            "HOME_NOT_ALLOWED",
        )
    assert not harness.fake.calls
