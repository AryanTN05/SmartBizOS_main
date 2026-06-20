import uuid
from datetime import datetime
import asyncio
from sqlalchemy import select

from lara_smartbiz.utils.clients import get_openai_client
from lara_smartbiz.utils.clients import get_gemini_client
from db.connection import SessionLocal
from db.models import LaraMemory

async def embed(text: str) -> list[float]:
    openai_client = get_openai_client()
    response = await openai_client.embeddings.create(
        model="text-embedding-3-small",
        input=text
    )
    return response.data[0].embedding

async def search_memory(query: str, session_id: str, top_k: int = 5) -> list[str]:
    query_vector = await embed(query)
    
    async with SessionLocal() as session:
        stmt = (
            select(LaraMemory)
            .filter(LaraMemory.session_id == session_id)
            .order_by(LaraMemory.vector.cosine_distance(query_vector))
            .limit(top_k)
        )
        result = await session.execute(stmt)
        records = result.scalars().all()
        
        if not records:
            return []
        return [r.chunk_text for r in records]

def chunk_text(text: str, size: int = 500, overlap: int = 50) -> list[str]:
    words = text.split()
    chunks = []
    for i in range(0, len(words), size - overlap):
        chunk = " ".join(words[i:i + size])
        if chunk:
            chunks.append(chunk)
    return chunks

async def ingest_document(
    text: str,
    filename: str,
    session_id: str,
    *,
    size_bytes: int | None = None,
    mime_type: str | None = None,
    page_count: int | None = None,
    extraction_status: str = "ready",
    extraction_error: str | None = None,
) -> str:
    """Persist a document. Writes one row per chunk; per-document metadata
    (size, mime, pages, extraction outcome) is duplicated across chunks so
    the list endpoint can pull it via any chunk row.

    If extraction failed (status='failed' or text is empty), we still write
    one placeholder row so the document shows up in the list with the error
    chip — the user shouldn't have to wonder why their upload vanished."""
    file_id = str(uuid.uuid4())
    common = dict(
        session_id=session_id, source_type="document", source_id=file_id,
        filename=filename, size_bytes=size_bytes, mime_type=mime_type,
        page_count=page_count, extraction_status=extraction_status,
        extraction_error=extraction_error,
    )

    chunks = chunk_text(text, size=500, overlap=50) if text else []

    async with SessionLocal() as session:
        if not chunks:
            # Placeholder so the failure is visible in the UI rather than silent.
            session.add(LaraMemory(
                id=f"{file_id}_0", vector=[0.0] * 1536,
                chunk_text="", chunk_index=0, **common,
            ))
        else:
            for i, chunk in enumerate(chunks):
                vector = await embed(chunk)
                session.add(LaraMemory(
                    id=f"{file_id}_{i}", vector=vector,
                    chunk_text=chunk, chunk_index=i, **common,
                ))
        await session.commit()
    return file_id

async def extract_and_store_memory(conversation_turn: str, session_id: str):
    """
    Extract memory-worthy facts using a fast LLM and store them in Postgres pgvector.
    """
    gemini_client = get_gemini_client()
    
    prompt = f"""
    Extract 1-2 key facts worth remembering about the user or the context from this 
    conversation turn. Return only the facts as a single sentence each.
    If nothing is worth remembering, return "NONE".
    
    Turn: {conversation_turn}
    """
    
    try:
        response = await gemini_client.aio.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        fact = response.text.strip()
    except Exception as e:
        print(f"Error extracting memory: {e}")
        return
        
    if "NONE" in fact.upper() or not fact:
        return
        
    vector = await embed(fact)
    
    async with SessionLocal() as session:
        memory_record = LaraMemory(
            id=str(uuid.uuid4()),
            vector=vector,
            session_id=session_id,
            source_type="memory",
            source_id="conversation",
            chunk_text=fact,
            extracted_at=datetime.utcnow()
        )
        session.add(memory_record)
        await session.commit()
