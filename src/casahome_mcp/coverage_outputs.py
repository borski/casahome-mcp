"""Explicit, strict DTOs for the additional Casa read surface."""

from typing import Annotated, Literal

from pydantic import Field

from .outputs import OutputModel, Page

Text = Annotated[str, Field(max_length=256)]
Brief = Annotated[str, Field(max_length=2000)]
CursorText = Annotated[str, Field(max_length=2048)]
Finite = Annotated[float, Field(allow_inf_nan=False)]


class TodoReadSummary(OutputModel):
    id: Text | None
    title: Text | None
    status: Text | None
    creator_role: Text | None
    created_at: int
    updated_at: int
    is_suggested: bool
    flagged_for_support: bool
    attachment_count: int
    prepared_brief: Brief | None


class SuggestedTodosData(OutputModel):
    page: Page[TodoReadSummary]


class TodoDetailsData(OutputModel):
    todo: TodoReadSummary


class CompletedCard(OutputModel):
    id: Text | None
    type: Text | None
    title: Text | None
    updated_at: int
    has_unread_messages: bool


class UpstreamPagination(OutputModel):
    """Exactly the SDK pagination, never derived from local slice counts."""

    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    total_count: int = Field(ge=0)
    total_pages: int = Field(ge=0)


class CompletedRequestsData(OutputModel):
    kind: Text | None
    upstream_pagination: UpstreamPagination
    page: Page[CompletedCard]


class PlanPricingPolicy(OutputModel):
    title: Text | None
    description: Brief | None


class PlanAssociation(OutputModel):
    kind: Literal["home", "room", "entity"]
    id: Text | None
    target_id: Text | None
    name: Text | None
    duration_minutes: int
    enabled: bool | None
    price_usd_cents: int | None


class PlanSummary(OutputModel):
    category_id: Text | None
    category_title: Text | None
    plan_id: Text | None
    plan_template_id: Text | None
    eligible: bool
    title: Text | None
    subtitle: Text | None
    description: Brief | None
    type: Text | None
    enabled: bool | None
    applies_to: Text | None
    fulfillment_policy: Text | None
    selected_cadence: Text | None
    default_cadence: Text | None
    cadence_options: list[Text | None] = Field(max_length=20)
    savings_percentage: int | None
    next_calendar_event_start_at: int | None
    pricing_policies: list[PlanPricingPolicy] = Field(max_length=20)
    associations: list[PlanAssociation] = Field(max_length=20)


class AutopilotPlansData(OutputModel):
    page: Page[PlanSummary]


class HistoryPlan(OutputModel):
    id: Text | None
    title: Text | None
    enabled: bool | None
    selected_cadence: Text | None
    next_service_at: int | None


class HistoryItem(OutputModel):
    task_id: Text | None
    task_type: Text | None
    task_title: Text | None
    serviced_at: int | None
    autopilot_plan_id: Text | None


class ServiceHistoryData(OutputModel):
    plans: Page[HistoryPlan]
    history: Page[HistoryItem]


class DocumentSummary(OutputModel):
    id: Text | None
    name: Text | None
    document_type: Text | None
    document_date: Text | None
    mimetype: Text | None
    size_bytes: int | None
    created_at: int | None
    updated_at: int | None
    organization_status: Text | None
    extraction_status: Text | None


class DocumentsData(OutputModel):
    page: Page[DocumentSummary]
    next_cursor: CursorText | None


class DocumentTypeSummary(OutputModel):
    key: Text | None
    label: Text | None
    description: Brief | None


class DocumentTypesData(OutputModel):
    page: Page[DocumentTypeSummary]
    max_file_size_bytes: int
    max_files_per_upload: int
    max_organization_size_bytes: int | None
    allowed_mimetypes: list[Text | None] = Field(max_length=100)


class CitationSummary(OutputModel):
    page_index: int | None
    page_label: Text | None
    excerpt: Brief | None


class DocumentSourceSummary(OutputModel):
    document_id: Text | None
    name: Text | None
    available: bool | None
    document_date: Text | None
    citations: Page[CitationSummary]


class WorkDocumentSourceData(OutputModel):
    source: DocumentSourceSummary | None


class PaintCatalogSummary(OutputModel):
    id: int | Text | None
    name: Text | None
    color_count: int


class PaintColorSummary(OutputModel):
    id: int | Text | None
    color_name: Text | None
    brand_name: Text | None
    collection_name: Text | None
    color_hex: Text | None


class PaintCatalogData(OutputModel):
    page: Page[PaintCatalogSummary]


class PaintColorsData(OutputModel):
    page: Page[PaintColorSummary]


class SchedulingDaySummary(OutputModel):
    day_of_week: int
    label: Text | None
    enabled: bool


class SchedulingWindowSummary(OutputModel):
    id: Text | None
    title: Text | None
    time_range: Text | None
    enabled: bool


class SchedulePreferencesData(OutputModel):
    days: Page[SchedulingDaySummary]
    windows: Page[SchedulingWindowSummary]


class NotificationChannelSummary(OutputModel):
    channel: Text | None
    enabled: bool
    default_enabled: bool
    required: bool


class NotificationTypeSummary(OutputModel):
    key: Text | None
    display_name: Text | None
    sort_order: int
    channels: list[NotificationChannelSummary] = Field(max_length=20)


class NotificationGroupSummary(OutputModel):
    key: Text | None
    display_name: Text | None
    sort_order: int
    types: list[NotificationTypeSummary] = Field(max_length=20)


class NotificationsData(OutputModel):
    page: Page[NotificationGroupSummary]


class AIMessageSummary(OutputModel):
    id: Text | None
    sender_role: Text | None
    created_at: int | None
    content: Brief | None


class AIHistoryData(OutputModel):
    page: Page[AIMessageSummary]
    next_cursor: CursorText | None


class AIBootstrapData(OutputModel):
    conversation_id: Text | None
    messages: AIHistoryData
    active_response_present: bool
    starter_suggestions: list[Brief | None] | None = Field(max_length=20)


class VehicleSummary(OutputModel):
    id: Text | None
    display_name: Text | None
    status: Text | None
    make: Text | None
    model: Text | None
    year: int | None
    powertrain_type: Text | None
    powertrain_name: Text | None


class VehiclesData(OutputModel):
    page: Page[VehicleSummary]


class UtilityStatementSummary(OutputModel):
    ends_at: int | None
    total_amount_usd_due: Finite | None
    service_usage_amount: Finite | None
    service_amount_usd: Finite | None


class UtilitySummary(OutputModel):
    id: Text | None
    service_type: Text | None
    usage_unit: Text | None
    account_count: int
    statement_count: int
    graph_count: int
    statements: list[UtilityStatementSummary] = Field(max_length=20)


class UtilitiesData(OutputModel):
    page: Page[UtilitySummary]


class TaxReportSummary(OutputModel):
    id: Text | None
    issued_at: int | None
    tax_year_start: int | None
    tax_year_end: int | None
    total_tax_due: Finite | None


class PropertyTaxesData(OutputModel):
    next_tax_bill_release_at: int | None
    refresh_status: Text | None
    next_fetch_at: int | None
    page: Page[TaxReportSummary]


class PurchaseSummary(OutputModel):
    lane: Literal["pending", "approved", "purchased"]
    id: Text | None
    title: Text | None
    vendor_name: Text | None
    unit_price_usd_cents: int | None
    quantity: int | None
    updated_at: int | None
    purchased_at: int | None
    approved_at: int | None
    is_voided: bool | None
    return_by_date: int | None
    return_policy_notes: Brief | None


class PurchasesData(OutputModel):
    context_title: Text | None
    next_package_pickup_by: int | None
    non_purchase_invoice_count: int
    page: Page[PurchaseSummary]


class OnboardingSlotSummary(OutputModel):
    start_time: int
    vendor_count: int


class OnboardingAvailabilityData(OutputModel):
    message: Text | None
    timezone: Text | None
    number_of_required_vendors: int
    estimated_visit_duration_seconds: int
    page: Page[OnboardingSlotSummary]


class OnboardingEventSummary(OutputModel):
    id: Text | None
    start_at: int
    end_at: int


class OnboardingCalendarData(OutputModel):
    not_modified: bool
    page: Page[OnboardingEventSummary] | None


class RoomImageSummary(OutputModel):
    id: Text | None
    is_current: bool


class RoomImagesData(OutputModel):
    member_image_present: bool
    page: Page[RoomImageSummary]


class PhotoSummary(OutputModel):
    id: Text | None
    is_home_hero_image: bool


class PhotosData(OutputModel):
    page: Page[PhotoSummary]
