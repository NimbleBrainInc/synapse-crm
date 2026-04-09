"""Retrieve all interactions for a contact in reverse chronological order."""

from typing import Any

from upjack.app import UpjackApp


def contact_timeline(
    app: UpjackApp,
    contact_id: str,
) -> dict[str, Any]:
    """Get the full interaction history for a contact.

    Args:
        app: UpjackApp instance.
        contact_id: ID of the contact.

    Returns:
        Context dict with contact info, interactions list (newest first),
        and next_step. Returns {"error": "..."} on failure.
    """
    # Validate contact exists
    try:
        contact = app.get_entity("contact", contact_id)
    except FileNotFoundError:
        return {"error": f"Contact {contact_id} not found"}

    # Query interactions linked to this contact via relationship index
    interactions = app.query_by_relationship("interaction", "belongs_to", contact_id, limit=100)

    # Sort by occurred_at descending (newest first)
    interactions.sort(
        key=lambda ix: ix.get("occurred_at", ""),
        reverse=True,
    )

    # Build timeline entries
    timeline = []
    for ix in interactions:
        entry = {
            "id": ix["id"],
            "type": ix.get("interaction_type"),
            "summary": ix.get("summary"),
            "occurred_at": ix.get("occurred_at"),
            "follow_up_date": ix.get("follow_up_date"),
        }
        if ix.get("details"):
            entry["details"] = ix["details"]
        timeline.append(entry)

    # Build next_step
    if not timeline:
        next_step = f"No interactions logged for {contact.get('name')}. Consider reaching out."
    else:
        latest = timeline[0]
        next_step = (
            f"Last interaction: {latest['type']} on {latest.get('occurred_at', 'unknown date')} "
            f"— \"{latest.get('summary', '')}\""
        )

    return {
        "contact": {
            "id": contact["id"],
            "name": contact.get("name"),
            "company": contact.get("company"),
            "email": contact.get("email"),
        },
        "interactions": timeline,
        "total": len(timeline),
        "next_step": next_step,
    }
