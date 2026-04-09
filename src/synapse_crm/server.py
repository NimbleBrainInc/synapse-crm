"""CRM MCP server built with Upjack + FastMCP.

Tier 2: Auto-generated entity CRUD from manifest (contacts, deals, interactions).
Tier 3: Custom domain tools for pipeline management and interaction tracking.
"""

import os
from pathlib import Path

from upjack.app import UpjackApp
from upjack.server import create_server

from synapse_crm.tools import register_tools

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
