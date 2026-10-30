"""Workspace compatibility and write boundaries for the native CRM store."""

from copy import deepcopy
import json
from pathlib import Path
from threading import Event, Thread

import pytest
from jsonschema import ValidationError

from synapse_crm.store import CRMStore


ROOT = Path(__file__).resolve().parents[1]


def test_existing_workspace_reads_preserve_bytes_and_custom_fields(tmp_path):
    fixture = json.loads((ROOT / "tests/fixtures/legacy-workspace.json").read_text())
    for relative, record in fixture.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record, indent=2) + "\n")
    original = {path: path.read_bytes() for path in tmp_path.rglob("*.json")}
    store = CRMStore(tmp_path, ROOT)
    contact = store.list_entities("contact")[0]
    assert contact["legacy_field"] == "retained"
    assert {path: path.read_bytes() for path in original} == original
    linked = store.get_related(contact["id"], direction="reverse")
    assert {item["type"] for item in linked} == {"deal", "interaction"}
    updated = store.update_entity("contact", contact["id"], {"company": "Updated Co"})
    restarted = CRMStore(tmp_path, ROOT).get_entity("contact", contact["id"])
    assert restarted == updated
    assert restarted["legacy_field"] == "retained"
    assert restarted["id"] == contact["id"]
    assert restarted["created_at"] == contact["created_at"]


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
    "invalid", ["../outside", "ct_../../outside", "dl_invalid", "dl_" + "Z" * 27]
)
def test_entity_id_paths_cannot_escape_workspace(tmp_path, invalid):
    store = CRMStore(tmp_path, ROOT)
    with pytest.raises(ValueError):
        store.get_entity("deal", invalid)
    assert list(tmp_path.rglob("*.json")) == []


def test_schema_extensions_persist_without_editing_installed_schema(tmp_path):
    schema = ROOT / "schemas/contact.schema.json"
    before = schema.read_bytes()
    store = CRMStore(tmp_path, ROOT)
    contact = store.create_entity("contact", {"name": "Example contact"})
    result = store.add_field("contact", "region", "string", "west")
    assert result["success"] is True
    assert schema.read_bytes() == before
    restarted = CRMStore(tmp_path, ROOT)
    assert restarted.get_entity("contact", contact["id"])["region"] == "west"
    assert (
        restarted.update_entity("contact", contact["id"], {"region": "east"})["region"]
        == "east"
    )
    assert schema.read_bytes() == before


def test_invalid_schema_extension_does_not_change_workspace(tmp_path):
    store = CRMStore(tmp_path, ROOT)
    assert "error" in store.add_field("contact", "region", "integer", "wrong")
    assert "error" in store.add_field("contact", "id", "string", "wrong")
    assert list(tmp_path.rglob("*.json")) == []


def test_explicit_hard_delete_and_derived_index_rebuild(tmp_path):
    store = CRMStore(tmp_path, ROOT)
    contact = store.create_entity("contact", {"name": "Example contact"})
    deal = store.create_entity(
        "deal",
        {
            "title": "Example deal",
            "relationships": [{"rel": "belongs_to", "target": contact["id"]}],
        },
    )
    assert store.rebuild_index() == {"success": True, "entries": 1}
    assert store.get_related(contact["id"], direction="reverse") == [deal]
    assert store.delete_entity("deal", deal["id"], hard=True) == deal
    with pytest.raises(FileNotFoundError):
        store.get_entity("deal", deal["id"])
    assert store.rebuild_index() == {"success": True, "entries": 0}
    assert store.get_related(contact["id"], direction="reverse") == []


def test_immutable_fields_and_caller_values_are_preserved(tmp_path):
    store = CRMStore(tmp_path, ROOT)
    supplied = {"name": "Example contact", "tags": ["example"]}
    original = deepcopy(supplied)
    contact = store.create_entity("contact", supplied)
    assert supplied == original
    updated = store.update_entity(
        "contact",
        contact["id"],
        {"id": "different", "created_at": "invalid", "company": "Example"},
    )
    assert updated["id"] == contact["id"]
    assert updated["created_at"] == contact["created_at"]


def test_reverse_relationships_survive_hard_deleted_target(tmp_path):
    store = CRMStore(tmp_path, ROOT)
    contact = store.create_entity("contact", {"name": "Removed contact"})
    deal = store.create_entity(
        "deal",
        {
            "title": "Retained deal",
            "relationships": [{"rel": "belongs_to", "target": contact["id"]}],
        },
    )
    store.delete_entity("contact", contact["id"], hard=True)
    assert store.get_related(contact["id"], direction="reverse") == [deal]
    with pytest.raises(FileNotFoundError):
        store.get_related(contact["id"], direction="forward")


def test_concurrent_create_cannot_leave_rebuilt_index_stale(tmp_path, monkeypatch):
    store = CRMStore(tmp_path, ROOT)
    contact = store.create_entity("contact", {"name": "Index target"})
    store.create_entity(
        "deal",
        {
            "title": "Existing deal",
            "relationships": [{"rel": "belongs_to", "target": contact["id"]}],
        },
    )
    scanned, release, probed, finished = Event(), Event(), Event(), Event()
    original_all = store._all
    acquired, created, errors = [], [], []

    def pause_after_scan(kind):
        records = original_all(kind)
        if kind == "interaction":
            scanned.set()
            assert release.wait(timeout=3)
        return records

    def rebuild():
        try:
            store.rebuild_index()
        except Exception as error:
            errors.append(error)

    def create():
        locked = store.lock.acquire(blocking=False)
        acquired.append(locked)
        probed.set()
        try:
            created.append(
                store.create_entity(
                    "deal",
                    {
                        "title": "Concurrent deal",
                        "relationships": [
                            {"rel": "belongs_to", "target": contact["id"]}
                        ],
                    },
                )
            )
        except Exception as error:
            errors.append(error)
        finally:
            if locked:
                store.lock.release()
            finished.set()

    monkeypatch.setattr(store, "_all", pause_after_scan)
    rebuilder, writer = Thread(target=rebuild), Thread(target=create)
    rebuilder.start()
    try:
        assert scanned.wait(timeout=3)
        writer.start()
        assert probed.wait(timeout=3)
        # Without a rebuild lock, force the new write to finish before the
        # stale snapshot is published. With the lock it waits for publication.
        if acquired[0]:
            assert finished.wait(timeout=3)
    finally:
        release.set()
        rebuilder.join(timeout=3)
        if writer.ident is not None:
            writer.join(timeout=3)
    assert not rebuilder.is_alive() and not writer.is_alive()
    assert errors == []
    index = tmp_path / "apps/crm/data/_index/relations.json"
    if index.exists():
        reverse = json.loads(index.read_text())["reverse"][contact["id"]]
        assert {"source": created[0]["id"], "rel": "belongs_to"} in reverse
