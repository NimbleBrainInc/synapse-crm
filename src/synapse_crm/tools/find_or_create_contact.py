"""Find an existing contact by name/email, or create one if none exists."""

from typing import Any

from synapse_crm.store import CRMStore


def find_or_create_contact(
    store: CRMStore,
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
    1. Exact email match, ignoring case and surrounding spaces (if email provided)
    2. Exact name match, ignoring case and surrounding spaces. With an email,
       only contacts that have no email yet are considered, so a contact
       first saved by name alone gets the email filled in.

    More than one active match returns an error and changes nothing.

    If a match is found, updates it with any new non-empty fields.
    If no match, creates a new contact.

    Returns:
        Dict with 'contact' (the entity), 'action' ('found' or 'created'),
        and 'next_step'. Returns {"error": "..."} on failure.
    """
    name, email = name.strip(), email.strip()
    if not name and not email:
        return {"error": "A contact name is required."}
    # Check every active contact: a limited search page cannot show that a
    # name or email identifies exactly one person.
    contacts = store.list_entities("contact")

    def _same(value: Any, wanted: str) -> bool:
        return (value or "").strip().casefold() == wanted.casefold()

    matches: list[dict[str, Any]] = []
    field, value = "email", email
    if email:
        matches = [c for c in contacts if _same(c.get("email"), email)]
    if not matches and name:
        field, value = "name", name
        matches = [
            c
            for c in contacts
            if _same(c.get("name"), name) and not (email and c.get("email"))
        ]
    if len(matches) > 1:
        return {
            "error": f"Multiple active contacts match {field} '{value}'. "
            "Choose the contact by ID before updating it."
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
            existing = store.update_entity("contact", existing["id"], updates)

        return {
            "contact": existing,
            "action": "found",
            "next_step": f"Found existing contact '{existing.get('name')}'. Updated with new info."
            if updates
            else f"Found existing contact '{existing.get('name')}'. No new info to update.",
        }

    # 3. Create new contact
    if not name:
        return {"error": "A contact name is required."}
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

    contact = store.create_entity("contact", data)
    return {
        "contact": contact,
        "action": "created",
        "next_step": f"Created new contact '{name}'.",
    }
