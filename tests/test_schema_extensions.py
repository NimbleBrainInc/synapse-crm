"""Custom fields stay in the workspace across application replacement."""

import errno
import fcntl
import json
import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import ValidationError

from synapse_crm.store import CRMStore, SchemaExtensionError

PROJECT = Path(__file__).resolve().parents[1]
KIND = "deal"
DATA = {"title": "Example"}


@pytest.fixture
def setup(tmp_path):
    project = tmp_path / "package"
    shutil.copytree(PROJECT / "schemas", project / "schemas")
    workspace = tmp_path / "workspace"
    return CRMStore(workspace, project), workspace, project


def fields_path(workspace):
    return workspace / "apps/crm/schemas" / f"{KIND}.fields.json"


def lock_is_free(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except BlockingIOError:
        return False
    finally:
        os.close(fd)


def test_fields_survive_restart_and_package_replacement_without_record_edits(
    setup, tmp_path
):
    store, workspace, project = setup
    record = store.create_entity(KIND, {**DATA, "custom": {"retained": True}})
    records = {path: path.read_bytes() for path in workspace.rglob("*.json")}
    source = {path: path.read_bytes() for path in (project / "schemas").glob("*.json")}
    assert store.add_field(KIND, "estimate", "integer", 2, "Points")["success"]
    assert store.get_entity(KIND, record["id"])["estimate"] == 2
    assert {path: path.read_bytes() for path in records} == records
    assert {path: path.read_bytes() for path in source} == source
    replacement = tmp_path / "replacement"
    shutil.copytree(PROJECT / "schemas", replacement / "schemas")
    restarted = CRMStore(workspace, replacement)
    assert restarted.get_entity(KIND, record["id"]) == {**record, "estimate": 2}
    with pytest.raises(ValidationError):
        restarted.update_entity(KIND, record["id"], {"estimate": "invalid"})
    assert {path: path.read_bytes() for path in records} == records
    changed = restarted.update_entity(KIND, record["id"], {"estimate": 5})
    assert changed["custom"] == record["custom"]
    for name in ("id", "type", "created_at", "created_by"):
        assert changed[name] == record[name]
    assert restarted.create_entity(KIND, DATA)["estimate"] == 2


@pytest.mark.parametrize(
    "field_type,default",
    [
        ("string", "west"),
        ("integer", 3),
        ("number", 1.5),
        ("boolean", False),
        ("array", ["one"]),
        ("object", {"one": 1}),
    ],
)
def test_supported_defaults_and_optional_metadata_round_trip(
    setup, field_type, default
):
    store, workspace, project = setup
    assert store.add_field(KIND, "extra", field_type, default, "Details", False)[
        "success"
    ]
    assert json.loads(fields_path(workspace).read_text())["fields"]["extra"] == {
        "type": field_type,
        "default": default,
        "description": "Details",
        "required": False,
    }
    assert CRMStore(workspace, project).create_entity(KIND, DATA)["extra"] == default


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "[]",
        '{"version":true,"fields":{}}',
        '{"version":2,"fields":{}}',
        '{"version":1,"fields":[],"extra":0}',
        '{"version":1,"fields":{},"fields":{}}',
        '{"version":1,"fields":{"extra":{"type":"string","default":"", "required":true,"required":false}}}',
        *[
            json.dumps({"version": 1, "fields": {name: definition}})
            for name, definition in [
                ("extra", []),
                ("extra", {"type": "string", "default": ""}),
                ("extra", {"type": [], "default": "", "required": True}),
                ("extra", {"type": "string", "default": 1, "required": True}),
                ("extra", {"type": "integer", "default": True, "required": True}),
                (
                    "extra",
                    {"type": "number", "default": float("nan"), "required": True},
                ),
                ("extra", {"type": "string", "default": "", "required": "yes"}),
                (
                    "extra",
                    {"type": "string", "default": "", "required": True, "unknown": 0},
                ),
                (
                    "extra",
                    {
                        "type": "string",
                        "default": "",
                        "required": True,
                        "description": 0,
                    },
                ),
                ("Bad", {"type": "string", "default": "", "required": True}),
                ("status", {"type": "string", "default": "", "required": True}),
                ("title", {"type": "string", "default": "", "required": True}),
            ]
        ],
    ],
)
def test_malformed_or_colliding_fields_refuse_load_and_add_without_overwrite(
    setup, raw
):
    store, workspace, project = setup
    record = store.create_entity(KIND, DATA)
    before = {path: path.read_bytes() for path in workspace.rglob("*.json")}
    path = fields_path(workspace)
    path.parent.mkdir(parents=True)
    path.write_text(raw)
    with pytest.raises(SchemaExtensionError, match="schema extension"):
        CRMStore(workspace, project)
    with pytest.raises(SchemaExtensionError, match="schema extension"):
        store.add_field(KIND, "another", "string", "")
    with pytest.raises(SchemaExtensionError, match="schema extension"):
        store.update_entity(KIND, record["id"], DATA)
    with pytest.raises(SchemaExtensionError, match="schema extension"):
        store.list_entities(KIND)
    assert path.read_text() == raw
    assert {path: path.read_bytes() for path in before} == before
    assert lock_is_free(path.with_suffix(".lock"))


@pytest.mark.parametrize(
    "field_type,default",
    [("number", float("nan")), ("number", float("inf")), ("array", [float("nan")])],
)
def test_add_field_returns_error_for_non_json_default(setup, field_type, default):
    store, workspace, _ = setup
    result = store.add_field(KIND, "extra", field_type, default)
    assert "is not compatible" in result["error"]
    assert not fields_path(workspace).exists()
    assert not fields_path(workspace).with_suffix(".lock").exists()


@pytest.mark.parametrize("schema_name", [KIND, "entity"])
def test_package_field_collision_requires_reconciliation(setup, schema_name):
    store, workspace, project = setup
    assert store.add_field(KIND, "extra", "string", "west")["success"]
    before = fields_path(workspace).read_bytes()
    path = project / "schemas" / f"{schema_name}.schema.json"
    schema = json.loads(path.read_text())
    schema["properties"]["extra"] = {"type": "string", "default": "east"}
    path.write_text(json.dumps(schema))
    with pytest.raises(SchemaExtensionError, match="colliding"):
        CRMStore(workspace, project)
    assert fields_path(workspace).read_bytes() == before


def test_existing_source_customizations_are_read_without_migration(setup):
    _, workspace, project = setup
    path = project / "schemas" / f"{KIND}.schema.json"
    schema = json.loads(path.read_text())
    schema["properties"]["legacy"] = {
        "type": "string",
        "default": "kept",
        "description": "Legacy",
    }
    schema.setdefault("required", []).append("legacy")
    path.write_text(json.dumps(schema))
    before = path.read_bytes()
    store = CRMStore(workspace, project)
    assert store.create_entity(KIND, DATA)["legacy"] == "kept"
    assert not fields_path(workspace).exists()
    assert "error" in store.add_field(KIND, "legacy", "string", "changed")
    assert store.add_field(KIND, "extra", "string", "new")["success"]
    assert path.read_bytes() == before
    assert CRMStore(workspace, project).create_entity(KIND, DATA)["legacy"] == "kept"


def test_two_stores_preserve_successive_fields_and_reject_concurrent_writer(
    setup, monkeypatch
):
    first, workspace, project = setup
    second = CRMStore(workspace, project)
    original = first._atomic

    def overlapping_write(path, value):
        assert "writer" in second.add_field(KIND, "second", "string", "two")["error"]
        original(path, value)

    monkeypatch.setattr(first, "_atomic", overlapping_write)
    assert first.add_field(KIND, "first", "string", "one")["success"]
    monkeypatch.setattr(first, "_atomic", original)
    assert second.add_field(KIND, "second", "integer", 2)["success"]
    assert set(json.loads(fields_path(workspace).read_text())["fields"]) == {
        "first",
        "second",
    }
    with pytest.raises(ValidationError):
        first.create_entity(KIND, {**DATA, "second": "wrong"})
    assert first.create_entity(KIND, DATA)["second"] == 2
    assert "already exists" in first.add_field(KIND, "second", "integer", 0)["error"]


def test_failed_write_preserves_extensions_and_releases_lock(setup, monkeypatch):
    store, workspace, project = setup
    assert store.add_field(KIND, "first", "string", "one")["success"]
    before = fields_path(workspace).read_bytes()

    def fail(path, value):
        raise OSError("test write failure")

    monkeypatch.setattr(store, "_atomic", fail)
    with pytest.raises(OSError, match="test write failure"):
        store.add_field(KIND, "second", "integer", 2)
    assert fields_path(workspace).read_bytes() == before
    assert lock_is_free(fields_path(workspace).with_suffix(".lock"))
    assert "second" not in CRMStore(workspace, project).create_entity(KIND, DATA)


def test_lock_error_other_than_contention_closes_the_lock_file(setup, monkeypatch):
    store, workspace, _ = setup

    def unsupported(fd, operation):
        raise OSError(errno.ENOLCK, "No locks available")

    monkeypatch.setattr(fcntl, "flock", unsupported)
    before = len(os.listdir("/dev/fd"))
    with pytest.raises(OSError, match="No locks available"):
        store.add_field(KIND, "extra", "string", "west")
    assert len(os.listdir("/dev/fd")) == before
    assert not fields_path(workspace).exists()


HOLD_LOCK = """
import sys, time
from synapse_crm.store import CRMStore

store = CRMStore(sys.argv[1], sys.argv[2])

def hold(path, value):
    print("held", flush=True)
    time.sleep(60)

store._atomic = hold
store.add_field("deal", "first", "string", "one")
"""


def test_add_field_lock_released_when_writer_killed(setup):
    store, workspace, project = setup
    child = subprocess.Popen(
        [sys.executable, "-c", HOLD_LOCK, str(workspace), str(project)],
        stdout=subprocess.PIPE,
        text=True,
        env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)},
    )
    try:
        assert child.stdout.readline() == "held\n"
        assert "writer" in store.add_field(KIND, "second", "string", "two")["error"]
    finally:
        child.kill()
        child.wait()
    assert child.returncode == -signal.SIGKILL
    assert store.add_field(KIND, "second", "string", "two")["success"]
    assert set(json.loads(fields_path(workspace).read_text())["fields"]) == {"second"}


def test_restart_exposes_fields_to_mcp_create_and_update(setup):
    from fastmcp import Client, FastMCP

    from synapse_crm.entity_tools import register_entity_tools
    from tests.conftest import _run

    store, workspace, project = setup
    first = FastMCP("field declaration")
    register_entity_tools(first, store, PROJECT)

    async def declare():
        async with Client(first) as client:
            result = await client.call_tool(
                "add_field",
                {
                    "entity_type": KIND,
                    "field_name": "extra",
                    "field_type": "string",
                    "default": "default",
                    "description": "Details",
                },
            )
            assert json.loads(result.content[0].text)["success"]

    _run(declare())
    restarted = CRMStore(workspace, project)
    second = FastMCP("restarted app")
    register_entity_tools(second, restarted, PROJECT)

    async def use():
        async with Client(second) as client:
            tools = {tool.name: tool for tool in await client.list_tools()}
            field = tools[f"create_{KIND}"].input_schema["properties"]["extra"]
            assert field["type"] == "string" and field["description"] == "Details"
            result = await client.call_tool(
                f"create_{KIND}", {**DATA, "extra": "chosen"}
            )
            record = json.loads(result.content[0].text)
            assert record["extra"] == "chosen"
            result = await client.call_tool(
                f"update_{KIND}", {f"{KIND}_id": record["id"], "extra": "updated"}
            )
            assert json.loads(result.content[0].text)["extra"] == "updated"

    _run(use())


@pytest.mark.parametrize(
    "failure", ["permission", "path_escape", "source_json", "source_missing"]
)
def test_shared_schema_failure_never_hides_records_or_rewrites_index(
    setup, tmp_path, monkeypatch, failure
):
    store, workspace, project = setup
    record = store.create_entity(KIND, DATA)
    store.update_entity(
        KIND,
        record["id"],
        {"relationships": [{"rel": "related_to", "target": record["id"]}]},
    )
    before = {
        path: path.read_bytes()
        for path in (workspace / "apps/crm/data").rglob("*.json")
    }
    assert any(json.loads(raw).get("reverse") for raw in before.values())
    extension = fields_path(workspace)
    if failure == "permission":
        original = Path.read_text

        def deny_extension(path, *args, **kwargs):
            if path == extension:
                raise PermissionError("test unreadable declarations")
            return original(path, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", deny_extension)
    elif failure == "path_escape":
        outside = tmp_path / "outside.fields.json"
        outside.write_text('{"version": 1, "fields": {}}')
        extension.parent.mkdir(parents=True)
        extension.symlink_to(outside)
    elif failure == "source_json":
        (project / "schemas" / f"{KIND}.schema.json").write_text("{")
    else:
        (project / "schemas" / f"{KIND}.schema.json").unlink()
    with pytest.raises(SchemaExtensionError):
        store.list_entities(KIND)
    with pytest.raises(SchemaExtensionError):
        store.rebuild_index()
    assert {path: path.read_bytes() for path in before} == before


@pytest.mark.parametrize("operation", ["create", "update"])
def test_required_field_publication_during_write_uses_one_schema_snapshot(
    setup, monkeypatch, operation
):
    first, workspace, project = setup
    second = CRMStore(workspace, project)
    existing = first.create_entity(KIND, DATA) if operation == "update" else None
    original = first._hydrate
    published = False

    def publish_after_hydration(*args, **kwargs):
        nonlocal published
        record = original(*args, **kwargs)
        if not published:
            published = True
            assert second.add_field(KIND, "late", "integer", 5)["success"]
        return record

    monkeypatch.setattr(first, "_hydrate", publish_after_hydration)
    if existing:
        record = first.update_entity(KIND, existing["id"], DATA)
    else:
        record = first.create_entity(KIND, DATA)
    assert record["late"] == 5
    assert second.get_entity(KIND, record["id"])["late"] == 5


def test_tools_report_broken_declarations_instead_of_a_missing_record(setup):
    from synapse_crm.tools.contact_timeline import contact_timeline

    store, workspace, _ = setup
    contact = store.create_entity("contact", {"name": "Example"})
    path = workspace / "apps/crm/schemas/contact.fields.json"
    path.parent.mkdir(parents=True)
    path.write_text("[]")
    with pytest.raises(SchemaExtensionError):
        contact_timeline(store, contact["id"])
