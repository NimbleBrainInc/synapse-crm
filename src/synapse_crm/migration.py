"""Move supported legacy source-schema additions into the CRM workspace.

This is an operator command, not an MCP tool. Stop the app and retain a workspace
backup before applying. Validation finishes before any file is changed; rollback
after an I/O failure remains the operator's responsibility.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import sys

from jsonschema import Draft202012Validator

from synapse_crm.assets import asset_root
from synapse_crm.store import BASE_FIELDS, CRMStore, ENTITIES


def _document(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _safe_path(root: Path, relative: str) -> Path:
    path = root / relative
    current = root
    for part in Path(relative).parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("Schema migration does not follow symlinks")
    if not path.resolve().is_relative_to(root):
        raise ValueError("Schema path escapes its root")
    return path


def _field(name: str, definition: object, required: bool) -> dict:
    if not re.fullmatch(r"[a-z][a-z0-9_]*", name) or name in BASE_FIELDS:
        raise ValueError("Legacy schema has an invalid or reserved field")
    if not isinstance(definition, dict) or set(definition) - {
        "type",
        "default",
        "description",
    }:
        raise ValueError("Legacy schema has unsupported field metadata")
    kind = definition.get("type")
    if kind not in {"string", "integer", "number", "boolean", "array", "object"}:
        raise ValueError("Legacy schema has an unsupported field type")
    if "default" not in definition or not Draft202012Validator({"type": kind}).is_valid(
        definition["default"]
    ):
        raise ValueError("Legacy schema field needs a valid default")
    if "description" in definition and not isinstance(definition["description"], str):
        raise ValueError("Legacy schema field description must be text")
    return {**deepcopy(definition), "required": required}


def plan_migration(
    legacy_source: Path, workspace: Path, project_root: Path | None = None
) -> dict:
    """Read and validate all entity schemas and all receiving overrides."""
    if legacy_source.is_symlink() or workspace.is_symlink():
        raise ValueError("Schema migration does not follow root symlinks")
    source, root = legacy_source.resolve(), workspace.resolve()
    if not source.is_dir() or not root.is_dir():
        raise ValueError("Choose existing source and workspace directories")
    project = project_root or asset_root()
    store = CRMStore(root, project)  # Also validates existing workspace extensions.
    sources, previous, updates = {}, {}, {}
    for entity in ENTITIES:
        relative = f"schemas/{entity}.schema.json"
        raw = _safe_path(source, relative).read_bytes()
        legacy = json.loads(raw)
        base = json.loads((project / relative).read_text())
        if not isinstance(legacy, dict) or not isinstance(
            legacy.get("properties"), dict
        ):
            raise ValueError("Legacy schema is not an entity schema")
        extra = set(legacy["properties"]) - set(base["properties"])
        required = legacy.get("required", [])
        if not isinstance(required, list) or any(
            not isinstance(name, str) for name in required
        ):
            raise ValueError("Legacy schema required fields are invalid")
        # The base reference became local when Upjack was removed. No other
        # existing property, constraint, or required field may be changed.
        normalized = deepcopy(legacy)
        base_value = normalized.get("allOf")
        inline_hash = hashlib.sha256(
            json.dumps(base_value, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        # Upjack 0.5.1's actual add_field writes this exact inlined base.
        # An altered base constraint must not be normalized away.
        supported_inline = (
            inline_hash
            == "ebb00234427150b70678b4f85f7812218e085d529d91aa9711672429824bd464"
        )
        if (
            base_value
            not in [
                base.get("allOf"),
                [{"$ref": "https://upjack.dev/schemas/v1/upjack-entity.schema.json"}],
            ]
            and not supported_inline
        ):
            raise ValueError("Legacy schema has an unsupported base reference")
        normalized["allOf"] = base.get("allOf")
        normalized["properties"] = {
            key: value
            for key, value in legacy["properties"].items()
            if key not in extra
        }
        normalized["required"] = [name for name in required if name not in extra]
        expected = {**base, "required": base.get("required", [])}
        if normalized != expected:
            raise ValueError("Legacy schema changes existing fields or constraints")

        target_relative = f"apps/crm/schemas/{entity}.schema.json"
        target = _safe_path(root, target_relative)
        old = target.read_bytes() if target.exists() else None
        fields = deepcopy(store._read_extensions(entity))
        for name in sorted(extra):
            value = _field(name, legacy["properties"][name], name in required)
            if name in fields and fields[name] != value:
                raise ValueError(
                    "Legacy field conflicts with an existing workspace field"
                )
            fields[name] = value
        sources[relative] = hashlib.sha256(raw).hexdigest()
        previous[target_relative] = (
            hashlib.sha256(old).hexdigest() if old is not None else None
        )
        if fields != store._read_extensions(entity):
            updates[target_relative] = {"version": 1, "fields": fields}

    plan = {
        "version": 1,
        "legacySource": str(source),
        "workspace": str(root),
        "sourceSchemas": sources,
        "previous": previous,
        "updates": updates,
    }
    return {**plan, "planHash": hashlib.sha256(_document(plan)).hexdigest()}


def apply_migration(
    legacy_source: Path, workspace: Path, expected_plan_hash: str
) -> dict:
    plan = plan_migration(legacy_source, workspace)
    if plan["planHash"] != expected_plan_hash:
        raise ValueError("Schema migration plan changed; review a new plan")
    root = workspace.resolve()
    for relative, value in plan["updates"].items():
        CRMStore._atomic(_safe_path(root, relative), value)
    return {"version": 1, "applied": True, "filesChanged": len(plan["updates"])}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--legacy-source", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-plan-hash")
    args = parser.parse_args()
    if args.apply != bool(args.expected_plan_hash):
        parser.error("--apply and --expected-plan-hash must be supplied together")
    try:
        result = (
            apply_migration(args.legacy_source, args.workspace, args.expected_plan_hash)
            if args.apply
            else plan_migration(args.legacy_source, args.workspace)
        )
    except (OSError, ValueError) as error:
        print(json.dumps({"error": str(error)}), file=sys.stderr)
        return 2
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
