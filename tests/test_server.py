"""Contract tests for the synapse-crm MCP server (Phase 1).

These tests pin the server's public contract:

* The server instantiates as a ``FastMCP`` with the manifest's entities.
* Every entity in the manifest gets the six auto-generated CRUD tools.
* Every hand-written domain tool is registered and callable.
* ``create_*`` tools accept flat kwargs (the 0.5.0+ shape).
* The legacy ``{"data": {...}}`` wrapper is rejected by the JSON Schema
  validator, matching the upjack 0.5.x contract.
"""

from __future__ import annotations

import pytest
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from tests.conftest import _call_tool, _list_tool_names, _run


# Hand-written (Tier 3) tools registered by ``synapse_crm.tools.register_tools``.
HAND_WRITTEN_TOOLS = {
    "move_deal_stage",
    "log_interaction",
    "pipeline_summary",
    "find_or_create_contact",
    "link_deals_to_contacts",
    "contact_timeline",
}

# Entities declared in manifest.json; each should yield six CRUD tools.
MANIFEST_ENTITIES = [
    ("contact", "contacts"),
    ("deal", "deals"),
    ("interaction", "interactions"),
]


def test_server_instantiates(mcp):
    """The reloaded module exposes a live FastMCP server."""
    assert isinstance(mcp, FastMCP)


def test_expected_auto_crud_tools_registered(mcp):
    """Every manifest entity gets create/get/update/list/search/delete.

    The ``contact`` entity declares an explicit ``tools`` filter in the
    manifest that omits ``create``, so we check each entity against its
    actual filter rather than assuming all six for every entity.
    """
    listed = _run(_list_tool_names(mcp))

    # contact: manifest filter is ["get", "update", "list", "search", "delete",
    # "query_by_relationship", "get_related", "get_composite"] — no create.
    assert "get_contact" in listed
    assert "update_contact" in listed
    assert "list_contacts" in listed
    assert "search_contacts" in listed
    assert "delete_contact" in listed

    # deal and interaction have no filter, so all six CRUD names must show up.
    for singular, plural in [("deal", "deals"), ("interaction", "interactions")]:
        assert f"create_{singular}" in listed, f"missing create_{singular}"
        assert f"get_{singular}" in listed, f"missing get_{singular}"
        assert f"update_{singular}" in listed, f"missing update_{singular}"
        assert f"list_{plural}" in listed, f"missing list_{plural}"
        assert f"search_{plural}" in listed, f"missing search_{plural}"
        assert f"delete_{singular}" in listed, f"missing delete_{singular}"


def test_hand_written_tools_registered(mcp):
    """All six Tier 3 domain tools are present in tools/list."""
    listed = _run(_list_tool_names(mcp))
    missing = HAND_WRITTEN_TOOLS - listed
    assert not missing, f"hand-written tools missing from server: {missing}"


def test_flat_kwargs_create_succeeds(mcp):
    """``create_deal`` accepts flat kwargs and returns a valid entity."""
    created = _run(_call_tool(mcp, "create_deal", {"title": "Test", "stage": "qualified"}))

    assert created["id"].startswith("dl_")
    assert created["type"] == "deal"
    assert created["title"] == "Test"
    assert created["stage"] == "qualified"


def test_legacy_data_wrapper_rejected(mcp):
    """The pre-0.5.0 ``{data: {...}}`` shape is no longer part of the contract.

    ``create_deal`` requires ``title`` at the top level, so a call whose only
    key is ``data`` fails JSON Schema validation and the client raises
    ``ToolError`` before reaching the server.
    """
    with pytest.raises(ToolError):
        _run(_call_tool(mcp, "create_deal", {"data": {"title": "Wrapped", "stage": "qualified"}}))
