"""Contract tests for the synapse-crm MCP server (Phase 1).

These tests pin the server's public contract:

* The server instantiates as a ``FastMCP`` with the manifest's entities.
* tools/list publishes exactly the 35 tools in ``EXPECTED_TOOLS``, and each
  tool's argument names, required arguments and types match the snapshot in
  ``tests/fixtures/tool-contract.json``.
* Every hand-written domain tool is registered and callable.
* ``create_*`` tools accept flat kwargs (the 0.5.0+ shape).
* The legacy ``{"data": {...}}`` wrapper is rejected by the JSON Schema
  validator, matching the upjack 0.5.x contract.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from tests.conftest import _call_tool, _list_tool_names, _run

# Every tool a host sees in tools/list. The manifest hides create_contact, so
# find_or_create_contact is the listed way to add a contact.
EXPECTED_TOOLS = {
    "add_field",
    "contact_timeline",
    "create_deal",
    "create_interaction",
    "delete_contact",
    "delete_deal",
    "delete_interaction",
    "find_or_create_contact",
    "get_contact",
    "get_contact_composite",
    "get_deal",
    "get_deal_composite",
    "get_interaction",
    "get_interaction_composite",
    "get_related_contact",
    "get_related_deal",
    "get_related_interaction",
    "link_deals_to_contacts",
    "list_contacts",
    "list_deals",
    "list_interactions",
    "log_interaction",
    "move_deal_stage",
    "pipeline_summary",
    "query_contacts_by_relationship",
    "query_deals_by_relationship",
    "query_interactions_by_relationship",
    "rebuild_index",
    "search_contacts",
    "search_deals",
    "search_interactions",
    "seed_data",
    "update_contact",
    "update_deal",
    "update_interaction",
}

_CONTRACT_PATH = Path(__file__).parent / "fixtures" / "tool-contract.json"


def _property_type(prop: dict):
    """Return a property's JSON Schema type, the types of its `anyOf`, or "any"."""
    if "type" in prop:
        return prop["type"]
    if "anyOf" in prop:
        return sorted(option.get("type", "any") for option in prop["anyOf"])
    return "any"


async def _tool_contract(mcp) -> dict[str, dict]:
    """Reduce each listed tool to its required arguments and argument types."""
    from fastmcp import Client

    async with Client(mcp) as client:
        tools = await client.list_tools()
    return {
        tool.name: {
            "required": sorted(tool.input_schema.get("required", [])),
            "properties": {
                name: _property_type(prop)
                for name, prop in sorted(tool.input_schema.get("properties", {}).items())
            },
        }
        for tool in sorted(tools, key=lambda t: t.name)
    }


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


def test_published_tool_surface_is_preserved(mcp):
    """tools/list publishes exactly `EXPECTED_TOOLS`, nothing more or less."""
    assert _run(_list_tool_names(mcp)) == EXPECTED_TOOLS


def test_tool_argument_contract_matches_snapshot(mcp):
    """Argument names, required arguments and types match the snapshot.

    A renamed, dropped or retyped argument breaks every caller that still
    uses the old shape, so the change must show up here first. When a
    change is intended, rewrite the fixture with
    `UPDATE_TOOL_CONTRACT=1 pytest tests/test_server.py -k argument_contract`
    and review its diff.
    """
    actual = _run(_tool_contract(mcp))
    if os.environ.get("UPDATE_TOOL_CONTRACT"):
        lines = [f"  {json.dumps(name)}: {json.dumps(entry)}" for name, entry in actual.items()]
        _CONTRACT_PATH.write_text("{\n" + ",\n".join(lines) + "\n}\n")
    assert actual == json.loads(_CONTRACT_PATH.read_text())


def test_tool_schemas_have_explicit_object_roots_for_strict_hosts(mcp):
    """Every input and output schema declares `type: object` at its root."""
    from fastmcp import Client

    async def check():
        async with Client(mcp) as client:
            for tool in await client.list_tools():
                assert tool.input_schema.get("type") == "object", tool.name
                if tool.output_schema is not None:
                    assert tool.output_schema.get("type") == "object", tool.name

    _run(check())


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
    key is ``data`` fails the store's JSON Schema validation on the server and
    the client surfaces it as ``ToolError``, the same way the Upjack version did.
    """
    with pytest.raises(ToolError, match="'title' is a required property"):
        _run(_call_tool(mcp, "create_deal", {"data": {"title": "Wrapped", "stage": "qualified"}}))


def test_hidden_create_contact_takes_the_update_contact_fields(mcp):
    """``create_contact`` is unlisted, so the snapshot cannot pin it; ``update_contact`` can.

    The two tools publish the same contact fields, the update tool adding the
    ``contact_id`` argument, so the hidden tool's contract is the listed one
    less that argument, with ``name`` required as the contact schema says.
    """
    contract = json.loads(_CONTRACT_PATH.read_text())["update_contact"]
    hidden = _run(mcp.get_tool("create_contact")).parameters
    assert sorted(hidden.get("required", [])) == ["name"]
    assert {name: _property_type(prop) for name, prop in hidden["properties"].items()} == {
        name: kind for name, kind in contract["properties"].items() if name != "contact_id"
    }
