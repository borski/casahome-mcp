import asyncio
from unittest.mock import AsyncMock, Mock

import aiohttp
import pytest
from casahome import CasaApi
from pydantic import SecretStr

from casahome_mcp import runtime
from casahome_mcp.config import Settings


@pytest.fixture
def sessions(monkeypatch: pytest.MonkeyPatch) -> list[aiohttp.ClientSession]:
    original = aiohttp.ClientSession
    allocated: list[aiohttp.ClientSession] = []

    def session_factory() -> aiohttp.ClientSession:
        session = original()
        allocated.append(session)
        return session

    monkeypatch.setattr(aiohttp, "ClientSession", session_factory)
    monkeypatch.setattr(
        original,
        "_request",
        AsyncMock(side_effect=AssertionError("Unexpected HTTP request")),
    )
    return allocated


def configured() -> Settings:
    return Settings(refresh_token=SecretStr("synthetic-runtime-token"))


async def test_no_credentials_allocates_nothing(sessions: list[aiohttp.ClientSession]) -> None:
    async with runtime.sdk_runtime(Settings()) as app:
        assert app.api is None
    assert sessions == []


async def test_single_shared_lazy_client_and_rotation(
    sessions: list[aiohttp.ClientSession], caplog: pytest.LogCaptureFixture
) -> None:
    async with runtime.sdk_runtime(configured()) as app:
        assert len(sessions) == 1 and not sessions[0].closed
        assert isinstance(app.api, CasaApi)
        assert app.api.client.auth.user_id is None
        app.on_rotated("synthetic-rotated-secret")
        assert app.refresh_token_rotated
        assert "synthetic-rotated-secret" not in caplog.text
        assert "TOKEN_ROTATED_NOT_PERSISTED" in caplog.text
    assert sessions[0].closed


@pytest.mark.parametrize("raise_inside", [False, True])
async def test_close_on_exit_and_body_failure(
    sessions: list[aiohttp.ClientSession], raise_inside: bool
) -> None:
    try:
        async with runtime.sdk_runtime(configured()):
            if raise_inside:
                raise RuntimeError("synthetic")
    except RuntimeError:
        assert raise_inside
    assert len(sessions) == 1 and sessions[0].closed


async def test_close_on_constructor_failure(
    sessions: list[aiohttp.ClientSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(runtime, "CasaClient", Mock(side_effect=RuntimeError("synthetic")))
    with pytest.raises(RuntimeError):
        async with runtime.sdk_runtime(configured()):
            pytest.fail("Should not reach yield")
    assert sessions[0].closed


async def test_close_on_cancellation(sessions: list[aiohttp.ClientSession]) -> None:
    entered = asyncio.Event()

    async def worker() -> None:
        async with runtime.sdk_runtime(configured()):
            entered.set()
            await asyncio.Event().wait()

    task = asyncio.create_task(worker())
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert sessions[0].closed
