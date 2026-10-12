"""Synthetic prepare inputs and the exact wire requests the real SDK should build."""

from dataclasses import dataclass, field

from test_tools import ENTITY, HOME

BASE = f"/protected/home/{HOME}"
MEMBER = f"/protected/member/home/{HOME}"
OK: dict[str, object] = {"message": "ok"}


@dataclass(frozen=True)
class WorkflowCase:
    operation: str
    arguments: dict[str, object]
    method: str
    path: str
    body: object = None
    # Key of a FakeCasa read fixture or a literal response body.
    response: object = field(default_factory=lambda: OK)


WIRE_CASES: tuple[WorkflowCase, ...] = (
    WorkflowCase(
        "update_todo",
        {"todo_id": "todo-one", "title": "New title", "prepared_brief": "Line one\nLine two"},
        "PATCH",
        f"{BASE}/todos/todo-one",
        {"title": "New title", "prepared_brief": "Line one\nLine two"},
        "todo",
    ),
    WorkflowCase(
        "reject_suggested_todo",
        {"suggestion_id": "suggestion-one", "reason": "already_handled"},
        "POST",
        f"{BASE}/suggested_todos/suggestion-one/respond",
        {"decision": "reject", "reason": "already_handled"},
        "todo",
    ),
    WorkflowCase(
        "confirm_todo_support",
        {"todo_id": "todo-one", "is_support_question": False},
        "POST",
        f"{BASE}/todos/todo-one/support_confirmation",
        {"is_support_question": False},
        "todo",
    ),
    WorkflowCase(
        "retry_todo",
        {"todo_id": "todo-one"},
        "POST",
        f"{BASE}/todos/todo-one/retry",
        None,
        "todo",
    ),
    WorkflowCase(
        "reorder_todo_section",
        {
            "section": "send_to_concierge",
            "expected_revision": 3,
            "ordered_item_ids": ["todo-two", "todo-one"],
        },
        "PUT",
        f"{BASE}/requests_tab/todo_sections/send_to_concierge/order",
        {"expected_revision": 3, "ordered_item_ids": ["todo-two", "todo-one"]},
        {"section": {"name": "send_to_concierge", "title": "Concierge"}},
    ),
    WorkflowCase(
        "update_document",
        {"document_id": "doc-one", "name": "Deed", "clear_document_date": True},
        "PATCH",
        f"{BASE}/documents/doc-one",
        {"name": "Deed", "document_date": None},
        "document",
    ),
    WorkflowCase(
        "analyze_document",
        {"document_id": "doc-one", "reanalyze": True},
        "POST",
        f"{BASE}/documents/doc-one/analysis",
        {"reanalyze": True},
        "document",
    ),
    WorkflowCase(
        "organize_document",
        {"document_id": "doc-one"},
        "POST",
        f"{BASE}/documents/doc-one/organization",
        None,
        "document",
    ),
    WorkflowCase(
        "update_schedule_preferences",
        {"selected_days_of_week": [1, 3], "selected_times_of_day": []},
        "PUT",
        f"{BASE}/schedule_preferences",
        {"selected_days_of_week": [1, 3], "selected_times_of_day": []},
        "schedule",
    ),
    WorkflowCase(
        "update_availability_slots",
        {
            "availability_request_id": "availability-one",
            "windows": [{"start_time": 1, "end_time": 2}],
        },
        "PUT",
        f"{BASE}/availability_requests/availability-one/slots",
        {"slots": [{"start_time": 1, "end_time": 2}]},
        "availability",
    ),
    WorkflowCase(
        "cancel_vendor_visit",
        {"visit_id": "visit-one"},
        "PUT",
        f"{BASE}/vendor_visits/visit-one/cancelation",
        None,
        {"id": "visit-one", "status": "canceled"},
    ),
    WorkflowCase(
        "remove_mailbox_recipient",
        {"recipient_id": "recipient-one"},
        "DELETE",
        f"{BASE}/mailbox/recipients/recipient-one",
    ),
    WorkflowCase(
        "mark_mail_item_read",
        {"mail_item_id": "mail-one"},
        "POST",
        f"{BASE}/mailbox/mail_items/mail-one/read",
    ),
    WorkflowCase(
        "mark_mail_item_unread",
        {"mail_item_id": "mail-one"},
        "POST",
        f"{BASE}/mailbox/mail_items/mail-one/unread",
    ),
    WorkflowCase(
        "set_mail_item_archived",
        {"mail_item_id": "mail-one", "archived": False},
        "POST",
        f"{BASE}/mailbox/mail_items/mail-one/unarchive",
    ),
    WorkflowCase(
        "validate_package_tracking_number",
        {"tracking_number": "1Z999AA10123456784"},
        "POST",
        f"{BASE}/packages/validate_tracking_number",
        {"tracking_number": "1Z999AA10123456784"},
        {
            "tracking_number": "1Z999AA10123456784",
            "valid": True,
            "carrier_matches": ["ups", "unsafe/carrier"],
        },
    ),
    WorkflowCase(
        "add_tracked_package",
        {
            "carrier_id": "carrier-one",
            "tracking_number": "TRACK-1",
            "name": "Boots",
            "direction": "inbound",
        },
        "POST",
        f"{BASE}/mail_packages/carrier/carrier-one/add_package",
        {"tracking_number": "TRACK-1", "name": "Boots", "direction": "inbound"},
    ),
    WorkflowCase(
        "update_package",
        {"package_id": "package-one", "archive": True, "name": "Boots"},
        "POST",
        f"{BASE}/mail_packages/package/package-one/update",
        {"archive": True, "name": "Boots"},
    ),
    WorkflowCase(
        "requeue_package_pickup",
        {"package_id": "package-one"},
        "POST",
        f"{BASE}/packages/package-one/pickup/requeue",
    ),
    WorkflowCase(
        "set_package_auto_archive",
        {"package_auto_archive_days": None},
        "PATCH",
        f"{BASE}/packages/preferences/auto_archive",
        {"package_auto_archive_days": None},
        {"success": True, "package_auto_archive_days": None},
    ),
    WorkflowCase(
        "create_inventory_entity",
        {"room_id": ENTITY},
        "PUT",
        f"{MEMBER}/entity",
        {"home_id": HOME, "room_id": ENTITY},
        {"entity_id": "entity-new", "message": "created"},
    ),
    WorkflowCase(
        "create_inventory_lighting",
        {"room_id": ENTITY, "fixture_entity_type_id": "type-fixture", "bulb_kind": "led"},
        "PUT",
        f"{MEMBER}/entity/lighting",
        {"room_id": ENTITY, "fixture": {"entity_type_id": "type-fixture"}, "bulb": {"kind": "led"}},
        {"fixture_entity_id": "fixture-new", "message": "created"},
    ),
    WorkflowCase(
        "create_paint_from_library",
        {"paint_color_id": 42, "room_ids": [ENTITY]},
        "POST",
        f"{BASE}/entity/paint/from-library",
        {"paint_color_id": 42, "room_ids": [ENTITY]},
        {"entity_id": "paint-new"},
    ),
    WorkflowCase(
        "update_entity_properties",
        {
            "entity_id": ENTITY,
            "props": [
                {"definition_id": "serial", "value": "ABC-123"},
                {"definition_id": "finish", "multi_enums": [{"id": "matte", "is_selected": False}]},
            ],
        },
        "PATCH",
        f"{MEMBER}/entity/{ENTITY}/props",
        {
            "props": [
                {"definition_id": "serial", "value": "ABC-123"},
                {"definition_id": "finish", "multi_enums": [{"id": "matte", "is_selected": False}]},
            ]
        },
    ),
    WorkflowCase(
        "clear_ai_message_rating",
        {"message_id": "message-one"},
        "DELETE",
        f"{BASE}/casa_ai/messages/message-one/feedback",
        None,
        None,
    ),
    WorkflowCase(
        "update_access_preferences",
        {
            "general_instructions": "Use the side gate.\nRing twice.",
            "package_pickup_method": "pickup_spot",
            "package_pickup_spot": "other",
            "package_pickup_general_instructions": None,
        },
        "PATCH",
        f"{BASE}/access_preferences",
        {
            "general_instructions": "Use the side gate.\nRing twice.",
            "package_pickup_method": "pickup_spot",
            "package_pickup_spot": "other",
            "package_pickup_general_instructions": None,
        },
        {"home_id": HOME},
    ),
)

WORKFLOW_CASES: tuple[tuple[str, dict[str, object]], ...] = tuple(
    (case.operation, case.arguments) for case in WIRE_CASES
)
