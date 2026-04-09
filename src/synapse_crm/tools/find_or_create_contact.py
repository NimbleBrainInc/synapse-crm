"""Find an existing contact by name/email, or create one if none exists."""

from typing import Any

from upjack.app import UpjackApp


def find_or_create_contact(
    app: UpjackApp,
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
    2. Name substring match

    If a match is found, updates it with any new non-empty fields.
    If no match, creates a new contact.

    Returns:
        Dict with 'contact' (the entity), 'action' ('found' or 'created'),
        and 'next_step'. Returns {"error": "..."} on failure.
    """
    existing = None

    # 1. Search by email (strongest signal)
    if email:
        results = app.search_entities("contact", query=email, limit=5)
        for r in results:
            if r.get("email", "").lower() == email.lower() and r.get("status") == "active":
                existing = r
                break

    # 2. Fall back to name search
    if not existing and name:
        results = app.search_entities("contact", query=name, limit=10)
        for r in results:
            if r.get("status") != "active":
                continue
            # Case-insensitive name match (exact or contained)
            r_name = r.get("name", "").lower()
            if name.lower() == r_name or name.lower() in r_name or r_name in name.lower():
                existing = r
                break

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
                updates["notes"] = f"{old_notes}\n{notes}".strip() if old_notes else notes

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
