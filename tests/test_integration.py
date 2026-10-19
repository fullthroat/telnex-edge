"""Pre-call integration tests for the Edge Function.

These tests exercise the same HTTP paths used by the assistant, without
spending telephony credits or requiring a live phone call.  Run with:
    python -m pytest -q
"""
import asyncio
import json
import os
import sys
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from function.func import Function

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    # The ASGI smoke test is portable; Selector avoids a Windows Proactor
    # self-pipe hang in some embedded Python environments.
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@contextmanager
def test_settings():
    names = {
        "REQUIRE_WEBHOOK_SIGNATURE": "false",
        "STATE_BACKEND": "memory",
        "ALLOW_IN_MEMORY_STATE": "true",
        "ACTOR_BASE_URL": "",
        "KV_NAMESPACE_ID": "",
        "TELNYX_API_KEY": "",
        "MCP_AUTH_TOKEN": "",
    }
    previous = {name: os.environ.get(name) for name in names}
    os.environ.update(names)
    try:
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


async def request(fn, method, path, payload=None):
    body = b"" if payload is None else json.dumps(payload).encode()
    messages = [{"type": "http.request", "body": body, "more_body": False}]
    sent = []

    async def receive():
        return messages.pop(0)

    async def send(message):
        sent.append(message)

    await fn.handle({
        "type": "http", "method": method, "path": path,
        "headers": [[b"content-type", b"application/json"]],
    }, receive, send)
    status = next(item["status"] for item in sent if item["type"] == "http.response.start")
    raw = next(item["body"] for item in sent if item["type"] == "http.response.body")
    return status, json.loads(raw)


def test_full_function_workflow_without_phone_call():
    """Cover health, webhook variables, MCP, information, callback, transfer and metrics."""
    with test_settings():
        fn = Function()

        status, readiness = asyncio.run(request(fn, "GET", "/health/readiness"))
        assert status == 200 and readiness["ready"] is True

        status, variables = asyncio.run(request(fn, "POST", "/webhook", {
            "id": "event-1", "payload": {"call_control_id": "call-test", "language": "sv-SE"}
        }))
        assert status == 200 and variables["dynamic_variables"]["language"] == "sv-SE"

        status, info = asyncio.run(request(fn, "POST", "/api/information", {
            "session_id": "call-test", "topic": "declaration", "language": "sv-SE"
        }))
        assert status == 200 and "Allmän information" in info["result"]["answer"]

        status, callback = asyncio.run(request(fn, "POST", "/api/callback", {
            "session_id": "call-test", "callback_name": "Test Caller",
            "callback_number": "+46700000000", "language": "sv-SE"
        }))
        assert status == 200 and callback["result"]["status"] == "queued"

        status, transfer = asyncio.run(request(fn, "POST", "/api/transfer", {
            "session_id": "call-test", "language": "sv-SE"
        }))
        assert status == 200 and transfer["result"]["queue"] == "live_tax_assistance"

        session = asyncio.run(fn._session("call-test"))
        assert session["callback_name"] == "Test Caller"
        assert session["transfer_status"] == "queued"

        status, metrics = asyncio.run(request(fn, "GET", "/metrics"))
        assert status == 200
        assert metrics["counters"]["callback_requests_total"] == 1
        assert metrics["counters"]["human_transfer_requests_total"] == 1

        sent = []

        async def send(message):
            sent.append(message)

        asyncio.run(fn._mcp(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
            "name": "lookup_tax_information", "arguments": {"topic": "deadlines", "language": "en-US"}
        }}).encode(), {}, send))
        mcp_response = json.loads(sent[-1]["body"])
        assert mcp_response["result"]["content"]


if __name__ == "__main__":
    test_full_function_workflow_without_phone_call()
    print("PASS: Edge Function pre-call integration test")
