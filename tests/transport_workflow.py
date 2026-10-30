"""Disposable HTTP and stdio acceptance for a source checkout.

Run with the project's locked Python environment. Uses synthetic data and
terminates its own loopback server before exiting.
"""

import asyncio
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time

from fastmcp import Client
from fastmcp.client.transports import StdioTransport
from mcp.types import ServerNotification

ROOT = Path(__file__).resolve().parents[1]


async def exercise(transport, prior_id=None):
    notices = []
    changed = asyncio.Event()

    async def on_message(message):
        if (
            isinstance(message, ServerNotification)
            and message.root.method == "notifications/resources/list_changed"
        ):
            notices.append(message.root.method)
            changed.set()

    async with Client(transport, message_handler=on_message) as client:
        assert len(await client.list_tools()) == 35
        assert len(await client.list_resources()) == 6
        if prior_id:
            previous = await client.call_tool("get_deal", {"deal_id": prior_id})
            assert (
                json.loads(previous.content[0].text)["title"] == "HTTP persisted deal"
            )
        await client.call_tool("list_deals", {"limit": None})
        await asyncio.sleep(0.1)
        assert notices == []
        created = await client.call_tool(
            "create_deal",
            {"title": "Stdio persisted deal" if prior_id else "HTTP persisted deal"},
        )
        record = json.loads(created.content[0].text)
        await asyncio.wait_for(changed.wait(), timeout=3)
        assert notices == ["notifications/resources/list_changed"]
        await client.call_tool("pipeline_summary", {})
        failed = await client.call_tool(
            "update_deal", {"deal_id": record["id"], "value": -1}, raise_on_error=False
        )
        assert failed.is_error
        await asyncio.sleep(0.1)
        assert len(notices) == 1
        observed = await client.call_tool("get_deal", {"deal_id": record["id"]})
        assert json.loads(observed.content[0].text) == record
        return {
            "id": record["id"],
            "tools": 35,
            "resources": 6,
            "write_notifications": len(notices),
            "read_notifications": 0,
        }


def main():
    evidence = Path(tempfile.mkdtemp(prefix="crm-native-transport-"))
    workspace = evidence / "workspace"
    blocked = evidence / "without-upjack"
    blocked.mkdir()
    (blocked / "upjack.py").write_text(
        "raise ImportError('Upjack must not be imported by the native CRM server')\n"
    )
    env = {
        key: os.environ[key]
        for key in ["PATH", "HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "TMPDIR"]
        if key in os.environ
    }
    env.update(
        MPAK_WORKSPACE=str(workspace),
        UPJACK_ROOT=str(workspace),
        PYTHONPATH=os.pathsep.join([str(blocked), str(ROOT / "src")]),
        PYTHONDONTWRITEBYTECODE="1",
    )
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    with (evidence / "http.log").open("w") as log:
        child = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "synapse_crm.server:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=ROOT,
            env=env,
            stdout=log,
            stderr=log,
        )
    try:
        for _ in range(100):
            if child.poll() is not None:
                raise RuntimeError(f"CRM exited; inspect {evidence / 'http.log'}")
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                    break
            except OSError:
                time.sleep(0.1)
        else:
            raise RuntimeError("CRM did not listen on its test port")
        http = asyncio.run(exercise(f"http://127.0.0.1:{port}/mcp"))
    finally:
        child.terminate()
        child.wait(timeout=10)
    with (evidence / "stdio.log").open("w") as log:
        transport = StdioTransport(
            command=sys.executable,
            args=["-m", "synapse_crm.server"],
            env=env,
            cwd=str(ROOT),
            log_file=log,
        )
        stdio = asyncio.run(exercise(transport, prior_id=http["id"]))
    receipt = {
        "http": http,
        "stdio": stdio,
        "restart_preserved_http_record": True,
        "upjack_import_blocked": True,
        "evidence": str(evidence),
    }
    (evidence / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
