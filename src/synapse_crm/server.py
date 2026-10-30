"""CRM MCP server with FastMCP and an app-owned JSON store."""

import logging
import os
from pathlib import Path

from fastmcp import FastMCP
from fastmcp.server.middleware import Middleware, MiddlewareContext

from synapse_crm.assets import asset_root
from synapse_crm.crud import register_store_tools
from synapse_crm.store import CRMStore, ChangeMarker, current_change
from synapse_crm.tools import register_tools
from synapse_crm.tools.link_deals_to_contacts import link_deals_to_contacts

logger = logging.getLogger(__name__)

_PROJECT_ROOT = asset_root()
workspace_root = os.environ.get(
    "MPAK_WORKSPACE", os.environ.get("UPJACK_ROOT", "./workspace")
)
_app = CRMStore(workspace_root, _PROJECT_ROOT)
mcp = FastMCP(
    "CRM",
    instructions=(
        "Contacts, deals and interactions stored locally. Read upjack://context for domain guidance. "
        "For follow-up planning, read skill://follow-up-coach/usage. "
        "For pipeline reviews, read skill://pipeline-reviewer/usage.\n\n"
        "CRITICAL — CRM Tools: "
        "Use find_or_create_contact() to add contacts — it deduplicates automatically. "
        "Use log_interaction() to create interactions — it auto-wires the contact relationship. "
        "Use move_deal_stage() for stage changes — it handles close date and probability. "
        "Use pipeline_summary() for aggregate metrics. "
        "Use contact_timeline() to review interaction history."
    ),
)


class CRMWriteNotifications(Middleware):
    async def on_list_tools(self, context, call_next):
        # Preserve the legacy hidden-but-callable create_contact contract.
        # Agents see find_or_create_contact as the supported creation path.
        return [
            tool for tool in await call_next(context) if tool.name != "create_contact"
        ]

    async def on_call_tool(self, context: MiddlewareContext, call_next):
        marker = ChangeMarker()
        token = current_change.set(marker)
        try:
            return await call_next(context)
        finally:
            current_change.reset(token)
            if marker.changed and context.fastmcp_context is not None:
                try:
                    await context.fastmcp_context.session.send_resource_list_changed()
                except Exception:
                    logger.warning(
                        "CRM change notification could not be sent", exc_info=True
                    )


mcp.add_middleware(CRMWriteNotifications())
register_store_tools(mcp, _app)


@mcp.resource("upjack://context")
def crm_context() -> str:
    """CRM guidance. Keep the resource URI for existing clients."""
    return (_PROJECT_ROOT / "context.md").read_text()


@mcp.resource("upjack://skills/follow-up-coach")
def follow_up_skill() -> str:
    """Guidance for contact follow-ups."""
    return (_PROJECT_ROOT / "skills/follow-up-coach/SKILL.md").read_text()


@mcp.resource("upjack://skills/pipeline-reviewer")
def pipeline_review_skill() -> str:
    """Guidance for pipeline reviews."""
    return (_PROJECT_ROOT / "skills/pipeline-reviewer/SKILL.md").read_text()


@mcp.resource("skill://follow-up-coach/usage", mime_type="text/markdown")
def follow_up_usage() -> str:
    """Native skill resource; the legacy resource remains available."""
    return (_PROJECT_ROOT / "skills/follow-up-coach/SKILL.md").read_text()


@mcp.resource("skill://pipeline-reviewer/usage", mime_type="text/markdown")
def pipeline_review_usage() -> str:
    """Native skill resource for a requested pipeline review."""
    return (_PROJECT_ROOT / "skills/pipeline-reviewer/SKILL.md").read_text()


# Register custom domain tools
register_tools(mcp, _app)

# Startup hook: idempotently backfill ``belongs_to`` edges from ``deal.contact_name``
# so seeded deals show up under their contacts immediately. Re-running is a no-op
# because ``link_deals_to_contacts`` skips deals that already have a ``belongs_to``.
# Wrapped in try/except so a transient storage error does not prevent the server
# from starting — the tool is still callable on demand via MCP.
try:
    _link_result = link_deals_to_contacts(_app)
    logger.info(
        "link_deals_to_contacts startup: linked=%d skipped=%d",
        _link_result.get("linked", 0),
        _link_result.get("skipped", 0),
    )
except Exception:
    logger.exception("link_deals_to_contacts startup hook failed; continuing")

# UI resource — served to the platform as an iframe
_UI_HTML = (
    Path(os.environ.get("CRM_UI_DIR", str(_PROJECT_ROOT / "ui" / "dist")))
    / "index.html"
)


@mcp.resource("ui://crm/main", mime_type="text/html;profile=mcp-app")
def crm_ui() -> str:
    """The CRM app UI — rendered in the platform sidebar."""
    if _UI_HTML.exists():
        return _UI_HTML.read_text()
    return "<html><body><p>UI not built. Run <code>cd ui && npm run build</code>.</p></body></html>"


# ASGI entrypoint (uvicorn / nimbletools-core)
app = mcp.http_app()

if __name__ == "__main__":
    mcp.run()
