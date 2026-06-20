import uuid
from datetime import datetime
from pydantic import BaseModel

class SessionStatus(BaseModel):
    valid: bool
    reason: str = ""
    tokens_remaining: int = 2000
    seconds_remaining: int = 300

# In-memory session store for local demo
_SESSIONS = {}

DEMO_LIMITS = {
    "max_tokens": 5000,
    "max_seconds": 600,
    "model": "gemini-3.1-flash-lite-preview"
}

async def create_session(ip: str) -> dict:
    session_id = str(uuid.uuid4())
    _SESSIONS[session_id] = {
        "session_id": session_id,
        "started_at": datetime.utcnow(),
        "tokens_used": 0,
        "requests_made": 0,
        "ip": ip,
        "model": DEMO_LIMITS["model"]
    }
    return {"allowed": True, "session_id": session_id}

async def check(session_id: str) -> SessionStatus:
    if session_id not in _SESSIONS:
        return SessionStatus(valid=False, reason="session_expired")
    
    session = _SESSIONS[session_id]
    elapsed = (datetime.utcnow() - session["started_at"]).total_seconds()
    
    if session["tokens_used"] >= DEMO_LIMITS["max_tokens"]:
        return SessionStatus(valid=False, reason="token_limit")
        
    if elapsed >= DEMO_LIMITS["max_seconds"]:
        return SessionStatus(valid=False, reason="time_limit")
        
    return SessionStatus(
        valid=True,
        tokens_remaining=DEMO_LIMITS["max_tokens"] - session["tokens_used"],
        seconds_remaining=int(DEMO_LIMITS["max_seconds"] - elapsed)
    )

async def update_tokens(session_id: str, tokens: int):
    if session_id in _SESSIONS:
        _SESSIONS[session_id]["tokens_used"] += tokens
        _SESSIONS[session_id]["requests_made"] += 1
