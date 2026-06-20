import json
import asyncio
from typing import List, Union, Literal, Optional
from datetime import datetime
from pydantic import BaseModel
from fastapi import APIRouter, UploadFile, WebSocket, BackgroundTasks
from fastapi.responses import StreamingResponse

from lara_smartbiz.services import session as session_service
from lara_smartbiz.services import agent as agent_service
from lara_smartbiz.services import voice as voice_service
from lara_smartbiz.services import extraction as extraction_service
from lara_smartbiz.services import memory as memory_service
from lara_smartbiz.db.connection import SessionLocal
from lara_smartbiz.db.models import Conversation

router = APIRouter(prefix="/lara-smartbiz")

class TextInput(BaseModel):
    type: Literal["text"]
    content: str

class FileInput(BaseModel):
    type: Literal["file"]
    file_ids: List[str]
    accompanying_text: Optional[str] = None

class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str

class RequestContext(BaseModel):
    current_module: Optional[str] = None
    current_record_id: Optional[str] = None

class LaraRequest(BaseModel):
    session_id: str
    input: Union[TextInput, FileInput]
    history: List[Message]
    context: Optional[RequestContext] = None

@router.post("/session/create")
async def create_session():
    # Provide a dummy IP for local testing
    return await session_service.create_session("127.0.0.1")

async def post_process_memory(session_id: str, full_response: str):
    """
    Extracts key facts from the assistant's turn and stores them in Milvus
    for long-term semantic retrieval.
    """
    if not full_response or len(full_response.strip()) < 10:
        return
        
    await memory_service.extract_and_store_memory(full_response, session_id)

@router.post("/chat")
async def chat(request: LaraRequest, background_tasks: BackgroundTasks):
    async def event_generator():
        status = await session_service.check(request.session_id)
        if not status.valid:
            yield f"data: {json.dumps({'event': 'session_expired'})}\n\n"
            return
            
        # Build context
        recent_memory = []
        user_message_text = request.input.content if request.input.type == "text" else "Here are the files."
        
        if request.input.type == "text":
            recent_memory = await memory_service.search_memory(request.input.content, request.session_id)
            
        ctx = agent_service.AgentContext(
            session_id=request.session_id,
            messages=[{"role": m.role, "content": m.content} for m in request.history],
            system_prompt="",
            current_module=request.context.current_module if request.context else "",
            memory_snippets="\n".join(recent_memory),
            seed_context="Zerotoprod AI Consultancy Demo"
        )
        
        # We also need to append the current input message
        if request.input.type == "text":
            ctx.messages.append({"role": "user", "content": request.input.content})
        elif request.input.type == "file":
            text = f"Here are the files. {request.input.accompanying_text or ''}"
            ctx.messages.append({"role": "user", "content": text})

        full_response = ""
        async for chunk in agent_service.run(ctx):
            full_response += chunk
            yield f"data: {json.dumps({'token': chunk})}\n\n"
            await session_service.update_tokens(request.session_id, len(chunk))
            
        # Add a background task to process memory extraction
        background_tasks.add_task(post_process_memory, request.session_id, full_response)
        
        yield f"data: {json.dumps({'event': 'done'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no"}
    )

@router.post("/upload")
async def upload_file(file: UploadFile, session_id: str):
    contents = await file.read()
    meta = await extraction_service.extract(contents, file.content_type, file.filename or "")
    file_id = await memory_service.ingest_document(
        meta["text"], file.filename, session_id,
        size_bytes=meta["size_bytes"], mime_type=meta["mime_type"],
        page_count=meta["page_count"], extraction_status=meta["status"],
        extraction_error=meta["error"],
    )
    return {
        "file_id": file_id, "filename": file.filename,
        "size_bytes": meta["size_bytes"], "mime_type": meta["mime_type"],
        "page_count": meta["page_count"], "extraction_status": meta["status"],
        "extraction_error": meta["error"],
    }

@router.websocket("/voice")
async def voice(websocket: WebSocket, session_id: str):
    await websocket.accept()
    await voice_service.handle(websocket, session_id)
