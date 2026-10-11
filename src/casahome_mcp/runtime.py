"""One lazy SDK client per process, no startup authentication or registration."""

import asyncio
import logging
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Protocol

import aiohttp
from casahome import CasaApi, CasaClient, FirebaseAuth
from casahome.const import CASA_APP_BUILD
from casahome.models.ai import CasaAIBootstrapResponse, CasaAIMessagesResponse
from casahome.models.assets import ReleaseNotesResponse, UtilitiesInsightsResponse, VehiclesResponse
from casahome.models.availability import MemberAvailabilityDetail
from casahome.models.bootstrap import HomeBadgeCounts
from casahome.models.calendar import VisitsCalendarResponse
from casahome.models.catalogs import InventoryEnumsResponse
from casahome.models.credits import MemberCredits
from casahome.models.documents import (
    DocumentDetailsResponse,
    DocumentsResponse,
    DocumentStructureSuggestionsResponse,
    DocumentSuggestionsResponse,
    DocumentTypesResponse,
    WorkDocumentSourceResponse,
)
from casahome.models.feed import HomeFeedResponse
from casahome.models.help_center import HelpCenterBundleResponse
from casahome.models.home import HomeDetailsResponse, WeatherResponse
from casahome.models.images import MatterportImage, RoomImageOptionsResponse
from casahome.models.mailbox import (
    MailboxMailItemsResponse,
    MailboxOverviewResponse,
    PackagesResponse,
)
from casahome.models.maintenance import (
    AutopilotCategory,
    CompletedRequestsResponse,
    InventoryServiceHistoryResponse,
)
from casahome.models.membership import MembershipDetails, MembershipSavings
from casahome.models.paint import (
    InventoryPaintMatchesResponse,
    PaintBrandsResponse,
    PaintCollectionsResponse,
    PaintColorsResponse,
    PaintSearchResponse,
)
from casahome.models.preferences import (
    NotificationSettingsResponse,
    OnboardingAvailabilityResponse,
    OnboardingDetailsResponse,
    SchedulePreferencesResponse,
)
from casahome.models.purchases import PurchasesResponse, ScopedPurchasesResponse
from casahome.models.read_todos import SuggestedTodosResponse, TodoDetailsResponse
from casahome.models.referral import ReferralCodeResponse
from casahome.models.requests import RequestDetails, RequestsResponse
from casahome.models.tasks import BookableHandymanTasksResponse, GroupedTaskDetails, TaskDetails
from casahome.models.taxes import PropertyTaxesResponse
from casahome.models.visits import VendorVisitDetails, VisitCallsResponse, VisitConversation

from .action_protocol import CasaActionsProtocol
from .actions.store import ActionStore
from .actions.uploads import SnapshotWorker
from .config import Settings


class CasaReads(Protocol):
    async def home_details(self, home_id: str) -> HomeDetailsResponse: ...
    async def badge_counts(self, home_id: str) -> HomeBadgeCounts: ...
    async def weather(self, home_id: str) -> WeatherResponse: ...
    async def requests_tab(self, home_id: str) -> RequestsResponse: ...
    async def request_details(self, home_id: str, request_id: str) -> RequestDetails: ...
    async def calendar(
        self, home_id: str, start: datetime | int, end: datetime | int
    ) -> VisitsCalendarResponse: ...
    async def credits_summary(self, home_id: str) -> MemberCredits: ...
    async def mailbox(self, home_id: str) -> MailboxOverviewResponse: ...
    async def mail_items(self, home_id: str) -> MailboxMailItemsResponse: ...
    async def packages(self, home_id: str) -> PackagesResponse: ...
    async def suggested_todos(self, home_id: str) -> SuggestedTodosResponse: ...
    async def todo_details(self, home_id: str, todo_id: str) -> TodoDetailsResponse: ...
    async def completed_requests(
        self, home_id: str, page: int, page_size: int = 100, search: str | None = None
    ) -> CompletedRequestsResponse: ...
    async def autopilot_plans(
        self,
        home_id: str,
        requirement_kinds: Sequence[Literal["entity_property", "room_property"]] = (
            "entity_property",
            "room_property",
        ),
    ) -> list[AutopilotCategory]: ...
    async def inventory_service_history(
        self, home_id: str, target_type: Literal["entity", "room", "home"], target_id: str
    ) -> InventoryServiceHistoryResponse: ...
    async def documents(
        self,
        home_id: str,
        *,
        cursor: str | None = None,
        limit: int = 30,
        q: str | None = None,
        document_type: str | None = None,
        sort: str | None = None,
    ) -> DocumentsResponse: ...
    async def document_types(self, home_id: str) -> DocumentTypesResponse: ...
    async def work_document_source(
        self,
        home_id: str,
        *,
        todo_id: str | None = None,
        task_id: str | None = None,
        request_id: str | None = None,
    ) -> WorkDocumentSourceResponse: ...
    async def paint_search(self, home_id: str, q: str) -> PaintSearchResponse: ...
    async def paint_brands(self, home_id: str) -> PaintBrandsResponse: ...
    async def paint_collections(
        self, home_id: str, brand_id: int | str
    ) -> PaintCollectionsResponse: ...
    async def paint_colors(self, home_id: str, collection_id: int | str) -> PaintColorsResponse: ...
    async def schedule_preferences(self, home_id: str) -> SchedulePreferencesResponse: ...
    async def notification_settings(self, home_id: str) -> NotificationSettingsResponse: ...
    async def casa_ai_bootstrap(self, home_id: str) -> CasaAIBootstrapResponse: ...
    async def casa_ai_messages(
        self, home_id: str, *, limit: int | None = None, before: str | None = None
    ) -> CasaAIMessagesResponse: ...
    async def vehicles(self, home_id: str) -> VehiclesResponse: ...
    async def utilities_insights(self, home_id: str) -> UtilitiesInsightsResponse: ...
    async def property_taxes(self, home_id: str) -> PropertyTaxesResponse: ...
    async def purchases(self, home_id: str) -> PurchasesResponse: ...
    async def onboarding_availability(self, home_id: str) -> OnboardingAvailabilityResponse: ...
    async def onboarding_details_typed(self, home_id: str) -> OnboardingDetailsResponse | None: ...
    async def room_image_options(self, home_id: str, room_id: str) -> RoomImageOptionsResponse: ...
    async def matterport_images(self, home_id: str) -> list[MatterportImage]: ...
    async def bookable_handyman_tasks(
        self, home_id: str, *, include_current_vendor_visit_id: str | None = None
    ) -> BookableHandymanTasksResponse: ...
    async def membership_info(self, home_id: str) -> MembershipDetails: ...
    async def membership_savings(self, home_id: str) -> MembershipSavings: ...
    async def inventory_enums(self, enum_type: str) -> InventoryEnumsResponse: ...
    async def release_notes_diff(
        self, *, current_build: int = CASA_APP_BUILD
    ) -> ReleaseNotesResponse: ...
    async def availability_request_details(
        self, home_id: str, availability_request_id: str
    ) -> MemberAvailabilityDetail: ...
    async def document_details(self, home_id: str, document_id: str) -> DocumentDetailsResponse: ...
    async def document_suggestions(
        self, home_id: str, document_id: str, *, view: str | None = None
    ) -> DocumentSuggestionsResponse: ...
    async def document_structure_suggestions(
        self, home_id: str, document_id: str
    ) -> DocumentStructureSuggestionsResponse: ...
    async def inventory_paint_matches(
        self, home_id: str, entity_id: str
    ) -> InventoryPaintMatchesResponse: ...
    async def request_purchases(self, home_id: str, request_id: str) -> ScopedPurchasesResponse: ...
    async def task_details(self, home_id: str, task_id: str) -> TaskDetails: ...
    async def vendor_visit_details(self, home_id: str, visit_id: str) -> VendorVisitDetails: ...
    async def vendor_visit_autopilot_plan(
        self, home_id: str, visit_id: str, plan_id: str
    ) -> GroupedTaskDetails: ...
    async def vendor_visit_calls(self, home_id: str, visit_id: str) -> VisitCallsResponse: ...
    async def vendor_visit_conversation(self, home_id: str, visit_id: str) -> VisitConversation: ...
    async def vendor_visit_purchases(
        self, home_id: str, visit_id: str
    ) -> ScopedPurchasesResponse: ...
    async def help_center_bundle(self, app_id: str) -> HelpCenterBundleResponse: ...
    async def referral_code(self) -> ReferralCodeResponse: ...
    async def home_feed(
        self, home_id: str, *, app_build: int = CASA_APP_BUILD
    ) -> HomeFeedResponse: ...


@dataclass
class AppContext:
    settings: Settings
    api: CasaReads | None = field(default=None, repr=False)
    actions: CasaActionsProtocol | None = field(default=None, repr=False)
    action_store: ActionStore = field(default_factory=ActionStore, repr=False)
    upload_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)
    upload_workers: set[SnapshotWorker] = field(default_factory=set, repr=False)
    uploads_closed: bool = False
    semaphore: asyncio.Semaphore = field(default_factory=lambda: asyncio.Semaphore(2), repr=False)
    refresh_token_rotated: bool = False
    deadline_seconds: float = 45.0

    def on_rotated(self, token: str) -> None:
        self.refresh_token_rotated = True
        logging.getLogger("casahome_mcp").warning("TOKEN_ROTATED_NOT_PERSISTED")


RuntimeFactory = Callable[[Settings], AbstractAsyncContextManager[AppContext]]


@asynccontextmanager
async def sdk_runtime(settings: Settings) -> AsyncIterator[AppContext]:
    app = AppContext(settings)
    if settings.refresh_token is None:
        yield app
        return
    async with aiohttp.ClientSession() as session:
        auth = FirebaseAuth(
            session,
            settings.refresh_token.get_secret_value(),
            on_refresh_token_rotated=app.on_rotated,
        )
        api = CasaApi(CasaClient(session, auth))
        app.api = api
        app.actions = api
        yield app
