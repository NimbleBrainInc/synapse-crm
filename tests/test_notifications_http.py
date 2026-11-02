"""CRM write notices follow the HTTP response mode and available streams."""

import asyncio
import secrets
import socket
import threading
import time

import fastmcp
import httpx
import pytest
import uvicorn
from fastmcp.server.auth.providers.debug import DebugTokenVerifier
from mcp.server.session import ServerSession

from tests.conftest import _run
from tests.test_notifications import LIST_CHANGED, _exercise


@pytest.mark.parametrize(
    ("settings_json_response", "json_response_override", "stateless_http", "authenticated"),
    [
        (False, None, False, False),
        (False, None, True, False),
        (True, None, False, False),
        (True, None, True, False),
        (False, True, False, False),
        (True, False, True, False),
        (False, True, False, True),
    ],
    ids=[
        "stateful-sse",
        "stateless-sse",
        "stateful-json",
        "stateless-json",
        "json-overrides-sse-setting",
        "stateless-sse-overrides-json-setting",
        "authenticated-json-overrides-sse-setting",
    ],
)
def test_write_notifications_reach_http_clients(
    mcp, monkeypatch, settings_json_response, json_response_override, stateless_http, authenticated
):
    monkeypatch.setattr(fastmcp.settings, "json_response", settings_json_response)
    monkeypatch.setattr(fastmcp.settings, "stateless_http", stateless_http)
    json_response = (
        settings_json_response if json_response_override is None else json_response_override
    )
    token = secrets.token_urlsafe(24)
    if authenticated:
        monkeypatch.setattr(mcp, "auth", DebugTokenVerifier(validate=lambda value: value == token))
    app = mcp.http_app(json_response=json_response_override)
    responses = []
    attempted_notices = []
    send_notification = ServerSession.send_notification

    async def record_notice(session, notification, related_request_id=None):
        if notification.root.method == LIST_CHANGED:
            attempted_notices.append(related_request_id)
        await send_notification(session, notification, related_request_id=related_request_id)

    monkeypatch.setattr(ServerSession, "send_notification", record_notice)

    async def observe_responses(scope, receive, send):
        async def record(message):
            if scope["type"] == "http" and message["type"] == "http.response.start":
                headers = dict(message.get("headers", []))
                responses.append(
                    (scope["method"], message["status"], headers.get(b"content-type", b""),
                     headers.get(b"mcp-session-id"))
                )
            await send(message)

        await app(scope, receive, record)

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        url = f"http://127.0.0.1:{port}/mcp"
        server = uvicorn.Server(
            uvicorn.Config(
                observe_responses,
                loop="asyncio",
                ws="none",
                log_level="critical",
                timeout_graceful_shutdown=1,
            )
        )
        thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 5
            while not server.started:
                assert thread.is_alive(), "HTTP server stopped before startup"
                assert time.monotonic() < deadline, "HTTP server did not start"
                time.sleep(0.01)
            if authenticated:
                assert httpx.get(url, timeout=2).status_code == 401

            async def wait_for_get():
                if json_response and not stateless_http:
                    deadline = time.monotonic() + 5
                    while not any(
                        method == "GET" and status == 200 for method, status, _, _ in responses
                    ):
                        assert time.monotonic() < deadline, "Standing GET stream did not connect"
                        await asyncio.sleep(0.01)
                    assert any(
                        method == "GET"
                        and status == 200
                        and content.startswith(b"text/event-stream")
                        for method, status, content, _ in responses
                    ), "Stateful JSON notifications need the standing GET stream"

            results, notices = _run(
                _exercise(
                    url,
                    [
                        ("create_deal", {"title": "HTTP deal", "error": "record field"}),
                        ("list_deals", {}),
                        ("create_deal", {"title": "Invalid", "value": -1}),
                        ("move_deal_stage", {"deal_id": "missing", "stage": "closed_won"}),
                    ],
                    auth=token if authenticated else None,
                    before_calls=wait_for_get,
                    # Stateless JSON has no stream for notices; writes still succeed.
                    notification_count=lambda: (
                        0 if stateless_http and json_response else len(attempted_notices)
                    ),
                )
            )
            created, read, invalid, missing = results
            assert not created.is_error and not read.is_error
            assert created.structured_content["error"] == "record field"
            assert invalid.is_error
            assert missing.structured_content == {"error": "Deal missing not found"}
            assert len(attempted_notices) == 2
            assert notices == (0 if stateless_http and json_response else 2)
            assert all((request_id is None) == json_response for request_id in attempted_notices)
            expected_type = b"application/json" if json_response else b"text/event-stream"
            posts = [
                (content, session_id)
                for method, status, content, session_id in responses
                if method == "POST" and status == 200
            ]
            assert posts and all(content.startswith(expected_type) for content, _ in posts)
            assert all((session_id is None) == stateless_http for _, session_id in posts)
        finally:
            server.should_exit = True
            thread.join(timeout=5)
            assert not thread.is_alive(), "HTTP server did not stop"
