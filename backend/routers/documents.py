"""
routers/documents.py — M1 Lara document & memory browser endpoints.

Documents are ingested via POST /lara-smartbiz/upload, chunked, embedded, and stored
in the shared `lara_memory` pgvector table. These endpoints surface that
table so admins can audit what's been remembered, by which session, and delete
entries on demand.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, Form
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import require_admin
from db.connection import get_db
from db.models import LaraMemory

router = APIRouter(
    prefix="/api",
    tags=["Documents"],
    dependencies=[Depends(require_admin)],
)


# ─────────────────────────────────────────
# Upload — alias of /lara-smartbiz/upload for the admin UI
# ─────────────────────────────────────────

@router.post("/documents/upload")
async def upload_document(file: UploadFile, session_id: str = Form(default="admin")):
    """Thin wrapper around /lara-smartbiz/upload so the admin UI's POST
    /api/documents/upload works without redirects.

    Extraction returns metadata (size/mime/page_count/status) which we
    persist so the DocumentsPage list can show file size, page count, and
    a status chip per row without a follow-up call."""
    from lara_smartbiz.services import extraction as extraction_service
    from lara_smartbiz.services import memory as memory_service

    contents = await file.read()
    meta = await extraction_service.extract(contents, file.content_type, file.filename or "")
    file_id = await memory_service.ingest_document(
        meta["text"], file.filename, session_id,
        size_bytes=meta["size_bytes"], mime_type=meta["mime_type"],
        page_count=meta["page_count"], extraction_status=meta["status"],
        extraction_error=meta["error"],
    )
    return {
        "id": file_id, "file_id": file_id,
        "filename": file.filename, "session_id": session_id,
        "size_bytes": meta["size_bytes"], "mime_type": meta["mime_type"],
        "page_count": meta["page_count"], "extraction_status": meta["status"],
        "extraction_error": meta["error"],
    }


# ─────────────────────────────────────────
# Documents: grouped by source_id when source_type == "document"
# ─────────────────────────────────────────

@router.get("/documents")
async def list_documents(
    session_id: Optional[str] = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """Return one row per uploaded document, with chunk count + filename."""
    # Aggregate by source_id and pull per-document metadata via max(). All
    # chunks of a given document share the same size/mime/page/status values
    # (set once at upload time), so max() is just a pick-any aggregate.
    stmt = (
        select(
            LaraMemory.source_id,
            LaraMemory.session_id,
            LaraMemory.filename,
            func.count(LaraMemory.id).label("chunk_count"),
            func.max(LaraMemory.extracted_at).label("uploaded_at"),
            func.max(LaraMemory.size_bytes).label("size_bytes"),
            func.max(LaraMemory.mime_type).label("mime_type"),
            func.max(LaraMemory.page_count).label("page_count"),
            func.max(LaraMemory.extraction_status).label("extraction_status"),
            func.max(LaraMemory.extraction_error).label("extraction_error"),
        )
        .where(LaraMemory.source_type == "document")
        .group_by(LaraMemory.source_id, LaraMemory.session_id, LaraMemory.filename)
        .order_by(func.max(LaraMemory.extracted_at).desc().nulls_last())
        .limit(limit)
    )
    if session_id:
        stmt = stmt.where(LaraMemory.session_id == session_id)
    result = await db.execute(stmt)
    rows = result.all()
    return {
        "items": [
            {
                "id": r.source_id,
                "session_id": r.session_id,
                "filename": r.filename,
                "chunk_count": r.chunk_count,
                "uploaded_at": r.uploaded_at.isoformat() if r.uploaded_at else None,
                "size_bytes": r.size_bytes,
                "mime_type": r.mime_type,
                "page_count": r.page_count,
                "extraction_status": r.extraction_status,
                "extraction_error": r.extraction_error,
            }
            for r in rows
        ],
        "next_cursor": None,
    }


@router.get("/documents/{document_id}")
async def get_document(document_id: str, db: AsyncSession = Depends(get_db)):
    stmt = (
        select(LaraMemory)
        .where(
            LaraMemory.source_type == "document",
            LaraMemory.source_id == document_id,
        )
        .order_by(LaraMemory.chunk_index)
    )
    result = await db.execute(stmt)
    chunks = result.scalars().all()
    if not chunks:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Document not found"})
    head = chunks[0]
    return {
        "id": document_id,
        "filename": head.filename,
        "session_id": head.session_id,
        "chunk_count": len(chunks),
        "chunks": [
            {"index": c.chunk_index, "text": c.chunk_text, "id": c.id}
            for c in chunks
        ],
    }


@router.delete("/documents/{document_id}", status_code=204)
async def delete_document(document_id: str, db: AsyncSession = Depends(get_db)):
    stmt = select(LaraMemory).where(
        LaraMemory.source_type == "document",
        LaraMemory.source_id == document_id,
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()
    if not rows:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Document not found"})
    for row in rows:
        await db.delete(row)
    await db.commit()
    return None


# ─────────────────────────────────────────
# Memory: any chunk regardless of source_type, with delete + browse
# ─────────────────────────────────────────

_MEMORY_KIND_TO_DB = {
    "fact": "memory",
    "doc_chunk": "document",
    "conversation_summary": "conversation",
}


def _shape_memory(r: LaraMemory) -> dict:
    """Map the LaraMemory row to the shape MemoryPage renders."""
    db_to_kind = {"memory": "fact", "document": "doc_chunk", "conversation": "conversation_summary"}
    kind = db_to_kind.get(r.source_type or "", "fact")
    if kind == "doc_chunk":
        source_ref = r.filename or r.source_id
    else:
        source_ref = r.source_id
    return {
        "id": r.id,
        "kind": kind,
        "content": r.chunk_text or "",
        "source_ref": source_ref,
        "session_id": r.session_id,
        "used_count": 0,                                   # not tracked yet — placeholder
        "extracted_at": r.extracted_at.isoformat() if r.extracted_at else None,
        # Legacy keys so older callers don't break:
        "source_type": r.source_type,
        "chunk_text": r.chunk_text,
        "filename": r.filename,
    }


@router.get("/admin/memory")
async def list_memory(
    session_id: Optional[str] = None,
    source_type: Optional[str] = None,
    kind: Optional[str] = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(LaraMemory).limit(limit).order_by(LaraMemory.extracted_at.desc().nulls_last())
    if session_id:
        stmt = stmt.where(LaraMemory.session_id == session_id)
    # Accept both `source_type` (legacy) and `kind` (frontend) — map kind to DB value.
    db_filter = source_type or _MEMORY_KIND_TO_DB.get(kind or "")
    if db_filter:
        stmt = stmt.where(LaraMemory.source_type == db_filter)
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return {"items": [_shape_memory(r) for r in rows], "next_cursor": None}


@router.delete("/admin/memory/{memory_id}", status_code=204)
async def delete_memory(memory_id: str, db: AsyncSession = Depends(get_db)):
    row = await db.get(LaraMemory, memory_id)
    if not row:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Memory not found"})
    await db.delete(row)
    await db.commit()
    return None
