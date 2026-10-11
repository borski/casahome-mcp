"""Create a server without starting it or reading process settings."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp.server import MCPServer

from . import __version__
from .actions.tools import register_action_tools
from .config import Settings
from .coverage_tools import register_coverage_tools
from .detail_tools import register_detail_tools
from .runtime import AppContext, RuntimeFactory, sdk_runtime
from .tools import register_tools
from .validation import input_guard


def create_server(settings: Settings, runtime_factory: RuntimeFactory = sdk_runtime) -> MCPServer:
    @asynccontextmanager
    async def lifespan(server: MCPServer) -> AsyncIterator[AppContext]:
        async with runtime_factory(settings) as app:
            try:
                yield app
            finally:
                app.uploads_closed = True
                # No await or executor join. Workers retain lock/capacity until
                # actual completion and discard bytes when they eventually finish.
                for worker in tuple(app.upload_workers):
                    worker.abandon()
                app.action_store.clear()

    server = MCPServer("casahome", version=__version__, lifespan=lifespan)
    register_tools(server)
    register_coverage_tools(server)
    register_detail_tools(server)
    action_validators = register_action_tools(server)
    server.middleware.append(input_guard(server, action_validators))
    return server
