"""One lazy SDK client per process, no startup authentication or registration."""

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

import aiohttp
from casahome import CasaApi, CasaClient, FirebaseAuth
from casahome.models.bootstrap import HomeBadgeCounts
from casahome.models.calendar import VisitsCalendarResponse
from casahome.models.credits import MemberCredits
from casahome.models.home import HomeDetailsResponse, WeatherResponse
from casahome.models.mailbox import (
    MailboxMailItemsResponse,
    MailboxOverviewResponse,
    PackagesResponse,
)
from casahome.models.requests import RequestDetails, RequestsResponse

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


@dataclass
class AppContext:
    settings: Settings
    api: CasaReads | None = field(default=None, repr=False)
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
        app.api = CasaApi(CasaClient(session, auth))
        yield app
