"""Log an interaction for a contact with auto-wired relationship."""

from datetime import UTC, datetime
from typing import Any

from upjack.app import UpjackApp

_VALID_TYPES = ("meeting", "email", "call", "note")


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def log_interaction(
    app: UpjackApp,
    contact_id: str,
    interaction_type: str,
    summary: str,
    details: str = "",
    follow_up_date: str = "",
) -> dict[str, Any]:
    """Create an interaction linked to a contact.

    Args:
        app: UpjackApp instance.
        contact_id: ID of the contact this interaction is for.
        interaction_type: One of: meeting, email, call, note.
        summary: Brief description of the interaction.
        details: Longer notes (optional).
        follow_up_date: ISO date for follow-up (optional).

    Returns:
        The created interaction entity, or an error dict.
    """
    if interaction_type not in _VALID_TYPES:
        return {"error": f"Invalid type '{interaction_type}'. Must be one of: {', '.join(_VALID_TYPES)}"}

    # Validate contact exists
    try:
        contact = app.get_entity("contact", contact_id)
    except FileNotFoundError:
        return {"error": f"Contact {contact_id} not found"}

    data: dict[str, Any] = {
        "interaction_type": interaction_type,
        "summary": summary,
        "occurred_at": _now_iso(),
        "contact_name": contact.get("name", ""),
        "relationships": [{"rel": "belongs_to", "target": contact_id}],
    }

    if details:
        data["details"] = details
    if follow_up_date:
        data["follow_up_date"] = follow_up_date

    interaction = app.create_entity("interaction", data)
    return interaction
