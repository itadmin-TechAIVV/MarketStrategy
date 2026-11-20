"""Gemini adapter: history conversion and reply parsing. No network, no API key."""
from __future__ import annotations

import base64
import json

from google.genai import types

from app.agent.llm import function_declarations, parts_to_blocks, to_contents
from app.agent.tools import TOOLS

SIG = base64.b64encode(b"sig-bytes").decode()


def test_reply_parts_become_blocks_with_signatures():
    parts = [
        types.Part(text="Hello "),
        types.Part(text="there."),
        types.Part(function_call=types.FunctionCall(name="crawl_site", args={"force": False}), thought_signature=b"sig-bytes"),
        types.Part(function_call=types.FunctionCall(name="read_sources", args={}, id="g-2")),
        types.Part(text="hidden reasoning", thought=True),
        types.Part(text="   "),
    ]
    blocks = parts_to_blocks(parts)
    assert blocks[0] == {"type": "text", "text": "Hello there."}
    assert blocks[1]["type"] == "tool_use" and blocks[1]["name"] == "crawl_site"
    assert blocks[1]["thought_signature"] == SIG and blocks[1]["gemini_id"] is None and blocks[1]["id"].startswith("call_")
    assert blocks[2]["id"] == "g-2" and blocks[2]["gemini_id"] == "g-2"
    assert len(blocks) == 3  # thought and blank text dropped
    json.dumps(blocks)  # storable in MongoDB as plain JSON


def test_history_round_trip_keeps_calls_responses_and_signatures():
    history = [
        {"role": "user", "content": [{"type": "text", "text": "Study acme.com"}]},
        {"role": "system", "content": "<workspace_state>\nproduct: Acme\n</workspace_state>"},
        {"role": "assistant", "content": [
            {"type": "text", "text": "Reading it now."},
            {"type": "tool_use", "id": "call_1", "gemini_id": None, "name": "crawl_site", "input": {}, "thought_signature": SIG},
        ]},
        {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "call_1", "content": json.dumps({"pages_stored": 3})},
        ]},
        {"role": "assistant", "content": [
            {"type": "tool_use", "id": "call_2", "name": "ask_user", "input": {"questions": []}},
        ]},
        {"role": "user", "content": [
            {"type": "text", "text": "[app] The user edited a section."},
            {"type": "tool_result", "tool_use_id": "call_2", "content": "not json", "is_error": True},
        ]},
    ]
    contents = to_contents(history)
    assert [c.role for c in contents] == ["user", "model", "user", "model", "user"]
    # user text + workspace state merged into one user turn
    assert contents[0].parts[0].text == "Study acme.com" and "workspace_state" in contents[0].parts[1].text
    call = contents[1].parts[1]
    assert call.function_call.name == "crawl_site" and call.thought_signature == b"sig-bytes"
    resp = contents[2].parts[0].function_response
    assert resp.name == "crawl_site" and resp.response == {"pages_stored": 3}
    # function responses are moved before text in a user turn; errors are wrapped
    last = contents[4].parts
    assert last[0].function_response.name == "ask_user"
    assert last[0].function_response.response == {"error": {"result": "not json"}}
    assert last[1].text.startswith("[app]")


def test_legacy_blocks_from_older_provider_are_ignored():
    history = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": [{"type": "thinking", "thinking": "x", "signature": "y"}, {"type": "text", "text": "Hello"}]},
    ]
    contents = to_contents(history)
    assert contents[1].parts[0].text == "Hello" and len(contents[1].parts) == 1


def test_every_tool_converts_to_a_gemini_declaration():
    decls = function_declarations(TOOLS)
    assert {d.name for d in decls} == {t["name"] for t in TOOLS}
    assert "research_web" in {d.name for d in decls}
    assert all(d.parameters_json_schema["type"] == "object" for d in decls)
