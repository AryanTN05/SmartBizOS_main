from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from db.connection import get_db
from db.models import Lead
import schemas

router = APIRouter(prefix="/api/public", tags=["Public API"])

@router.post("/capture-lead", response_model=schemas.LeadResponse)
async def capture_website_lead(
    lead: schemas.LeadCreate,
    # TODO(security): tenant_id as an unsigned query param means anyone can POST leads to any tenant. Needs origin verification or signed tokens before production.
    tenant_id: UUID = Query(..., description="The unique public ID of the tenant's workspace"),
    db: AsyncSession = Depends(get_db)
):
    """
    Public endpoint for capturing leads from an embedded website widget.
    Forces the source to 'website_widget'.
    """
    lead_data = lead.model_dump()
    lead_data["source"] = "website_widget"
    
    new_lead = Lead(**lead_data, tenant_id=tenant_id)
    db.add(new_lead)
    await db.commit()
    await db.refresh(new_lead)
    
    return new_lead
