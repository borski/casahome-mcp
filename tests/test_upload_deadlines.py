"""Offline upload deadline/lease regressions. Only synthetic regular-file fixtures."""

import asyncio
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
from action_fakes import FakeActions
from casahome.models.documents import DocumentTypesResponse
from mcp import Client
from mcp.server.mcpserver.exceptions import ToolError
from test_actions import harness
from test_tools import MODES, SECRET, Harness, failed, guard_sockets, success

from casahome_mcp.actions.store import MAX_BYTES
from casahome_mcp.actions.tools import prepare_upload_document
from casahome_mcp.actions.uploads import LOCAL_FILE_CAP, snapshot_file


class BlockingSnapshot:
    def __init__(self) -> None:
        self.entered = threading.Event()
        self.release = threading.Event()
        self.calls = 0

    def read(self, file_path: str, limit: int) -> bytes:
        self.calls += 1
        self.entered.set()
        # A finite test fail-safe, not an interrupt capability of the real reader.
        if not self.release.wait(5):
            raise AssertionError("Synthetic worker wasn't released")
        return snapshot_file(file_path, limit)


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    guard_sockets(monkeypatch)


@pytest.fixture
def fixture_path(tmp_path: Path) -> Path:
    path = tmp_path / "synthetic.txt"
    path.write_bytes(b"fixture")
    return path


@pytest.fixture
def blocked_reader(monkeypatch: pytest.MonkeyPatch) -> Iterator[BlockingSnapshot]:
    reader = BlockingSnapshot()
    monkeypatch.setattr("casahome_mcp.actions.tools.snapshot_file", reader.read)
    yield reader
    reader.release.set()


def configured_harness() -> Harness:
    h = harness()
    h.app.actions = FakeActions(h.fake)
    # Exercise the actual 25 MiB reservation without allocating a large fixture.
    h.fake.document_types_result = h.fake.document_types_result.model_copy(
        update={"max_file_size_bytes": LOCAL_FILE_CAP}
    )
    return h


def arguments(path: Path) -> dict[str, object]:
    return {
        "file_path": str(path),
        "filename": "fixture.txt",
        "mimetype": "text/plain",
        "find_todos": False,
    }


async def wait_started(reader: BlockingSnapshot) -> None:
    async with asyncio.timeout(1):
        while not reader.entered.is_set():
            await asyncio.sleep(0.001)


async def wait_reclaimed(h: Harness) -> None:
    async with asyncio.timeout(1):
        while h.app.upload_workers:
            await asyncio.sleep(0.001)
    assert not h.app.upload_lock.locked()
    assert h.app.action_store.remaining_bytes() == MAX_BYTES


@pytest.mark.parametrize("mode", MODES)
async def test_actual_mcp_snapshot_timeout_no_late_token_or_write(
    fixture_path: Path,
    blocked_reader: BlockingSnapshot,
    mode: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    h = configured_harness()
    actions = FakeActions(h.fake)
    h.app.actions = actions
    h.app.deadline_seconds = 0.01
    async with Client(h.server, mode=mode) as client:
        # The reader stays blocked, so a successful preview would reproduce P2.
        async with asyncio.timeout(1):
            response = await client.call_tool(
                "casa_prepare_upload_document", arguments(fixture_path)
            )
        failed(response, "TIMEOUT")
        assert str(fixture_path) not in response.model_dump_json()
        await wait_started(blocked_reader)
        assert h.app.upload_lock.locked()
        assert len(h.app.upload_workers) == 1
        worker = next(iter(h.app.upload_workers))
        assert h.app.action_store.remaining_bytes() == MAX_BYTES - LOCAL_FILE_CAP
        assert actions.calls == []
        # Repeated timeouts must queue, not launch more allocating workers.
        for _ in range(3):
            failed(
                await client.call_tool("casa_prepare_upload_document", arguments(fixture_path)),
                "TIMEOUT",
            )
        assert blocked_reader.calls == 1
        assert len(h.fake.calls) == 1  # Only the first policy GET.
        assert h.app.action_store.remaining_bytes() == MAX_BYTES - LOCAL_FILE_CAP
        blocked_reader.release.set()
        await wait_reclaimed(h)  # MAX_BYTES also proves no late snapshot token.
        assert not any(isinstance(value, bytes) for value in vars(worker).values())
        h.app.deadline_seconds = 1
        prepared = success(
            await client.call_tool("casa_prepare_upload_document", arguments(fixture_path))
        )
        assert "confirmation_token" in prepared
        assert h.app.action_store.remaining_bytes() == MAX_BYTES - 7
        assert actions.calls == []
    assert SECRET not in caplog.text


@pytest.mark.parametrize("queued", ["lock", "semaphore"])
@pytest.mark.parametrize("mode", MODES)
async def test_queued_wait_uses_deadline_without_releasing_another_lease(
    fixture_path: Path,
    blocked_reader: BlockingSnapshot,
    mode: str,
    queued: str,
) -> None:
    h = configured_harness()
    h.app.deadline_seconds = 0.01
    if queued == "lock":
        await h.app.upload_lock.acquire()
    else:
        await h.app.semaphore.acquire()
        await h.app.semaphore.acquire()
    try:
        async with Client(h.server, mode=mode) as client, asyncio.timeout(1):
            failed(
                await client.call_tool("casa_prepare_upload_document", arguments(fixture_path)),
                "TIMEOUT",
            )
            assert h.app.upload_lock.locked() is (queued == "lock")
            assert h.fake.calls == []
            assert h.app.action_store.remaining_bytes() == MAX_BYTES
            assert not h.app.upload_workers
            assert blocked_reader.calls == 0
    finally:
        if queued == "lock":
            h.app.upload_lock.release()
        else:
            h.app.semaphore.release()
            h.app.semaphore.release()


@pytest.mark.parametrize("mode", MODES)
async def test_policy_timeout_is_sanitized_and_never_starts_worker(
    fixture_path: Path,
    blocked_reader: BlockingSnapshot,
    mode: str,
) -> None:
    h = configured_harness()
    h.app.deadline_seconds = 0.01
    h.fake.release = asyncio.Event()
    async with Client(h.server, mode=mode) as client, asyncio.timeout(1):
        failed(
            await client.call_tool("casa_prepare_upload_document", arguments(fixture_path)),
            "TIMEOUT",
        )
    assert blocked_reader.calls == 0
    assert not h.app.upload_workers
    assert not h.app.upload_lock.locked()
    assert h.app.action_store.remaining_bytes() == MAX_BYTES


@pytest.mark.parametrize("queued", [False, True])
async def test_parent_cancelled_twice_keeps_actual_worker_lease(
    fixture_path: Path,
    blocked_reader: BlockingSnapshot,
    queued: bool,
) -> None:
    h = configured_harness()
    h.app.deadline_seconds = 1
    first = asyncio.create_task(
        prepare_upload_document(h.app, str(fixture_path), "fixture.txt", "text/plain", False)
    )
    await wait_started(blocked_reader)
    parent = first
    if queued:
        parent = asyncio.create_task(
            prepare_upload_document(h.app, str(fixture_path), "fixture.txt", "text/plain", False)
        )
        await asyncio.sleep(0)
    try:
        parent.cancel()
        parent.cancel()
        with pytest.raises(asyncio.CancelledError):
            await parent
        assert parent.cancelling() == 2
        assert h.app.upload_lock.locked()
        assert len(h.app.upload_workers) == 1
        assert h.app.action_store.remaining_bytes() == MAX_BYTES - LOCAL_FILE_CAP
        first.cancel()
        first.cancel()
        await asyncio.gather(first, return_exceptions=True)
        assert h.app.action_store.remaining_bytes() == MAX_BYTES - LOCAL_FILE_CAP
        blocked_reader.release.set()
        await wait_reclaimed(h)
        assert blocked_reader.calls == 1
        assert len(h.fake.calls) == 1
    finally:
        first.cancel()
        parent.cancel()
        blocked_reader.release.set()
        await asyncio.gather(first, parent, return_exceptions=True)
        await wait_reclaimed(h)


async def test_reservation_bounds_pending_plus_abandoned_worker(
    fixture_path: Path,
    blocked_reader: BlockingSnapshot,
) -> None:
    h = configured_harness()
    h.app.deadline_seconds = 0.01
    with pytest.raises(ToolError, match="TIMEOUT"):
        await prepare_upload_document(h.app, str(fixture_path), "fixture.txt", "text/plain", False)
    assert h.app.action_store.remaining_bytes() == MAX_BYTES - LOCAL_FILE_CAP
    with pytest.raises(ToolError, match="CAPACITY_EXCEEDED"):
        h.app.action_store.reserve_snapshot(40 * 1024 * 1024)
    # Clearing previews must not clear live-worker capacity ownership.
    h.app.action_store.clear()
    assert h.app.action_store.remaining_bytes() == MAX_BYTES - LOCAL_FILE_CAP
    blocked_reader.release.set()
    await wait_reclaimed(h)
    reservation = h.app.action_store.reserve_snapshot(MAX_BYTES)
    h.app.action_store.release_snapshot(reservation)
    assert h.app.action_store.remaining_bytes() == MAX_BYTES


async def test_shutdown_abandons_worker_without_waiting_for_filesystem(
    fixture_path: Path,
    blocked_reader: BlockingSnapshot,
) -> None:
    h = configured_harness()
    h.app.deadline_seconds = 0.01
    async with asyncio.timeout(1):
        async with Client(h.server) as client:
            failed(
                await client.call_tool("casa_prepare_upload_document", arguments(fixture_path)),
                "TIMEOUT",
            )
            await wait_started(blocked_reader)
        # EOF/server shutdown returned while the synthetic syscall is still blocked.
        assert not blocked_reader.release.is_set()
        assert h.app.uploads_closed
        assert h.app.upload_lock.locked()
        assert h.app.action_store.remaining_bytes() == MAX_BYTES - LOCAL_FILE_CAP
    with pytest.raises(ToolError, match="TIMEOUT"):
        await prepare_upload_document(h.app, str(fixture_path), "fixture.txt", "text/plain", False)
    blocked_reader.release.set()
    await wait_reclaimed(h)


async def test_policy_time_spends_the_same_snapshot_deadline(
    fixture_path: Path,
    blocked_reader: BlockingSnapshot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    h = configured_harness()
    h.app.deadline_seconds = 0.2
    policy_started = asyncio.Event()
    original = h.fake.document_types

    async def delayed_policy(home: str) -> DocumentTypesResponse:
        policy_started.set()
        await asyncio.sleep(0.15)
        return await original(home)

    monkeypatch.setattr(h.fake, "document_types", delayed_policy)
    async with Client(h.server) as client:
        request = asyncio.create_task(
            client.call_tool("casa_prepare_upload_document", arguments(fixture_path))
        )
        try:
            await policy_started.wait()
            await wait_started(blocked_reader)
            # Only ~50 ms remains. A fresh 200 ms snapshot timeout would fail
            # this bound, proving lock/policy/reader don't get separate budgets.
            async with asyncio.timeout(0.12):
                failed(await request, "TIMEOUT")
            assert h.app.action_store.remaining_bytes() == MAX_BYTES - LOCAL_FILE_CAP
        finally:
            request.cancel()
            blocked_reader.release.set()
            await asyncio.gather(request, return_exceptions=True)
            await wait_reclaimed(h)


async def test_thread_start_failure_reclaims_reservation_and_caller_lock(
    fixture_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_start(thread: threading.Thread) -> None:
        raise RuntimeError(SECRET)

    monkeypatch.setattr(threading.Thread, "start", fail_start)
    h = configured_harness()
    with pytest.raises(ToolError, match=r"^INVALID_FILE:") as raised:
        await prepare_upload_document(h.app, str(fixture_path), "fixture.txt", "text/plain", False)
    assert SECRET not in str(raised.value)
    await wait_reclaimed(h)
