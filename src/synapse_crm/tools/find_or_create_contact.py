"""Find an existing contact by name/email, or create one if none exists."""

from typing import Any

from synapse_crm.store import CRMStore


def find_or_create_contact(
    app: CRMStore,
    name: str,
    email: str = "",
    phone: str = "",
    company: str = "",
    role: str = "",
    lead_source: str = "",
    notes: str = "",
) -> dict[str, Any]:
    """Find a contact by email or name, or create one if no match exists.

    Search priority:
    1. Exact email match (if email provided)
    2. Exact normalized name match (only without an email)

    If a match is found, updates it with any new non-empty fields.
    If no match, creates a new contact.

    Returns:
        Dict with 'contact' (the entity), 'action' ('found' or 'created'),
        and 'next_step'. Returns {"error": "..."} on failure.
    """
    name, email = name.strip(), email.strip()
    if not name:
        return {"error": "A contact name is required."}
    field, value = ("email", email) if email else ("name", name)
    # The uniqueness check must cover the whole active collection. A limited
    # search page cannot establish that a name or email identifies one person.
    matches = [
        contact
        for contact in app.list_entities("contact", limit=None)
        if (contact.get(field) or "").strip().casefold() == value.casefold()
    ]
    if len(matches) > 1:
        return {
            "error": f"Multiple active contacts match {field} '{value}'. Choose the contact by ID before updating it."
        }
    existing = matches[0] if matches else None

    if existing:
        # Update with any new non-empty fields
        updates: dict[str, Any] = {}
        if email and not existing.get("email"):
            updates["email"] = email
        if phone and not existing.get("phone"):
            updates["phone"] = phone
        if company and not existing.get("company"):
            updates["company"] = company
        if role and not existing.get("role"):
            updates["role"] = role
        if lead_source and not existing.get("lead_source"):
            updates["lead_source"] = lead_source
        if notes:
            old_notes = existing.get("notes", "") or ""
            if notes not in old_notes:
                updates["notes"] = (
                    f"{old_notes}\n{notes}".strip() if old_notes else notes
                )

        if updates:
            existing = app.update_entity("contact", existing["id"], updates)

        return {
            "contact": existing,
            "action": "found",
            "next_step": f"Found existing contact '{existing.get('name')}'. Updated with new info."
            if updates
            else f"Found existing contact '{existing.get('name')}'. No new info to update.",
        }

    # 3. Create new contact
    data: dict[str, Any] = {"name": name}
    if email:
        data["email"] = email
    if phone:
        data["phone"] = phone
    if company:
        data["company"] = company
    if role:
        data["role"] = role
    if lead_source:
        data["lead_source"] = lead_source
    if notes:
        data["notes"] = notes

    contact = app.create_entity("contact", data)
    return {
        "contact": contact,
        "action": "created",
        "next_step": f"Created new contact '{name}'.",
    }
