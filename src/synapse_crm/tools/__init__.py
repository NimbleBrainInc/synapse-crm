"""Custom domain tools for the CRM app.

Exports register_tools() which binds all tool functions to the MCP server.
"""

from synapse_crm.tools.contact_timeline import contact_timeline
from synapse_crm.tools.find_or_create_contact import find_or_create_contact
from synapse_crm.tools.link_deals_to_contacts import link_deals_to_contacts
from synapse_crm.tools.log_interaction import log_interaction
from synapse_crm.tools.move_deal_stage import move_deal_stage
from synapse_crm.tools.pipeline_summary import pipeline_summary

__all__ = ["register_tools"]


def register_tools(mcp, app):
    """Register all custom tools on the MCP server.

    Args:
        mcp: FastMCP server instance.
        app: UpjackApp instance for entity access.
    """

    @mcp.tool(
        name="move_deal_stage",
        description=(
            "Move a deal to a new pipeline stage. Validates the stage is one of: "
            "lead, qualified, proposal, negotiation, closed_won, closed_lost. "
            "Automatically sets close_date to today when moving to closed_won or "
            "closed_lost (if not already set). Use this instead of update_deal "
            "for stage changes."
        ),
    )
    def _move_deal_stage(
        deal_id: str,
        stage: str,
    ) -> dict:
        return move_deal_stage(app, deal_id, stage)

    @mcp.tool(
        name="log_interaction",
        description=(
            "Log an interaction (meeting, email, call, note) for a contact. "
            "Automatically links the interaction to the contact via a belongs_to "
            "relationship and denormalizes the contact name. Use this instead of "
            "create_interaction directly."
        ),
    )
    def _log_interaction(
        contact_id: str,
        interaction_type: str,
        summary: str,
        details: str = "",
        follow_up_date: str = "",
    ) -> dict:
        return log_interaction(app, contact_id, interaction_type, summary, details, follow_up_date)

    @mcp.tool(
        name="pipeline_summary",
        description=(
            "Get an aggregate view of the sales pipeline: deal count, total value, "
            "and average probability grouped by stage. Also shows weighted pipeline "
            "value and overall win rate. Read-only, no side effects."
        ),
    )
    def _pipeline_summary() -> dict:
        return pipeline_summary(app)

    @mcp.tool(
        name="find_or_create_contact",
        description=(
            "ALWAYS use this instead of create_contact. Searches for an existing "
            "contact by email (exact) or name (fuzzy) and returns it, updating any "
            "new fields. Only creates a new contact if no match is found. Prevents "
            "duplicates."
        ),
    )
    def _find_or_create_contact(
        name: str,
        email: str = "",
        phone: str = "",
        company: str = "",
        role: str = "",
        lead_source: str = "",
        notes: str = "",
    ) -> dict:
        return find_or_create_contact(app, name, email, phone, company, role, lead_source, notes)

    @mcp.tool(
        name="link_deals_to_contacts",
        description=(
            "Wire deals to contacts by matching the deal's contact_name field "
            "to existing contacts. Run this after seed_data to establish "
            "belongs_to relationships. Safe to run multiple times — skips "
            "deals that are already linked."
        ),
    )
    def _link_deals_to_contacts() -> dict:
        return link_deals_to_contacts(app)

    @mcp.tool(
        name="contact_timeline",
        description=(
            "Get all interactions for a contact in reverse chronological order. "
            "Shows the full history of meetings, emails, calls, and notes. "
            "Use this to review relationship history before outreach."
        ),
    )
    def _contact_timeline(contact_id: str) -> dict:
        return contact_timeline(app, contact_id)
