"""CRM records in the existing workspace JSON format."""

from copy import deepcopy
from contextvars import ContextVar
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re
import tempfile
from threading import RLock

from jsonschema import Draft202012Validator
from ulid import ULID

ENTITIES = {
    "contact": ("contacts", "ct"),
    "deal": ("deals", "dl"),
    "interaction": ("interactions", "ix"),
}
BASE_FIELDS = {
    "id",
    "type",
    "version",
    "created_at",
    "updated_at",
    "created_by",
    "status",
    "tags",
    "source",
    "relationships",
}
IMMUTABLE = {"id", "type", "version", "created_at", "created_by"}


class ChangeMarker:
    changed = False


current_change: ContextVar[ChangeMarker | None] = ContextVar("crm_change", default=None)


def mark_changed():
    marker = current_change.get()
    if marker is not None:
        marker.changed = True


def now():
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def matches(entity, filters):
    for field, expected in (filters or {}).items():
        value = entity.get(field)
        if not isinstance(expected, dict):
            if value != expected:
                return False
            continue
        for operator, operand in expected.items():
            if operator == "$exists":
                okay = (field in entity and value is not None) == operand
            elif operator == "$ne":
                okay = value != operand
            elif operator == "$in":
                okay = value in operand
            elif operator == "$contains":
                okay = isinstance(value, list) and operand in value
            elif operator in {"$gt", "$gte", "$lt", "$lte"}:
                try:
                    okay = (
                        value is not None
                        and {
                            "$gt": lambda: value > operand,
                            "$gte": lambda: value >= operand,
                            "$lt": lambda: value < operand,
                            "$lte": lambda: value <= operand,
                        }[operator]()
                    )
                except TypeError:
                    okay = False
            else:
                raise ValueError(f"Unsupported filter operator: {operator}")
            if not okay:
                return False
    return True


class CRMStore:
    def __init__(self, root, project_root):
        self.root = Path(root).resolve()
        self.project_root = Path(project_root).resolve()
        self.lock = RLock()
        self.schemas = {kind: self._load_schema(kind) for kind in ENTITIES}

    def _load_schema(self, kind):
        schema = json.loads(
            (self.project_root / "schemas" / f"{kind}.schema.json").read_text()
        )
        for name, field in self._read_extensions(kind).items():
            if (
                not re.fullmatch(r"[a-z][a-z0-9_]*", name)
                or name in BASE_FIELDS
                or name in schema["properties"]
            ):
                raise ValueError(
                    f"Invalid or colliding {kind} schema extension: {name}"
                )
            if not isinstance(field, dict) or set(field) - {
                "type",
                "default",
                "description",
                "required",
            }:
                raise ValueError(f"Invalid {kind} schema extension: {name}")
            if (
                field.get("type")
                not in {"string", "integer", "number", "boolean", "array", "object"}
                or "default" not in field
                or not isinstance(field.get("required"), bool)
            ):
                raise ValueError(f"Invalid {kind} schema extension: {name}")
            if "description" in field and not isinstance(field["description"], str):
                raise ValueError(f"Invalid {kind} schema extension: {name}")
            if not Draft202012Validator({"type": field["type"]}).is_valid(
                field["default"]
            ):
                raise ValueError(f"Invalid {kind} schema extension default: {name}")
            schema["properties"][name] = {
                key: value for key, value in field.items() if key != "required"
            }
            if field["required"]:
                schema.setdefault("required", []).append(name)
        base = json.loads(
            (self.project_root / "schemas/entity.schema.json").read_text()
        )
        schema["allOf"] = [base]
        return schema

    def _read_extensions(self, kind):
        path = self.path(f"apps/crm/schemas/{kind}.schema.json")
        if not path.exists():
            return {}
        data = json.loads(path.read_text())
        if (
            not isinstance(data, dict)
            or data.get("version") != 1
            or not isinstance(data.get("fields"), dict)
            or set(data) != {"version", "fields"}
        ):
            raise ValueError(f"Invalid {kind} schema extensions")
        return data["fields"]

    def path(self, relative):
        path = self.root / relative
        if not path.resolve().is_relative_to(self.root):
            raise ValueError("Path escapes workspace root")
        return path

    def _entity_path(self, kind, entity_id):
        plural, prefix = ENTITIES[kind]
        if not re.fullmatch(prefix + r"_[0-9A-HJKMNP-TV-Z]{26}", entity_id):
            raise ValueError(f"Invalid {kind} ID")
        return self.path(f"apps/crm/data/{plural}/{entity_id}.json")

    @staticmethod
    def _atomic(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".crm-", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "w") as stream:
                json.dump(value, stream, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def _save(self, kind, record):
        Draft202012Validator(self.schemas[kind]).validate(record)
        path = self._entity_path(kind, record["id"])
        # Discard the derived legacy index before writing. An older runtime
        # rebuilds a missing index from these same records on its next query.
        self.path("apps/crm/data/_index/relations.json").unlink(missing_ok=True)
        self._atomic(path, record)
        mark_changed()
        return deepcopy(record)

    def _hydrate(self, kind, record):
        record = deepcopy(record)
        for schema in [*self.schemas[kind].get("allOf", []), self.schemas[kind]]:
            for field, definition in schema.get("properties", {}).items():
                if field not in record and "default" in definition:
                    record[field] = deepcopy(definition["default"])
        return record

    def create_entity(self, kind, data, created_by="agent"):
        with self.lock:
            data = deepcopy(data)
            supplied_id = data.pop("id", None)
            entity_id = supplied_id or f"{ENTITIES[kind][1]}_{ULID()}"
            path = self._entity_path(kind, entity_id)
            if path.exists():
                raise ValueError(f"Entity already exists: {entity_id}")
            record = {
                "version": 1,
                "created_at": now(),
                "updated_at": now(),
                "created_by": created_by,
                "status": "active",
                "tags": [],
                "relationships": [],
                **data,
                "id": entity_id,
                "type": kind,
            }
            return self._save(kind, self._hydrate(kind, record))

    def get_entity(self, kind, entity_id):
        with self.lock:
            return self._hydrate(
                kind, json.loads(self._entity_path(kind, entity_id).read_text())
            )

    def update_entity(self, kind, entity_id, data):
        with self.lock:
            record = self.get_entity(kind, entity_id)
            record.update({k: v for k, v in data.items() if k not in IMMUTABLE})
            record["updated_at"] = now()
            return self._save(kind, record)

    def _all(self, kind):
        directory = self.path(f"apps/crm/data/{ENTITIES[kind][0]}")
        records = []
        for path in sorted(directory.glob("*.json")):
            try:
                records.append(self.get_entity(kind, path.stem))
            except json.JSONDecodeError:
                continue
        return records

    def list_entities(self, kind, status="active", limit=None):
        records = [
            record
            for record in self._all(kind)
            if record.get("status", "active") == status
        ]
        ordered = sorted(
            records, key=lambda record: record.get("updated_at", ""), reverse=True
        )
        return ordered if limit is None else ordered[: max(0, limit)]

    def delete_entity(self, kind, entity_id, hard=False):
        with self.lock:
            record = self.get_entity(kind, entity_id)
            if hard:
                self.path("apps/crm/data/_index/relations.json").unlink(missing_ok=True)
                self._entity_path(kind, entity_id).unlink()
                mark_changed()
                return record
            return self.update_entity(kind, entity_id, {"status": "deleted"})

    def search_entities(
        self, kind, query=None, filter=None, sort="-updated_at", limit=20
    ):
        records = [
            record
            for record in self._all(kind)
            if ((filter and "status" in filter) or record.get("status") != "deleted")
            and (
                not query
                or any(
                    query.lower() in v.lower()
                    for v in record.values()
                    if isinstance(v, str)
                )
            )
            and matches(record, filter)
        ]
        field = sort.lstrip("-")

        def sort_key(record):
            value = record.get(field)
            return (
                value is not None,
                isinstance(value, str),
                value if value is not None else "",
            )

        return sorted(records, key=sort_key, reverse=sort.startswith("-"))[
            : max(0, limit)
        ]

    def query_by_relationship(self, kind, rel, target_id, filter=None, limit=None):
        records = [
            record
            for record in self._all(kind)
            if record.get("status", "active") == "active"
            and matches(record, filter)
            and any(
                edge.get("rel") == rel and edge.get("target") == target_id
                for edge in record.get("relationships", [])
            )
        ]
        return records if limit is None else records[: max(0, limit)]

    def _kind(self, entity_id):
        for kind, (_, prefix) in ENTITIES.items():
            if entity_id.startswith(prefix + "_"):
                return kind
        raise ValueError("Unknown entity ID prefix")

    def get_related(self, entity_id, rel=None, direction="forward"):
        # Reverse edges can outlive a hard-deleted target. Validate its ID and
        # path, but do not require its record to exist before scanning sources.
        self._entity_path(self._kind(entity_id), entity_id)
        if direction == "reverse":
            return [
                record
                for kind in ENTITIES
                for record in self._all(kind)
                if any(
                    edge.get("target") == entity_id
                    and (rel is None or edge.get("rel") == rel)
                    for edge in record.get("relationships", [])
                )
            ]
        if direction != "forward":
            raise ValueError("Direction must be forward or reverse")
        source = self.get_entity(self._kind(entity_id), entity_id)
        related = []
        for edge in source.get("relationships", []):
            if rel is not None and edge.get("rel") != rel:
                continue
            try:
                target = self.get_entity(self._kind(edge["target"]), edge["target"])
                related.append(target)
            except (FileNotFoundError, ValueError):
                continue
        return related

    def get_composite(self, kind, entity_id, depth=1):
        entity = self.get_entity(kind, entity_id)
        if depth < 1:
            return {**entity, "_related": {}}
        related = {}
        for edge in entity.get("relationships", []):
            related[edge["rel"]] = self.get_related(entity_id, edge["rel"])
        for source in self.get_related(entity_id, direction="reverse"):
            for edge in source.get("relationships", []):
                if edge.get("target") == entity_id:
                    related.setdefault("~" + edge["rel"], []).append(source)
        return {**entity, "_related": related}

    def rebuild_index(self):
        # Serialize the snapshot and its publication with record writes. A
        # writer afterwards invalidates this cache; it cannot be overwritten
        # by an older snapshot after its record has already been committed.
        with self.lock:
            reverse = {}
            for kind in ENTITIES:
                for record in self._all(kind):
                    for edge in record.get("relationships", []):
                        entry = {"source": record["id"], "rel": edge["rel"]}
                        entries = reverse.setdefault(edge["target"], [])
                        if entry not in entries:
                            entries.append(entry)
            self._atomic(
                self.path("apps/crm/data/_index/relations.json"), {"reverse": reverse}
            )
            return {"success": True, "entries": sum(map(len, reverse.values()))}

    def add_field(
        self,
        entity_type,
        field_name,
        field_type,
        default,
        description="",
        required=True,
    ):
        if (
            entity_type not in ENTITIES
            or not re.fullmatch(r"[a-z][a-z0-9_]*", field_name)
            or field_name in BASE_FIELDS
        ):
            return {"error": "Unknown entity or invalid/reserved field name"}
        if field_type not in {
            "string",
            "integer",
            "number",
            "boolean",
            "array",
            "object",
        }:
            return {"error": "Unsupported field type"}
        if not isinstance(required, bool) or not isinstance(description, str):
            return {"error": "Invalid field metadata"}
        definition = {"type": field_type, "default": default}
        if not Draft202012Validator(definition).is_valid(default):
            return {"error": "Default does not match field type"}
        with self.lock:
            if field_name in self.schemas[entity_type]["properties"]:
                return {"error": "Field already exists"}
            fields = deepcopy(self._read_extensions(entity_type))
            fields[field_name] = {
                **definition,
                "required": required,
                **({"description": description} if description else {}),
            }
            path = self.path(f"apps/crm/schemas/{entity_type}.schema.json")
            self._atomic(path, {"version": 1, "fields": fields})
            mark_changed()
            self.schemas[entity_type] = self._load_schema(entity_type)
            return {
                "success": True,
                "entity_type": entity_type,
                "field": {"name": field_name, **definition, "required": required},
            }
