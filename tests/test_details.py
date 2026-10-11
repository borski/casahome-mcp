"""Privacy and runtime contracts for the 20 independently pinned named GETs."""

import inspect
import json

import pytest
from casahome import CasaApi
from detail_cases import DETAIL_CASES, ENTITY, INPUT_FIELDS, REQUIRED_FIELDS
from detail_fakes import (
    BODY_TEXT,
    EXCERPT_TEXT,
    FEED_TITLE,
    NOTE_TEXT,
    PRELUDE_TEXT,
    REFERRAL_LABEL,
    RELEASE_TEXT,
    UPDATE_TEXT,
    URL,
    VISIT_TEXT,
)
from mcp import Client
from test_tools import (
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

from casahome_mcp.detail_manifest import DETAIL_METHODS
from casahome_mcp.runtime import CasaReads
from casahome_mcp.tools import TOOL_METHODS


@pytest.fixture(autouse=True)
def reject_socket_access(monkeypatch: pytest.MonkeyPatch) -> None:
    guard_sockets(monkeypatch)


def test_independent_named_get_inventory_and_protocol_signature_parity() -> None:
    assert len(DETAIL_CASES) == 20
    expected = {name: method for name, method, *_ in DETAIL_CASES}
    assert expected == DETAIL_METHODS
    assert {name: TOOL_METHODS[name] for name in expected} == expected
    for method in expected.values():
        assert inspect.signature(getattr(CasaReads, method), eval_str=True) == inspect.signature(
            getattr(CasaApi, method), eval_str=True
        )


OPT_INS: tuple[tuple[str, dict[str, object], str, str], ...] = (
    (
        "casa_list_document_suggestions",
        {"document_id": "doc-one"},
        "include_excerpts",
        EXCERPT_TEXT,
    ),
    (
        "casa_list_document_structure_suggestions",
        {"document_id": "doc-one"},
        "include_excerpts",
        EXCERPT_TEXT,
    ),
    ("casa_get_task_details", {"task_id": "task-one"}, "include_messages", UPDATE_TEXT),
    (
        "casa_get_vendor_visit_autopilot_plan",
        {"visit_id": "visit-one", "plan_id": "plan-one"},
        "include_messages",
        UPDATE_TEXT,
    ),
    (
        "casa_get_vendor_visit_conversation",
        {"visit_id": "visit-one"},
        "include_messages",
        VISIT_TEXT,
    ),
    ("casa_list_request_purchases", {"request_id": "request-one"}, "include_notes", NOTE_TEXT),
    ("casa_list_vendor_visit_purchases", {"visit_id": "visit-one"}, "include_notes", NOTE_TEXT),
    (
        "casa_get_help_center_bundle",
        {"app_id": "synthetic-app", "kind": "articles"},
        "include_body",
        BODY_TEXT,
    ),
    ("casa_get_release_notes_diff", {}, "include_content", RELEASE_TEXT),
)


@pytest.mark.parametrize("mode", MODES)
async def test_all_new_opt_ins_are_explicit_and_never_dump_opaque_data(mode: str) -> None:
    harness = Harness()
    async with Client(harness.server, mode=mode) as client:
        for name, args, opt_in, marker in OPT_INS:
            for include in (False, True):
                result = await client.call_tool(name, {**args, opt_in: include})
                payload = success(result)
                assert (marker in json.dumps(payload)) is include
                for channel in (json.dumps(payload), result.content[0].model_dump_json()):
                    for forbidden in (
                        URL,
                        SECRET,
                        "sender_user_id",
                        "event_cursor",
                        "parts",
                        "join_url",
                        "access_grant",
                        "phone",
                        "member_pricing_summary",
                        "purchase_link",
                    ):
                        assert forbidden not in channel
            invalid: tuple[object, ...] = ("true", "false", 1, 0, None, [], {}, SECRET)
            for bad in invalid:
                before = len(harness.fake.calls)
                failed(await client.call_tool(name, {**args, opt_in: bad}), "INVALID_ARGUMENT")
                assert len(harness.fake.calls) == before


@pytest.mark.parametrize("mode", MODES)
async def test_new_path_identifiers_reject_raw_and_json_union_attacks(
    mode: str, caplog: pytest.LogCaptureFixture
) -> None:
    harness = Harness(settings(homes=(), token=False))
    bad_values: tuple[object, ...] = (
        "",
        "x" * 129,
        "../" + SECRET,
        "%2F" + SECRET,
        URL,
        "x?token=" + SECRET,
        SECRET + "#fragment",
        SECRET + "\n",
        SECRET + "\u200b",
        "é",
        [],
        {},
        1.0,
        True,
        '{"private":"' + SECRET + '"}',
        '["' + SECRET + '"]',
        "null",
        '"' + SECRET + '"',
    )
    async with Client(harness.server, mode=mode) as client:
        for name, _, args, *_ in DETAIL_CASES:
            fields = REQUIRED_FIELDS.get(name, set()) | (
                {"include_current_vendor_visit_id"}
                if name == "casa_list_bookable_handyman_tasks"
                else set()
            )
            for field in fields:
                for bad in bad_values:
                    failed(await client.call_tool(name, {**args, field: bad}), "INVALID_ARGUMENT")
        for bad in (ENTITY.replace("-", ""), "enum-one", '{"id":1}'):
            failed(
                await client.call_tool("casa_get_inventory_paint_matches", {"entity_id": bad}),
                "INVALID_ARGUMENT",
            )
        for name, _, args, *_ in DETAIL_CASES:
            for bad in (HOME.replace("-", ""), "null", '{"private":"' + SECRET + '"}'):
                failed(await client.call_tool(name, {**args, "home_id": bad}), "INVALID_ARGUMENT")
    assert not harness.fake.calls
    assert SECRET not in caplog.text


@pytest.mark.parametrize("mode", MODES)
async def test_metadata_only_bookable_membership_calls_and_visit_detail(mode: str) -> None:
    harness = Harness()
    async with Client(harness.server, mode=mode) as client:
        bookable = success(await client.call_tool("casa_list_bookable_handyman_tasks"))
        assert bookable["confidence"] == "VERIFIED"
        assert bookable["data"] == {
            "item_count": 4,
            "current_vendor_additional_availability_minutes": 0,
            "total_additional_availability_minutes": 90,
        }
        assert "OPAQUE_ITEMS_OMITTED" in sequence(bookable["warnings"])
        query = success(
            await client.call_tool(
                "casa_list_bookable_handyman_tasks",
                {"include_current_vendor_visit_id": "visit-one"},
            )
        )
        assert "UPSTREAM_QUERY_BEHAVIOR_UNVERIFIED" in sequence(query["warnings"])
        assert harness.fake.calls[-1] == ("bookable_handyman_tasks", (HOME, "visit-one"))
        harness.fake.bookable.items.clear()
        empty = mapping(
            success(await client.call_tool("casa_list_bookable_handyman_tasks"))["data"]
        )
        assert empty["item_count"] == 0 and "items" not in empty
        membership = success(await client.call_tool("casa_get_membership_info"))
        assert set(mapping(membership["data"])) == {"name", "member_since", "benefits"}
        assert "OPAQUE_FIELDS_OMITTED" in sequence(membership["warnings"])
        benefit = mapping(sequence(mapping(mapping(membership["data"])["benefits"])["items"])[0])
        assert set(benefit) == {"title", "emoji", "symbol", "description"}
        calls = mapping(
            success(
                await client.call_tool("casa_list_vendor_visit_calls", {"visit_id": "visit-one"})
            )["data"]
        )
        call = mapping(sequence(mapping(calls["page"])["items"])[0])
        assert call == {
            "id": "call-one",
            "vendor_visit_id": "visit-one",
            "status": "future-status",
            "started_by_role": "vendor",
            "started_at": 1,
            "answered_at": 2,
            "ended_at": 3,
            "duration_seconds": 0,
            "recorded": False,
            "participant_count": 1,
        }
        details = success(
            await client.call_tool("casa_get_vendor_visit_details", {"visit_id": "visit-one"})
        )
        assert VISIT_TEXT not in json.dumps(details)
        assert "OPAQUE_ITEMS_OMITTED" in sequence(details["warnings"])
        assert "OPAQUE_FIELDS_OMITTED" in sequence(details["warnings"])
        conversation = success(
            await client.call_tool("casa_get_vendor_visit_conversation", {"visit_id": "visit-one"})
        )
        assert "OPAQUE_PARTS_OMITTED" in sequence(conversation["warnings"])
        assert "TIMESTAMP_UNITS_UNVERIFIED" in sequence(conversation["warnings"])


@pytest.mark.parametrize("mode", MODES)
async def test_new_evidence_marker_drives_gate_descriptions_and_confidence(
    mode: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A future SDK verification changes production behavior automatically. Tests
    # pin actual evidence separately, never weaken it by deriving expectations.
    monkeypatch.setattr(CasaApi.vendor_visit_calls, "__casa_unverified__", False)
    harness = Harness(settings(enabled=False))
    async with Client(harness.server, mode=mode) as client:
        payload = success(
            await client.call_tool("casa_list_vendor_visit_calls", {"visit_id": "visit-one"})
        )
        assert payload["confidence"] == "VERIFIED"
        tool = next(
            tool
            for tool in (await client.list_tools()).tools
            if tool.name == "casa_list_vendor_visit_calls"
        )
        assert "Item fields not yet observed live." in (tool.description or "")
        assert "Experimental" not in (tool.description or "")
        status = mapping(success(await client.call_tool("casa_get_status"))["data"])
        assert tool.name not in sequence(status["disabled_features"])
    monkeypatch.setattr(CasaApi.bookable_handyman_tasks, "__casa_unverified__", True, raising=False)
    harness = Harness(settings(enabled=False, token=False))
    async with Client(harness.server, mode=mode) as client:
        failed(await client.call_tool("casa_list_bookable_handyman_tasks"), "UNVERIFIED_DISABLED")
    assert not harness.fake.calls


@pytest.mark.parametrize("mode", MODES)
async def test_new_reads_share_sanitized_errors_and_deny_action_stream_names(
    mode: str, caplog: pytest.LogCaptureFixture
) -> None:
    harness = Harness()
    harness.fake.error = RuntimeError(SECRET + URL)
    async with Client(harness.server, mode=mode) as client:
        for name, _, args, *_ in DETAIL_CASES:
            failed(await client.call_tool(name, args), "INTERNAL_ERROR")
        assert len(harness.fake.calls) == len(DETAIL_CASES)
        for name in (
            "casa_start_visit_call",
            "casa_send_vendor_message",
            "casa_ai_events",
            "vendor_visit_events",
            "execute_static_write",
            "casa_help_article_view",
            "casa_accept_document_suggestion",
        ):
            failed(await client.call_tool(name, {"private": SECRET}), "INVALID_ARGUMENT")
        assert len(harness.fake.calls) == len(DETAIL_CASES)
    assert SECRET not in caplog.text and URL not in caplog.text


@pytest.mark.parametrize("mode", MODES)
async def test_new_pages_preserve_lanes_and_do_not_invent_upstream_totals(mode: str) -> None:
    harness = Harness()
    f = harness.fake
    f.enums.enums *= 26
    async with Client(harness.server, mode=mode) as client:
        payload = success(
            await client.call_tool("casa_list_inventory_enums", {"enum_type": "light_fixture_type"})
        )
        page = mapping(mapping(payload["data"])["page"])
        assert page["returned_count"] == 25 and page["total_in_response"] == 26
        assert page["next_offset"] == 25 and page["pagination_scope"] == "single_upstream_response"
        assert "LOCAL_PAGE_TRUNCATED" in sequence(payload["warnings"])
        for name, field in (
            ("casa_list_request_purchases", "request_id"),
            ("casa_list_vendor_visit_purchases", "visit_id"),
        ):
            purchases = mapping(success(await client.call_tool(name, {field: "item-one"}))["data"])
            assert "non_purchase_invoice_count" not in purchases
            rows = [mapping(row) for row in sequence(mapping(purchases["page"])["items"])]
            assert [row["lane"] for row in rows] == ["pending", "approved", "purchased"]
            assert all(row["unit_price_usd_cents"] == row["quantity"] == 0 for row in rows)
        f.enums.enums.clear()
        empty = success(
            await client.call_tool("casa_list_inventory_enums", {"enum_type": "light_fixture_type"})
        )
        assert "UPSTREAM_COMPLETENESS_UNKNOWN" in sequence(empty["warnings"])
        assert mapping(mapping(empty["data"])["page"])["items"] == []
        for name, _, args, *_ in DETAIL_CASES:
            if "offset" not in INPUT_FIELDS[name]:
                continue
            for bad in (0, 101, True, 1.0, "25", None):
                failed(await client.call_tool(name, {**args, "limit": bad}), "INVALID_ARGUMENT")


@pytest.mark.parametrize("mode", MODES)
async def test_help_kind_and_body_have_no_assumed_app_id_or_tracking(mode: str) -> None:
    harness = Harness()
    async with Client(harness.server, mode=mode) as client:
        for app in ("member_ios", "future-app", "0012"):
            for kind in ("topics", "articles"):
                payload = success(
                    await client.call_tool(
                        "casa_get_help_center_bundle", {"app_id": app, "kind": kind}
                    )
                )
                assert mapping(payload["data"])["kind"] == kind
                assert harness.fake.calls[-1] == ("help_center_bundle", (app,))
        before = len(harness.fake.calls)
        for args in (
            {"app_id": "synthetic-app", "kind": "topics", "include_body": True},
            {"app_id": "synthetic-app", "kind": "unknown"},
            {"kind": "articles"},
        ):
            failed(await client.call_tool("casa_get_help_center_bundle", args), "INVALID_ARGUMENT")
        assert len(harness.fake.calls) == before


@pytest.mark.parametrize("mode", MODES)
async def test_detail_text_controls_url_before_clipping_and_nested_caps(mode: str) -> None:
    harness = Harness()
    f = harness.fake
    f.conversation.messages[0].content = "界" * 2001 + " " + URL
    f.conversation.messages[0].sender_display_name = "bad\u200bname"
    f.conversation.messages[0].id = URL
    f.conversation.participants *= 21
    f.doc_suggestions.suggestions[0].citations *= 21
    f.structure_suggestions.suggestions[0].current_values *= 21
    f.savings.categories[0].breakdown *= 21
    f.release_notes.data[0].sections *= 21
    f.visit_plan.tasks[0].updates *= 21
    f.visit_details.vendors *= 21
    async with Client(harness.server, mode=mode) as client:
        payload = success(
            await client.call_tool(
                "casa_get_vendor_visit_conversation",
                {"visit_id": "visit-one", "include_messages": True},
            )
        )
        warnings = sequence(payload["warnings"])
        assert {
            "URL_TEXT_OMITTED",
            "CONTROL_TEXT_OMITTED",
            "UNSAFE_ID_OMITTED",
            "NESTED_COLLECTION_TRUNCATED",
        } <= set(warnings)
        assert "界" * 2000 not in json.dumps(payload, ensure_ascii=False)
        for name, args in (
            ("casa_list_document_suggestions", {"document_id": "doc-one"}),
            ("casa_list_document_structure_suggestions", {"document_id": "doc-one"}),
            ("casa_get_membership_savings", {}),
            ("casa_get_release_notes_diff", {}),
            (
                "casa_get_vendor_visit_autopilot_plan",
                {"visit_id": "visit-one", "plan_id": "plan-one"},
            ),
            ("casa_get_vendor_visit_details", {"visit_id": "visit-one"}),
        ):
            assert "NESTED_COLLECTION_TRUNCATED" in sequence(
                success(await client.call_tool(name, args))["warnings"]
            )
        f.conversation.messages[0].content = "界" * 2001
        payload = success(
            await client.call_tool(
                "casa_get_vendor_visit_conversation",
                {"visit_id": "visit-one", "include_messages": True},
            )
        )
        assert "TEXT_TRUNCATED" in sequence(payload["warnings"])
        row = mapping(sequence(mapping(mapping(payload["data"])["page"])["items"])[0])
        assert row["content"] == "界" * 2000


@pytest.mark.parametrize("mode", MODES)
async def test_64kib_guard_and_nonfinite_paint_fail_without_partial_outputs(mode: str) -> None:
    harness = Harness()
    f = harness.fake
    f.conversation.messages[0].content = "界" * 2000
    f.conversation.messages *= 100
    async with Client(harness.server, mode=mode) as client:
        failed(
            await client.call_tool(
                "casa_get_vendor_visit_conversation",
                {"visit_id": "visit-one", "include_messages": True, "limit": 100},
            ),
            "OUTPUT_TOO_LARGE",
        )
        success(
            await client.call_tool(
                "casa_get_vendor_visit_conversation",
                {"visit_id": "visit-one", "include_messages": True, "limit": 1},
            )
        )
        for value in (float("inf"), float("-inf"), float("nan")):
            f.paint_matches.matches[0].closeness_percentage = value
            failed(
                await client.call_tool("casa_get_inventory_paint_matches", {"entity_id": ENTITY}),
                "SCHEMA_MISMATCH",
            )


@pytest.mark.parametrize("mode", MODES)
async def test_new_reads_preserve_deadline_concurrency_and_rotation_controls(mode: str) -> None:
    import asyncio

    harness = Harness()
    harness.fake.release = asyncio.Event()
    harness.app.deadline_seconds = 0.01
    async with Client(harness.server, mode=mode) as client:
        results = await asyncio.gather(
            *(
                client.call_tool(name, args)
                for name, args in (
                    ("casa_get_membership_info", {}),
                    ("casa_get_task_details", {"task_id": "task-one"}),
                    ("casa_list_vendor_visit_calls", {"visit_id": "visit-one"}),
                )
            )
        )
        for result in results:
            failed(result, "TIMEOUT")
        assert harness.fake.maximum_active <= 2
        harness.fake.release = None
        harness.app.deadline_seconds = 45
        harness.app.on_rotated(SECRET)
        payload = success(await client.call_tool("casa_get_membership_info"))
        assert "TOKEN_ROTATED_NOT_PERSISTED" in sequence(payload["warnings"])


@pytest.mark.parametrize("mode", MODES)
async def test_referral_code_exposes_code_and_labels_never_urls_or_referred_homes(
    mode: str,
) -> None:
    harness = Harness(settings(enabled=False))
    async with Client(harness.server, mode=mode) as client:
        result = await client.call_tool("casa_get_referral_code")
        payload = success(result)
        assert payload["confidence"] == "VERIFIED"
        assert harness.fake.calls == [("referral_code", ())]
        # Only allowlisted display keys survive. share_message, nested and
        # unsafe keys are dropped without being echoed as keys or values.
        assert payload["data"] == {
            "code": "SYNTHCODE",
            "display": [{"key": "title", "value": REFERRAL_LABEL}],
            "referred_home_count": 2,
        }
        assert {"OPAQUE_FIELDS_OMITTED", "OPAQUE_ITEMS_OMITTED"} <= set(
            sequence(payload["warnings"])
        )
        for channel in (json.dumps(payload), result.content[0].model_dump_json()):
            for forbidden in ("share_message", "bad key", "nested", "Join me"):
                assert forbidden not in channel
        for channel in (json.dumps(payload), result.content[0].model_dump_json()):
            for forbidden in (URL, SECRET, "referral_url", "example.invalid", "address"):
                assert forbidden not in channel


@pytest.mark.parametrize("mode", MODES)
async def test_enum_tool_forwards_snake_case_enum_type_keys_without_gate(mode: str) -> None:
    # The live route takes a property's enum_type string key, not a UUID.
    harness = Harness(settings(enabled=False))
    async with Client(harness.server, mode=mode) as client:
        for key in ("light_fixture_type", "home_type"):
            payload = success(
                await client.call_tool("casa_list_inventory_enums", {"enum_type": key})
            )
            assert payload["confidence"] == "VERIFIED"
            assert harness.fake.calls[-1] == ("inventory_enums", (key,))
        failed(
            await client.call_tool("casa_list_inventory_enums", {"enum_type_id": "home_type"}),
            "INVALID_ARGUMENT",
        )


@pytest.mark.parametrize("mode", MODES)
async def test_referral_display_allowlist_skips_non_string_and_url_labels(mode: str) -> None:
    harness = Harness(settings(enabled=False))
    harness.fake.referral.referral_code.display = {
        "title": {"secret": SECRET},
        "description": "Visit " + URL,
        "subtitle": "not an observed key",
    }
    async with Client(harness.server, mode=mode) as client:
        payload = success(await client.call_tool("casa_get_referral_code"))
        assert payload["data"] == {
            "code": "SYNTHCODE",
            "display": [{"key": "description", "value": None}],
            "referred_home_count": 2,
        }
        assert {"OPAQUE_FIELDS_OMITTED", "URL_TEXT_OMITTED"} <= set(sequence(payload["warnings"]))
        assert SECRET not in json.dumps(payload)


@pytest.mark.parametrize("mode", MODES)
async def test_release_notes_diff_is_ungated_with_titles_and_opt_in_content(mode: str) -> None:
    harness = Harness(settings(enabled=False))
    async with Client(harness.server, mode=mode) as client:
        result = await client.call_tool("casa_get_release_notes_diff")
        payload = success(result)
        assert payload["confidence"] == "VERIFIED"
        assert harness.fake.calls == [("release_notes_diff", ())]
        note = mapping(sequence(mapping(mapping(payload["data"])["page"])["items"])[0])
        assert note["title"] == "Synthetic release"
        assert note["prelude"] is None
        section = mapping(sequence(note["sections"])[0])
        assert section == {"id": "section-one", "title": "Synthetic section", "content": None}
        assert "UPSTREAM_QUERY_BEHAVIOR_UNVERIFIED" not in sequence(payload["warnings"])
        full = success(
            await client.call_tool("casa_get_release_notes_diff", {"include_content": True})
        )
        dumped = json.dumps(full)
        assert RELEASE_TEXT in dumped and PRELUDE_TEXT in dumped
        for channel in (json.dumps(payload), dumped, result.content[0].model_dump_json()):
            for forbidden in (URL, SECRET, "hero_image_url", "example.invalid"):
                assert forbidden not in channel


@pytest.mark.parametrize("mode", MODES)
async def test_home_feed_projects_allowlisted_props_only(mode: str) -> None:
    harness = Harness(settings(enabled=False))
    async with Client(harness.server, mode=mode) as client:
        result = await client.call_tool("casa_get_home_feed")
        payload = success(result)
        assert payload["confidence"] == "VERIFIED"
        assert harness.fake.calls == [("home_feed", (HOME,))]
        page = mapping(mapping(payload["data"])["page"])
        first, second = (mapping(row) for row in sequence(page["items"]))
        assert first == {
            "id": "card-one",
            "template_id": "home_onboarding",
            "name": "Home Onboarding",
            "title": FEED_TITLE,
            "subtitle": "Synthetic subtitle",
            "feature_name": "Synthetic feature",
            "button_caption": "Continue",
            "action": None,
            "button_action": "open_onboarding",
            "completed_count": 2,
            "total_count": 5,
            "show_starts_at_minutes_after_onboarding": 0,
            "show_ends_at_minutes_after_onboarding": None,
            "child_count": 0,
        }
        # URL title, object subtitle, Boolean and string counts are all dropped.
        assert (second["title"], second["subtitle"]) == (None, None)
        assert (second["completed_count"], second["total_count"]) == (None, None)
        assert second["show_ends_at_minutes_after_onboarding"] == 120
        assert second["child_count"] == 1
        assert {
            "UPSTREAM_COMPLETENESS_UNKNOWN",
            "OPAQUE_FIELDS_OMITTED",
            "OPAQUE_ITEMS_OMITTED",
            "URL_TEXT_OMITTED",
            "UNSAFE_ID_OMITTED",
        } <= set(sequence(payload["warnings"]))
        for channel in (json.dumps(payload), result.content[0].model_dump_json()):
            for forbidden in (
                URL,
                SECRET,
                "example.invalid",
                "colors",
                "image",
                "visual_style",
                "button_symbol",
                "props",
                "children",
                "child-one",
            ):
                assert forbidden not in channel


@pytest.mark.parametrize("mode", MODES)
async def test_home_feed_pages_locally(mode: str) -> None:
    harness = Harness()
    harness.fake.feed.cards *= 13
    async with Client(harness.server, mode=mode) as client:
        payload = success(await client.call_tool("casa_get_home_feed", {"limit": 25}))
        page = mapping(mapping(payload["data"])["page"])
        assert page["returned_count"] == 25 and page["total_in_response"] == 26
        assert "LOCAL_PAGE_TRUNCATED" in sequence(payload["warnings"])
        assert len(harness.fake.calls) == 1
