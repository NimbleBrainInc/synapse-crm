"""Exercise the entire public CRM tool surface in a disposable workspace."""

import asyncio
import json

from fastmcp import Client


def test_every_public_tool_and_resource(mcp):
    async def exercise():
        called = set()
        async with Client(mcp) as client:
            listed = {tool.name for tool in await client.list_tools()}
            assert len(listed) == 35
            assert "create_contact" not in listed
            resources = {str(item.uri) for item in await client.list_resources()}
            assert resources == {
                "upjack://context",
                "upjack://skills/follow-up-coach",
                "upjack://skills/pipeline-reviewer",
                "ui://crm/main",
                "skill://follow-up-coach/usage",
                "skill://pipeline-reviewer/usage",
            }
            for resource in resources:
                assert await client.read_resource(resource)

            async def call(name, args=None):
                result = await client.call_tool(name, args or {})
                called.add(name)
                return json.loads(result.content[0].text)

            contact = (
                await call("find_or_create_contact", {"name": "Workflow contact"})
            )["contact"]
            deal = await call(
                "create_deal",
                {
                    "title": "Workflow deal",
                    "stage": "lead",
                    "relationships": [{"rel": "belongs_to", "target": contact["id"]}],
                },
            )
            interaction = await call(
                "create_interaction",
                {
                    "interaction_type": "note",
                    "summary": "Workflow note",
                    "relationships": [{"rel": "belongs_to", "target": contact["id"]}],
                },
            )
            records = {"contact": contact, "deal": deal, "interaction": interaction}
            for kind, plural in [
                ("contact", "contacts"),
                ("deal", "deals"),
                ("interaction", "interactions"),
            ]:
                identifier = {f"{kind}_id": records[kind]["id"]}
                assert (await call(f"get_{kind}", identifier))["id"] == records[kind][
                    "id"
                ]
                assert (
                    await call(f"update_{kind}", {**identifier, "tags": ["workflow"]})
                )["tags"] == ["workflow"]
                assert (await call(f"list_{plural}", {"limit": None}))["count"] == 1
                assert (
                    await call(
                        f"search_{plural}",
                        {"filter": {"tags": {"$contains": "workflow"}}},
                    )
                )["count"] == 1
                await call(
                    f"query_{plural}_by_relationship",
                    {"rel": "belongs_to", "target_id": contact["id"]},
                )
                await call(
                    f"get_related_{kind}", {**identifier, "direction": "reverse"}
                )
                await call(f"get_{kind}_composite", identifier)
            assert (
                await call(
                    "move_deal_stage", {"deal_id": deal["id"], "stage": "closed_won"}
                )
            )["deal"]["stage"] == "closed_won"
            await call(
                "log_interaction",
                {
                    "contact_id": contact["id"],
                    "interaction_type": "call",
                    "summary": "Workflow follow-up",
                },
            )
            await call("pipeline_summary")
            await call("contact_timeline", {"contact_id": contact["id"]})
            await call("link_deals_to_contacts")
            assert (
                await call(
                    "add_field",
                    {
                        "entity_type": "contact",
                        "field_name": "region",
                        "field_type": "string",
                        "default": "west",
                    },
                )
            )["success"] is True
            assert (await call("get_contact", {"contact_id": contact["id"]}))[
                "region"
            ] == "west"
            assert (await call("rebuild_index"))["success"] is True
            seeded = await call("seed_data")
            assert seeded["loaded"]
            assert seeded["errors"] == []
            for kind in records:
                deleted = await call(
                    f"delete_{kind}", {f"{kind}_id": records[kind]["id"]}
                )
                assert deleted["status"] == "deleted"
            assert listed <= called
            return called

    asyncio.run(exercise())
