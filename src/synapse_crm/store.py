"""CRM records in the existing workspace JSON format."""

import json
import os
import re
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Any

from jsonschema import Draft202012Validator
from ulid import ULID

_ENTITIES = {
    "contact": ("contacts", "ct"),
    "deal": ("deals", "dl"),
    "interaction": ("interactions", "ix"),
}
_IMMUTABLE = {"id", "type", "version", "created_at", "created_by"}
_BASE_SCHEMA_REF = "https://upjack.dev/schemas/v1/upjack-entity.schema.json"
_INDEX = "apps/crm/data/_index/relations.json"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _matches(entity: dict[str, Any], filters: dict[str, Any] | None) -> bool:
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


def _load_schema(schemas: Path, kind: str) -> dict[str, Any]:
    schema = json.loads((schemas / f"{kind}.schema.json").read_text())
    base = json.loads((schemas / "entity.schema.json").read_text())
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
        schemas = Path(project_root).resolve() / "schemas"
        self._schemas = {kind: _load_schema(schemas, kind) for kind in _ENTITIES}

    def _path(self, relative: str) -> Path:
        path = self.root / relative
        if not path.resolve().is_relative_to(self.root):
            raise ValueError("Path escapes workspace root")
        return path

    def _entity_path(self, kind: str, entity_id: Any) -> Path:
        plural, prefix = _ENTITIES[kind]
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

    def _rebuild_index(self) -> None:
        """Rewrite Upjack's reverse relationship index from every record file."""
        reverse: dict[str, list[dict[str, str]]] = {}
        for kind in _ENTITIES:
            for record in self._all(kind):
                for link in record.get("relationships", []):
                    if not link.get("target") or not link.get("rel"):
                        continue
                    entry = {"source": record.get("id", ""), "rel": link["rel"]}
                    sources = reverse.setdefault(link["target"], [])
                    if entry not in sources:
                        sources.append(entry)
        self._atomic(self._path(_INDEX), {"reverse": reverse})

    def _save(self, kind: str, record: dict[str, Any]) -> dict[str, Any]:
        Draft202012Validator(self._schemas[kind]).validate(record)
        self._atomic(self._entity_path(kind, record["id"]), record)
        self._rebuild_index()
        return deepcopy(record)

    def _hydrate(self, kind: str, record: dict[str, Any]) -> dict[str, Any]:
        record = deepcopy(record)
        for schema in [*self._schemas[kind].get("allOf", []), self._schemas[kind]]:
            for field, definition in schema.get("properties", {}).items():
                if field not in record and "default" in definition:
                    record[field] = deepcopy(definition["default"])
        return record

    def _all(self, kind: str) -> list[dict[str, Any]]:
        directory = self._path(f"apps/crm/data/{_ENTITIES[kind][0]}")
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
                data.pop("id") if "id" in data else f"{_ENTITIES[kind][1]}_{ULID()}"
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
            return self._save(kind, self._hydrate(kind, record))

    def get_entity(self, kind: str, entity_id: str) -> dict[str, Any]:
        """Read one record, with schema defaults filled in memory only.

        Args:
            kind: One of contact, deal or interaction.
            entity_id: The record ID.

        Returns:
            The record.
        """
        with self._lock:
            return self._hydrate(
                kind, json.loads(self._entity_path(kind, entity_id).read_text())
            )

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
            record.update({k: v for k, v in data.items() if k not in _IMMUTABLE})
            record["updated_at"] = _now_iso()
            return self._save(kind, record)

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
                self._rebuild_index()
                return record
            return self.update_entity(kind, entity_id, {"status": "deleted"})

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
