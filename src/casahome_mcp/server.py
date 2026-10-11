"""Create a server without starting it or reading process settings."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp.server import MCPServer

from . import __version__
from .config import Settings
from .runtime import AppContext, RuntimeFactory, sdk_runtime
from .tools import register_tools
from .validation import input_guard


def create_server(settings: Settings, runtime_factory: RuntimeFactory = sdk_runtime) -> MCPServer:
    @asynccontextmanager
    async def lifespan(server: MCPServer) -> AsyncIterator[AppContext]:
        async with runtime_factory(settings) as app:
            yield app

    server = MCPServer("casahome", version=__version__, lifespan=lifespan)
    register_tools(server)
    server.middleware.append(input_guard(server))
    return server
