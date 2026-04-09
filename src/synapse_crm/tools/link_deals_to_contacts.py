"""Post-seed utility: wire deals to contacts by matching contact_name."""

from typing import Any

from upjack.app import UpjackApp


def link_deals_to_contacts(app: UpjackApp) -> dict[str, Any]:
    """Find deals with a contact_name but no belongs_to relationship and link them.

    Matches deal.contact_name to contact.name (case-insensitive).

    Returns:
        Dict with linked count, skipped count, and details.
    """
    deals = app.list_entities("deal", limit=1000)
    contacts = app.list_entities("contact", limit=1000)

    # Build name -> contact lookup (lowercase)
    contact_by_name: dict[str, dict[str, Any]] = {}
    for c in contacts:
        name = (c.get("name") or "").lower().strip()
        if name:
            contact_by_name[name] = c

    linked = 0
    skipped = 0
    details: list[dict[str, str]] = []

    for deal in deals:
        # Skip if already has a belongs_to relationship
        rels = deal.get("relationships", [])
        has_belongs_to = any(r.get("rel") == "belongs_to" for r in rels)
        if has_belongs_to:
            skipped += 1
            continue

        # Match by contact_name
        deal_contact = (deal.get("contact_name") or "").lower().strip()
        if not deal_contact:
            skipped += 1
            continue

        contact = contact_by_name.get(deal_contact)
        if not contact:
            details.append({
                "deal": deal.get("title", deal["id"]),
                "status": f"no contact match for '{deal.get('contact_name')}'",
            })
            skipped += 1
            continue

        # Wire the relationship
        new_rels = list(rels) + [{"rel": "belongs_to", "target": contact["id"]}]
        app.update_entity("deal", deal["id"], {"relationships": new_rels})
        linked += 1
        details.append({
            "deal": deal.get("title", deal["id"]),
            "contact": contact.get("name", contact["id"]),
            "status": "linked",
        })

    return {
        "linked": linked,
        "skipped": skipped,
        "details": details,
        "next_step": f"Linked {linked} deals to contacts."
        if linked
        else "All deals already linked or no matches found.",
    }
