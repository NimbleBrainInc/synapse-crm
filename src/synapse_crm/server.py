"""CRM MCP server built with Upjack + FastMCP.

Tier 2: Auto-generated entity CRUD from manifest (contacts, deals, interactions).
Tier 3: Custom domain tools for pipeline management and interaction tracking.
"""

import logging
import os
from pathlib import Path

from fastmcp.server.middleware import Middleware
from mcp.types import ResourceListChangedNotification
from upjack.app import UpjackApp
from upjack.server import create_server

from synapse_crm.tools import register_tools
from synapse_crm.tools.link_deals_to_contacts import link_deals_to_contacts

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).parent.parent.parent
manifest_path = _PROJECT_ROOT / "manifest.json"
workspace_root = os.environ.get("MPAK_WORKSPACE", "./workspace")
mcp = create_server(manifest_path, root=workspace_root)

# Append CRM-specific instructions
mcp._mcp_server.instructions = (
    (mcp.instructions or "")
    + "\n\nCRITICAL — CRM Tools: "
    "Use find_or_create_contact() to add contacts — it deduplicates automatically. "
    "Use log_interaction() to create interactions — it auto-wires the contact relationship. "
    "Use move_deal_stage() for stage changes — it handles close date and probability. "
    "Use pipeline_summary() for aggregate metrics. "
    "Use contact_timeline() to review interaction history."
)

# Load app instance for custom tools
_app = UpjackApp.from_manifest(manifest_path, root=workspace_root)

# Register custom domain tools
register_tools(mcp, _app)

# Tools that change CRM records, beyond the create_*, update_* and delete_* CRUD tools.
WRITE_TOOLS = frozenset(
    {
        "find_or_create_contact",
        "log_interaction",
        "move_deal_stage",
        "link_deals_to_contacts",
        "seed_data",
        "add_field",
    }
)


def is_write_tool(name: str) -> bool:
    """Whether a call to the named tool may change CRM records."""
    return name in WRITE_TOOLS or name.startswith(("create_", "update_", "delete_"))


def is_error_result(content: object) -> bool:
    """Whether a tool returned the domain error shape, {"error": ...}.

    add_field also adds "diagnostics". A record may carry its own "error"
    field, so the key alone does not mark a failure.
    """
    return (
        isinstance(content, dict)
        and "error" in content
        and set(content) <= {"error", "diagnostics"}
    )


class NotifyAfterWrites(Middleware):
    """Send resources/list_changed once after each successful write tool call.

    A UI on @nimblebrain/synapse 0.35 or later refetches its data when this
    notification arrives. Reads send nothing. A call that raises, or that
    returns the domain error shape, sends nothing. The notification is best
    effort: the write is already saved, so a failed send is logged and the
    call still reports success.
    """

    async def on_call_tool(self, context, call_next):
        result = await call_next(context)
        ctx = context.fastmcp_context
        name = context.message.name
        if ctx and is_write_tool(name) and not is_error_result(result.structured_content):
            try:
                await ctx.send_notification(ResourceListChangedNotification())
            except Exception:
                logger.warning(
                    "Could not send resources/list_changed after %s", name, exc_info=True
                )
        return result


mcp.add_middleware(NotifyAfterWrites())

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
_UI_HTML = _PROJECT_ROOT / "ui" / "dist" / "index.html"


@mcp.resource("ui://crm/main")
def crm_ui() -> str:
    """The CRM app UI — rendered in the platform sidebar."""
    if _UI_HTML.exists():
        return _UI_HTML.read_text()
    return "<html><body><p>UI not built. Run <code>cd ui && npm run build</code>.</p></body></html>"


# ASGI entrypoint (uvicorn / nimbletools-core)
app = mcp.http_app()

if __name__ == "__main__":
    mcp.run()
