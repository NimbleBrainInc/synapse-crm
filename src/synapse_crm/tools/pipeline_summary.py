"""Aggregate pipeline metrics: deals by stage, total value, win rate."""

from typing import Any

from upjack.app import UpjackApp

_STAGE_ORDER = ["lead", "qualified", "proposal", "negotiation", "closed_won", "closed_lost"]


def pipeline_summary(app: UpjackApp) -> dict[str, Any]:
    """Compute aggregate sales pipeline metrics.

    Args:
        app: UpjackApp instance.

    Returns:
        Context dict with stages array, totals, weighted value, win rate,
        and next_step.
    """
    all_deals = app.list_entities("deal", limit=1000)

    # Group by stage
    stages: dict[str, dict[str, Any]] = {}
    for stage in _STAGE_ORDER:
        stages[stage] = {
            "stage": stage,
            "count": 0,
            "total_value": 0.0,
            "probabilities": [],
        }

    total_active = 0
    total_active_value = 0.0
    weighted_value = 0.0
    closed_won = 0
    closed_lost = 0

    for deal in all_deals:
        stage = deal.get("stage", "lead")
        if stage not in stages:
            continue

        value = deal.get("value", 0) or 0
        probability = deal.get("probability", 0) or 0

        stages[stage]["count"] += 1
        stages[stage]["total_value"] += value
        stages[stage]["probabilities"].append(probability)

        if stage == "closed_won":
            closed_won += 1
        elif stage == "closed_lost":
            closed_lost += 1
        else:
            total_active += 1
            total_active_value += value
            weighted_value += value * probability / 100

    # Build stage results with average probability
    stage_results = []
    for stage in _STAGE_ORDER:
        s = stages[stage]
        probs = s["probabilities"]
        avg_prob = round(sum(probs) / len(probs)) if probs else 0
        stage_results.append({
            "stage": s["stage"],
            "count": s["count"],
            "total_value": s["total_value"],
            "avg_probability": avg_prob,
        })

    # Win rate
    total_closed = closed_won + closed_lost
    win_rate = round(closed_won / total_closed * 100) if total_closed > 0 else None

    # Next step
    if total_active == 0:
        next_step = "No active deals in the pipeline. Time to prospect."
    else:
        next_step = (
            f"{total_active} active deal{'s' if total_active != 1 else ''} "
            f"worth ${total_active_value:,.0f} "
            f"(${weighted_value:,.0f} weighted)."
        )

    return {
        "stages": stage_results,
        "totals": {
            "active_deals": total_active,
            "active_value": total_active_value,
            "weighted_value": round(weighted_value, 2),
            "closed_won": closed_won,
            "closed_lost": closed_lost,
            "win_rate_pct": win_rate,
        },
        "next_step": next_step,
    }
