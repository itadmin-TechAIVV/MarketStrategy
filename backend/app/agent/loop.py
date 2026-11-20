"""The agent turn: stream Gemini's reply, run tools, persist every message.

History is append-only, in a provider-neutral block format (see llm.py), with
Gemini's thought signatures kept on the blocks. A turn ends when the model
finishes, or when it calls ask_user: the question is stored as `pending_ask`,
and the user's answers become that tool call's result at the start of the next turn.
"""
from __future__ import annotations

import json
import logging
from datetime import timedelta
from typing import Any

from pymongo import ReturnDocument

from ..db import get_db, new_id, utcnow
from ..services.sections import MongoSectionStore, SectionService
from ..services.sources import active_sources
from . import llm
from .prompts import SYSTEM_PROMPT
from .stages import STAGE_BY_KEY, STAGES
from .tools import TOOL_LABELS, TOOLS, Emit, ToolContext, ToolFailure, run_tool, validate_input

log = logging.getLogger(__name__)

MAX_ITERATIONS = 20
LOCK_MINUTES = 10
BLOCKED_FINISH = {"SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "RECITATION", "IMAGE_SAFETY"}


class TurnBusy(Exception):
    pass


# ----------------------------------------------------------------- history
async def _load_history(org: str, ws: str) -> list[dict]:
    cur = get_db().messages.find({"organization_id": org, "workspace_id": ws}).sort("seq", 1)
    return [{"role": m["role"], "content": m["content"]} async for m in cur]


async def _append(org: str, ws: str, role: str, content: Any, display: list[dict]) -> None:
    db = get_db()
    last = await db.messages.find_one({"organization_id": org, "workspace_id": ws}, sort=[("seq", -1)])
    seq = (last["seq"] + 1) if last else 1
    await db.messages.insert_one(
        {
            "_id": new_id(),
            "organization_id": org,
            "workspace_id": ws,
            "seq": seq,
            "role": role,
            "content": content,
            "display": display,
            "created_at": utcnow(),
        }
    )


async def _state_message(org: str, workspace: dict) -> str:
    ws = workspace["_id"]
    svc = SectionService(MongoSectionStore(get_db(), org), org, ws)
    sections = {d["key"]: d for d in await svc.store.list(ws)}
    statuses = await svc.stage_statuses()
    lines = [
        "<workspace_state>",
        f"product: {workspace['product_name']}",
        f"website: {workspace['website_url']}",
        f"current_stage: {workspace.get('current_stage', 'brief')}",
        f"stored_sources: {len(await active_sources(org, ws))}",
        "stages:",
    ]
    for st in STAGES:
        avail = "" if st.ready else " (not available yet)"
        lines.append(f"- {st.key}: {statuses[st.key]}{avail}")
        for sec in st.sections:
            d = sections.get(sec.key)
            if d:
                extra = f", needs refresh because {d['refresh_reason']}" if d["status"] == "needs_refresh" else ""
                edited = ", edited by user" if d.get("user_edited") else ""
                lines.append(f"    - {sec.key}: {d['status']}, confidence {d['confidence']}{edited}{extra}")
    lines.append("</workspace_state>")
    return "\n".join(lines)


def _answers_text(ask: dict, answers: dict) -> str:
    parts = []
    for q in ask["questions"]:
        a = answers.get(q["id"]) or {}
        chosen = a.get("selected") or []
        free = (a.get("text") or "").strip()
        val = "; ".join(chosen + ([free] if free else [])) or "(no answer)"
        parts.append(f"{q['text']} -> {val}")
    return "\n".join(parts)


async def _repair_tail(org: str, ws: str) -> list[dict]:
    """If an earlier turn failed midway, make the history valid again.

    - A trailing system message that never got a reply is removed (a system
      message must be followed by an assistant turn).
    - Tool calls left without results get error results.
    """
    db = get_db()
    last = await db.messages.find_one({"organization_id": org, "workspace_id": ws}, sort=[("seq", -1)])
    if last and last["role"] == "system":
        await db.messages.delete_one({"_id": last["_id"]})
        last = await db.messages.find_one({"organization_id": org, "workspace_id": ws}, sort=[("seq", -1)])
    if last and last["role"] == "assistant":
        return [
            {"type": "tool_result", "tool_use_id": b["id"], "is_error": True,
             "content": json.dumps({"error": "Interrupted before this tool ran."})}
            for b in last["content"]
            if isinstance(b, dict) and b.get("type") == "tool_use"
        ]
    return []


# ----------------------------------------------------------------- locking
async def _acquire(org: str, ws: str) -> dict:
    now = utcnow()
    doc = await get_db().workspaces.find_one_and_update(
        {
            "_id": ws,
            "organization_id": org,
            "$or": [{"turn_lock_until": None}, {"turn_lock_until": {"$lt": now}}, {"turn_lock_until": {"$exists": False}}],
        },
        {"$set": {"turn_lock_until": now + timedelta(minutes=LOCK_MINUTES)}},
        return_document=ReturnDocument.AFTER,
    )
    if doc is None:
        raise TurnBusy("The agent is already working on this workspace")
    return doc


async def _release(org: str, ws: str) -> None:
    await get_db().workspaces.update_one({"_id": ws, "organization_id": org}, {"$set": {"turn_lock_until": None, "updated_at": utcnow()}})


# -------------------------------------------------------------------- turn
async def run_turn(org: str, ws: str, text: str | None, answers: dict | None, emit: Emit) -> None:
    """Run one user turn. Raises TurnBusy if another turn is running."""
    workspace = await _acquire(org, ws)
    try:
        await _run(org, workspace, text, answers, emit)
    except llm.LLMError as exc:
        await emit({"type": "error", "message": str(exc)})
    except RuntimeError as exc:
        await emit({"type": "error", "message": str(exc)})
    except Exception:
        log.exception("agent turn failed")
        await emit({"type": "error", "message": "Something went wrong in the agent. Please try again."})
    finally:
        await _release(org, ws)
        await emit({"type": "done"})


async def _run(org: str, workspace: dict, text: str | None, answers: dict | None, emit: Emit) -> None:
    db = get_db()
    ws = workspace["_id"]
    llm.get_client()  # fail fast, before saving anything, if the API key is missing

    # 1. Build the user message (answers to a pending question, notes from the app, the user's text).
    content: list[dict] = []
    display: list[dict] = []
    pending = workspace.get("pending_ask")
    if not pending:
        content.extend(await _repair_tail(org, ws))
    if pending:
        content.extend(pending.get("other_results", []))
        if answers:
            summary = _answers_text(pending["ask"], answers)
            result = {"answers": answers, "summary": summary}
            if text:
                result["note"] = text
            display.append({"kind": "answer", "text": summary + (f"\n{text}" if text else "")})
        else:
            result = {"answers": {}, "note": text or "", "summary": "The user replied in chat instead of choosing options."}
            if text:
                display.append({"kind": "text", "text": text})
        content.append({"type": "tool_result", "tool_use_id": pending["tool_use_id"], "content": json.dumps(result)})
    notes = workspace.get("pending_notes") or []
    for note in notes:
        content.append({"type": "text", "text": f"[app] {note}"})
    if text and not pending:
        content.append({"type": "text", "text": text})
        display.append({"kind": "text", "text": text})
    if not content:
        content.append({"type": "text", "text": "[app] The user opened the workspace. Continue where you left off."})

    await _append(org, ws, "user", content, display)
    await db.workspaces.update_one({"_id": ws, "organization_id": org}, {"$set": {"pending_ask": None, "pending_notes": []}})
    workspace["pending_ask"] = None

    # 2. Fresh workspace state for the agent, as a mid-conversation system message.
    await _append(org, ws, "system", await _state_message(org, workspace), [])

    ctx = ToolContext(organization_id=org, workspace=workspace, emit=emit)

    async def on_text(text: str) -> None:
        await emit({"type": "text", "text": text})

    async def on_tool(name: str) -> None:
        await emit({"type": "tool", "name": name, "status": "start", "label": TOOL_LABELS.get(name, name)})

    retries = 0
    for _ in range(MAX_ITERATIONS):
        history = await _load_history(org, ws)
        reply = await llm.stream_reply(history, SYSTEM_PROMPT, TOOLS, on_text, on_tool)
        await emit({"type": "block_end"})
        blocks = reply.blocks

        if reply.block_reason or reply.finish_reason in BLOCKED_FINISH:
            log.warning("Gemini blocked the reply: %s %s", reply.block_reason, reply.finish_reason)
            await emit({"type": "error", "message": "The AI declined to continue this request. Try rephrasing."})
            return
        if not blocks:
            # Empty or malformed reply (Gemini occasionally returns nothing): ask again, a bounded number of times.
            retries += 1
            if retries > 2:
                raise RuntimeError("The AI returned an empty reply. Please send your message again.")
            continue
        retries = 0

        texts = [b["text"] for b in blocks if b.get("type") == "text" and b.get("text", "").strip()]
        asks = [b for b in blocks if b.get("type") == "tool_use" and b.get("name") == "ask_user"]
        assistant_display = [{"kind": "text", "text": t} for t in texts]
        await _append(org, ws, "assistant", blocks, assistant_display)

        tool_uses = [b for b in blocks if b.get("type") == "tool_use"]
        if not tool_uses:
            if reply.finish_reason == "MAX_TOKENS":
                raise RuntimeError("The agent's reply was cut off. Please ask it to continue.")
            return

        results: list[dict] = []
        ask_block = asks[0] if asks else None
        ask_payload = None
        for b in tool_uses:
            if b is ask_block:
                try:
                    ask_payload = validate_input("ask_user", b["input"]).model_dump()
                except ToolFailure as exc:
                    results.append({"type": "tool_result", "tool_use_id": b["id"], "is_error": True, "content": json.dumps({"error": str(exc)})})
                    ask_block = None
                continue
            if b["name"] == "ask_user":
                results.append({"type": "tool_result", "tool_use_id": b["id"], "is_error": True,
                                "content": json.dumps({"error": "Only one ask_user call per turn; combine questions."})})
                continue
            out, is_error = await run_tool(ctx, b["name"], b["input"])
            await emit({"type": "tool", "name": b["name"], "status": "error" if is_error else "done",
                        "label": TOOL_LABELS.get(b["name"], b["name"])})
            item = {"type": "tool_result", "tool_use_id": b["id"], "content": out}
            if is_error:
                item["is_error"] = True
            results.append(item)

        if ask_block is not None and ask_payload is not None:
            pending = {"tool_use_id": ask_block["id"], "ask": ask_payload, "other_results": results, "asked_at": utcnow()}
            await db.workspaces.update_one({"_id": ws, "organization_id": org}, {"$set": {"pending_ask": pending}})
            # Keep the question in the transcript display.
            await db.messages.update_one(
                {"organization_id": org, "workspace_id": ws},
                {"$push": {"display": {"kind": "ask", "ask": ask_payload}}},
                sort=[("seq", -1)],
            )
            await emit({"type": "ask", "ask": ask_payload})
            return

        await _append(org, ws, "user", results, [])

    await emit({"type": "error", "message": "The agent took too many steps in one turn. Send a message to continue."})


def stage_title(key: str) -> str:
    st = STAGE_BY_KEY.get(key)
    return st.title if st else key
