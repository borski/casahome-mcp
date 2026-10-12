"""Finite action manifest and operator gating derived from SDK evidence markers.

Imports nothing from the server or tool modules, so read-side status reporting
can share it without reaching any action implementation.
"""

from casahome import CasaApi, is_unverified

from ..config import Settings

ACTION_METHODS = frozenset(
    {
        "move_entity_to_room",
        "rate_ai_message",
        "respond_to_suggested_todo",
        "send_todo_to_concierge",
        "answer_todo_question",
        "submit_todo_question_round",
        "update_autopilot_plan",
        "update_notification_settings",
        "send_ai_message",
        "send_request_message",
        "create_todo_result",
        "upload_document",
        "delete_todo",
        "update_entity_model",
        "update_entity_make_model",
        "rename_room",
        "respond_to_document_structure_suggestion",
        "add_mailbox_recipient",
        "update_mailbox_auto_archive",
        "update_access_preferences",
        "update_todo",
        "reject_suggested_todo",
        "confirm_todo_support",
        "update_document",
        "analyze_document",
        "organize_document",
        "update_schedule_preferences",
        "update_availability_slots",
        "reorder_todo_section",
        "retry_todo",
        "cancel_vendor_visit",
        "remove_mailbox_recipient",
        "mark_mail_item_read",
        "mark_mail_item_unread",
        "set_mail_item_archived",
        "validate_package_tracking_number",
        "add_tracked_package",
        "update_package",
        "requeue_package_pickup",
        "set_package_auto_archive",
        "create_inventory_entity",
        "create_inventory_lighting",
        "create_paint_from_library",
        "clear_ai_message_rating",
        "update_entity_properties",
    }
)
"""Exact SDK write allowlist. Confidence comes from the SDK marker, never this list."""

ACTION_TOOLS = frozenset(f"casa_prepare_{method}" for method in ACTION_METHODS) | {
    "casa_execute_action",
    "casa_cancel_action",
}

UNVERIFIED_CONTRACT_WARNING = (
    "UNVERIFIED_CONTRACT: reconstructed from the app, not yet confirmed against Casa. "
    "May fail or behave differently."
)


def action_unverified(method_name: str) -> bool:
    """The SDK's own evidence marker. Unknown names fail closed as unverified."""
    method = getattr(CasaApi, method_name, None)
    return method is None or is_unverified(method)


def gated_action_tools(settings: Settings) -> list[str]:
    """Prepare tools the unverified-actions gate currently blocks."""
    if settings.allow_unverified_actions:
        return []
    return sorted(f"casa_prepare_{name}" for name in ACTION_METHODS if action_unverified(name))
