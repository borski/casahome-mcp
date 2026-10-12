"""Exercise the real stdio entry point without credentials or network access.

MCP owns negotiation, framing, and pipe shutdown. Parent-side instrumentation
only observes the spawned process and tees its raw stdout, including bytes the
SDK discards during shutdown. The child has no production fake mode.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TextIO

import anyio
import pytest
from anyio.abc import Process
from coverage_cases import COVERAGE_CASES
from detail_cases import DETAIL_CASES
from detail_cases import GATED_TOOLS as DETAIL_GATED_TOOLS
from mcp import Client
from mcp.client import stdio as stdio_transport
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import CallToolResult, TextContent, Tool, jsonrpc_message_adapter
from test_actions import CASES as ACTION_CASES

from casahome_mcp.actions.policy import gated_action_tools
from casahome_mcp.actions.tools import ACTION_TOOLS
from casahome_mcp.config import Settings
from casahome_mcp.tools import TOOL_METHODS

HOME_ID = "11111111-1111-4111-8111-111111111111"
HOME_LABEL = "Synthetic home"
DUMMY_TOKEN = "synthetic-refresh-token-never-log-stdio-42"
LOCAL_TOOLS = frozenset({"casa_get_status", "casa_list_homes"})
REMOTE_TOOLS = (
    frozenset(case[0] for case in COVERAGE_CASES) | frozenset(case[0] for case in DETAIL_CASES)
) | frozenset(
    {
        "casa_get_badge_counts",
        "casa_get_weather",
        "casa_list_inventory",
        "casa_get_inventory_item",
        "casa_list_requests",
        "casa_get_request",
        "casa_list_calendar",
        "casa_get_credits",
        "casa_get_mailbox",
        "casa_list_mail_items",
        "casa_list_packages",
    }
)
# Reads python-casahome still marks unverified. Only these sit behind the gate.
GATED_TOOLS = DETAIL_GATED_TOOLS
INHERITED_SENTINEL = "synthetic-inherited-secret-must-not-reach-child"
FORBIDDEN_INHERITED_KEYS = (
    "CASA_MODE",
    "CASA_REFRESH_TOKEN",
    "CASA_HOMES_JSON",
    "CASA_ALLOW_UNVERIFIED_READS",
    "CASA_ALLOW_ACTIONS",
    "CASA_ALLOW_UNVERIFIED_ACTIONS",
    "CASA_ALLOW_MESSAGES",
    "CASA_ALLOW_UPLOADS",
    "CASA_UNKNOWN_SETTING",
    "OP_SERVICE_ACCOUNT_TOKEN",
    "OP_SESSION_TEST",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "no_proxy",
    "PYTHONPATH",
    "PYTHONHOME",
    "PYTHONSTARTUP",
    "PYTHONINSPECT",
    "PYTHONUSERBASE",
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "OTEL_EXPORTER_OTLP_HEADERS",
    "OTEL_TRACES_EXPORTER",
    "OTEL_METRICS_EXPORTER",
    "OTEL_LOGS_EXPORTER",
    "SSLKEYLOGFILE",
    "REQUESTS_CA_BUNDLE",
    "AWS_SECRET_ACCESS_KEY",
)

# This source lives only in a test-owned temporary directory. Recording fixed
# markers never includes addresses, arguments, or credentials. The audit hook
# also rejects lower-level connect calls and DNS resolution before any syscall.
GUARD_SOURCE = """\
import os
import socket
import sys
from pathlib import Path
from typing import NoReturn

_violations = Path(os.environ["TEST_EGRESS_VIOLATIONS"])

def _deny(marker: str) -> NoReturn:
    with _violations.open("a", encoding="utf-8") as stream:
        stream.write(marker + "\\n")
    raise PermissionError("TEST_EGRESS_BLOCKED")

def _connect(self: socket.socket, address: object) -> NoReturn:
    _deny("socket.connect")

def _connect_ex(self: socket.socket, address: object) -> NoReturn:
    _deny("socket.connect_ex")

def _create_connection(*args: object, **kwargs: object) -> NoReturn:
    _deny("socket.create_connection")

def _audit(event: str, args: tuple[object, ...]) -> None:
    if event in {
        "socket.connect", "socket.getaddrinfo",
        "socket.gethostbyname", "socket.gethostbyaddr", "socket.bind",
    }:
        _deny("socket.audit")

socket.socket.connect = _connect
socket.socket.connect_ex = _connect_ex
socket.create_connection = _create_connection
sys.addaudithook(_audit)
Path(os.environ["TEST_EGRESS_LOADED"]).write_text("guard-loaded\\n", encoding="utf-8")
"""

# A separate audit hook and resolver sentinel make this control fail closed even
# if sitecustomize fails to load or stops intercepting an API. No OS connect or
# resolver call is permitted, even to the numeric documentation-only address.
NEGATIVE_CONTROL_SOURCE = """\
import socket
import sys
from typing import NoReturn

def _no_syscall(event: str, args: tuple[object, ...]) -> None:
    if event in {"socket.connect", "socket.getaddrinfo"}:
        raise AssertionError("GUARD_REACHED_SOCKET_OR_RESOLVER")

def _no_resolver(*args: object, **kwargs: object) -> NoReturn:
    raise AssertionError("GUARD_REACHED_RESOLVER")

sys.addaudithook(_no_syscall)
socket.getaddrinfo = _no_resolver
try:
    if sys.argv[1] == "create_connection":
        socket.create_connection(("203.0.113.1", 443), timeout=0.1)
    else:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            if sys.argv[1] == "connect":
                sock.connect(("203.0.113.1", 443))
            else:
                assert sys.argv[1] == "connect_ex"
                sock.connect_ex(("203.0.113.1", 443))
except PermissionError as exc:
    assert str(exc) == "TEST_EGRESS_BLOCKED"
else:
    raise AssertionError("GUARD_DID_NOT_BLOCK")
print("blocked-before-network")
"""


@dataclass
class GuardedChild:
    env: dict[str, str]
    loaded: Path
    violations: Path

    def assert_loaded(self) -> None:
        assert self.loaded.read_text(encoding="utf-8") == "guard-loaded\n"

    def assert_no_egress(self) -> None:
        self.assert_loaded()
        assert self.violations.read_text(encoding="utf-8") == ""


@dataclass
class ProcessCapture:
    process: Process | None = None
    stdout: bytearray = field(default_factory=bytearray)
    stdout_eof: bool = False


def _interpreter() -> str:
    # Don't accidentally spawn a system Python that lacks the locked packages.
    project = Path(__file__).resolve().parents[1]
    assert Path(sys.executable).parent.parent == project / ".venv"
    return sys.executable


def _poison_inherited_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in FORBIDDEN_INHERITED_KEYS:
        monkeypatch.setenv(name, INHERITED_SENTINEL)
    # A leaked setting would enable the remote call in the absent-token case.
    monkeypatch.setenv("CASA_ALLOW_UNVERIFIED_READS", "true")


def _guarded_child(tmp_path: Path) -> GuardedChild:
    guard_dir = tmp_path / "egress-guard"
    guard_dir.mkdir()
    home_dir = tmp_path / "isolated-home"
    home_dir.mkdir()
    (guard_dir / "sitecustomize.py").write_text(GUARD_SOURCE, encoding="utf-8")
    loaded = tmp_path / "guard-loaded"
    violations = tmp_path / "guard-violations"
    violations.write_text("", encoding="utf-8")

    # Construct, never copy, the environment. HOME and cwd are test-owned so
    # startup cannot discover a user's dotenv, credential files, or configuration.
    os_allowlist = ("PATH",)
    if sys.platform == "win32":
        os_allowlist += ("SYSTEMROOT", "WINDIR", "PATHEXT")
    env = {name: os.environ[name] for name in os_allowlist if name in os.environ}
    env.update(
        {
            "HOME": str(home_dir),
            "PYTHONPATH": str(guard_dir),
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUNBUFFERED": "1",
            "PYTHONWARNINGS": "always::ResourceWarning",
            "TEST_EGRESS_LOADED": str(loaded),
            "TEST_EGRESS_VIOLATIONS": str(violations),
            "CASA_HOMES_JSON": json.dumps([{"id": HOME_ID, "label": HOME_LABEL}]),
            "CASA_MODE": "read_only",
            "CASA_ALLOW_UNVERIFIED_READS": "false",
        }
    )
    if sys.platform == "win32":
        env["USERPROFILE"] = str(home_dir)
    return GuardedChild(env=env, loaded=loaded, violations=violations)


def _observe_stdio_process(monkeypatch: pytest.MonkeyPatch, child: GuardedChild) -> ProcessCapture:
    capture = ProcessCapture()
    open_process = anyio.open_process

    # The official transport merges a small default environment into env. Remove
    # extra default names from the parent for this test rather than permitting
    # anything beyond our explicit OS allowlist. All changes are fixture-scoped.
    for name in stdio_transport.DEFAULT_INHERITED_ENV_VARS:
        if name not in child.env:
            monkeypatch.delenv(name, raising=False)

    async def observed_open_process(
        command: Sequence[str],
        *,
        env: Mapping[str, str] | None,
        stderr: TextIO,
        cwd: Path | str | None,
        start_new_session: bool,
    ) -> Process:
        assert capture.process is None, "Expected exactly one real server process"
        assert list(command) == [_interpreter(), "-m", "casahome_mcp"]
        assert env == child.env, "The actual spawn environment must be explicitly controlled"
        process = await open_process(
            command, env=env, stderr=stderr, cwd=cwd, start_new_session=start_new_session
        )
        capture.process = process
        stdout = process.stdout
        assert stdout is not None
        receive = stdout.receive

        async def tee_receive(max_bytes: int = 65536) -> bytes:
            try:
                chunk = await receive(max_bytes)
            except anyio.EndOfStream:
                capture.stdout_eof = True
                raise
            capture.stdout.extend(chunk)
            return chunk

        monkeypatch.setattr(stdout, "receive", tee_receive)
        return process

    monkeypatch.setattr(anyio, "open_process", observed_open_process)
    return capture


def _object(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    assert all(isinstance(key, str) for key in value)
    return {str(key): item for key, item in value.items()}


def _structured_payload(result: CallToolResult) -> dict[str, object]:
    assert not result.is_error
    assert result.structured_content is not None
    assert len(result.content) == 1
    text = result.content[0]
    assert isinstance(text, TextContent)
    assert json.loads(text.text) == result.structured_content
    assert DUMMY_TOKEN not in result.model_dump_json()
    assert INHERITED_SENTINEL not in result.model_dump_json()
    return _object(result.structured_content)


def _assert_tool_listing(tools: list[Tool]) -> None:
    names = [tool.name for tool in tools]
    assert len(names) == len(set(names)) == len(TOOL_METHODS) + len(LOCAL_TOOLS) + len(ACTION_TOOLS)
    assert set(names) == LOCAL_TOOLS | REMOTE_TOOLS | ACTION_TOOLS
    for tool in tools:
        if tool.name in ACTION_TOOLS:
            assert tool.annotations and tool.annotations.read_only_hint is False
            continue  # Exact action annotations covered by the action protocol tests.
        assert tool.description and tool.description.strip()
        assert tool.input_schema["type"] == "object"
        properties = _object(tool.input_schema["properties"])
        assert "ctx" not in properties
        assert "context" not in properties
        if tool.name in LOCAL_TOOLS:
            assert properties == {}
        elif tool.name in GATED_TOOLS:
            assert "home_id" in properties
            assert "CASA_ALLOW_UNVERIFIED_READS" in tool.description
            assert "UNVERIFIED" in tool.description
        else:
            assert "home_id" in properties
            assert "Casa read verified by SDK evidence." in tool.description
            assert "CASA_ALLOW_UNVERIFIED_READS" not in tool.description
        assert tool.output_schema is not None
        assert tool.output_schema["type"] == "object"
        assert set(_object(tool.output_schema["properties"])) == {
            "source",
            "confidence",
            "home_id",
            "fetched_at",
            "warnings",
            "data",
        }
        annotations = tool.annotations
        assert annotations is not None
        assert annotations.read_only_hint is True
        assert annotations.destructive_hint is False
        assert annotations.idempotent_hint is True
        assert annotations.open_world_hint is (tool.name in REMOTE_TOOLS)


def _assert_private_diagnostics(stdout: bytes, stderr: bytes) -> None:
    for marker in (DUMMY_TOKEN, INHERITED_SENTINEL):
        assert marker.encode() not in stdout
        assert marker.encode() not in stderr
    lowered = stderr.lower()
    for warning in (b"unclosed", b"resourcewarning", b"traceback", b"was never awaited"):
        assert warning not in lowered


def test_child_environment_excludes_inherited_credentials_and_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _poison_inherited_environment(monkeypatch)
    child = _guarded_child(tmp_path)
    assert INHERITED_SENTINEL not in child.env.values()
    assert "CASA_REFRESH_TOKEN" not in child.env
    assert child.env["CASA_ALLOW_UNVERIFIED_READS"] == "false"
    assert child.env["CASA_MODE"] == "read_only"
    assert child.env["PYTHONPATH"] == str(tmp_path / "egress-guard")
    assert Path(child.env["HOME"]).parent == tmp_path
    for name in FORBIDDEN_INHERITED_KEYS:
        if name not in {
            "CASA_HOMES_JSON",
            "CASA_MODE",
            "CASA_ALLOW_UNVERIFIED_READS",
            "PYTHONPATH",
        }:
            assert name not in child.env


@pytest.mark.parametrize("mode", ["auto", "legacy"])
@pytest.mark.parametrize("token", [None, DUMMY_TOKEN], ids=["absent-token", "dummy-token"])
async def test_real_stdio_smoke_and_clean_eof(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str, token: str | None
) -> None:
    _poison_inherited_environment(monkeypatch)
    child = _guarded_child(tmp_path)
    if token is not None:
        child.env["CASA_REFRESH_TOKEN"] = token
    capture = _observe_stdio_process(monkeypatch, child)
    parameters = StdioServerParameters(
        command=_interpreter(), args=["-m", "casahome_mcp"], env=child.env, cwd=tmp_path
    )
    stderr_path = tmp_path / "server-stderr"
    with anyio.fail_after(20), stderr_path.open("w", encoding="utf-8") as errlog:
        async with Client(
            stdio_client(parameters, errlog=errlog), mode=mode, read_timeout_seconds=10
        ) as client:
            child.assert_no_egress()
            listing = await client.list_tools()
            assert listing.next_cursor is None
            _assert_tool_listing(listing.tools)

            status = _structured_payload(await client.call_tool("casa_get_status"))
            assert status["source"] == "runtime"
            assert status["confidence"] == "LOCAL"
            assert status["home_id"] is None
            assert status["fetched_at"] is None
            assert status["warnings"] == []
            data = _object(status["data"])
            assert isinstance(data["version"], str) and data["version"]
            assert data["mode"] == "read_only"
            assert data["token_configured"] is (token is not None)
            assert data["configured_home_count"] == 1
            assert data["allow_unverified_reads"] is False
            assert data["allow_actions"] is data["allow_messages"] is data["allow_uploads"] is False
            assert data["refresh_token_rotated"] is False
            disabled = data["disabled_features"]
            assert isinstance(disabled, list)
            expected = GATED_TOOLS | set(gated_action_tools(Settings()))
            assert len(disabled) == len(expected)
            assert set(disabled) == expected
            assert data["allow_unverified_actions"] is False

            homes = _structured_payload(await client.call_tool("casa_list_homes"))
            assert homes == {
                "source": "configuration",
                "confidence": "LOCAL",
                "home_id": None,
                "fetched_at": None,
                "warnings": [],
                "data": {"homes": [{"id": HOME_ID, "label": HOME_LABEL}]},
            }

            # The gated read must refuse before credentials, with or without a token.
            denied = await client.call_tool(
                "casa_get_task_details", {"home_id": HOME_ID, "task_id": "task-one"}
            )
            assert denied.is_error is True
            assert denied.structured_content is None
            assert len(denied.content) == 1
            error_text = denied.content[0]
            assert isinstance(error_text, TextContent)
            assert "UNVERIFIED_DISABLED:" in error_text.text
            assert "CASA_ALLOW_UNVERIFIED_READS" in error_text.text
            assert "AUTH_NOT_CONFIGURED" not in error_text.text
            for operation, arguments in ACTION_CASES:
                action_denied = await client.call_tool(
                    "casa_prepare_" + operation, {**arguments, "home_id": HOME_ID}
                )
                assert action_denied.is_error
                assert "ACTIONS_DISABLED" in action_denied.model_dump_json()
            upload_denied = await client.call_tool(
                "casa_prepare_upload_document",
                {
                    "file_path": "/synthetic/never-read",
                    "filename": "fixture.txt",
                    "mimetype": "text/plain",
                    "find_todos": False,
                    "home_id": HOME_ID,
                },
            )
            assert upload_denied.is_error
            assert "ACTIONS_DISABLED" in upload_denied.model_dump_json()
            if token is None:
                # A verified read skips the gate but still can't reach Casa without a token.
                unauth = await client.call_tool("casa_get_weather", {"home_id": HOME_ID})
                assert unauth.is_error is True
                assert unauth.structured_content is None
                unauth_text = unauth.content[0]
                assert isinstance(unauth_text, TextContent)
                assert "AUTH_NOT_CONFIGURED:" in unauth_text.text
            child.assert_no_egress()
        # Leaving the official transport closes stdin. A signal-killed server
        # fails the returncode assertion instead of masquerading as an EOF exit.

    assert capture.process is not None
    assert capture.process.returncode == 0
    assert capture.stdout_eof, "Capture must include all stdout through EOF, including shutdown"
    child.assert_no_egress()
    stdout = bytes(capture.stdout)
    stderr = stderr_path.read_bytes()
    _assert_private_diagnostics(stdout, stderr)
    assert stderr == b"", "Unexpected stderr can hide sanitized unclosed-session diagnostics"
    assert stdout and stdout.endswith(b"\n")
    lines = stdout.splitlines()
    assert len(lines) >= 5
    for line in lines:
        # Independent validation only. Never generate our own MCP requests or
        # initialize/discover messages, and never trust the SDK's stdout drain.
        assert line
        jsonrpc_message_adapter.validate_json(line, by_name=False)


@pytest.mark.parametrize("api", ["connect", "connect_ex", "create_connection"])
def test_child_egress_guard_negative_control(tmp_path: Path, api: str) -> None:
    child = _guarded_child(tmp_path)
    completed = subprocess.run(
        [_interpreter(), "-c", NEGATIVE_CONTROL_SOURCE, api],
        input=b"",
        capture_output=True,
        env=child.env,
        cwd=tmp_path,
        timeout=15,
        check=False,
    )
    child.assert_loaded()
    assert completed.returncode == 0
    assert completed.stdout == b"blocked-before-network\n"
    assert completed.stderr == b""
    assert child.violations.read_text(encoding="utf-8") == f"socket.{api}\n"


@pytest.mark.parametrize(
    ("setting", "value"),
    [
        ("CASA_HOMES_JSON", DUMMY_TOKEN),
        ("CASA_HOMES_JSON", json.dumps([{"id": DUMMY_TOKEN, "label": HOME_LABEL}])),
        ("CASA_ALLOW_UNVERIFIED_READS", DUMMY_TOKEN),
        ("CASA_REFRESH_TOKEN", f"op://synthetic/{DUMMY_TOKEN}"),
        ("CASA_REFRESH_TOKEN", " \t\n"),
    ],
    ids=["malformed-json", "invalid-home", "invalid-boolean", "unresolved-token", "blank-token"],
)
def test_bad_config_exits_two_with_setting_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, setting: str, value: str
) -> None:
    _poison_inherited_environment(monkeypatch)
    child = _guarded_child(tmp_path)
    child.env["CASA_REFRESH_TOKEN"] = DUMMY_TOKEN
    child.env[setting] = value
    completed = subprocess.run(
        [_interpreter(), "-m", "casahome_mcp"],
        input=b"",
        capture_output=True,
        env=child.env,
        cwd=tmp_path,
        timeout=15,
        check=False,
    )
    child.assert_no_egress()
    assert completed.returncode == 2
    assert completed.stdout == b""
    assert completed.stderr == f"Invalid configuration: {setting}.\n".encode()
    _assert_private_diagnostics(completed.stdout, completed.stderr)
