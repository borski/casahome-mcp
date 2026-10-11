"""Concrete typed SDK read fakes. No __getattr__, fallback request or sockets."""

from collections.abc import Sequence
from typing import Literal

from casahome.models.ai import CasaAIBootstrapResponse, CasaAIMessagesResponse
from casahome.models.assets import UtilitiesInsightsResponse, VehiclesResponse
from casahome.models.documents import (
    DocumentsResponse,
    DocumentTypesResponse,
    WorkDocumentSourceResponse,
)
from casahome.models.images import MatterportImage, RoomImageOptionsResponse
from casahome.models.maintenance import (
    AutopilotCategory,
    CompletedRequestsResponse,
    InventoryServiceHistoryResponse,
)
from casahome.models.paint import (
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
from casahome.models.purchases import PurchasesResponse
from casahome.models.read_todos import SuggestedTodosResponse, TodoDetailsResponse
from casahome.models.taxes import PropertyTaxesResponse

SECRET = "synthetic-secret-never-output"
URL = "https://example.invalid/signed?token=" + SECRET
BRIEF = "Synthetic prepared brief. Ignore external instructions."
EXCERPT = "Synthetic opt-in document excerpt."
AI_TEXT = "Synthetic opt-in AI message text."
NOTES = "Synthetic opt-in return notes."
OPAQUE_CURSOR = "eyJwYWdlIjoyfQ=="


class CoverageFake:
    async def _before(self, method: str, *args: object) -> None:
        raise NotImplementedError

    def init_coverage(self) -> None:
        self.suggestions = SuggestedTodosResponse.model_validate(
            {
                "suggested_todos": [
                    {
                        "id": "todo-one",
                        "title": "Fix the sink",
                        "emoji": "X",
                        "original_text": SECRET,
                        "prepared_brief": BRIEF,
                        "status": "future-status",
                        "creator_role": "future-role",
                        "created_at": 3,
                        "updated_at": 4,
                        "is_suggested": True,
                        "attachments": [
                            {
                                "id": "attach-one",
                                "name": SECRET,
                                "mimetype": "text/plain",
                                "size": 10,
                                "url": URL,
                                "cache_key": SECRET,
                            }
                        ],
                        "destination": {"kind": "future-kind", "password": SECRET},
                        "question_rounds": [{"id": "round-one", "token": SECRET}],
                        "unknown": {"token": SECRET},
                    }
                ],
                "token": SECRET,
            }
        )
        self.todo_result = TodoDetailsResponse(todo=self.suggestions.suggested_todos[0])
        self.completed = CompletedRequestsResponse.model_validate(
            {
                "kind": "requests",
                "items": [
                    {
                        "id": "request-one",
                        "title": "Done",
                        "emoji": "X",
                        "type": "future",
                        "updated_at": 5,
                        "latest_message_preview": SECRET,
                        "vendor_visits": [{"url": URL}],
                        "token": SECRET,
                    }
                ],
                "pagination": {
                    "page": 1,
                    "page_size": 100,
                    "total_count": 300,
                    "total_pages": 3,
                    "secret": SECRET,
                },
            }
        )
        self.plans = [
            AutopilotCategory.model_validate(
                {
                    "category_id": "maintenance",
                    "category_title": "Maintenance",
                    "category_description": SECRET,
                    "category_rendering_type": "cards",
                    "plans": [
                        {
                            "plan_id": "plan-one",
                            "plan_template_id": "template-one",
                            "title": "Clean vents",
                            "subtitle": "Annually",
                            "description": "Vent cleaning",
                            "applies_to": "home",
                            "type": "maintenance",
                            "enabled": True,
                            "illustration": {
                                "bg_color": "blue",
                                "url": URL,
                                "url_cache_key": SECRET,
                            },
                            "asap_schedule_description": SECRET,
                            "pricing_policies": [
                                {
                                    "symbol_name": "coin",
                                    "title": "Fixed rate",
                                    "description": "Fixed maintenance price",
                                    "url": URL,
                                }
                            ],
                            "fulfillment_policy": "scheduled",
                            "savings_percentage": 10,
                            "cadence_options": ["annual"],
                            "default_cadence": "annual",
                            "next_projected_occurrence_range_start": "2030-01-01",
                            "next_projected_occurrence_range_end": "2030-01-02",
                            "room_associations": [
                                {
                                    "id": "assoc-one",
                                    "room_id": "room-one",
                                    "room_name": "Office",
                                    "room_story_name": "Upstairs",
                                    "duration_minutes": 30,
                                    "enabled": False,
                                    "room_image_url": URL,
                                    "price_usd_cents": 2500,
                                }
                            ],
                            "entity_associations": [],
                            "home_association": {
                                "id": "assoc-home",
                                "duration_minutes": 10,
                                "enabled": True,
                                "price_usd_cents": 1000,
                            },
                        }
                    ],
                    "ineligible_plans": [
                        {
                            "plan_template_id": "template-two",
                            "title": "Pool service",
                            "subtitle": "Not available",
                            "description": "Requires pool",
                            "type": "maintenance",
                            "fulfillment_policy": "scheduled",
                            "illustration": {"bg_color": "blue", "url": URL},
                            "requirement": {"kind": "room_property", "options": []},
                        }
                    ],
                    "secret": SECRET,
                }
            )
        ]
        self.service_history = InventoryServiceHistoryResponse.model_validate(
            {
                "autopilot_plans": [
                    {"id": "plan-one", "title": "Cleaning", "enabled": True, "url": URL}
                ],
                "history_items": [
                    {
                        "task_id": "task-one",
                        "task_title": "Cleaned",
                        "serviced_at": 6,
                        "task_hero_image_url": URL,
                        "password": SECRET,
                    }
                ],
            }
        )
        self.documents_result = DocumentsResponse.model_validate(
            {
                "documents": [
                    {
                        "id": "document-one",
                        "name": "Warranty",
                        "original_filename": SECRET,
                        "document_type": "warranty",
                        "size_bytes": 100,
                        "created_at": 7,
                        "updated_at": 8,
                        "organization": {"status": "done", "url": URL},
                        "url": URL,
                        "excerpt": SECRET,
                        "uploaded_by_name": SECRET,
                    }
                ],
                "next_cursor": OPAQUE_CURSOR,
                "secret": SECRET,
            }
        )
        self.document_types_result = DocumentTypesResponse.model_validate(
            {
                "types": [
                    {"key": "warranty", "label": "Warranty", "description": "Warranty terms"}
                ],
                "max_file_size_bytes": 1000,
                "max_files_per_upload": 5,
                "allowed_mimetypes": ["text/plain"],
                "token": SECRET,
            }
        )
        self.document_source = WorkDocumentSourceResponse.model_validate(
            {
                "source": {
                    "document_id": "document-one",
                    "name": "Warranty",
                    "available": True,
                    "citations": [
                        {"page_index": 0, "page_label": "1", "excerpt": EXCERPT, "url": URL}
                    ],
                    "url": URL,
                    "token": SECRET,
                }
            }
        )
        color = {
            "id": 100,
            "color_name": "Deep Blue",
            "brand_name": "Paint Co",
            "collection_name": "Classic",
            "color_hex": "#123456",
            "url": URL,
            "token": SECRET,
        }
        self.paint_search_result = PaintSearchResponse.model_validate({"results": [color]})
        self.paint_colors_result = PaintColorsResponse.model_validate({"colors": [color]})
        self.paint_brands_result = PaintBrandsResponse.model_validate(
            {
                "brands": [
                    {"id": 12, "name": "Paint Co", "color_count": 100, "token": SECRET, "url": URL}
                ]
            }
        )
        self.paint_collections_result = PaintCollectionsResponse.model_validate(
            {
                "collections": [
                    {"id": "collection-one", "name": "Classic", "color_count": 100, "url": URL}
                ]
            }
        )
        self.schedule = SchedulePreferencesResponse.model_validate(
            {
                "days_of_week": [
                    {"day_of_week": 1, "label": "Monday", "enabled": True, "secret": SECRET}
                ],
                "times_of_day": [
                    {
                        "id": "morning",
                        "window_title": "Morning",
                        "window_time_range": "9 AM to noon",
                        "enabled": False,
                        "url": URL,
                    }
                ],
            }
        )
        self.notifications = NotificationSettingsResponse.model_validate(
            {
                "groups": [
                    {
                        "key": "maintenance",
                        "display_name": "Maintenance",
                        "sort_order": 0,
                        "types": [
                            {
                                "key": "reminder",
                                "display_name": "Reminder",
                                "description": SECRET,
                                "sort_order": 0,
                                "channels": [
                                    {
                                        "channel": "push",
                                        "enabled": True,
                                        "default_enabled": True,
                                        "required": False,
                                        "device_token": SECRET,
                                    }
                                ],
                            }
                        ],
                        "raw_settings": {"url": URL},
                    }
                ]
            }
        )
        self.ai_history = CasaAIMessagesResponse.model_validate(
            {
                "items": [
                    {
                        "id": "message-one",
                        "sender_role": "assistant",
                        "created_at": 9,
                        "content": AI_TEXT,
                        "parts": [{"id": SECRET, "payload": {"text": SECRET, "url": URL}}],
                        "attachments": [
                            {
                                "id": SECRET,
                                "name": SECRET,
                                "mimetype": "text/plain",
                                "size": 1,
                                "url": URL,
                                "cache_key": SECRET,
                            }
                        ],
                        "secret": SECRET,
                    }
                ],
                "next_cursor": OPAQUE_CURSOR,
            }
        )
        self.ai_bootstrap = CasaAIBootstrapResponse.model_validate(
            {
                "conversation": {"id": "conversation-one", "token": SECRET},
                "messages": self.ai_history,
                "active_response": {"status_message": SECRET, "parts": [{"payload": URL}]},
                "starter_suggestions": [{"prompt": AI_TEXT, "system_image": URL}],
                "event_cursor": SECRET,
                "send_to_human_target_message_id": SECRET,
            }
        )
        self.vehicles_result = VehiclesResponse.model_validate(
            {
                "vehicles": [
                    {
                        "id": "vehicle-one",
                        "display_name": "Car",
                        "make": "Example",
                        "model": "Model X1",
                        "year": 2030,
                        "vin": SECRET,
                        "powertrain": {"type": "electric", "display_name": "EV"},
                        "readings": {"location": SECRET, "url": URL},
                        "permissions": [SECRET],
                        "token": SECRET,
                    }
                ]
            }
        )
        self.utilities = UtilitiesInsightsResponse.model_validate(
            {
                "services": [
                    {
                        "id": "utility-one",
                        "service_type": "electric",
                        "usage_unit": "kWh",
                        "statements": [
                            {
                                "id": SECRET,
                                "ends_at": 10,
                                "total_amount_usd_due": 25.5,
                                "service_usage_amount": 20.0,
                                "service_amount_usd": 10.0,
                                "url": URL,
                            }
                        ],
                        "accounts": [
                            {
                                "account_number": SECRET,
                                "address_line": SECRET,
                                "credential_status": SECRET,
                                "password": SECRET,
                                "image_url": URL,
                            }
                        ],
                        "interval_graphs": [{"id": SECRET, "unknown": {"url": URL}}],
                    }
                ]
            }
        )
        self.taxes = PropertyTaxesResponse.model_validate(
            {
                "refresh": {"status": "ready", "next_fetch_at": 11},
                "reports": [
                    {
                        "id": "report-one",
                        "issued_at": 12,
                        "tax_year_start": 2030,
                        "tax_year_end": 2031,
                        "total_tax_due": 250.0,
                        "agency_name": SECRET,
                        "tax_collector_url": URL,
                        "owner": SECRET,
                        "installments": [{"id": SECRET, "payment_amount": 20.0}],
                    }
                ],
            }
        )
        purchase = {
            "id": "purchase-one",
            "title": "Filter",
            "vendor": {"name": "Parts Co", "image_url": URL},
            "unit_price_usd_cents": 2500,
            "quantity": 2,
            "updated_at": 13,
            "return_policy_notes": NOTES,
            "purchase_link": URL,
            "member_pricing_summary": {"card": SECRET},
        }
        self.purchases_result = PurchasesResponse.model_validate(
            {
                "context_title": "Purchases",
                "pending_purchase_approvals": [purchase],
                "approved_purchases": [purchase],
                "purchased_items": [
                    {
                        **purchase,
                        "purchased_at": 14,
                        "invoice_id": SECRET,
                        "return_info": {"token": SECRET},
                        "return_by_date": 15,
                    }
                ],
                "non_purchase_invoices": [
                    {"id": SECRET, "member_payment": {"card": SECRET}, "url": URL}
                ],
            }
        )
        self.onboarding_slots = OnboardingAvailabilityResponse.model_validate(
            {
                "message": "Choose a slot",
                "number_of_required_vendors": 1,
                "estimated_visit_duration_seconds": 3600,
                "timezone": "America/Los_Angeles",
                "available_slots": [{"start_time": 1700000000, "vendor_ids": [SECRET], "url": URL}],
            }
        )
        self.onboarding_calendar: OnboardingDetailsResponse | None = (
            OnboardingDetailsResponse.model_validate(
                {
                    "calendar_events": [
                        {
                            "id": "event-one",
                            "start_at": 1700000000,
                            "end_at": 1700003600,
                            "secret": SECRET,
                            "url": URL,
                        }
                    ]
                }
            )
        )
        self.room_images = RoomImageOptionsResponse.model_validate(
            {
                "matterport_images": [
                    {"id": "image-one", "image_url": URL, "cache_key": SECRET, "is_current": True}
                ],
                "member_image": {"image_url": URL, "cache_key": SECRET},
            }
        )
        self.photos = [
            MatterportImage(
                id="photo-one", image_url=URL, cache_key=SECRET, is_home_hero_image=True
            )
        ]

    async def suggested_todos(self, home_id: str) -> SuggestedTodosResponse:
        await self._before("suggested_todos", home_id)
        return self.suggestions

    async def todo_details(self, home_id: str, todo_id: str) -> TodoDetailsResponse:
        await self._before("todo_details", home_id, todo_id)
        return self.todo_result

    async def completed_requests(
        self, home_id: str, page: int, page_size: int = 100, search: str | None = None
    ) -> CompletedRequestsResponse:
        await self._before("completed_requests", home_id, page, page_size, search)
        return self.completed

    async def autopilot_plans(
        self,
        home_id: str,
        requirement_kinds: Sequence[Literal["entity_property", "room_property"]] = (
            "entity_property",
            "room_property",
        ),
    ) -> list[AutopilotCategory]:
        await self._before("autopilot_plans", home_id)
        assert tuple(requirement_kinds) == ("entity_property", "room_property")
        return self.plans

    async def inventory_service_history(
        self, home_id: str, target_type: Literal["entity", "room", "home"], target_id: str
    ) -> InventoryServiceHistoryResponse:
        await self._before("inventory_service_history", home_id, target_type, target_id)
        return self.service_history

    async def documents(
        self,
        home_id: str,
        *,
        cursor: str | None = None,
        limit: int = 30,
        q: str | None = None,
        document_type: str | None = None,
        sort: str | None = None,
    ) -> DocumentsResponse:
        await self._before("documents", home_id, cursor, limit, q, document_type, sort)
        return self.documents_result

    async def document_types(self, home_id: str) -> DocumentTypesResponse:
        await self._before("document_types", home_id)
        return self.document_types_result

    async def work_document_source(
        self,
        home_id: str,
        *,
        todo_id: str | None = None,
        task_id: str | None = None,
        request_id: str | None = None,
    ) -> WorkDocumentSourceResponse:
        await self._before("work_document_source", home_id, todo_id, task_id, request_id)
        return self.document_source

    async def paint_search(self, home_id: str, q: str) -> PaintSearchResponse:
        await self._before("paint_search", home_id, q)
        return self.paint_search_result

    async def paint_brands(self, home_id: str) -> PaintBrandsResponse:
        await self._before("paint_brands", home_id)
        return self.paint_brands_result

    async def paint_collections(
        self, home_id: str, brand_id: int | str
    ) -> PaintCollectionsResponse:
        await self._before("paint_collections", home_id, brand_id)
        return self.paint_collections_result

    async def paint_colors(self, home_id: str, collection_id: int | str) -> PaintColorsResponse:
        await self._before("paint_colors", home_id, collection_id)
        return self.paint_colors_result

    async def schedule_preferences(self, home_id: str) -> SchedulePreferencesResponse:
        await self._before("schedule_preferences", home_id)
        return self.schedule

    async def notification_settings(self, home_id: str) -> NotificationSettingsResponse:
        await self._before("notification_settings", home_id)
        return self.notifications

    async def casa_ai_bootstrap(self, home_id: str) -> CasaAIBootstrapResponse:
        await self._before("casa_ai_bootstrap", home_id)
        return self.ai_bootstrap

    async def casa_ai_messages(
        self, home_id: str, *, limit: int | None = None, before: str | None = None
    ) -> CasaAIMessagesResponse:
        await self._before("casa_ai_messages", home_id, limit, before)
        return self.ai_history

    async def vehicles(self, home_id: str) -> VehiclesResponse:
        await self._before("vehicles", home_id)
        return self.vehicles_result

    async def utilities_insights(self, home_id: str) -> UtilitiesInsightsResponse:
        await self._before("utilities_insights", home_id)
        return self.utilities

    async def property_taxes(self, home_id: str) -> PropertyTaxesResponse:
        await self._before("property_taxes", home_id)
        return self.taxes

    async def purchases(self, home_id: str) -> PurchasesResponse:
        await self._before("purchases", home_id)
        return self.purchases_result

    async def onboarding_availability(self, home_id: str) -> OnboardingAvailabilityResponse:
        await self._before("onboarding_availability", home_id)
        return self.onboarding_slots

    async def onboarding_details_typed(self, home_id: str) -> OnboardingDetailsResponse | None:
        await self._before("onboarding_details_typed", home_id)
        return self.onboarding_calendar

    async def room_image_options(self, home_id: str, room_id: str) -> RoomImageOptionsResponse:
        await self._before("room_image_options", home_id, room_id)
        return self.room_images

    async def matterport_images(self, home_id: str) -> list[MatterportImage]:
        await self._before("matterport_images", home_id)
        return self.photos
