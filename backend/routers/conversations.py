"""
routers/conversations.py — M1 Lara conversation history endpoints.

These complement /lara-smartbiz/chat by exposing the persisted Conversation rows so the
admin sidebar at /admin/conversations can list, view, rename, and delete past
chat sessions. Backed by the Lara SQLite store (sync session via SessionLocal).
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc

from auth.dependencies import require_admin
from lara_smartbiz.db.connection import SessionLocal
from lara_smartbiz.db.models import Conversation

router = APIRouter(
    prefix="/api/conversations",
    tags=["Conversations"],
    dependencies=[Depends(require_admin)],
)


def _session_summary(session_id: str, rows: list[Conversation]) -> dict:
    first = rows[0] if rows else None
    last = rows[-1] if rows else None
    title = ""
    if first and first.content:
        title = first.content.strip().splitlines()[0][:80]
    return {
        "session_id": session_id,
        "title": title or "(empty session)",
        "message_count": len(rows),
        "started_at": first.created_at.isoformat() if first and first.created_at else None,
        "ended_at": last.created_at.isoformat() if last and last.created_at else None,
    }


@router.get("")
async def list_conversations(limit: int = 25):
    """Group persisted Conversation rows by session_id and return summaries."""
    with SessionLocal() as db:
        rows = (
            db.query(Conversation)
            .order_by(desc(Conversation.created_at))
            .limit(2000)
            .all()
        )
    grouped: dict[str, list[Conversation]] = {}
    for row in rows:
        grouped.setdefault(row.session_id, []).append(row)
    items = [_session_summary(sid, sorted(msgs, key=lambda m: m.created_at or 0)) for sid, msgs in grouped.items()]
    items.sort(key=lambda s: s["ended_at"] or "", reverse=True)
    return {"items": items[:limit], "next_cursor": None}


@router.get("/{session_id}")
async def get_conversation(session_id: str):
    with SessionLocal() as db:
        rows = (
            db.query(Conversation)
            .filter(Conversation.session_id == session_id)
            .order_by(Conversation.created_at)
            .all()
        )
    if not rows:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Conversation not found"})
    return {
        "session_id": session_id,
        "messages": [
            {
                "id": r.id,
                "role": r.role,
                "content": r.content,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
    }


@router.patch("/{session_id}")
async def rename_conversation(session_id: str, body: dict):
    """V0: titles are derived from the first message and not persisted as a
    distinct column. We accept the call so the UI's optimistic rename
    succeeds, but it has no effect after a refresh until we add a
    `conversations.title` column. Tracked for V1."""
    title = (body or {}).get("title")
    return {"session_id": session_id, "title": title, "persisted": False}


@router.delete("/{session_id}", status_code=204)
async def delete_conversation(session_id: str):
    with SessionLocal() as db:
        deleted = (
            db.query(Conversation)
            .filter(Conversation.session_id == session_id)
            .delete(synchronize_session=False)
        )
        db.commit()
    if not deleted:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Conversation not found"})
    return None
