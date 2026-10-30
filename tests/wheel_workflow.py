"""Check an already-built wheel without installing it or using checkout assets.

Run with the project's Python environment: python tests/wheel_workflow.py <wheel>.
The subprocess uses synthetic data, and every CRM module must come from the wheel.
"""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import sysconfig
import tempfile
import zipfile

PROBE = r"""
import asyncio, hashlib, json, os
from pathlib import Path
import sys
from fastmcp import Client
from synapse_crm import assets, server

root = Path(os.environ["CRM_WHEEL_ROOT"]).resolve()
for name, module in tuple(sys.modules.items()):
    if name.startswith("synapse_crm") and getattr(module, "__file__", None):
        assert Path(module.__file__).resolve().is_relative_to(root), name
assert assets.asset_root().resolve() == root / "synapse_crm/assets"

async def exercise():
    async with Client(server.mcp) as client:
        tools = await client.list_tools()
        resources = await client.list_resources()
        for name in ["follow-up-coach", "pipeline-reviewer"]:
            text = (await client.read_resource(f"skill://{name}/usage"))[0].text
            assert text.startswith("---\n") and f"name: {name}\n" in text
        ui = (await client.read_resource("ui://crm/main"))[0]
        expected = assets.asset_root() / "ui/dist/index.html"
        assert ui.text.encode() == expected.read_bytes()
        assert ui.mimeType == "text/html;profile=mcp-app"
        created = await client.call_tool("find_or_create_contact", {"name": "Wheel example"})
        contact = json.loads(created.content[0].text)["contact"]
        fetched = await client.call_tool("get_contact", {"contact_id": contact["id"]})
        assert json.loads(fetched.content[0].text) == contact
        return {"tools": len(tools), "resources": len(resources), "skills": 2,
                "ui_sha256": hashlib.sha256(ui.text.encode()).hexdigest(),
                "workspace_write_read": True, "checkout_assets_used": False}

print(json.dumps(asyncio.run(exercise())))
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="crm-wheel-check-") as temporary:
        root = Path(temporary)
        package = root / "package"
        with zipfile.ZipFile(args.wheel.resolve()) as archive:
            archive.extractall(package)
        env = dict(os.environ)
        env.update(
            # Skip editable-install .pth files so they cannot shadow the wheel.
            PYTHONPATH=os.pathsep.join(
                dict.fromkeys(
                    [
                        str(package),
                        sysconfig.get_path("purelib"),
                        sysconfig.get_path("platlib"),
                    ]
                )
            ),
            PYTHONDONTWRITEBYTECODE="1",
            MPAK_WORKSPACE=str(root / "workspace"),
            UPJACK_ROOT=str(root / "workspace"),
            CRM_WHEEL_ROOT=str(package),
        )
        env.pop("CRM_UI_DIR", None)
        result = subprocess.run(
            [sys.executable, "-S", "-c", PROBE],
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
        )
        if result.returncode:
            sys.stderr.write(result.stdout + result.stderr)
            return result.returncode
        print(json.dumps(json.loads(result.stdout.strip().splitlines()[-1]), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
