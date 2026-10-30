# CRM

[![mpak](https://img.shields.io/badge/mpak-registry-blue)](https://mpak.dev/packages/@nimblebraininc/synapse-crm?utm_source=github&utm_medium=readme&utm_campaign=synapse-crm)
[![NimbleBrain](https://img.shields.io/badge/NimbleBrain-nimblebrain.ai-purple)](https://nimblebrain.ai?utm_source=github&utm_medium=readme&utm_campaign=synapse-crm)
[![Discord](https://img.shields.io/badge/Discord-community-5865F2)](https://nimblebrain.ai/discord?utm_source=github&utm_medium=readme&utm_campaign=synapse-crm)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Contacts, deals and interaction history inside NimbleBrain. FastMCP serves the tools and HTTP endpoint; the Synapse UI uses those same tools. Records stay in the selected workspace as JSON files.

**[View on mpak registry](https://mpak.dev/packages/@nimblebraininc/synapse-crm?utm_source=github&utm_medium=readme&utm_campaign=synapse-crm)** | **Built by [NimbleBrain](https://nimblebrain.ai?utm_source=github&utm_medium=readme&utm_campaign=synapse-crm)**

## Run

Requires Python 3.13+, uv, Node.js and npm.

```bash
uv sync --frozen
cd ui
npm ci --ignore-scripts
npm run build
cd ..
MPAK_WORKSPACE=/absolute/path/to/workspace uv run uvicorn synapse_crm.server:app --host 127.0.0.1 --port 8001
```

Connect an MCP client to `http://127.0.0.1:8001/mcp`. The HTTP server is for local or otherwise protected deployments; deployment authentication belongs to the host. `python -m synapse_crm.server` remains the stdio entry point for MCP bundle clients.

`MPAK_WORKSPACE` selects the workspace; the legacy `UPJACK_ROOT` variable is a fallback. Without either, storage is under `./workspace`. The process working directory therefore matters when no absolute workspace is configured.

`CRM_UI_DIR` can select the directory containing the built `index.html` when the UI is deployed separately from the Python source. The default is the checkout's `ui/dist` or the installed wheel's packaged UI directory. The HTML is static; account and workspace data are fetched through the MCP bridge.

Wheel builds include schemas, skills, seed data and context. Build the UI before creating a release wheel to include its HTML too. Editable bootstrap still works before the UI build; it reads assets from the checkout. Installed wheels resolve their packaged assets without depending on the original source directory.

## Entity Types

| Entity | Prefix | Schema | Notes |
|--------|--------|--------|-------|
| Contact | `ct_` | [contact.schema.json](schemas/contact.schema.json) | People — the hub entity. Deals and interactions link here. |
| Deal | `dl_` | [deal.schema.json](schemas/deal.schema.json) | Sales opportunities with stage, value, and close date. |
| Interaction | `ix_` | [interaction.schema.json](schemas/interaction.schema.json) | Activity log: meetings, emails, calls, notes. |

## Custom Tools

| Tool | Purpose |
|------|---------|
| `move_deal_stage` | Advance/regress a deal with auto close-date and probability |
| `log_interaction` | Create an interaction with auto-wired contact relationship |
| `pipeline_summary` | Aggregate metrics by stage: count, value, win rate |
| `contact_timeline` | Full interaction history for a contact (newest first) |
| `find_or_create_contact` | Resolve one active contact by exact normalized email, or name when no email is supplied; ambiguous matches leave records unchanged |
| `link_deals_to_contacts` | Backfill a deal's contact relationship only when its normalized contact name identifies one active contact |

Each entity also has get, update, list, search, delete and relationship tools. Deals and interactions expose create tools. `create_contact` remains callable for older clients but is hidden from tool discovery; agents should use `find_or_create_contact`.

`add_field` saves schema extensions inside the workspace. `rebuild_index` regenerates the derived relationship index. `seed_data` loads the bundled examples; examples without stable IDs create new records when loaded again. It does not overwrite records with existing IDs.

List and relationship-query tools retain their existing limits; `limit: null` requests the full collection. The UI requests complete contact and deal lists. Reads are quiet; committed record or schema changes announce `notifications/resources/list_changed`, which Synapse uses to refresh open views.

## Skills

### [Follow-Up Coach](skills/follow-up-coach/SKILL.md)

Guides an agent through setting the next step after an interaction or deal stage change. Read `skill://follow-up-coach/usage`; the legacy `upjack://skills/follow-up-coach` remains available.

### [Pipeline Reviewer](skills/pipeline-reviewer/SKILL.md)

Guides a requested pipeline health review: stale deals, overdue follow-ups and past-due close dates. Read `skill://pipeline-reviewer/usage`; the legacy `upjack://skills/pipeline-reviewer` remains available. These skills are guidance; this server does not install an automatic schedule or event-hook runner.

## Workspace compatibility

Existing records remain in `apps/crm/data/{contacts,deals,interactions}`. IDs, timestamps, unknown fields and relationships survive the migration. Reads hydrate schema defaults in memory without rewriting files. Updates validate the complete record before atomic replacement. Soft deletion is the default; explicit `hard: true` retains the existing permanent-delete behavior.

Schema extensions live under `apps/crm/schemas/`, so `add_field` does not edit the installed source. If an earlier installation modified its source schemas, export those definitions before replacing it; record contents alone cannot recover field types or defaults. See [storage and migration](docs/storage.md).

The `upjack://` resource URIs remain for existing clients. The application no longer imports or runs Upjack.

## Verify and contribute

```bash
uv run pytest tests/
uv run ruff check src/
uv run ty check src/
cd ui && npm run build
```

`tests/transport_workflow.py` exercises a disposable loopback HTTP server, stdio, restart persistence and write notifications. Run it with the same project Python environment. It uses synthetic data and terminates its own server.

After building the UI, `uv build --wheel` creates the release wheel. Run `python tests/wheel_workflow.py <wheel-file>` in the project environment to check its packaged skills, static UI and workspace tools without installing it or reading checkout assets.

Read [AGENTS.md](AGENTS.md) for the source map and contribution boundaries. Tool and schema changes belong here; installers should consume an accepted revision or package and manage only preparation, configuration, processes and rollback.
