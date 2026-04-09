"""Move a deal between pipeline stages with close-date side effects."""

from datetime import UTC, datetime
from typing import Any

from upjack.app import UpjackApp

_VALID_STAGES = ("lead", "qualified", "proposal", "negotiation", "closed_won", "closed_lost")
_CLOSED_STAGES = ("closed_won", "closed_lost")


def _today_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def move_deal_stage(
    app: UpjackApp,
    deal_id: str,
    stage: str,
) -> dict[str, Any]:
    """Move a deal to a new pipeline stage.

    Args:
        app: UpjackApp instance.
        deal_id: ID of the deal to move.
        stage: Target stage (must be a valid pipeline stage).

    Returns:
        Context dict with deal, previous_stage, close_date_set, and next_step.
        Returns {"error": "..."} on failure.
    """
    if stage not in _VALID_STAGES:
        return {"error": f"Invalid stage '{stage}'. Must be one of: {', '.join(_VALID_STAGES)}"}

    try:
        deal = app.get_entity("deal", deal_id)
    except FileNotFoundError:
        return {"error": f"Deal {deal_id} not found"}

    previous_stage = deal.get("stage", "lead")
    if previous_stage == stage:
        return {"error": f"Deal is already in stage '{stage}'"}

    update_data: dict[str, Any] = {"stage": stage}

    # Auto-set close_date when closing a deal
    close_date_set = False
    if stage in _CLOSED_STAGES and not deal.get("close_date"):
        update_data["close_date"] = _today_iso()
        close_date_set = True

    # Set probability based on stage
    stage_probabilities = {
        "lead": 10,
        "qualified": 25,
        "proposal": 50,
        "negotiation": 75,
        "closed_won": 100,
        "closed_lost": 0,
    }
    update_data["probability"] = stage_probabilities[stage]

    updated_deal = app.update_entity("deal", deal_id, update_data)

    # Build next_step guidance
    next_steps = {
        "lead": "Schedule a discovery call to qualify this lead.",
        "qualified": "Prepare and send a proposal.",
        "proposal": "Follow up on the proposal within 3 business days.",
        "negotiation": "Address objections and prepare final terms.",
        "closed_won": "Send a welcome email and begin onboarding.",
        "closed_lost": "Log the reason for loss and schedule a 90-day check-in.",
    }

    return {
        "deal": {
            "id": updated_deal["id"],
            "title": updated_deal.get("title"),
            "stage": updated_deal.get("stage"),
            "value": updated_deal.get("value"),
            "close_date": updated_deal.get("close_date"),
            "probability": updated_deal.get("probability"),
        },
        "previous_stage": previous_stage,
        "close_date_set": close_date_set,
        "next_step": next_steps[stage],
    }
