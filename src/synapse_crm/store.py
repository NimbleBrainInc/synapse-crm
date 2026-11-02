"""CRM records in the existing workspace JSON format."""

import json
import operator
import os
import re
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Any

from jsonschema import Draft202012Validator
from ulid import ULID

ENTITIES = {
    "contact": ("contacts", "ct"),
    "deal": ("deals", "dl"),
    "interaction": ("interactions", "ix"),
}
_IMMUTABLE = {"id", "type", "version", "created_at", "created_by"}
# Fields the base record schema manages; tool inputs and add_field never take them.
BASE_FIELDS = frozenset(
    {
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
)
_FIELD_TYPES: dict[str, type | tuple[type, ...]] = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "array": list,
    "object": dict,
}
_BASE_SCHEMA_REF = "https://upjack.dev/schemas/v1/upjack-entity.schema.json"
_INDEX = "apps/crm/data/_index/relations.json"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


_COMPARE = {
    "$gt": operator.gt,
    "$gte": operator.ge,
    "$lt": operator.lt,
    "$lte": operator.le,
}


def _matches(entity: dict[str, Any], filters: dict[str, Any] | None) -> bool:
    for field, expected in (filters or {}).items():
        value = entity.get(field)
        if not isinstance(expected, dict):
            if value != expected:
                return False
            continue
        for op, operand in expected.items():
            if op == "$exists":
                okay = (field in entity and value is not None) == operand
            elif op == "$ne":
                okay = value != operand
            elif op == "$in":
                okay = value in operand
            elif op == "$contains":
                okay = isinstance(value, list) and operand in value
            elif op in _COMPARE:
                try:
                    okay = value is not None and _COMPARE[op](value, operand)
                except TypeError:
                    okay = False
            else:
                raise ValueError(f"Unsupported filter operator: {op}")
            if not okay:
                return False
    return True


def _load_base(schemas: Path) -> dict[str, Any]:
    base = json.loads((schemas / "entity.schema.json").read_text())
    base.pop("$schema", None)
    return base


def _load_schema(schemas: Path, kind: str, base: dict[str, Any]) -> dict[str, Any]:
    schema = json.loads((schemas / f"{kind}.schema.json").read_text())
    # Swap the local base record schema in for the remote $ref only.
    schema["allOf"] = [
        base
        if isinstance(part, dict) and part.get("$ref") == _BASE_SCHEMA_REF
        else part
        for part in schema.get("allOf", [])
    ]
    return schema


class CRMStore:
    """CRM records stored as one JSON file each under the workspace root."""

    def __init__(self, root: str | Path, project_root: str | Path) -> None:
        """Load the entity schemas.

        Args:
            root: Workspace root that holds ``apps/crm/data``.
            project_root: Repository root that holds ``schemas``.
        """
        self.root = Path(root).resolve()
        self._lock = RLock()
        self._schema_dir = Path(project_root).resolve() / "schemas"
        self._base = _load_base(self._schema_dir)
        self._schemas = {
            kind: _load_schema(self._schema_dir, kind, self._base) for kind in ENTITIES
        }

    def schema(self, kind: str) -> dict[str, Any]:
        """The entity schema for ``kind`` with the base record schema inlined.

        Args:
            kind: One of contact, deal or interaction.

        Returns:
            A copy of the schema the store validates records of this kind against.
        """
        return deepcopy(self._schemas[kind])

    def base_schema(self) -> dict[str, Any]:
        """The base record schema as :meth:`schema` inlines it under ``allOf``."""
        return deepcopy(self._base)

    def _path(self, relative: str) -> Path:
        path = self.root / relative
        if not path.resolve().is_relative_to(self.root):
            raise ValueError("Path escapes workspace root")
        return path

    def _entity_path(self, kind: str, entity_id: Any) -> Path:
        plural, prefix = ENTITIES[kind]
        if not isinstance(entity_id, str) or not re.fullmatch(
            prefix + r"_[0-9A-HJKMNP-TV-Z]{26}", entity_id
        ):
            raise ValueError(f"Invalid {kind} ID")
        try:
            # The pattern admits suffixes past 128 bits; the parser rejects them.
            ULID.from_str(entity_id[len(prefix) + 1 :])
        except ValueError:
            raise ValueError(f"Invalid {kind} ID") from None
        return self._path(f"apps/crm/data/{plural}/{entity_id}.json")

    @staticmethod
    def _atomic(path: Path, value: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{ULID()}.tmp")
        # 0o666 lets the umask set a new file's mode, as a plain write does.
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
        try:
            with os.fdopen(fd, "w") as stream:
                if path.exists():
                    os.fchmod(stream.fileno(), path.stat().st_mode & 0o7777)
                json.dump(value, stream, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def rebuild_index(self) -> dict[str, Any]:
        """Rewrite the reverse relationship index from every record file.

        The index is the derived file Upjack kept at ``_index/relations.json``;
        the records' own ``relationships`` arrays stay the source of truth and
        every relationship query here reads those directly.

        Returns:
            ``{"success": True, "entries": n}`` with the number of index entries.
        """
        with self._lock:
            reverse: dict[str, list[dict[str, str]]] = {}
            for kind in ENTITIES:
                for record in self._all(kind):
                    for link in record.get("relationships", []):
                        if not link.get("target") or not link.get("rel"):
                            continue
                        entry = {"source": record.get("id", ""), "rel": link["rel"]}
                        sources = reverse.setdefault(link["target"], [])
                        if entry not in sources:
                            sources.append(entry)
            self._atomic(self._path(_INDEX), {"reverse": reverse})
            return {"success": True, "entries": sum(map(len, reverse.values()))}

    def _save(
        self,
        kind: str,
        record: dict[str, Any],
        edges_changed: bool = True,
        validate: bool = True,
    ) -> dict[str, Any]:
        if validate:
            Draft202012Validator(self._schemas[kind]).validate(record)
        self._atomic(self._entity_path(kind, record["id"]), record)
        if edges_changed:
            self.rebuild_index()
        return deepcopy(record)

    def _hydrate(self, kind: str, record: dict[str, Any]) -> dict[str, Any]:
        record = deepcopy(record)
        for schema in [*self._schemas[kind].get("allOf", []), self._schemas[kind]]:
            for field, definition in schema.get("properties", {}).items():
                if field not in record and "default" in definition:
                    record[field] = deepcopy(definition["default"])
        return record

    def _all(self, kind: str) -> list[dict[str, Any]]:
        directory = self._path(f"apps/crm/data/{ENTITIES[kind][0]}")
        records = []
        for path in sorted(directory.glob("*.json")):
            try:
                records.append(self.get_entity(kind, path.stem))
            except (ValueError, FileNotFoundError):
                # Bad JSON, a name that is not an ID, or a file removed since the glob.
                continue
        return records

    def create_entity(
        self, kind: str, data: dict[str, Any], created_by: str = "agent"
    ) -> dict[str, Any]:
        """Validate and write a new record.

        Args:
            kind: One of contact, deal or interaction.
            data: Record fields. A supplied ``id`` must be a valid ID for the kind.
            created_by: Stored as ``created_by``.

        Returns:
            The saved record.
        """
        with self._lock:
            data = deepcopy(data)
            entity_id = (
                data.pop("id") if "id" in data else f"{ENTITIES[kind][1]}_{ULID()}"
            )
            path = self._entity_path(kind, entity_id)
            if path.exists():
                raise ValueError(f"Entity already exists: {entity_id}")
            stamp = _now_iso()
            record = {
                "version": 1,
                "created_at": stamp,
                "updated_at": stamp,
                "created_by": created_by,
                "status": "active",
                "tags": [],
                "relationships": [],
                **data,
                "id": entity_id,
                "type": kind,
            }
            return self._save(
                kind, self._hydrate(kind, record), bool(record.get("relationships"))
            )

    def get_entity(self, kind: str, entity_id: str) -> dict[str, Any]:
        """Read one record, with schema defaults filled in memory only.

        Args:
            kind: One of contact, deal or interaction.
            entity_id: The record ID.

        Returns:
            The record.

        Raises:
            FileNotFoundError: No record has this ID. The message names the ID
                only, never the workspace path, since it reaches tool callers.
        """
        with self._lock:
            path = self._entity_path(kind, entity_id)
            try:
                raw = path.read_text()
            except FileNotFoundError:
                raise FileNotFoundError(f"Entity not found: {entity_id}") from None
            return self._hydrate(kind, json.loads(raw))

    def update_entity(
        self, kind: str, entity_id: str, data: dict[str, Any]
    ) -> dict[str, Any]:
        """Merge fields into a record and validate the whole record before writing.

        Args:
            kind: One of contact, deal or interaction.
            entity_id: The record ID.
            data: Fields to set. Immutable fields are ignored.

        Returns:
            The saved record.
        """
        with self._lock:
            record = self.get_entity(kind, entity_id)
            edges = record.get("relationships")
            record.update({k: v for k, v in data.items() if k not in _IMMUTABLE})
            record["updated_at"] = _now_iso()
            return self._save(kind, record, edges != record.get("relationships"))

    def list_entities(
        self, kind: str, status: str = "active", limit: int | None = None
    ) -> list[dict[str, Any]]:
        """List records with one status, most recently updated first.

        Args:
            kind: One of contact, deal or interaction.
            status: Status to match.
            limit: Maximum number of records, or None for all.

        Returns:
            The matching records.
        """
        records = [
            record
            for record in self._all(kind)
            if record.get("status", "active") == status
        ]
        ordered = sorted(
            records, key=lambda record: record.get("updated_at", ""), reverse=True
        )
        return ordered if limit is None else ordered[: max(0, limit)]

    def delete_entity(
        self, kind: str, entity_id: str, hard: bool = False
    ) -> dict[str, Any]:
        """Set a record's status to deleted, or remove its file when ``hard``.

        A soft delete skips schema validation, as Upjack did, so a record a
        hand edit left invalid can still be marked deleted.

        Args:
            kind: One of contact, deal or interaction.
            entity_id: The record ID.
            hard: Remove the file instead of marking the record deleted.

        Returns:
            The record as saved, or as it was before a hard delete.
        """
        with self._lock:
            record = self.get_entity(kind, entity_id)
            if hard:
                self._entity_path(kind, entity_id).unlink()
                if record.get("relationships"):
                    self.rebuild_index()
                return record
            record["status"] = "deleted"
            record["updated_at"] = _now_iso()
            return self._save(kind, record, edges_changed=False, validate=False)

    def search_entities(
        self,
        kind: str,
        query: str | None = None,
        filter: dict[str, Any] | None = None,
        sort: str = "-updated_at",
        limit: int | None = 20,
    ) -> list[dict[str, Any]]:
        """Search records by text and field filters.

        Args:
            kind: One of contact, deal or interaction.
            query: Case-insensitive text matched against string fields.
            filter: Field values or operators such as ``{"value": {"$gte": 50}}``.
                Deleted records are left out unless the filter names ``status``.
            sort: Field to sort by, with a leading ``-`` for descending.
            limit: Maximum number of records, or None for all.

        Returns:
            The matching records.
        """
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
            and _matches(record, filter)
        ]
        field = sort.lstrip("-")

        def sort_key(record: dict[str, Any]) -> tuple[bool, bool, Any]:
            value = record.get(field)
            return (
                value is not None,
                isinstance(value, str),
                value if value is not None else "",
            )

        ordered = sorted(records, key=sort_key, reverse=sort.startswith("-"))
        return ordered if limit is None else ordered[: max(0, limit)]

    def query_by_relationship(
        self,
        kind: str,
        rel: str,
        target_id: str,
        filter: dict[str, Any] | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """List active records of one kind with a ``rel`` edge to ``target_id``.

        Args:
            kind: One of contact, deal or interaction.
            rel: Relationship name the edge must carry.
            target_id: ID the edge must point at.
            filter: Field values or operators, as in :meth:`search_entities`.
            limit: Maximum number of records, or None for all.

        Returns:
            The matching records, in file name order.
        """
        records = [
            record
            for record in self._all(kind)
            if record.get("status", "active") == "active"
            and _matches(record, filter)
            and any(
                edge.get("rel") == rel and edge.get("target") == target_id
                for edge in record.get("relationships", [])
            )
        ]
        return records if limit is None else records[: max(0, limit)]

    def _kind(self, entity_id: str) -> str:
        for kind, (_, prefix) in ENTITIES.items():
            if isinstance(entity_id, str) and entity_id.startswith(prefix + "_"):
                return kind
        raise ValueError("Unknown entity ID prefix")

    def _resolve(self, entity_id: Any) -> dict[str, Any] | None:
        try:
            return self.get_entity(self._kind(entity_id), entity_id)
        except (FileNotFoundError, ValueError):
            return None

    def get_related(
        self, entity_id: str, rel: str | None = None, direction: str = "forward"
    ) -> list[dict[str, Any]]:
        """Follow a record's edges, or find the records whose edges point at it.

        Args:
            entity_id: The record to start from; its kind comes from the ID prefix.
            rel: Only follow edges with this relationship name, or None for all.
            direction: ``forward`` reads the record's own edges; ``reverse``
                finds every record with an edge pointing at ``entity_id``.

        Returns:
            The related records. A dangling edge is skipped.
        """
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
            raise ValueError("direction must be 'forward' or 'reverse'")
        source = self.get_entity(self._kind(entity_id), entity_id)
        found = [
            self._resolve(edge.get("target"))
            for edge in source.get("relationships", [])
            if rel is None or edge.get("rel") == rel
        ]
        return [record for record in found if record]

    def get_composite(
        self, kind: str, entity_id: str, depth: int = 1
    ) -> dict[str, Any]:
        """Read a record with its related records under ``_related``.

        Args:
            kind: One of contact, deal or interaction.
            entity_id: The record ID.
            depth: Hops to follow; only 0 (none) and 1 (direct) are distinguished.

        Returns:
            The record plus ``_related``: forward edges keyed by relationship
            name, reverse edges keyed by ``~`` and the relationship name.
        """
        entity = self.get_entity(kind, entity_id)
        related: dict[str, list[dict[str, Any]]] = {}
        if depth < 1:
            return {**entity, "_related": related}
        for edge in entity.get("relationships", []):
            found = self._resolve(edge.get("target"))
            if edge.get("rel") and found:
                related.setdefault(edge["rel"], []).append(found)
        for source in self.get_related(entity_id, direction="reverse"):
            for edge in source.get("relationships", []):
                if edge.get("target") == entity_id and edge.get("rel"):
                    related.setdefault("~" + edge["rel"], []).append(source)
        return {**entity, "_related": related}

    def add_field(
        self,
        kind: str,
        field_name: str,
        field_type: str,
        default: Any,
        description: str = "",
        required: bool = True,
    ) -> dict[str, Any]:
        """Add a field to an entity schema on disk and start validating with it.

        Args:
            kind: One of contact, deal or interaction.
            field_name: Lowercase identifier, ``[a-z][a-z0-9_]*``.
            field_type: One of string, integer, number, boolean, array, object.
            default: Value records without the field take; must fit ``field_type``.
            description: Stored on the field.
            required: Also list the field under the schema's ``required``.

        Returns:
            ``{"success": True, "entity_type": kind, "field": {...}}``, or
            ``{"error": ...}`` when the change is refused and nothing is written.
        """
        if not re.fullmatch(r"[a-z][a-z0-9_]*", field_name):
            return {
                "error": f"Invalid field_name '{field_name}'. Must match [a-z][a-z0-9_]*"
            }
        if field_name in BASE_FIELDS:
            return {"error": f"Field '{field_name}' is a reserved base entity field"}
        if field_type not in _FIELD_TYPES:
            return {
                "error": f"Invalid field_type '{field_type}'. Allowed: {sorted(_FIELD_TYPES)}"
            }
        # bool is an int subclass, so a True default is checked by name.
        fits = isinstance(default, _FIELD_TYPES[field_type]) and (
            field_type == "boolean" or not isinstance(default, bool)
        )
        if not fits:
            return {
                "error": f"Default value {default!r} is not compatible with type '{field_type}'"
            }
        if kind not in ENTITIES:
            return {"error": f"Unknown entity type '{kind}'"}
        with self._lock:
            path = self._schema_dir / f"{kind}.schema.json"
            schema = json.loads(path.read_text())
            properties = schema.setdefault("properties", {})
            if field_name in properties:
                existing = properties[field_name].get("type")
                if existing and existing != field_type:
                    return {
                        "error": f"Field '{field_name}' already exists with type '{existing}'"
                    }
                return {"error": f"Field '{field_name}' already exists"}
            definition: dict[str, Any] = {"type": field_type, "default": default}
            if description:
                definition["description"] = description
            properties[field_name] = definition
            if required and field_name not in schema.setdefault("required", []):
                schema["required"].append(field_name)
            # Every schema loads at startup, so a torn write here would stop the server.
            self._atomic(path, schema)
            self._schemas[kind] = _load_schema(self._schema_dir, kind, self._base)
        return {
            "success": True,
            "entity_type": kind,
            "field": {
                "name": field_name,
                "type": field_type,
                "default": default,
                "required": required,
            },
        }
