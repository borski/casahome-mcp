"""Allowlisted DTOs for static detail GETs. No opaque or extra fields."""

from typing import Literal

from pydantic import Field

from .coverage_outputs import Brief, CitationSummary, DocumentSummary, Finite, PurchaseSummary, Text
from .outputs import OutputModel, Page


class BookableTasksData(OutputModel):
    item_count: int
    current_vendor_additional_availability_minutes: int | None
    total_additional_availability_minutes: int | None


class BenefitSummary(OutputModel):
    title: Text | None
    emoji: Text | None
    symbol: Text | None
    description: Brief | None


class MembershipInfoData(OutputModel):
    name: Text | None
    member_since: int | None
    benefits: Page[BenefitSummary] | None


class SavingsBreakdown(OutputModel):
    title: Text | None
    value: Text | None


class SavingsCategory(OutputModel):
    type: Text | None
    label: Text | None
    color: Text | None
    preview: Text | None
    is_visible: bool
    time_saved_seconds: int
    money_saved_cents: int
    breakdown: list[SavingsBreakdown] = Field(max_length=20)


class MembershipSavingsData(OutputModel):
    calculated_at: Text | None
    total_time_saved_seconds: int
    total_money_saved_cents: int
    page: Page[SavingsCategory]


class InventoryEnumSummary(OutputModel):
    id: Text | None
    type: Text | None
    name: Text | None
    symbol_name: Text | None
    category: Text | None


class InventoryEnumsData(OutputModel):
    page: Page[InventoryEnumSummary]


class ReleaseSectionSummary(OutputModel):
    id: Text | None
    title: Text | None
    content: Brief | None


class ReleaseNoteSummary(OutputModel):
    id: Text | None
    title: Text | None
    version: Text | None
    date: int
    min_build_number: int
    max_build_number: int | None
    prelude: Brief | None
    sections: list[ReleaseSectionSummary] = Field(max_length=20)


class ReleaseNotesData(OutputModel):
    page: Page[ReleaseNoteSummary]


class AvailabilitySummary(OutputModel):
    id: Text | None
    request_id: Text | None
    status: Text | None
    slot_count: int
    first_submitted_at: int | None
    last_submitted_at: int | None
    created_at: int


class AvailabilityConstraints(OutputModel):
    snap_minutes: int
    min_slot_minutes: int
    default_duration_minutes: int
    lead_time_minutes: int


class AvailabilitySlot(OutputModel):
    id: Text | None
    start_time: int
    end_time: int


class AvailabilityDetailsData(OutputModel):
    availability_request: AvailabilitySummary
    home_timezone: Text | None
    constraints: AvailabilityConstraints
    page: Page[AvailabilitySlot]


class DocumentDetailsData(OutputModel):
    document: DocumentSummary


class DocumentSuggestionSummary(OutputModel):
    id: Text | None
    todo_id: Text | None
    task_id: Text | None
    request_id: Text | None
    title: Text | None
    action: Text | None
    reason: Brief | None
    area: Text | None
    state: Text | None
    work_deleted: bool
    citations: list[CitationSummary] = Field(max_length=20)


class DocumentSuggestionsData(OutputModel):
    analysis_status: Text | None
    limitations: list[Brief | None] = Field(max_length=20)
    page: Page[DocumentSuggestionSummary]


class StructureSuggestionSummary(OutputModel):
    id: Text | None
    entity_id: Text | None = None
    definition_id: Text | None = None
    responded_at: int | None = None
    section: Text | None
    title: Text | None
    current_values: list[Text | None] = Field(max_length=20)
    current_values_complete: bool
    current_label: Text | None
    proposed_label: Text | None
    reason: Brief | None
    state: Text | None
    changed_since_analysis: bool
    citations: list[CitationSummary] = Field(max_length=20)


class StructureSuggestionsData(OutputModel):
    page: Page[StructureSuggestionSummary]


class PaintMatchSummary(OutputModel):
    id: int
    color_name: Text | None
    brand_name: Text | None
    color_hex: Text | None
    closeness_percentage: Finite


class PaintMatchesData(OutputModel):
    is_manually_added: bool
    page: Page[PaintMatchSummary]


class ScopedPurchasesData(OutputModel):
    context_title: Text | None
    next_package_pickup_by: int | None
    page: Page[PurchaseSummary]


class TaskVisitSummary(OutputModel):
    id: Text | None
    start_time: int


class UpdateSummary(OutputModel):
    id: Text | None
    sender_name: Text | None
    sent_at: int
    message: Brief | None
    attachment_count: int


class TaskDetailsData(OutputModel):
    id: Text | None
    title: Text | None
    description: Brief | None
    emoji: Text | None
    status: Text | None
    visit: TaskVisitSummary | None
    attachment_count: int
    can_schedule_handyman_vendor_visit: bool
    can_chat_with_concierge: bool
    can_edit: bool
    can_delete: bool
    page: Page[UpdateSummary]


class ConversationWindow(OutputModel):
    state: Text | None
    opens_at: int | None
    closes_at: int | None
    closed_reason: Text | None


class ConversationSummary(OutputModel):
    thread_id: Text | None
    window: ConversationWindow
    calls_enabled: bool | None
    unread_count: int
    counterparty_count: int
    live_call_present: bool


class VisitRequestSummary(OutputModel):
    id: Text | None
    type: Text | None
    status: Text | None
    title: Text | None
    emoji: Text | None
    has_unread_messages: bool


class VisitEventSummary(OutputModel):
    id: Text | None
    start_time: int
    end_time: int


class VisitVendorSummary(OutputModel):
    id: Text | None
    display_name: Text | None
    compact_display_name: Text | None
    type: Text | None
    active_work_started_at: int | None


class VendorVisitDetailsData(OutputModel):
    id: Text | None
    type: Text | None
    status: Text | None
    request: VisitRequestSummary
    calendar_event: VisitEventSummary | None
    vendors: list[VisitVendorSummary] = Field(max_length=20)
    task_item_count: int
    invoice_count: int
    purchase_count: int
    can_add_remove_items: bool
    can_cancel: bool
    conversation: ConversationSummary | None


class VisitPlanSummary(OutputModel):
    id: Text | None
    title: Text | None
    description: Brief | None
    emoji: Text | None


class TaskTargetSummary(OutputModel):
    id: Text | None
    kind: Text | None
    primary_label: Text | None
    secondary_label: Text | None
    symbol_name: Text | None


class GroupedTaskSummary(OutputModel):
    id: Text | None
    status: Text | None
    target: TaskTargetSummary | None
    updates: list[UpdateSummary] = Field(max_length=20)


class VisitAutopilotPlanData(OutputModel):
    plan: VisitPlanSummary
    visit: TaskVisitSummary | None
    page: Page[GroupedTaskSummary]


class CallSummary(OutputModel):
    id: Text | None
    vendor_visit_id: Text | None
    status: Text | None
    started_by_role: Text | None
    started_at: int
    answered_at: int | None
    ended_at: int | None
    duration_seconds: int | None
    recorded: bool
    participant_count: int


class VisitCallsData(OutputModel):
    page: Page[CallSummary]


class ParticipantSummary(OutputModel):
    role: Text | None
    vendor_id: Text | None
    display_name: Text | None
    is_me: bool


class VisitMessageSummary(OutputModel):
    id: Text | None
    thread_id: Text | None
    created_at: int
    sender_role: Text | None
    sender_display_name: Text | None
    is_mine: bool
    content: Brief | None
    attachment_count: int


class VisitConversationData(OutputModel):
    visit_id: Text | None
    thread_id: Text | None
    window: ConversationWindow
    calls_enabled: bool | None
    live_call_present: bool
    unread_count: int
    participants: list[ParticipantSummary] = Field(max_length=20)
    page: Page[VisitMessageSummary]


class HelpTopicSummary(OutputModel):
    id: Text | None
    slug: Text | None
    name: Text | None
    blurb: Brief | None
    system_image: Text | None
    sort_order: int


class HelpArticleSummary(OutputModel):
    id: Text | None
    topic_id: Text | None
    slug: Text | None
    sort_order: int
    is_top_question: bool
    is_featured: bool
    article_version_id: Text | None
    version_number: int
    title: Text | None
    summary: Brief | None
    body_markdown: Brief | None


class ReferralLabel(OutputModel):
    key: Text
    value: Text | None


class ReferralCodeData(OutputModel):
    code: Text | None
    display: list[ReferralLabel] = Field(max_length=20)
    referred_home_count: int


class HelpCenterData(OutputModel):
    app: Text | None
    kind: Literal["topics", "articles"]
    page: Page[HelpTopicSummary] | Page[HelpArticleSummary]


class FeedCardSummary(OutputModel):
    """Allowlisted card text, safe action tokens and counts. Never colors, images or URLs."""

    id: Text | None
    template_id: Text | None
    name: Text | None
    title: Text | None
    subtitle: Brief | None
    feature_name: Text | None
    button_caption: Text | None
    action: Text | None
    button_action: Text | None
    completed_count: int | None
    total_count: int | None
    show_starts_at_minutes_after_onboarding: int
    show_ends_at_minutes_after_onboarding: int | None
    child_count: int


class HomeFeedData(OutputModel):
    page: Page[FeedCardSummary]
