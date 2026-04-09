# Pipeline Reviewer

Daily health check of the sales pipeline. Identifies stale deals, overdue follow-ups, and summarizes pipeline metrics so the user starts their day knowing exactly where to focus.

## When to Use

- Daily schedule fires (weekday mornings at 9 AM)
- The user asks about pipeline health, revenue forecast, or "what needs attention"
- The user asks for a deal status summary

## Process

1. **Load all active deals**: Use `pipeline_summary()` to get aggregate metrics by stage.

2. **Identify stale deals**: Search for deals where no interaction has been logged for the related contact in the last 14 days. A deal is stale when its contact has gone quiet.
   - For each active deal, get the contact via `belongs_to` relationship
   - Use `contact_timeline(contact_id)` to check the most recent interaction
   - Flag deals where the latest interaction is older than 14 days

3. **Check overdue follow-ups**: Search interactions where `follow_up_date` is before today and no newer interaction exists for that contact.

4. **Check overdue close dates**: Find deals where `close_date` is in the past but stage is not `closed_won` or `closed_lost`.

5. **Compile the daily briefing**:

   ### Pipeline Summary
   - Total active deals: count and total value
   - By stage: count, total value, average probability
   - Weighted pipeline value: sum of (value * probability / 100) across active deals

   ### Attention Required
   - **Stale deals** (no interaction in 14+ days): list with contact name, deal title, days since last interaction
   - **Overdue follow-ups**: list with contact name, interaction summary, days overdue
   - **Past-due close dates**: list with deal title, close date, days overdue

   ### Win Rate
   - Closed won / (closed won + closed lost) over the last 90 days
   - Average deal age (days from creation to close for recently closed deals)

6. **Recommend actions**: For each item requiring attention, suggest a specific next step (e.g., "Call Sarah Chen about the Acme deal — last interaction was 18 days ago").

## Scoring Criteria

| Signal | Severity | Action |
|--------|----------|--------|
| No interaction in 14-21 days | Warning | Suggest a check-in call or email |
| No interaction in 21+ days | Critical | Flag as at-risk, recommend immediate outreach |
| Follow-up overdue by 1-3 days | Low | Gentle reminder |
| Follow-up overdue by 4+ days | High | Escalate — the contact may feel ignored |
| Close date passed by 1-7 days | Warning | Update close date or advance/close the deal |
| Close date passed by 7+ days | Critical | Deal is likely stalled — reassess or close |

## Rules

- Always show the pipeline summary even if nothing needs attention — the user wants to see the numbers.
- Sort attention items by severity (critical first, then warning, then low).
- Never suggest closing a deal as lost without asking the user first.
- When recommending outreach, reference the last interaction so the user has context.
- Keep the briefing scannable — use bullet points and tables, not paragraphs.
