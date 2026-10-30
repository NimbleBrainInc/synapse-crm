"""Shared fixtures and helpers for synapse-crm tests.

The CRM server is a module-level singleton (``synapse_crm.server.mcp``) bound
to a workspace at import time. To get an isolated workspace per test, we set
both supported workspace variables to ``tmp_path`` and reload the server so it
re-binds to the fresh workspace.
"""

from __future__ import annotations

import asyncio
import importlib
import json
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Async helpers for MCP Client interaction
# ---------------------------------------------------------------------------


def _run(coro):
    """Run a coroutine synchronously."""
    return asyncio.run(coro)


async def _list_tool_names(mcp) -> set[str]:
    from fastmcp import Client

    async with Client(mcp) as client:
        tools = await client.list_tools()
        return {t.name for t in tools}


async def _call_tool(mcp, name: str, arguments: dict | None = None) -> Any:
    from fastmcp import Client

    async with Client(mcp) as client:
        result = await client.call_tool(name, arguments or {})
        if not result.content:
            return None
        return json.loads(result.content[0].text)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def server_module(tmp_path, monkeypatch):
    """Reload ``synapse_crm.server`` against an isolated per-test workspace.

    ``MPAK_WORKSPACE`` is the primary selection; ``UPJACK_ROOT`` remains a
    fallback for older clients. Set both so an inherited shell value cannot
    redirect tests to a real workspace. Reload is required because the module
    captures ``mcp`` and ``_app`` at import time.
    """
    monkeypatch.setenv("UPJACK_ROOT", str(tmp_path))
    monkeypatch.setenv("MPAK_WORKSPACE", str(tmp_path))

    import synapse_crm.server as module

    importlib.reload(module)
    return module


@pytest.fixture
def mcp(server_module):
    """The reloaded FastMCP server, bound to the per-test workspace."""
    return server_module.mcp


@pytest.fixture
def app(server_module):
    """The reloaded CRMStore, bound to the per-test workspace."""
    return server_module._app
