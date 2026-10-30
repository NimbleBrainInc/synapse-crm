# Working on CRM

Read [README.md](README.md) for setup and behavior. Follow this repository's current organization contribution and security policies. Use focused topic branches and PRs; maintainers own releases and upstream acceptance.

State what changed, why and how it was verified in the PR body, naming the tested commit and any checks still unavailable. Independent review covers the current pushed head; review later changes as a delta. Required checks must pass without an admin bypass. Verify the accepted source before claiming it landed.

- `src/synapse_crm/server.py`: FastMCP setup, MCP resources, transport and write notifications.
- `src/synapse_crm/assets.py`: one asset locator for source checkouts and installed wheels.
- `src/synapse_crm/store.py`: workspace paths, JSON record validation, atomic writes, relationships and schema extensions.
- `src/synapse_crm/crud.py`: explicit public CRUD and utility tool contracts.
- `src/synapse_crm/tools/`: contact matching, pipeline and interaction operations.
- `schemas/`: base and entity schemas; `skills/`: agent guidance.
- `ui/src/`: Synapse app; UI actions use the same server tools as agents.
- `tests/`: tool workflows, workspace compatibility and write boundaries.
- [docs/storage.md](docs/storage.md): retained data format and migration details.

Preserve IDs, timestamps, custom fields, tool inputs/results, existing resource URIs and both stdio and HTTP entry points. Test invalid writes against saved bytes. Announce persisted changes, including partial writes before a later error; reads and rejected requests must not trigger refresh loops.

Keep source/package changes in this canonical app. Do not add installer-specific policies, machine paths, credentials or internal company documents. Use synthetic records for tests. A suite, build or MCP smoke test does not by itself prove the app's behavior in a live host.
