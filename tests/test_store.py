"""Workspace compatibility and write boundaries for the CRM record store."""

import importlib
import json
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import ValidationError

from synapse_crm.store import CRMStore
from synapse_crm.tools.contact_timeline import contact_timeline
from synapse_crm.tools.log_interaction import log_interaction
from tests.conftest import _call_tool, _list_tool_names, _run

ROOT = Path(__file__).resolve().parents[1]
INDEX = "apps/crm/data/_index/relations.json"


def _write_fixture(workspace: Path) -> dict[str, dict]:
    """Lay the pre-migration workspace fixture out under ``workspace``.

    Upjack wrote each record as ``indent=2`` plus a newline and the index as
    ``indent=2`` with none; the files land here as that version left them.
    """
    fixture = json.loads((ROOT / "tests/fixtures/workspace.json").read_text())
    for relative, record in fixture.items():
        path = workspace / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(record, indent=2) + ("" if relative == INDEX else "\n")
        )
    return fixture


def test_existing_workspace_reads_preserve_bytes_and_custom_fields(tmp_path):
    fixture = _write_fixture(tmp_path)
    original = {path: path.read_bytes() for path in tmp_path.rglob("*.json")}
    store = CRMStore(tmp_path, ROOT)
    contact = store.list_entities("contact")[0]
    assert contact["custom_field"] == "retained"
    assert {path: path.read_bytes() for path in original} == original
    updated = store.update_entity("contact", contact["id"], {"company": "Updated Co"})
    restarted = CRMStore(tmp_path, ROOT).get_entity("contact", contact["id"])
    assert restarted == updated
    assert restarted["custom_field"] == "retained"
    assert restarted["id"] == contact["id"]
    assert restarted["created_at"] == contact["created_at"]
    # An update that leaves the edges alone leaves the index file alone.
    assert (tmp_path / INDEX).read_bytes() == original[tmp_path / INDEX]
    # A rebuild writes the same index content; the store adds the trailing
    # newline every record file already has, which Upjack left off the index.
    assert store.rebuild_index() == {"success": True, "entries": 2}
    assert (tmp_path / INDEX).read_bytes() == original[tmp_path / INDEX] + b"\n"
    assert json.loads((tmp_path / INDEX).read_text()) == fixture[INDEX]


def test_invalid_updates_leave_saved_record_unchanged(tmp_path):
    store = CRMStore(tmp_path, ROOT)
    deal = store.create_entity("deal", {"title": "Original", "value": 20})
    path = tmp_path / "apps/crm/data/deals" / f"{deal['id']}.json"
    before = path.read_bytes()
    with pytest.raises(ValidationError):
        store.update_entity("deal", deal["id"], {"value": -1})
    assert path.read_bytes() == before
    assert store.get_entity("deal", deal["id"]) == deal


@pytest.mark.parametrize(
    "invalid",
    [
        "../../../../../outside",
        "dl_../../outside",
        "ct_" + "0" * 26,
        "dl_" + "Z" * 27,
        "dl_" + "Z" * 26,
        "",
        None,
        False,
        0,
    ],
)
def test_invalid_ids_never_become_paths(tmp_path, invalid):
    store = CRMStore(tmp_path / "workspace", ROOT)
    attempts = [
        lambda: store.create_entity("deal", {"id": invalid, "title": "X", "value": 1}),
        lambda: store.get_entity("deal", invalid),
        lambda: store.update_entity("deal", invalid, {"title": "Changed"}),
        lambda: store.delete_entity("deal", invalid),
        lambda: store.delete_entity("deal", invalid, hard=True),
    ]
    for attempt in attempts:
        with pytest.raises(ValueError):
            attempt()
    assert list(tmp_path.rglob("*")) == []


def test_symlinked_record_directory_cannot_leave_workspace(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    deals = tmp_path / "workspace/apps/crm/data/deals"
    deals.parent.mkdir(parents=True)
    deals.symlink_to(outside, target_is_directory=True)
    store = CRMStore(tmp_path / "workspace", ROOT)
    with pytest.raises(ValueError):
        store.create_entity("deal", {"title": "Escape", "value": 1})
    assert list(outside.iterdir()) == []


def test_soft_delete_hides_record_and_hard_delete_removes_file(tmp_path):
    store = CRMStore(tmp_path, ROOT)
    kept = store.create_entity("deal", {"title": "Kept", "value": 10})
    soft = store.create_entity("deal", {"title": "Soft", "value": 20})
    hard = store.create_entity("deal", {"title": "Hard", "value": 30})
    assert store.delete_entity("deal", soft["id"])["status"] == "deleted"
    assert store.delete_entity("deal", hard["id"], hard=True) == hard
    # The message names the ID and not the workspace path; it reaches tool callers.
    with pytest.raises(FileNotFoundError, match=f"^Entity not found: {hard['id']}$"):
        store.get_entity("deal", hard["id"])
    assert [deal["id"] for deal in store.list_entities("deal")] == [kept["id"]]
    assert [deal["id"] for deal in store.list_entities("deal", status="deleted")] == [
        soft["id"]
    ]
    assert [deal["id"] for deal in store.search_entities("deal")] == [kept["id"]]


def test_soft_delete_skips_validation_as_upjack_did(tmp_path):
    store = CRMStore(tmp_path, ROOT)
    deal = store.create_entity("deal", {"title": "Hand edited", "value": 10})
    path = tmp_path / "apps/crm/data/deals" / f"{deal['id']}.json"
    path.write_text(json.dumps({**json.loads(path.read_text()), "value": -1}) + "\n")
    with pytest.raises(ValidationError):
        store.update_entity("deal", deal["id"], {"title": "Still invalid"})
    assert store.delete_entity("deal", deal["id"])["status"] == "deleted"
    assert json.loads(path.read_text())["status"] == "deleted"


def test_search_applies_query_filters_and_sort(tmp_path):
    store = CRMStore(tmp_path, ROOT)
    small = store.create_entity("deal", {"title": "Small renewal", "value": 10})
    large = store.create_entity("deal", {"title": "Large renewal", "value": 90})
    store.create_entity("deal", {"title": "Other", "value": 50, "tags": ["hot"]})
    (tmp_path / "apps/crm/data/deals/notes.json").write_text("{}\n")
    found = store.search_entities("deal", query="RENEWAL", sort="value")
    assert [deal["id"] for deal in found] == [small["id"], large["id"]]
    found = store.search_entities("deal", filter={"value": {"$gte": 50}})
    assert {deal["title"] for deal in found} == {"Large renewal", "Other"}
    found = store.search_entities("deal", filter={"tags": {"$contains": "hot"}})
    assert [deal["title"] for deal in found] == ["Other"]
    assert len(store.search_entities("deal", limit=None)) == 3
    with pytest.raises(ValueError):
        store.search_entities("deal", filter={"value": {"$regex": "."}})


def test_server_reads_a_workspace_written_by_the_upjack_version(tmp_path, monkeypatch):
    """Every tool reads the records Upjack wrote, through the server, files untouched.

    The fixture is a workspace the Upjack-backed server saved: three linked
    records plus its relationship index. Reads must leave every file as it
    was, and a write through a tool must keep the record's own fields.
    """
    from synapse_crm import server

    fixture = _write_fixture(tmp_path)
    original = {path: path.read_bytes() for path in tmp_path.rglob("*.json")}
    monkeypatch.setenv("MPAK_WORKSPACE", str(tmp_path))
    monkeypatch.delenv("UPJACK_ROOT", raising=False)
    importlib.reload(server)
    mcp = server.mcp
    contact_id = "ct_01M6720C22S98N4VC7WXTR33SC"

    contact = _run(_call_tool(mcp, "get_contact", {"contact_id": contact_id}))
    assert contact["custom_field"] == "retained"
    assert [
        c["id"] for c in _run(_call_tool(mcp, "list_contacts", {}))["entities"]
    ] == [contact_id]
    deals = _run(
        _call_tool(
            mcp,
            "query_deals_by_relationship",
            {"rel": "belongs_to", "target_id": contact_id},
        )
    )
    assert [deal["title"] for deal in deals["entities"]] == ["Example renewal"]
    assert deals["count"] == 1
    timeline = _run(_call_tool(mcp, "contact_timeline", {"contact_id": contact_id}))
    assert timeline["total"] == 1
    composite = _run(
        _call_tool(mcp, "get_contact_composite", {"contact_id": contact_id})
    )
    assert {kind for kind in composite["_related"]} == {"~belongs_to"}
    assert len(composite["_related"]["~belongs_to"]) == 2
    related = _run(
        _call_tool(
            mcp,
            "get_related_deal",
            {"deal_id": "dl_01M6720C24Z6CYW78JHKD9KBV3", "direction": "forward"},
        )
    )
    assert [record["id"] for record in related["entities"]] == [contact_id]
    assert (
        _run(_call_tool(mcp, "pipeline_summary", {}))["totals"]["active_value"] == 2000
    )
    assert {path: path.read_bytes() for path in original} == original

    updated = _run(
        _call_tool(
            mcp, "update_contact", {"contact_id": contact_id, "company": "Updated Co"}
        )
    )
    assert updated["custom_field"] == "retained"
    assert updated["created_at"] == contact["created_at"]
    saved = json.loads(
        (tmp_path / f"apps/crm/data/contacts/{contact_id}.json").read_text()
    )
    assert saved["company"] == "Updated Co" and saved["custom_field"] == "retained"
    assert (tmp_path / INDEX).read_bytes() == original[tmp_path / INDEX]
    # rebuild_index through the tool rewrites the same index content, plus the
    # trailing newline Upjack left off this one file.
    assert _run(_call_tool(mcp, "rebuild_index", {})) == {"success": True, "entries": 2}
    assert (tmp_path / INDEX).read_bytes() == original[tmp_path / INDEX] + b"\n"
    assert json.loads((tmp_path / INDEX).read_text()) == fixture[INDEX]


def test_workspace_root_honours_upjack_root_then_mpak_workspace(monkeypatch):
    from synapse_crm.server import workspace_root

    monkeypatch.setenv("UPJACK_ROOT", "/from-upjack")
    monkeypatch.setenv("MPAK_WORKSPACE", "/from-host")
    assert workspace_root() == Path("/from-upjack")
    monkeypatch.delenv("UPJACK_ROOT")
    assert workspace_root() == Path("/from-host")
    monkeypatch.delenv("MPAK_WORKSPACE")
    assert workspace_root() == Path("./workspace")


def test_writes_keep_the_saved_file_mode(tmp_path):
    store = CRMStore(tmp_path, ROOT)
    contact = store.create_entity("contact", {"name": "Mode kept"})
    path = tmp_path / "apps/crm/data/contacts" / f"{contact['id']}.json"
    path.chmod(0o640)
    store.update_entity("contact", contact["id"], {"company": "Example Co"})
    assert store.get_entity("contact", contact["id"])["company"] == "Example Co"
    assert path.stat().st_mode & 0o777 == 0o640


def test_relationship_queries_follow_writes_and_hard_deletes(tmp_path):
    store = CRMStore(tmp_path, ROOT)
    first = store.create_entity("contact", {"name": "First"})
    second = store.create_entity("contact", {"name": "Second"})
    early = log_interaction(store, first["id"], "note", "Before the update")
    store.update_entity("contact", second["id"], {"company": "Example Co"})
    late = log_interaction(store, second["id"], "note", "After the update")
    assert contact_timeline(store, first["id"])["total"] == 1
    assert [r["id"] for r in store.get_related(first["id"], direction="reverse")] == [
        early["id"]
    ]
    assert [r["id"] for r in store.get_related(late["id"], rel="belongs_to")] == [
        second["id"]
    ]
    composite = store.get_composite("interaction", late["id"])
    assert [r["id"] for r in composite["_related"]["belongs_to"]] == [second["id"]]
    index = json.loads((tmp_path / INDEX).read_text())["reverse"]
    assert index[second["id"]] == [{"source": late["id"], "rel": "belongs_to"}]
    store.delete_entity("interaction", late["id"], hard=True)
    assert contact_timeline(store, first["id"])["total"] == 1
    assert second["id"] not in json.loads((tmp_path / INDEX).read_text())["reverse"]
    store.delete_entity("interaction", early["id"], hard=True)
    assert contact_timeline(store, first["id"])["total"] == 0
    assert store.rebuild_index() == {"success": True, "entries": 0}
    with pytest.raises(ValueError):
        store.get_related(first["id"], direction="sideways")


def test_seed_data_loads_every_sample_record_once(mcp, app):
    result = _run(_call_tool(mcp, "seed_data", {}))
    assert result["errors"] == []
    assert len(result["loaded"]) == 25 + 21 + 15
    assert len(app.list_entities("contact")) == 25
    assert {c["created_by"] for c in app.list_entities("contact")} == {"system"}
    linked = _run(_call_tool(mcp, "link_deals_to_contacts", {}))
    assert linked["linked"] > 0 and linked["linked"] + linked["skipped"] == 21
    assert _run(_call_tool(mcp, "pipeline_summary", {}))["totals"]["active_deals"] > 0


def test_add_field_writes_the_schema_and_validates_with_it(tmp_path):
    schemas = tmp_path / "project/schemas"
    schemas.mkdir(parents=True)
    for path in (ROOT / "schemas").glob("*.json"):
        (schemas / path.name).write_bytes(path.read_bytes())
    store = CRMStore(tmp_path / "workspace", tmp_path / "project")
    assert store.add_field("deal", "Region", "string", "west") == {
        "error": "Invalid field_name 'Region'. Must match [a-z][a-z0-9_]*"
    }
    assert "reserved" in store.add_field("deal", "status", "string", "x")["error"]
    assert (
        "Invalid field_type" in store.add_field("deal", "region", "text", "x")["error"]
    )
    assert (
        "not compatible" in store.add_field("deal", "region", "integer", True)["error"]
    )
    assert store.add_field("deal", "title", "string", "x") == {
        "error": "Field 'title' already exists"
    }
    assert store.add_field("deal", "value", "string", "x") == {
        "error": "Field 'value' already exists with type '['number', 'null']'"
    }
    assert store.add_field("deal", "region", "string", "west", "Sales region") == {
        "success": True,
        "entity_type": "deal",
        "field": {
            "name": "region",
            "type": "string",
            "default": "west",
            "required": True,
        },
    }
    saved = json.loads((schemas / "deal.schema.json").read_text())
    assert saved["properties"]["region"] == {
        "type": "string",
        "default": "west",
        "description": "Sales region",
    }
    assert "region" in saved["required"]
    assert store.create_entity("deal", {"title": "Defaulted"})["region"] == "west"
    with pytest.raises(ValidationError):
        store.create_entity("deal", {"title": "Wrong type", "region": 3})
    assert store.add_field("deal", "region", "string", "west") == {
        "error": "Field 'region' already exists"
    }


def test_create_arguments_keep_an_entity_allof_member(tmp_path):
    from synapse_crm.entity_tools import _fields_schema

    store = CRMStore(tmp_path, ROOT)
    schema = store.schema("deal")
    own = {
        "if": {"properties": {"stage": {"const": "closed_won"}}},
        "then": {"required": ["value"]},
    }
    schema["allOf"].append(own)
    fields = _fields_schema(schema, store.base_schema())
    assert fields["allOf"] == [own]
    assert "id" not in fields["properties"] and "title" in fields["properties"]
    assert "allOf" not in _fields_schema(store.schema("deal"), store.base_schema())


def test_hidden_create_contact_stays_callable(mcp):
    listed = _run(_list_tool_names(mcp))
    assert "create_contact" not in listed
    created = _run(_call_tool(mcp, "create_contact", {"name": "Hidden but callable"}))
    assert created["id"].startswith("ct_")
    assert (
        _run(_call_tool(mcp, "get_contact", {"contact_id": created["id"]})) == created
    )


def test_immutable_fields_and_caller_values_are_preserved(tmp_path):
    store = CRMStore(tmp_path, ROOT)
    supplied = {"name": "Example contact", "tags": ["example"]}
    original = deepcopy(supplied)
    contact = store.create_entity("contact", supplied)
    assert supplied == original
    assert contact["created_at"] == contact["updated_at"]
    updated = store.update_entity(
        "contact",
        contact["id"],
        {"id": "different", "created_at": "invalid", "company": "Example"},
    )
    assert updated["id"] == contact["id"]
    assert updated["created_at"] == contact["created_at"]
