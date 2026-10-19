import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from function.func import Function


def test_tax_information_is_bilingual_and_general():
    fn = Function()
    en = asyncio.run(fn.information("declaration", "en-US"))
    sv = asyncio.run(fn.information("deklaration", "sv-SE"))
    assert "General information" in en["answer"]
    assert "Allmän information" in sv["answer"]
    assert "individual tax advice" in en["disclaimer"]


def test_callback_persists_name_and_number():
    fn = Function()
    result = asyncio.run(fn.callback("call-1", "Ada Example", "+46700000000", "en-US"))
    session = asyncio.run(fn._session("call-1"))
    assert result["status"] == "queued"
    assert session["callback_name"] == "Ada Example"
    assert session["callback_number"] == "+46700000000"


def test_mcp_lists_four_tools():
    fn = Function()
    sent = []

    async def send(message):
        sent.append(message)

    asyncio.run(fn._mcp(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).encode(), {}, send))
    body = json.loads(sent[-1]["body"])
    assert len(body["result"]["tools"]) == 4
