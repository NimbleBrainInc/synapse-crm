"""Behavior tests for the hand-written domain tools (Phase 2).

Every test drives the real tool through ``fastmcp.Client`` and asserts a
business-meaningful property. Error paths are verified either via
``pytest.raises(ToolError)`` (for schema-level failures the client catches)
or by inspecting the returned ``{"error": ...}`` envelope the tools emit
for invalid business inputs.

The six tools under test:

* ``find_or_create_contact`` — dedup on email/name, merge new fields
* ``log_interaction`` — create interaction, auto-wire ``belongs_to``,
  denormalize contact name
* ``move_deal_stage`` — stage transition with ``close_date`` side effects
* ``pipeline_summary`` — stage aggregates, win rate, weighted value
* ``link_deals_to_contacts`` — backfill ``belongs_to`` via ``contact_name``
* ``contact_timeline`` — interactions reverse-chronologically
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastmcp.exceptions import ToolError

from synapse_crm.tools.link_deals_to_contacts import link_deals_to_contacts
from tests.conftest import _call_tool, _run


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _create_contact(mcp, **fields) -> dict:
    """Create a contact via ``create_contact`` (present on the server even
    though the manifest filter hides it from ``tools/list``)."""
    return _run(_call_tool(mcp, "create_contact", fields))


def _create_deal(mcp, **fields) -> dict:
    return _run(_call_tool(mcp, "create_deal", fields))


# ---------------------------------------------------------------------------
# find_or_create_contact
# ---------------------------------------------------------------------------


class TestFindOrCreateContact:
    def test_creates_new_when_no_match(self, mcp):
        result = _run(
            _call_tool(
                mcp,
                "find_or_create_contact",
                {"name": "Brand New Person", "email": "brand.new@example.com"},
            )
        )
        assert result["action"] == "created"
        assert result["contact"]["id"].startswith("ct_")
        assert result["contact"]["name"] == "Brand New Person"
        assert result["contact"]["email"] == "brand.new@example.com"

    def test_finds_existing_by_exact_email(self, mcp):
        first = _run(
            _call_tool(
                mcp,
                "find_or_create_contact",
                {"name": "Alice Original", "email": "alice@example.com"},
            )
        )
        first_id = first["contact"]["id"]
        assert first["action"] == "created"

        second = _run(
            _call_tool(
                mcp,
                "find_or_create_contact",
                {"name": "Alice DifferentName", "email": "alice@example.com"},
            )
        )
        assert second["action"] == "found"
        assert second["contact"]["id"] == first_id

    def test_finds_existing_by_fuzzy_name(self, mcp):
        first = _run(
            _call_tool(
                mcp,
                "find_or_create_contact",
                {"name": "Alice Chen"},
            )
        )
        first_id = first["contact"]["id"]

        # Different capitalisation — should match via case-insensitive compare.
        second = _run(
            _call_tool(
                mcp,
                "find_or_create_contact",
                {"name": "alice chen"},
            )
        )
        assert second["action"] == "found"
        assert second["contact"]["id"] == first_id

    def test_updates_with_new_fields_on_match(self, mcp):
        first = _run(
            _call_tool(
                mcp,
                "find_or_create_contact",
                {"name": "Bare Contact", "email": "bare@example.com"},
            )
        )
        first_id = first["contact"]["id"]
        assert not first["contact"].get("phone")
        assert not first["contact"].get("role")

        second = _run(
            _call_tool(
                mcp,
                "find_or_create_contact",
                {
                    "name": "Bare Contact",
                    "email": "bare@example.com",
                    "phone": "555-1234",
                    "role": "CTO",
                },
            )
        )
        assert second["action"] == "found"
        assert second["contact"]["id"] == first_id
        assert second["contact"]["phone"] == "555-1234"
        assert second["contact"]["role"] == "CTO"


# ---------------------------------------------------------------------------
# log_interaction
# ---------------------------------------------------------------------------


class TestLogInteraction:
    def test_creates_interaction_entity(self, mcp):
        contact = _create_contact(mcp, name="Timeline Target")
        ix = _run(
            _call_tool(
                mcp,
                "log_interaction",
                {
                    "contact_id": contact["id"],
                    "interaction_type": "email",
                    "summary": "Sent intro email",
                },
            )
        )
        assert ix["id"].startswith("ix_")

        # Round-trip — the entity is persisted and fetchable.
        fetched = _run(_call_tool(mcp, "get_interaction", {"interaction_id": ix["id"]}))
        assert fetched["id"] == ix["id"]
        assert fetched["summary"] == "Sent intro email"

    def test_auto_wires_belongs_to_relationship(self, mcp):
        contact = _create_contact(mcp, name="Relationship Parent")
        ix = _run(
            _call_tool(
                mcp,
                "log_interaction",
                {
                    "contact_id": contact["id"],
                    "interaction_type": "meeting",
                    "summary": "Kickoff call",
                },
            )
        )
        rels = ix.get("relationships") or []
        assert any(
            r.get("rel") == "belongs_to" and r.get("target") == contact["id"] for r in rels
        ), f"interaction missing belongs_to -> {contact['id']}; got {rels!r}"

    def test_denormalizes_contact_name(self, mcp):
        contact = _create_contact(mcp, name="Jane Doe", email="jane@example.com")
        ix = _run(
            _call_tool(
                mcp,
                "log_interaction",
                {
                    "contact_id": contact["id"],
                    "interaction_type": "call",
                    "summary": "Discovery call",
                },
            )
        )
        assert ix.get("contact_name") == "Jane Doe"

    def test_handles_optional_follow_up_date(self, mcp):
        contact = _create_contact(mcp, name="Follow Up Test")

        no_followup = _run(
            _call_tool(
                mcp,
                "log_interaction",
                {
                    "contact_id": contact["id"],
                    "interaction_type": "note",
                    "summary": "Quick note",
                },
            )
        )
        assert no_followup["id"].startswith("ix_")
        assert not no_followup.get("follow_up_date")

        with_followup = _run(
            _call_tool(
                mcp,
                "log_interaction",
                {
                    "contact_id": contact["id"],
                    "interaction_type": "note",
                    "summary": "Note with followup",
                    "follow_up_date": "2099-06-15",
                },
            )
        )
        assert with_followup["follow_up_date"] == "2099-06-15"


# ---------------------------------------------------------------------------
# move_deal_stage
# ---------------------------------------------------------------------------


class TestMoveDealStage:
    def test_valid_transition(self, mcp):
        deal = _create_deal(mcp, title="Valid Move", stage="lead")
        result = _run(
            _call_tool(
                mcp,
                "move_deal_stage",
                {"deal_id": deal["id"], "stage": "qualified"},
            )
        )
        assert result["deal"]["stage"] == "qualified"
        assert result["previous_stage"] == "lead"

        # Persisted on disk, not just in the response envelope.
        fetched = _run(_call_tool(mcp, "get_deal", {"deal_id": deal["id"]}))
        assert fetched["stage"] == "qualified"

    def test_rejects_invalid_stage(self, mcp):
        deal = _create_deal(mcp, title="Bad Move", stage="lead")
        result = _run(
            _call_tool(
                mcp,
                "move_deal_stage",
                {"deal_id": deal["id"], "stage": "not_a_stage"},
            )
        )
        # Tool returns an explicit error envelope; assert on its shape so a
        # silent success would fail this test.
        assert "error" in result
        assert "not_a_stage" in result["error"]

        # And the deal's stage is unchanged.
        fetched = _run(_call_tool(mcp, "get_deal", {"deal_id": deal["id"]}))
        assert fetched["stage"] == "lead"

    def test_auto_sets_close_date_on_closed_won(self, mcp):
        deal = _create_deal(mcp, title="Won Deal", stage="negotiation")
        result = _run(
            _call_tool(
                mcp,
                "move_deal_stage",
                {"deal_id": deal["id"], "stage": "closed_won"},
            )
        )
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        assert result["close_date_set"] is True
        assert result["deal"]["close_date"] == today

    def test_auto_sets_close_date_on_closed_lost(self, mcp):
        deal = _create_deal(mcp, title="Lost Deal", stage="negotiation")
        result = _run(
            _call_tool(
                mcp,
                "move_deal_stage",
                {"deal_id": deal["id"], "stage": "closed_lost"},
            )
        )
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        assert result["close_date_set"] is True
        assert result["deal"]["close_date"] == today

    def test_does_not_overwrite_existing_close_date(self, mcp):
        deal = _create_deal(mcp, title="Pre-dated Deal", stage="negotiation")
        # Pre-seed close_date to a distinct value.
        _run(
            _call_tool(
                mcp,
                "update_deal",
                {"deal_id": deal["id"], "close_date": "2020-01-15"},
            )
        )

        result = _run(
            _call_tool(
                mcp,
                "move_deal_stage",
                {"deal_id": deal["id"], "stage": "closed_won"},
            )
        )
        assert result["close_date_set"] is False
        assert result["deal"]["close_date"] == "2020-01-15"


# ---------------------------------------------------------------------------
# pipeline_summary
# ---------------------------------------------------------------------------


def _stage_row(summary: dict, stage: str) -> dict:
    for row in summary["stages"]:
        if row["stage"] == stage:
            return row
    raise AssertionError(f"stage {stage!r} missing from summary: {summary['stages']!r}")


class TestPipelineSummary:
    def test_empty_pipeline_returns_zeros(self, mcp):
        summary = _run(_call_tool(mcp, "pipeline_summary", {}))
        assert summary["totals"]["active_deals"] == 0
        assert summary["totals"]["active_value"] == 0
        assert summary["totals"]["weighted_value"] == 0
        # Every stage row exists but has zero count.
        for row in summary["stages"]:
            assert row["count"] == 0
            assert row["total_value"] == 0

    def test_mixed_stages_aggregate_correctly(self, mcp):
        _create_deal(mcp, title="Lead A", stage="lead", value=1000, probability=10)
        _create_deal(mcp, title="Qualified A", stage="qualified", value=2000, probability=25)
        _create_deal(mcp, title="Qualified B", stage="qualified", value=3000, probability=25)
        _create_deal(mcp, title="Proposal A", stage="proposal", value=5000, probability=50)

        summary = _run(_call_tool(mcp, "pipeline_summary", {}))
        assert _stage_row(summary, "lead")["count"] == 1
        assert _stage_row(summary, "lead")["total_value"] == 1000
        assert _stage_row(summary, "qualified")["count"] == 2
        assert _stage_row(summary, "qualified")["total_value"] == 5000
        assert _stage_row(summary, "proposal")["count"] == 1
        assert _stage_row(summary, "proposal")["total_value"] == 5000
        assert summary["totals"]["active_deals"] == 4
        assert summary["totals"]["active_value"] == 11000

    def test_computes_weighted_value_and_win_rate(self, mcp):
        # Active deals: weighted = 1000*0.10 + 2000*0.50 + 4000*0.75 = 100 + 1000 + 3000 = 4100
        _create_deal(mcp, title="Lead", stage="lead", value=1000, probability=10)
        _create_deal(mcp, title="Prop", stage="proposal", value=2000, probability=50)
        _create_deal(mcp, title="Neg", stage="negotiation", value=4000, probability=75)
        # Closed: 2 won, 1 lost => win rate = 2/3 ~= 67%
        _create_deal(mcp, title="Won1", stage="closed_won", value=10000, probability=100)
        _create_deal(mcp, title="Won2", stage="closed_won", value=8000, probability=100)
        _create_deal(mcp, title="Lost", stage="closed_lost", value=5000, probability=0)

        summary = _run(_call_tool(mcp, "pipeline_summary", {}))
        assert summary["totals"]["weighted_value"] == 4100
        assert summary["totals"]["win_rate_pct"] == 67
        assert summary["totals"]["closed_won"] == 2
        assert summary["totals"]["closed_lost"] == 1
        assert summary["totals"]["active_deals"] == 3


# ---------------------------------------------------------------------------
# link_deals_to_contacts
# ---------------------------------------------------------------------------


def _deal_belongs_to_targets(deal: dict) -> list[str]:
    return [
        r["target"]
        for r in (deal.get("relationships") or [])
        if r.get("rel") == "belongs_to"
    ]


class TestLinkDealsToContacts:
    def test_links_deals_by_contact_name(self, mcp):
        contact = _create_contact(mcp, name="Alice Linker")
        deal = _create_deal(
            mcp, title="Linkable Deal", stage="qualified", contact_name="Alice Linker"
        )

        result = _run(_call_tool(mcp, "link_deals_to_contacts", {}))
        assert result["linked"] == 1

        fetched = _run(_call_tool(mcp, "get_deal", {"deal_id": deal["id"]}))
        assert contact["id"] in _deal_belongs_to_targets(fetched)

    def test_idempotent(self, mcp):
        contact = _create_contact(mcp, name="Idem Person")
        deal = _create_deal(
            mcp, title="Idem Deal", stage="qualified", contact_name="Idem Person"
        )

        first = _run(_call_tool(mcp, "link_deals_to_contacts", {}))
        assert first["linked"] == 1

        second = _run(_call_tool(mcp, "link_deals_to_contacts", {}))
        assert second["linked"] == 0

        fetched = _run(_call_tool(mcp, "get_deal", {"deal_id": deal["id"]}))
        targets = _deal_belongs_to_targets(fetched)
        assert targets.count(contact["id"]) == 1, (
            f"expected exactly one belongs_to -> {contact['id']}, got {targets!r}"
        )

    def test_leaves_unmatched_deals_alone(self, mcp):
        deal = _create_deal(
            mcp,
            title="Orphan Deal",
            stage="qualified",
            contact_name="Nobody Registered Here",
        )

        result = _run(_call_tool(mcp, "link_deals_to_contacts", {}))
        assert result["linked"] == 0

        fetched = _run(_call_tool(mcp, "get_deal", {"deal_id": deal["id"]}))
        assert _deal_belongs_to_targets(fetched) == []

    @pytest.mark.parametrize("names", [("Alex Morgan", " alex MORGAN "), ("Straße", "STRASSE")])
    def test_leaves_ambiguous_contact_name_unlinked(self, mcp, app, names):
        for name in names:
            app.create_entity("contact", {"name": name})
        deal = app.create_entity(
            "deal",
            {
                "title": "Unresolved Deal",
                "stage": "qualified",
                "contact_name": names[0],
            },
        )

        result = _run(_call_tool(mcp, "link_deals_to_contacts", {}))

        assert result["linked"] == 0
        assert result["skipped"] == 1
        assert any("ambiguous" in detail["status"] for detail in result["details"])
        assert _deal_belongs_to_targets(app.get_entity("deal", deal["id"])) == []

    @pytest.mark.parametrize("has_active_match", [False, True])
    def test_archived_contacts_do_not_match_or_make_active_match_ambiguous(
        self, mcp, app, has_active_match
    ):
        archived = app.create_entity("contact", {"name": "Alex Morgan"})
        app.update_entity("contact", archived["id"], {"status": "archived"})
        active = app.create_entity("contact", {"name": "Alex Morgan"}) if has_active_match else None
        deal = app.create_entity(
            "deal",
            {
                "title": "Active contact's deal",
                "stage": "qualified",
                "contact_name": "Alex Morgan",
            },
        )

        result = _run(_call_tool(mcp, "link_deals_to_contacts", {}))

        assert result["linked"] == (1 if has_active_match else 0)
        targets = _deal_belongs_to_targets(app.get_entity("deal", deal["id"]))
        assert targets == ([active["id"]] if active else [])

    def test_duplicate_beyond_first_thousand_contacts_stays_unlinked(self, mcp, app):
        older = app.create_entity("contact", {"name": "Alex Morgan"})
        for index in range(999):
            app.create_entity("contact", {"name": f"Unrelated contact {index}"})
        app.create_entity("contact", {"name": " alex MORGAN "})
        deal = app.create_entity(
            "deal",
            {
                "title": "Ambiguous large-library deal",
                "stage": "qualified",
                "contact_name": "Alex Morgan",
            },
        )
        first_page = app.list_entities("contact", limit=1000)
        assert len(first_page) == 1000
        assert older["id"] not in {contact["id"] for contact in first_page}

        result = _run(_call_tool(mcp, "link_deals_to_contacts", {}))

        assert result["linked"] == 0
        assert any("ambiguous" in detail["status"] for detail in result["details"])
        assert _deal_belongs_to_targets(app.get_entity("deal", deal["id"])) == []

    def test_unique_contact_beyond_first_thousand_can_be_linked(self, mcp, app):
        older = app.create_entity("contact", {"name": "Older unique contact"})
        for index in range(1000):
            app.create_entity("contact", {"name": f"Unrelated contact {index}"})
        deal = app.create_entity(
            "deal",
            {
                "title": "Older contact's deal",
                "stage": "qualified",
                "contact_name": "Older unique contact",
            },
        )
        assert older["id"] not in {
            contact["id"] for contact in app.list_entities("contact", limit=1000)
        }

        result = _run(_call_tool(mcp, "link_deals_to_contacts", {}))

        assert result["linked"] == 1
        assert _deal_belongs_to_targets(app.get_entity("deal", deal["id"])) == [older["id"]]

    def test_startup_hook_backfills_relationships_idempotently(self, mcp, app):
        """Mirrors the server-startup hook: deals seeded with ``contact_name``
        but no ``belongs_to`` should become reachable via ``query_by_relationship``
        after a single call, and a re-run must not duplicate the edge."""
        alice = _create_contact(mcp, name="Alice")
        _create_contact(mcp, name="Bob")

        alice_deal = _create_deal(
            mcp, title="Alice Deal", stage="qualified", contact_name="Alice"
        )
        _create_deal(mcp, title="Bob Deal", stage="qualified", contact_name="Bob")

        # Pre-condition: no graph edge wires the Alice deal to Alice yet.
        before = app.query_by_relationship("deal", "belongs_to", alice["id"])
        assert before == []

        # First run wires the relationships up.
        link_deals_to_contacts(app)
        after_first = app.query_by_relationship("deal", "belongs_to", alice["id"])
        assert [d["id"] for d in after_first] == [alice_deal["id"]]

        # Second run is a no-op: still exactly one belongs_to edge, not two.
        link_deals_to_contacts(app)
        after_second = app.query_by_relationship("deal", "belongs_to", alice["id"])
        assert [d["id"] for d in after_second] == [alice_deal["id"]]

        fetched = _run(_call_tool(mcp, "get_deal", {"deal_id": alice_deal["id"]}))
        targets = _deal_belongs_to_targets(fetched)
        assert targets.count(alice["id"]) == 1, (
            f"expected exactly one belongs_to -> {alice['id']}, got {targets!r}"
        )


# ---------------------------------------------------------------------------
# contact_timeline
# ---------------------------------------------------------------------------


class TestContactTimeline:
    def test_reverse_chronological_order(self, mcp):
        contact = _create_contact(mcp, name="Timeline Hero")

        # Three interactions; rewrite ``occurred_at`` to deterministic times
        # since ``log_interaction`` stamps ``datetime.now(UTC)``.
        ix_old = _run(
            _call_tool(
                mcp,
                "log_interaction",
                {
                    "contact_id": contact["id"],
                    "interaction_type": "email",
                    "summary": "Oldest",
                },
            )
        )
        ix_mid = _run(
            _call_tool(
                mcp,
                "log_interaction",
                {
                    "contact_id": contact["id"],
                    "interaction_type": "call",
                    "summary": "Middle",
                },
            )
        )
        ix_new = _run(
            _call_tool(
                mcp,
                "log_interaction",
                {
                    "contact_id": contact["id"],
                    "interaction_type": "meeting",
                    "summary": "Newest",
                },
            )
        )

        _run(
            _call_tool(
                mcp,
                "update_interaction",
                {"interaction_id": ix_old["id"], "occurred_at": "2025-01-01T10:00:00Z"},
            )
        )
        _run(
            _call_tool(
                mcp,
                "update_interaction",
                {"interaction_id": ix_mid["id"], "occurred_at": "2025-06-01T10:00:00Z"},
            )
        )
        _run(
            _call_tool(
                mcp,
                "update_interaction",
                {"interaction_id": ix_new["id"], "occurred_at": "2026-01-01T10:00:00Z"},
            )
        )

        timeline = _run(_call_tool(mcp, "contact_timeline", {"contact_id": contact["id"]}))
        summaries = [entry["summary"] for entry in timeline["interactions"]]
        assert summaries == ["Newest", "Middle", "Oldest"]
        assert timeline["total"] == 3

    def test_empty_timeline_returns_empty_list(self, mcp):
        contact = _create_contact(mcp, name="Ghost Contact")
        timeline = _run(_call_tool(mcp, "contact_timeline", {"contact_id": contact["id"]}))
        assert timeline["interactions"] == []
        assert timeline["total"] == 0

    def test_missing_contact_returns_error(self, mcp):
        # The tool returns ``{"error": ...}`` rather than raising, so we
        # assert on that shape explicitly — no bare try/except.
        result = _run(
            _call_tool(
                mcp,
                "contact_timeline",
                {"contact_id": "ct_does_not_exist_01234567890123456"},
            )
        )
        assert "error" in result
        assert "not found" in result["error"].lower()


# ---------------------------------------------------------------------------
# Schema-level error paths (ToolError)
# ---------------------------------------------------------------------------


class TestSchemaLevelErrors:
    """Guards that the client layer rejects malformed calls before the tool
    body runs. These use ``ToolError`` because FastMCP raises it when JSON
    Schema validation fails (missing required args, wrong types)."""

    def test_move_deal_stage_missing_required_arg_raises(self, mcp):
        # ``deal_id`` is required; omitting it is a schema violation.
        with pytest.raises(ToolError):
            _run(_call_tool(mcp, "move_deal_stage", {"stage": "qualified"}))

    def test_log_interaction_missing_required_arg_raises(self, mcp):
        with pytest.raises(ToolError):
            _run(
                _call_tool(
                    mcp,
                    "log_interaction",
                    {"interaction_type": "email", "summary": "no contact"},
                )
            )
