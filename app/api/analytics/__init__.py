"""Analytics router — delegates to AnalyticsService."""
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.session import get_db
from app.services.analytics_service import AnalyticsService

router = APIRouter(prefix="/analytics", tags=["Analytics"])


async def _analytics_service(db: AsyncSession = Depends(get_db)) -> AnalyticsService:
    return AnalyticsService(db)


@router.get("/overview")
async def get_overview(tenant_id: str, svc: AnalyticsService = Depends(_analytics_service)):
    try:
        return await svc.get_overview(tenant_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get overview: {str(e)}")


@router.get("/campaigns/{campaign_id}/performance")
async def get_campaign_performance(campaign_id: str, svc: AnalyticsService = Depends(_analytics_service)):
    try:
        return await svc.get_campaign_performance(campaign_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get campaign performance: {str(e)}")


@router.get("/leads")
async def get_lead_stats(tenant_id: str, svc: AnalyticsService = Depends(_analytics_service)):
    try:
        return await svc.get_lead_stats(tenant_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get lead stats: {str(e)}")
