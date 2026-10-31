"""Write tools tell the client that CRM resources changed; reads and failures stay silent."""

from __future__ import annotations

import asyncio

from fastmcp import Client
from fastmcp.server.context import Context
from mcp.types import ServerNotification

from tests.conftest import _list_tool_names, _run

LIST_CHANGED = "notifications/resources/list_changed"

# Every published tool is in exactly one of these sets, so a new tool fails the
# classing test until it is listed as a write or a read.
EXPECTED_WRITE_TOOLS = {
    "add_field",
    "create_deal",
    "create_interaction",
    "delete_contact",
    "delete_deal",
    "delete_interaction",
    "find_or_create_contact",
    "link_deals_to_contacts",
    "log_interaction",
    "move_deal_stage",
    "seed_data",
    "update_contact",
    "update_deal",
    "update_interaction",
}
EXPECTED_READ_TOOLS = {
    "contact_timeline",
    "pipeline_summary",
    "rebuild_index",
    "get_contact",
    "get_deal",
    "get_interaction",
    "get_contact_composite",
    "get_deal_composite",
    "get_interaction_composite",
    "get_related_contact",
    "get_related_deal",
    "get_related_interaction",
    "list_contacts",
    "list_deals",
    "list_interactions",
    "query_contacts_by_relationship",
    "query_deals_by_relationship",
    "query_interactions_by_relationship",
    "search_contacts",
    "search_deals",
    "search_interactions",
}


async def _exercise(mcp, calls):
    """Make each (tool, arguments) call, then one write; return results and the notice count.

    Notifications arrive in order, so waiting for the final write's notice
    means any notice from an earlier call has already been counted.
    """
    results = []
    notices = 0
    changed = asyncio.Event()

    async def message_handler(message):
        nonlocal notices
        if isinstance(message, ServerNotification) and message.root.method == LIST_CHANGED:
            notices += 1
            changed.set()

    async with Client(mcp, message_handler=message_handler) as client:
        for name, arguments in calls:
            results.append(
                await client.call_tool(name, arguments, raise_on_error=False)
            )
        changed.clear()
        await client.call_tool("find_or_create_contact", {"name": "Final write"})
        await asyncio.wait_for(changed.wait(), timeout=2)
    return results, notices


def test_every_published_tool_is_classed(server_module, mcp):
    published = _run(_list_tool_names(mcp))
    writes = {name for name in published if server_module.is_write_tool(name)}
    assert writes == EXPECTED_WRITE_TOOLS
    assert published - writes == EXPECTED_READ_TOOLS


def test_write_sends_one_notification(mcp):
    results, notices = asyncio.run(
        _exercise(mcp, [("create_deal", {"title": "Notified deal"})])
    )
    assert not results[0].is_error
    assert notices == 2


def test_record_with_an_error_field_still_notifies(mcp):
    results, notices = asyncio.run(
        _exercise(mcp, [("create_deal", {"title": "Edge", "error": "x"})])
    )
    assert not results[0].is_error
    assert results[0].structured_content["error"] == "x"
    assert notices == 2


def test_reads_send_nothing(mcp):
    results, notices = asyncio.run(
        _exercise(
            mcp,
            [
                ("list_deals", {}),
                ("search_contacts", {"query": "anyone"}),
                ("pipeline_summary", {}),
            ],
        )
    )
    assert not any(result.is_error for result in results)
    assert notices == 1


def test_rejected_write_sends_nothing(mcp):
    results, notices = asyncio.run(
        _exercise(
            mcp,
            [
                ("create_deal", {"title": "Invalid", "value": -1}),
                ("move_deal_stage", {"deal_id": "missing", "stage": "closed_won"}),
            ],
        )
    )
    invalid, missing = results
    assert invalid.is_error
    assert missing.structured_content == {"error": "Deal missing not found"}
    assert notices == 1


def test_failed_notification_still_reports_the_write(mcp, monkeypatch):
    async def closed_stream(self, notification):
        raise RuntimeError("stream closed")

    monkeypatch.setattr(Context, "send_notification", closed_stream)

    async def write_then_read():
        async with Client(mcp) as client:
            created = await client.call_tool(
                "create_deal", {"title": "Saved deal"}, raise_on_error=False
            )
            found = await client.call_tool(
                "get_deal", {"deal_id": created.structured_content["id"]}
            )
            return created, found

    created, found = _run(write_then_read())
    assert not created.is_error
    assert found.structured_content["title"] == "Saved deal"
