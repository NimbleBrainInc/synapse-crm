# CRM — Upjack Demo App

[![mpak](https://img.shields.io/badge/mpak-registry-blue)](https://mpak.dev/packages/@nimblebraininc/synapse-crm?utm_source=github&utm_medium=readme&utm_campaign=synapse-crm)
[![NimbleBrain](https://img.shields.io/badge/NimbleBrain-nimblebrain.ai-purple)](https://nimblebrain.ai?utm_source=github&utm_medium=readme&utm_campaign=synapse-crm)
[![Discord](https://img.shields.io/badge/Discord-community-5865F2)](https://nimblebrain.ai/discord?utm_source=github&utm_medium=readme&utm_campaign=synapse-crm)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Lightweight contact and deal tracker with agent-driven follow-ups and pipeline reviews, built with Upjack.

**[View on mpak registry](https://mpak.dev/packages/@nimblebraininc/synapse-crm?utm_source=github&utm_medium=readme&utm_campaign=synapse-crm)** | **Built by [NimbleBrain](https://nimblebrain.ai?utm_source=github&utm_medium=readme&utm_campaign=synapse-crm)**

## What This Demonstrates

- **3 entity types** with JSON Schema definitions and `allOf` composition
- **4 custom domain tools** for pipeline management and interaction tracking
- **2 bundled skills**: follow-up coaching and daily pipeline review
- **Hooks**: auto-trigger follow-up coach on new interactions and deal stage changes
- **Schedules**: daily weekday pipeline review at 9 AM
- **3 named views**: active pipeline, needs follow-up, recent interactions
- **Seed data** with realistic contacts, deals, and interactions

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

## Skills

### [Follow-Up Coach](skills/follow-up-coach/SKILL.md)

Ensures every interaction has a concrete next step. Auto-sets follow-up dates based on interaction type (meetings: 2 days, calls: 5 days, emails: 3 days). Triggered on `interaction.created` and `deal.updated` (stage change).

### [Pipeline Reviewer](skills/pipeline-reviewer/SKILL.md)

Daily health check of the sales pipeline. Identifies stale deals (no interaction in 14+ days), overdue follow-ups, and past-due close dates. Runs weekdays at 9 AM.

## File Structure

```
crm/
├── manifest.json
├── server.py
├── context.md
├── schemas/
│   ├── contact.schema.json
│   ├── deal.schema.json
│   └── interaction.schema.json
├── skills/
│   ├── follow-up-coach/SKILL.md
│   └── pipeline-reviewer/SKILL.md
├── seed/
│   ├── sample-contacts.json
│   ├── sample-deals.json
│   └── sample-interactions.json
└── tools/
    ├── __init__.py
    ├── move_deal_stage.py
    ├── log_interaction.py
    ├── pipeline_summary.py
    └── contact_timeline.py
```

## Running the Server

```bash
uv pip install upjack[mcp]
python server.py
```
