"""Refresh only after persisted writes, including writes followed by an error."""

import asyncio

from fastmcp import Client
from mcp.types import ServerNotification


def test_write_notifications_and_read_silence(server_module):
    async def exercise():
        notifications = []
        changed = asyncio.Event()

        async def message_handler(message):
            if isinstance(message, ServerNotification):
                notifications.append(message.root.method)
                changed.set()

        async with Client(server_module.mcp, message_handler=message_handler) as client:
            await client.call_tool("list_deals", {})
            await asyncio.sleep(0.05)
            assert notifications == []
            contact = await client.call_tool(
                "find_or_create_contact", {"name": "Notification contact"}
            )
            assert not contact.is_error
            await asyncio.wait_for(changed.wait(), timeout=2)
            assert notifications == ["notifications/resources/list_changed"]
            changed.clear()
            await client.call_tool(
                "find_or_create_contact", {"name": "Notification contact"}
            )
            await client.call_tool("pipeline_summary", {})
            invalid = await client.call_tool(
                "create_deal", {"title": "Invalid", "value": -1}, raise_on_error=False
            )
            assert invalid.is_error
            await asyncio.sleep(0.05)
            assert len(notifications) == 1

            @server_module.mcp.tool()
            def partially_committed_test_write() -> dict:
                server_module._app.create_entity(
                    "deal", {"title": "Persisted before error"}
                )
                raise ValueError("Synthetic error after persistence")

            result = await client.call_tool(
                "partially_committed_test_write", {}, raise_on_error=False
            )
            assert result.is_error
            await asyncio.wait_for(changed.wait(), timeout=2)
            assert notifications == ["notifications/resources/list_changed"] * 2
            assert (
                server_module._app.list_entities("deal")[0]["title"]
                == "Persisted before error"
            )

    asyncio.run(exercise())
