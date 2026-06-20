from fastapi import APIRouter
import schemas

router = APIRouter(tags=["System"])

@router.get("/health", response_model=schemas.HealthResponse)
async def health_check():
    """
    Standard liveness probe. 
    Can be expanded later to check DB connectivity or Redis.
    """
    return {"status": "ok", "service": "smartbiz-os-api"}
