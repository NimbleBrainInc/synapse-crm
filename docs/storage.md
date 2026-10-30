# Storage and migration

The workspace is selected by `MPAK_WORKSPACE`, then the legacy `UPJACK_ROOT`, then `./workspace`. Configure an absolute path for managed processes. Changing the working directory must not silently select another person's workspace.

| Data | Relative path |
| --- | --- |
| Contacts | `apps/crm/data/contacts/<ct_id>.json` |
| Deals | `apps/crm/data/deals/<dl_id>.json` |
| Interactions | `apps/crm/data/interactions/<ix_id>.json` |
| Derived relationship index | `apps/crm/data/_index/relations.json` |
| Schema extensions | `apps/crm/schemas/<entity>.schema.json` |

Record paths validate their entity prefixes and ULIDs and remain inside the workspace. The native store reads existing JSON records directly. Default hydration is an in-memory operation; reading an older record does not change its bytes. Updates preserve unknown fields and immutable identity/creation fields, validate the merged record and atomically replace its file.

Run one writable CRM process per workspace. Atomic file replacement prevents partial JSON files; it does not coordinate separate processes racing to update the same record. A managed deployment needs the same single-writer arrangement or a separately designed storage adapter.

The relationship index is derived. Writes discard a stale legacy index before changing a record; `rebuild_index` recreates it from the authoritative JSON files. Existing readers can rebuild the same index. Reverse relationships can return another CRM entity type, so the MCP result schema permits heterogeneous records.

`add_field` writes a versioned extension document with the field name, type, default, required flag and optional description. Restarting reloads it. Existing records acquire defaults when read and retain them when next updated. The installed app schemas remain unchanged.

An older `add_field` could modify source files. Preserve that old source tree and back up the workspace before upgrading. Stop writers while applying the app's operator migration helper:

```bash
python -m synapse_crm.migration --legacy-source /old/app/source --workspace /absolute/workspace
python -m synapse_crm.migration --legacy-source /old/app/source --workspace /absolute/workspace --apply --expected-plan-hash <reviewed-plan-hash>
```

The first command reads and validates all schemas without changing files. The plan binds the source schemas, receiving workspace, existing extension bytes and proposed changes. Apply refuses a changed plan. Supported additions need a type and valid default; edits to existing constraints, unsupported definitions and conflicts are rejected before writing. Both original references and the exact base schema written by the previous `add_field` tool are supported.

Records remain untouched; source definitions are not rewritten. Each extension file is replaced atomically, but an I/O failure after an earlier file changed can require restoring the operator's backup. Keep that backup until representative records have been read and updated successfully. The helper does not locate other installations, infer field definitions from record values or stop running processes.

The server retains the legacy context/skill resource URIs and the hidden-but-callable `create_contact` tool. The standard contact-creation tool resolves an exact normalized email, or an exact normalized name when no email was given. More than one active match is an error without writes; a name-only match never merges a different supplied email.

Soft deletion sets `status: deleted`. Explicit `hard: true` permanently removes the validated record, as in the original app.
