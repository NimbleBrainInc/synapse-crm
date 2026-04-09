# Follow-Up Coach

Ensures every contact interaction has a clear next step. Analyzes the interaction type and content, suggests concrete follow-up actions, and sets a follow-up date when one is missing.

## When to Use

- A new interaction is logged (automatic hook on `interaction.created`)
- A deal changes stage (automatic hook on `deal.updated` when `$.stage changed`)
- The user asks what to do next with a contact or deal

## Process

1. **Load context**: Get the interaction that triggered this skill. Load the related contact via the `belongs_to` relationship. Check for any active deals linked to the same contact.

2. **Evaluate follow-up urgency**: Determine the appropriate follow-up window based on interaction type:

   | Interaction Type | Follow-Up Window |
   |------------------|-----------------|
   | meeting          | 2 business days |
   | email            | 3 business days |
   | call             | 5 business days |
   | note             | No automatic follow-up unless the note mentions a deadline |

3. **Set follow-up date**: If the interaction has no `follow_up_date`, calculate one using the window above from `occurred_at` (or today if `occurred_at` is not set). Update the interaction with the calculated date.

4. **Suggest next action**: Based on the interaction type and any active deals:
   - **After a meeting**: Suggest sending a recap email summarizing key decisions and action items.
   - **After a call**: Suggest documenting key takeaways as a note interaction and scheduling a follow-up if the call was exploratory.
   - **After an email**: Suggest a phone call if no response is received by the follow-up date.
   - **On deal stage change**: Suggest the natural next action for the new stage:
     - `lead` → Qualify: schedule a discovery call
     - `qualified` → Prepare and send a proposal
     - `proposal` → Follow up on proposal within 3 days
     - `negotiation` → Address objections, prepare final terms
     - `closed_won` → Send welcome/onboarding email, log the win
     - `closed_lost` → Log the reason, schedule a check-in in 90 days

5. **Communicate**: Tell the user what you did (set a follow-up date, suggested next steps) in a concise message.

## Rules

- Never leave an interaction without a follow-up date unless it is explicitly a `note` with no deadline mentioned.
- Follow-up dates must be business days (skip weekends).
- When a deal moves to `closed_won` or `closed_lost`, always log an interaction summarizing the outcome.
- Do not overwrite a follow-up date that the user explicitly set.
- Keep suggestions actionable and specific — "follow up" is not specific enough; "send a recap email covering the three pricing options discussed" is.
