"""Chat endpoint: runs one agent turn and streams its events as Server-Sent Events.

The turn runs as its own task, so it finishes and saves its state even if the
browser disconnects. A comment line is sent every 15 s to keep proxies from
closing an idle stream.
"""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..agent.loop import TurnBusy, run_turn
from ..auth import Tenant, get_tenant
from ..db import utcnow
from .workspaces import load_workspace

router = APIRouter(prefix="/api/workspaces", tags=["chat"])
HEARTBEAT_SECONDS = 15
_running_turns: set[asyncio.Task] = set()


class Answer(BaseModel):
    selected: list[str] = Field(default_factory=list)
    text: str = ""


class ChatIn(BaseModel):
    text: str | None = Field(default=None, max_length=20_000)
    answers: dict[str, Answer] | None = None


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, default=str)}\n\n"


@router.post("/{workspace_id}/chat")
async def chat(workspace_id: str, body: ChatIn, tenant: Tenant = Depends(get_tenant)):
    ws = await load_workspace(tenant, workspace_id)
    if ws.get("turn_lock_until") and ws["turn_lock_until"] > utcnow():
        raise HTTPException(status.HTTP_409_CONFLICT, "The agent is already working on this workspace")

    queue: asyncio.Queue[dict | None] = asyncio.Queue()

    async def emit(event: dict) -> None:
        await queue.put(event)

    answers = {k: v.model_dump() for k, v in body.answers.items()} if body.answers else None

    async def runner() -> None:
        try:
            await run_turn(tenant.organization_id, workspace_id, body.text, answers, emit)
        except TurnBusy as exc:
            await emit({"type": "error", "message": str(exc)})
            await emit({"type": "done"})
        finally:
            await queue.put(None)

    task = asyncio.create_task(runner())

    _running_turns.add(task)  # keep a reference: if the client disconnects, the turn still finishes
    task.add_done_callback(_running_turns.discard)

    async def stream():
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SECONDS)
            except asyncio.TimeoutError:
                yield ": ping\n\n"
                continue
            if event is None:
                break
            yield _sse(event)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
