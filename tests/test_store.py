"""Workspace compatibility and write boundaries for the CRM record store."""

import json
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import ValidationError

from synapse_crm.store import CRMStore
from synapse_crm.tools.contact_timeline import contact_timeline
from synapse_crm.tools.log_interaction import log_interaction

ROOT = Path(__file__).resolve().parents[1]
INDEX = "apps/crm/data/_index/relations.json"


def test_existing_workspace_reads_preserve_bytes_and_custom_fields(tmp_path):
    fixture = json.loads((ROOT / "tests/fixtures/workspace.json").read_text())
    for relative, record in fixture.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record, indent=2) + "\n")
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
    with pytest.raises(FileNotFoundError):
        store.get_entity("deal", hard["id"])
    assert [deal["id"] for deal in store.list_entities("deal")] == [kept["id"]]
    assert [deal["id"] for deal in store.list_entities("deal", status="deleted")] == [
        soft["id"]
    ]
    assert [deal["id"] for deal in store.search_entities("deal")] == [kept["id"]]


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


def test_upjack_reads_store_records_and_store_reads_upjack_records(tmp_path, app):
    store = CRMStore(tmp_path, ROOT)
    from_store = store.create_entity("contact", {"name": "Written by store"})
    assert app.get_entity("contact", from_store["id"])["name"] == "Written by store"
    from_upjack = app.create_entity("contact", {"name": "Written by Upjack"})
    assert store.get_entity("contact", from_upjack["id"])["name"] == "Written by Upjack"
    contacts = tmp_path / "apps/crm/data/contacts"
    path = contacts / f"{from_upjack['id']}.json"
    assert (contacts / f"{from_store['id']}.json").stat().st_mode == path.stat().st_mode
    path.chmod(0o640)
    store.update_entity("contact", from_upjack["id"], {"company": "Example Co"})
    assert app.get_entity("contact", from_upjack["id"])["company"] == "Example Co"
    assert path.stat().st_mode & 0o777 == 0o640


def test_store_writes_keep_upjack_relationship_queries_whole(tmp_path, app):
    store = CRMStore(tmp_path, ROOT)
    first = app.create_entity("contact", {"name": "First"})
    second = app.create_entity("contact", {"name": "Second"})
    early = log_interaction(app, first["id"], "note", "Before the store write")
    store.update_entity("contact", second["id"], {"company": "Example Co"})
    late = log_interaction(app, second["id"], "note", "After the store write")
    assert contact_timeline(app, first["id"])["total"] == 1
    store.update_entity("contact", second["id"], {"company": "Other Co"})
    app.delete_entity("interaction", late["id"], hard=True)
    assert contact_timeline(app, first["id"])["total"] == 1
    store.delete_entity("interaction", early["id"], hard=True)
    assert contact_timeline(app, first["id"])["total"] == 0


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
