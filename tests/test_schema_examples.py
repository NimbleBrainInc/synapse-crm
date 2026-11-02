"""Entity schema ``examples`` reach the published tool schemas.

upjack passes a schema's top-level ``examples`` through to the ``create_*``
and ``update_*`` input schemas, so an LLM sees a worked call next to the
field list. These tests read ``tools/list`` the way a client does, and check
that every example is a call the server accepts.
"""

from __future__ import annotations

import pytest
from fastmcp import Client

from tests.conftest import _call_tool, _run

ENTITIES = [("contact", "ct"), ("deal", "dl"), ("interaction", "ix")]


async def _input_schemas(mcp) -> dict[str, dict]:
    async with Client(mcp) as client:
        return {t.name: t.input_schema for t in await client.list_tools()}


@pytest.mark.parametrize(("entity", "prefix"), ENTITIES)
def test_tools_list_publishes_schema_examples(mcp, entity, prefix):
    schemas = _run(_input_schemas(mcp))
    update = schemas[f"update_{entity}"]
    id_param = f"{entity}_id"

    assert update.get("examples"), f"update_{entity} publishes no examples"
    for example in update["examples"]:
        assert example[id_param].startswith(f"{prefix}_")
        # Every key is a declared field, so an example can never teach a
        # wrong name such as ``email_address``.
        assert set(example) <= set(update["properties"])

    # The manifest hides create_contact, so only deal and interaction list it.
    create = schemas.get(f"create_{entity}")
    if create is not None:
        assert create["examples"] == [
            {k: v for k, v in ex.items() if k != id_param} for ex in update["examples"]
        ]


@pytest.mark.parametrize(("entity", "prefix"), ENTITIES)
def test_schema_examples_are_valid_create_calls(mcp, entity, prefix):
    update = _run(_input_schemas(mcp))[f"update_{entity}"]
    for example in update["examples"]:
        fields = {k: v for k, v in example.items() if k != f"{entity}_id"}
        created = _run(_call_tool(mcp, f"create_{entity}", fields))
        assert created["id"].startswith(f"{prefix}_")
        assert {k: created[k] for k in fields} == fields
