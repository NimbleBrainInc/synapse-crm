"""Pipeline totals and timelines cover all records, not a hidden first page."""

from datetime import UTC, datetime, timedelta

from synapse_crm.tools.contact_timeline import contact_timeline
from synapse_crm.tools.pipeline_summary import pipeline_summary


def test_pipeline_counts_deals_beyond_old_limit(app):
    for index in range(1001):
        app.create_entity("deal", {"title": f"Example {index}", "value": 1})
    result = pipeline_summary(app)
    assert result["totals"]["active_deals"] == 1001
    assert result["totals"]["active_value"] == 1001


def test_contact_timeline_includes_history_beyond_old_limit(app):
    contact = app.create_entity("contact", {"name": "Example contact"})
    latest = None
    for index in range(101):
        occurred = datetime(2025, 1, 1, tzinfo=UTC) + timedelta(days=index)
        latest = app.create_entity(
            "interaction",
            {
                "interaction_type": "note",
                "summary": f"Example {index}",
                "occurred_at": occurred.isoformat(),
                "relationships": [{"rel": "belongs_to", "target": contact["id"]}],
            },
        )
    result = contact_timeline(app, contact["id"])
    assert result["total"] == 101
    assert result["interactions"][0]["id"] == latest["id"]
