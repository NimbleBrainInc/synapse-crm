"""A contact match must not update a different person's record."""

from tests.conftest import _call_tool, _run


def test_same_name_with_different_email_creates_distinct_contact(mcp, app):
    original = app.create_entity(
        "contact", {"name": "Alex Morgan", "email": "first@example.com"}
    )
    result = _run(
        _call_tool(
            mcp,
            "find_or_create_contact",
            {
                "name": "Alex Morgan",
                "email": "second@example.com",
                "notes": "Second person",
            },
        )
    )
    assert result["action"] == "created"
    assert result["contact"]["id"] != original["id"]
    assert app.get_entity("contact", original["id"]) == original


def test_duplicate_exact_email_is_ambiguous_without_writes(mcp, app):
    records = [
        app.create_entity("contact", {"name": name, "email": "shared@example.com"})
        for name in ["First", "Second"]
    ]
    result = _run(
        _call_tool(
            mcp,
            "find_or_create_contact",
            {"name": "First", "email": "shared@example.com", "notes": "Do not apply"},
        )
    )
    assert "error" in result
    assert [app.get_entity("contact", record["id"]) for record in records] == records


def test_contact_match_trims_whitespace_and_folds_unicode(mcp, app):
    original = app.create_entity("contact", {"name": "Straße"})
    result = _run(
        _call_tool(
            mcp, "find_or_create_contact", {"name": " STRASSE ", "phone": "555-0100"}
        )
    )
    assert result["action"] == "found"
    assert result["contact"]["id"] == original["id"]
    assert result["contact"]["phone"] == "555-0100"


def test_partial_name_does_not_select_existing_person(mcp, app):
    original = app.create_entity("contact", {"name": "Alexandra Morgan"})
    result = _run(
        _call_tool(
            mcp,
            "find_or_create_contact",
            {"name": "Alex", "notes": "Different contact"},
        )
    )
    assert result["action"] == "created"
    assert result["contact"]["id"] != original["id"]
    assert app.get_entity("contact", original["id"]) == original


def test_blank_name_returns_error_without_creating(mcp, app):
    result = _run(_call_tool(mcp, "find_or_create_contact", {"name": "   "}))
    assert "error" in result
    assert app.list_entities("contact") == []


def test_name_only_contact_gets_email_filled_in(mcp, app):
    original = app.create_entity("contact", {"name": "Alice Chen"})
    result = _run(
        _call_tool(
            mcp,
            "find_or_create_contact",
            {"name": "alice chen", "email": "alice@example.com"},
        )
    )
    assert result["action"] == "found"
    assert result["contact"]["id"] == original["id"]
    assert result["contact"]["email"] == "alice@example.com"
    assert len(app.list_entities("contact")) == 1


def test_blank_name_with_known_email_finds_contact(mcp, app):
    original = app.create_entity(
        "contact", {"name": "Alice Chen", "email": "alice@example.com"}
    )
    result = _run(
        _call_tool(
            mcp, "find_or_create_contact", {"name": " ", "email": "ALICE@example.com"}
        )
    )
    assert result["action"] == "found"
    assert result["contact"]["id"] == original["id"]


def test_duplicate_exact_name_is_ambiguous_without_writes(mcp, app):
    records = [app.create_entity("contact", {"name": "Alex Morgan"}) for _ in range(2)]
    result = _run(
        _call_tool(
            mcp,
            "find_or_create_contact",
            {"name": "alex morgan", "phone": "555-0100"},
        )
    )
    assert "error" in result
    assert [app.get_entity("contact", record["id"]) for record in records] == records
    assert len(app.list_entities("contact")) == 2


def test_email_enrichment_of_duplicate_names_is_ambiguous_without_writes(mcp, app):
    records = [app.create_entity("contact", {"name": "Alex Morgan"}) for _ in range(2)]
    result = _run(
        _call_tool(
            mcp,
            "find_or_create_contact",
            {"name": "Alex Morgan", "email": "alex@example.com"},
        )
    )
    assert "error" in result
    assert [app.get_entity("contact", record["id"]) for record in records] == records
    assert len(app.list_entities("contact")) == 2
