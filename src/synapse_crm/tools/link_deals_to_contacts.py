"""Post-seed utility: wire deals to contacts by matching contact_name."""

from typing import Any

from synapse_crm.store import CRMStore


def link_deals_to_contacts(store: CRMStore) -> dict[str, Any]:
    """Find deals with a contact_name but no belongs_to relationship and link them.

    Matches deal.contact_name to one active contact.name (case-insensitive).
    Leaves deals unlinked when multiple contacts share the matching name.

    Returns:
        Dict with linked count, skipped count, and details.
    """
    deals = store.list_entities("deal")
    # Every active contact, so an older match or duplicate is never hidden.
    contacts = store.list_entities("contact", status="active")

    contacts_by_name: dict[str, list[dict[str, Any]]] = {}
    for c in contacts:
        name = (c.get("name") or "").strip().casefold()
        if name:
            contacts_by_name.setdefault(name, []).append(c)

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
        deal_contact = (deal.get("contact_name") or "").strip().casefold()
        if not deal_contact:
            skipped += 1
            continue

        matches = contacts_by_name.get(deal_contact, [])
        if len(matches) != 1:
            details.append({
                "deal": deal.get("title", deal["id"]),
                "status": (
                    f"ambiguous contact name '{deal.get('contact_name')}'"
                    if matches
                    else f"no contact match for '{deal.get('contact_name')}'"
                ),
            })
            skipped += 1
            continue

        # Wire the relationship
        contact = matches[0]
        new_rels = list(rels) + [{"rel": "belongs_to", "target": contact["id"]}]
        store.update_entity("deal", deal["id"], {"relationships": new_rels})
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
