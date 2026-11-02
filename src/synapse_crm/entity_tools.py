"""The generated CRM tools and resources, served from the record store.

Upjack generated these from the manifest: six CRUD tools and three relationship
tools per entity, ``seed_data``, ``add_field`` and ``rebuild_index``, the
``upjack://context`` and ``upjack://skills/<name>`` resources, and a tools/list
filter for the entities whose manifest entry names its ``tools``. This module
registers the same names, descriptions, argument schemas, output schemas and
``{"entities": [...], "count": n}`` envelopes on FastMCP, backed by
:class:`~synapse_crm.store.CRMStore`. The resource URIs keep the ``upjack://``
scheme so a host that reads them today keeps working.
"""

import json
from collections.abc import Callable, Sequence
from copy import deepcopy
from pathlib import Path
from typing import Annotated, Any

from fastmcp import FastMCP
from fastmcp.server.middleware import Middleware
from fastmcp.tools import Tool, ToolResult
from jsonschema import ValidationError
from mcp.types import TextContent
from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from synapse_crm.store import BASE_FIELDS, ENTITIES, CRMStore

_UPJACK_META = "ai.nimblebrain/upjack"
_SEED_SKIP = {"type", "created_at", "updated_at", "created_by"}
_UTILITY_TOOLS = frozenset({"seed_data", "add_field", "rebuild_index"})
# Manifest tool categories and the generated tool each one names.
_CATEGORIES = {
    "create": "create_{name}",
    "get": "get_{name}",
    "update": "update_{name}",
    "list": "list_{plural}",
    "search": "search_{plural}",
    "delete": "delete_{name}",
    "query_by_relationship": "query_{plural}_by_relationship",
    "get_related": "get_related_{name}",
    "get_composite": "get_{name}_composite",
}


def _envelope(entities: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    return {"entities": entities, "count": len(entities), **extra}


def _parse(value: Any) -> Any:
    """Decode an object or array argument a stdio host sent as a JSON string."""
    if isinstance(value, str) and value.startswith(("{", "[")):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


class SchemaTool(Tool):
    """A tool with a hand-written JSON Schema whose handler takes the parsed arguments.

    FastMCP builds a schema from a function signature; these tools publish the
    entity schema itself, so the handler receives the raw argument dict.
    """

    handler: Annotated[
        SkipJsonSchema[Callable[[dict[str, Any]], Any]], Field(exclude=True)
    ]

    async def run(self, arguments: dict[str, Any]) -> ToolResult:
        result = self.handler({key: _parse(value) for key, value in arguments.items()})
        text = json.dumps(result, default=str)
        return ToolResult(
            content=[TextContent(type="text", text=text)],
            structured_content=json.loads(text) if isinstance(result, dict) else None,
        )


class ListedTools(Middleware):
    """Leave the generated tools a manifest entity does not list out of tools/list.

    Upjack filtered the listing the same way: a hidden tool stays callable, so
    ``create_contact`` still serves a caller that knows it while
    ``find_or_create_contact`` is the listed way to add a contact.
    """

    def __init__(self, hidden: set[str]) -> None:
        self.hidden = hidden

    async def on_list_tools(self, context, call_next) -> Sequence[Tool]:
        return [
            tool for tool in await call_next(context) if tool.name not in self.hidden
        ]


def _hidden_tools(upjack: dict[str, Any]) -> set[str]:
    """The generated tools the manifest leaves out of tools/list.

    An entity's ``tools`` lists the categories to publish; ``utility_tools``
    does the same for seed_data, add_field and rebuild_index. An absent list
    publishes everything, as under Upjack.
    """
    hidden: set[str] = set()
    for entity in upjack.get("entities", []):
        listed = entity.get("tools")
        if listed is None:
            continue
        name = entity["name"]
        plural = entity.get("plural", name + "s")
        hidden |= {
            template.format(name=name, plural=plural)
            for category, template in _CATEGORIES.items()
            if category not in listed
        }
    utilities = upjack.get("utility_tools")
    if utilities is not None:
        hidden |= _UTILITY_TOOLS - set(utilities)
    return hidden


def _envelope_schema(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "entities": {"type": "array", "items": item},
            "count": {"type": "integer", "description": "Number of entities returned"},
        },
        "required": ["entities", "count"],
    }


def _output_schemas(schema: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """The entity output schema and the list envelope schema built on it."""
    entity = {k: v for k, v in schema.items() if k not in {"$schema", "$id"}}
    entity.setdefault("type", "object")
    return entity, _envelope_schema(entity)


def _fields_schema(schema: dict[str, Any], base: dict[str, Any]) -> dict[str, Any]:
    """The entity schema reduced to the fields a caller sets.

    The inlined base record schema under ``allOf`` describes the fields the
    store manages, so it goes along with those fields and the schema meta
    keywords; any other ``allOf`` member is the entity's own and stays.
    """
    fields = {k: v for k, v in schema.items() if k not in {"$schema", "$id"}}
    others = [part for part in fields.get("allOf", []) if part != base]
    if others:
        fields["allOf"] = others
    else:
        fields.pop("allOf", None)
    fields["properties"] = {
        k: v for k, v in fields.get("properties", {}).items() if k not in BASE_FIELDS
    }
    required = [
        field for field in fields.get("required", []) if field not in BASE_FIELDS
    ]
    if required:
        fields["required"] = required
    else:
        fields.pop("required", None)
    fields["examples"] = [
        {k: v for k, v in example.items() if k not in BASE_FIELDS}
        for example in fields.get("examples", [])
        if isinstance(example, dict)
    ]
    if not fields["examples"]:
        del fields["examples"]
    fields.setdefault("type", "object")
    return fields


def _id_property(kind: str, prefix: str) -> dict[str, Any]:
    return {"type": "string", "description": f"{kind} ID ({prefix}_...)"}


def _register_entity(mcp: FastMCP, store: CRMStore, kind: str) -> None:
    plural, prefix = ENTITIES[kind]
    id_param = f"{kind}_id"
    id_hint = f"IDs start with {prefix}_"
    schema = store.schema(kind)
    entity_out, list_out = _output_schemas(schema)
    create_params = _fields_schema(schema, store.base_schema())
    examples = create_params.get("examples", [])

    mcp.add_tool(
        SchemaTool(
            name=f"create_{kind}",
            description=f"Create a new {kind}. {id_hint}.",
            parameters=create_params,
            output_schema=entity_out,
            handler=lambda args: store.create_entity(kind, args),
        )
    )
    mcp.add_tool(
        SchemaTool(
            name=f"get_{kind}",
            description=f"Get a {kind} by ID. {id_hint}.",
            parameters={
                "type": "object",
                "properties": {id_param: _id_property(kind, prefix)},
                "required": [id_param],
                "examples": [{id_param: f"{prefix}_01HXXX"}],
            },
            output_schema=entity_out,
            handler=lambda args: store.get_entity(kind, args[id_param]),
        )
    )
    update_params: dict[str, Any] = {
        "type": "object",
        "properties": {
            id_param: _id_property(kind, prefix),
            **create_params["properties"],
        },
        "required": [id_param],
    }
    if examples:
        update_params["examples"] = [
            {id_param: f"{prefix}_01HXXX", **example} for example in examples
        ]
    mcp.add_tool(
        SchemaTool(
            name=f"update_{kind}",
            description=(
                f"Update a {kind} by ID. Merges fields by default — pass any subset "
                f"of fields to change. Unknown fields are merged onto the entity "
                f"as-is (the schema does not enforce additionalProperties=false). "
                f"{id_hint}."
            ),
            parameters=update_params,
            output_schema=entity_out,
            handler=lambda args: store.update_entity(
                kind, args[id_param], {k: v for k, v in args.items() if k != id_param}
            ),
        )
    )

    def list_tool(status: str = "active", limit: int = 50) -> dict[str, Any]:
        entities = store.list_entities(kind, status=status, limit=limit)
        return _envelope(entities, status_filter=status, limit=limit)

    mcp.tool(
        list_tool,
        name=f"list_{plural}",
        description=(
            f"List {plural}. Filters by status (default: active). "
            f"Returns newest first. {id_hint}."
        ),
        output_schema=list_out,
    )

    def search_tool(
        query: str | None = None,
        filter: dict[str, Any] | None = None,
        sort: str = "-updated_at",
        limit: int = 20,
    ) -> dict[str, Any]:
        entities = store.search_entities(
            kind, query=query, filter=filter, sort=sort, limit=limit
        )
        return _envelope(entities, query=query, limit=limit)

    mcp.tool(
        search_tool,
        name=f"search_{plural}",
        description=(
            f"Search {plural} with text query and/or structured filters. "
            f"Text query matches across all string fields (case-insensitive). "
            f"Filters support: direct equality, $gt, $gte, $lt, $lte, $ne, $in, "
            f"$contains, $exists. Sort with '-field' for descending. {id_hint}."
        ),
        output_schema=list_out,
    )
    mcp.add_tool(
        SchemaTool(
            name=f"delete_{kind}",
            description=(
                f"Delete a {kind} by ID. Soft delete by default (sets status to 'deleted'). "
                f"Set hard=true to permanently remove. {id_hint}."
            ),
            parameters={
                "type": "object",
                "properties": {
                    id_param: _id_property(kind, prefix),
                    "hard": {
                        "type": "boolean",
                        "description": "Permanently remove instead of soft delete.",
                        "default": False,
                    },
                },
                "required": [id_param],
                "examples": [{id_param: f"{prefix}_01HXXX"}],
            },
            output_schema=entity_out,
            handler=lambda args: store.delete_entity(
                kind, args[id_param], hard=args.get("hard", False)
            ),
        )
    )

    def query_tool(
        rel: str,
        target_id: str,
        filter: dict[str, Any] | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        return _envelope(
            store.query_by_relationship(
                kind, rel, target_id, filter=filter, limit=limit
            )
        )

    mcp.tool(
        query_tool,
        name=f"query_{plural}_by_relationship",
        description=(
            f"Find {plural} that have a specific relationship pointing to a target entity. "
            f"For example, find all {plural} that 'belongs_to' a given entity."
        ),
        output_schema=list_out,
    )
    mcp.add_tool(
        SchemaTool(
            name=f"get_related_{kind}",
            description=(
                f"Follow relationship edges from a {kind}. "
                f"'forward' returns entities this {kind} points to. "
                f"'reverse' returns entities that point to this {kind}."
            ),
            parameters={
                "type": "object",
                "properties": {
                    id_param: _id_property(kind, prefix),
                    "rel": {
                        "type": "string",
                        "description": "Relationship type to follow. Omit to follow all.",
                    },
                    "direction": {
                        "type": "string",
                        "description": "'forward' or 'reverse'.",
                        "default": "forward",
                    },
                },
                "required": [id_param],
            },
            # The related records are of other kinds, so the items are plain
            # objects; a validating client rejected the entity schema here.
            output_schema=_envelope_schema({"type": "object"}),
            handler=lambda args: _envelope(
                store.get_related(
                    args[id_param],
                    rel=args.get("rel"),
                    direction=args.get("direction", "forward"),
                )
            ),
        )
    )
    mcp.add_tool(
        SchemaTool(
            name=f"get_{kind}_composite",
            description=(
                f"Load a {kind} with all related entities in one call. "
                f"Returns the entity with a '_related' key containing forward "
                f"relationships (keyed by rel name) and reverse relationships "
                f"(keyed by ~rel name)."
            ),
            parameters={
                "type": "object",
                "properties": {
                    id_param: _id_property(kind, prefix),
                    "depth": {
                        "type": "integer",
                        "description": "Traversal depth (default 1).",
                        "default": 1,
                    },
                },
                "required": [id_param],
            },
            output_schema=entity_out,
            handler=lambda args: store.get_composite(
                kind, args[id_param], depth=args.get("depth", 1)
            ),
        )
    )


def _register_utilities(mcp: FastMCP, store: CRMStore, seed_dir: Path) -> None:
    def seed_data() -> dict[str, Any]:
        if not seed_dir.exists():
            return {"error": f"Seed directory not found: {seed_dir}"}
        loaded: list[str] = []
        errors: list[str] = []
        for file in sorted(seed_dir.glob("*.json")):
            raw = json.loads(file.read_text())
            for item in raw if isinstance(raw, list) else [raw]:
                kind = item.get("type")
                if not kind:
                    errors.append(f"{file.name}: missing 'type' field")
                    continue
                data = {k: v for k, v in item.items() if k not in _SEED_SKIP}
                try:
                    record = store.create_entity(kind, data, created_by="system")
                except (KeyError, ValueError, ValidationError) as error:
                    errors.append(f"{file.name} ({kind}): {error}")
                else:
                    loaded.append(f"{kind}: {record['id']}")
        return {"loaded": loaded, "errors": errors}

    mcp.tool(
        seed_data,
        name="seed_data",
        description="Load sample data from the app's seed directory into the workspace.",
    )

    def add_field(
        entity_type: str,
        field_name: str,
        field_type: str,
        default: Any,
        description: str = "",
        required: bool = True,
    ) -> dict[str, Any]:
        return store.add_field(
            entity_type, field_name, field_type, default, description, required
        )

    mcp.tool(
        add_field,
        name="add_field",
        description=(
            "Add a new field to an entity schema. Validates the change is safe, "
            "writes the updated schema to disk, and reloads it."
        ),
    )

    mcp.tool(
        store.rebuild_index,
        name="rebuild_index",
        description=(
            "Force a full rebuild of the relationship index from entity files. "
            "Use this if the index seems stale or after manual file edits."
        ),
    )


def _file_resource(
    mcp: FastMCP, uri: str, name: str, description: str, path: Path
) -> None:
    def read() -> str:
        return path.read_text()

    mcp.resource(uri, name=name, description=description)(read)


def _register_resources(
    mcp: FastMCP, project_root: Path, upjack: dict[str, Any]
) -> None:
    context = project_root / upjack.get("context", "")
    if upjack.get("context") and context.exists():
        _file_resource(
            mcp, "upjack://context", "Context", "App domain knowledge", context
        )
    for skill in upjack.get("skills", []):
        path = project_root / skill["path"]
        if skill.get("source") == "bundled" and path.exists():
            name = path.parent.name
            _file_resource(mcp, f"upjack://skills/{name}", name, f"Skill: {name}", path)


def instructions(name: str) -> str:
    """The server instructions Upjack wrote from the manifest."""
    kinds = ", ".join(f"{kind} ({prefix}_)" for kind, (_, prefix) in ENTITIES.items())
    return (
        f"{name} with {len(ENTITIES)} entity types: {kinds}.\n"
        "Read the upjack://context resource for domain knowledge."
    )


def register_entity_tools(mcp: FastMCP, store: CRMStore, project_root: Path) -> None:
    """Register the generated tools and resources on the server.

    Args:
        mcp: The FastMCP server.
        store: The record store every tool reads and writes through.
        project_root: Repository root holding manifest.json, seed/, skills/ and context.md.
    """
    manifest = json.loads((project_root / "manifest.json").read_text())
    upjack = deepcopy(manifest.get("_meta", {}).get(_UPJACK_META, {}))
    for entity in upjack.get("entities", []):
        kind = entity["name"]
        # The manifest names the entities; the store knows how to keep them.
        if ENTITIES.get(kind) != (
            entity.get("plural", kind + "s"),
            entity.get("prefix"),
        ):
            raise ValueError(f"Manifest entity {kind!r} does not match the store")
        _register_entity(mcp, store, kind)
    _register_utilities(
        mcp, store, project_root / upjack.get("seed", {}).get("data", "seed/")
    )
    _register_resources(mcp, project_root, upjack)
    hidden = _hidden_tools(upjack)
    if hidden:
        mcp.add_middleware(ListedTools(hidden))
