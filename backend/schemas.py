from pydantic import BaseModel, EmailStr, ConfigDict, Field
from typing import Optional, List, Any
from datetime import datetime
from uuid import UUID


# ─────────────────────────────────────────
# HEALTH & SYSTEM SCHEMAS
# ─────────────────────────────────────────
class HealthResponse(BaseModel):
    status: str
    service: str


# ─────────────────────────────────────────
# VALID KANBAN STAGES
# ─────────────────────────────────────────
VALID_STAGES = ["New", "Contacted", "Qualified", "Meeting", "Proposal", "Won", "Lost"]

VALID_SOURCES = [
    "manual", "hubspot", "sheets", "zoho", "tally",
    "scraper_linkedin", "scraper_producthunt", "scraper_directory",
    "scraper_review", "scraper_reddit", "scraper_upwork",
    "lara", "jarvis", "website_widget", "integration",  # "jarvis" kept for back-compat with rows created before the rename
]


# ─────────────────────────────────────────
# LEAD SCHEMAS
# ─────────────────────────────────────────
class LeadBase(BaseModel):
    name: str
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    company_name: Optional[str] = None   # Human-readable e.g. "Stripe"
    company_domain: Optional[str] = None # Root domain e.g. "stripe.com"
    title: Optional[str] = None
    linkedin_url: Optional[str] = None
    source: Optional[str] = "manual"
    notes: Optional[str] = None
    tags: Optional[List[str]] = []


class LeadCreate(LeadBase):
    pass


class LeadUpdate(BaseModel):
    """Partial update — only provided fields are changed."""
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    company_name: Optional[str] = None
    company_domain: Optional[str] = None
    title: Optional[str] = None
    linkedin_url: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None
    tags: Optional[List[str]] = None


class LeadResponse(LeadBase):
    id: UUID
    tenant_id: UUID
    status: str
    score: int
    score_reason: Optional[str] = None
    source_ref_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    last_activity: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ─────────────────────────────────────────
# KANBAN MOVE
# ─────────────────────────────────────────
class KanbanMoveRequest(BaseModel):
    stage: str


class KanbanMoveResponse(BaseModel):
    lead: LeadResponse


# ─────────────────────────────────────────
# ACTIVITY TIMELINE
# ─────────────────────────────────────────
class ActivityResponse(BaseModel):
    id: UUID
    lead_id: UUID
    action_type: str
    description: Optional[str] = None
    metadata: Optional[Any] = Field(None, validation_alias="metadata_")
    triggered_by: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ActivityListResponse(BaseModel):
    items: List[ActivityResponse]
    total: int
