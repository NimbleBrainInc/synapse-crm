"""Operator migration preserves fields without editing source or records."""

import json
from pathlib import Path
import shutil

import pytest

from synapse_crm.migration import apply_migration, plan_migration
from synapse_crm.store import CRMStore

PROJECT = Path(__file__).resolve().parents[1]


@pytest.fixture
def legacy(tmp_path):
    source = tmp_path / "source"
    schemas = source / "schemas"
    schemas.mkdir(parents=True)
    for entity in ("contact", "deal", "interaction"):
        schema = json.loads((PROJECT / "schemas" / f"{entity}.schema.json").read_text())
        schema["allOf"] = [
            {"$ref": "https://upjack.dev/schemas/v1/upjack-entity.schema.json"}
        ]
        (schemas / f"{entity}.schema.json").write_text(json.dumps(schema))
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return source, workspace


def add_field(source, entity, name="category", definition=None):
    path = source / "schemas" / f"{entity}.schema.json"
    value = json.loads(path.read_text())
    value["properties"][name] = definition or {"type": "string", "default": "general"}
    value.setdefault("required", []).append(name)
    path.write_text(json.dumps(value))


def test_plan_is_read_only_and_apply_preserves_source_records_and_existing_fields(
    legacy,
):
    source, workspace = legacy
    store = CRMStore(workspace, PROJECT)
    contact = store.create_entity("contact", {"name": "Existing"})
    store.add_field("contact", "owner", "string", "unassigned")
    record_path = workspace / "apps/crm/data/contacts" / f"{contact['id']}.json"
    before = record_path.read_bytes()
    add_field(source, "contact")
    schema_path = source / "schemas/contact.schema.json"
    old_schema = schema_path.read_bytes()

    plan = plan_migration(source, workspace)
    assert plan["version"] == 1
    assert plan["updates"]["apps/crm/schemas/contact.schema.json"]["fields"] == {
        "owner": {"type": "string", "default": "unassigned", "required": True},
        "category": {"type": "string", "default": "general", "required": True},
    }
    assert "category" not in store._read_extensions("contact")
    assert record_path.read_bytes() == before

    assert apply_migration(source, workspace, plan["planHash"])["filesChanged"] == 1
    reopened = CRMStore(workspace, PROJECT)
    assert reopened.get_entity("contact", contact["id"])["category"] == "general"
    assert reopened.get_entity("contact", contact["id"])["owner"] == "unassigned"
    assert record_path.read_bytes() == before
    assert schema_path.read_bytes() == old_schema
    assert plan_migration(source, workspace)["updates"] == {}


def test_changed_plan_is_rejected_before_any_schema_write(legacy):
    source, workspace = legacy
    add_field(source, "contact")
    plan = plan_migration(source, workspace)
    add_field(source, "deal", "estimate", {"type": "integer", "default": 0})
    with pytest.raises(ValueError, match="plan changed"):
        apply_migration(source, workspace, plan["planHash"])
    assert not (workspace / "apps/crm/schemas").exists()


def test_plan_cannot_be_applied_to_another_identical_workspace(legacy, tmp_path):
    source, workspace = legacy
    add_field(source, "contact")
    plan = plan_migration(source, workspace)
    other = tmp_path / "other-workspace"
    other.mkdir()
    with pytest.raises(ValueError, match="plan changed"):
        apply_migration(source, other, plan["planHash"])
    assert not (other / "apps").exists()


@pytest.mark.parametrize(
    "bad",
    [
        {"type": "integer", "default": "wrong"},
        {"type": "string", "default": "x", "pattern": ".*"},
    ],
)
def test_invalid_second_schema_prevents_all_writes(legacy, bad):
    source, workspace = legacy
    add_field(source, "contact")
    add_field(source, "deal", definition=bad)
    with pytest.raises(ValueError):
        plan_migration(source, workspace)
    assert not (workspace / "apps").exists()


def test_existing_field_conflict_is_rejected_without_changing_override(legacy):
    source, workspace = legacy
    store = CRMStore(workspace, PROJECT)
    store.add_field("contact", "category", "string", "other")
    target = workspace / "apps/crm/schemas/contact.schema.json"
    before = target.read_bytes()
    add_field(source, "contact")
    with pytest.raises(ValueError, match="conflicts"):
        plan_migration(source, workspace)
    assert target.read_bytes() == before


def test_existing_base_schema_edit_is_not_treated_as_a_field_addition(legacy):
    source, workspace = legacy
    path = source / "schemas/contact.schema.json"
    schema = json.loads(path.read_text())
    schema["properties"]["name"]["type"] = "integer"
    path.write_text(json.dumps(schema))
    with pytest.raises(ValueError, match="existing fields"):
        plan_migration(source, workspace)
    assert not (workspace / "apps").exists()


def test_schema_symlink_is_rejected(legacy, tmp_path):
    source, workspace = legacy
    path = source / "schemas/contact.schema.json"
    outside = tmp_path / "outside.json"
    shutil.copyfile(path, outside)
    path.unlink()
    path.symlink_to(outside)
    before = outside.read_bytes()
    with pytest.raises(ValueError, match="symlinks"):
        plan_migration(source, workspace)
    assert outside.read_bytes() == before


def test_actual_upjack_add_field_schema_is_supported(legacy):
    source, workspace = legacy
    # Captured from the previous tool on a disposable canonical source tree.
    fixture = (PROJECT / "tests/fixtures/legacy-added-field-schema.json").read_bytes()
    (source / "schemas/contact.schema.json").write_bytes(fixture)
    plan = plan_migration(source, workspace)
    assert apply_migration(source, workspace, plan["planHash"])["filesChanged"] == 1
    store = CRMStore(workspace, PROJECT)
    assert store.create_entity("contact", {"name": "Example"})["category"] == "general"


def test_altered_inlined_base_schema_is_rejected_before_any_write(legacy):
    source, workspace = legacy
    value = json.loads(
        (PROJECT / "tests/fixtures/legacy-added-field-schema.json").read_text()
    )
    value["allOf"][0]["properties"]["status"]["enum"] = ["active"]
    (source / "schemas/contact.schema.json").write_text(json.dumps(value))
    with pytest.raises(ValueError, match="base reference"):
        plan_migration(source, workspace)
    assert not (workspace / "apps").exists()
