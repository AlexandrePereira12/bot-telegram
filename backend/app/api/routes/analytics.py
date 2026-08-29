"""Endpoints de analytics do dashboard."""

from typing import Any

from fastapi import APIRouter, Depends, Query

from app.api.deps import SessionDep, require
from app.models import Operator
from app.services import analytics_service

router = APIRouter(prefix="/analytics", tags=["analytics"])

AnalyticsRead = Depends(require("analytics:read"))
Days = Query(default=30, ge=1, le=365)


@router.get("/overview")
async def overview(
    session: SessionDep, _: Operator = AnalyticsRead, days: int = Days
) -> dict[str, Any]:
    return await analytics_service.overview(session, days)


@router.get("/funnel")
async def funnel(
    session: SessionDep, _: Operator = AnalyticsRead, days: int = Days
) -> list[dict[str, Any]]:
    return await analytics_service.funnel(session, days)


@router.get("/campaigns")
async def campaigns(
    session: SessionDep, _: Operator = AnalyticsRead, days: int = Days
) -> list[dict[str, Any]]:
    return await analytics_service.campaigns_performance(session, days)


@router.get("/ads")
async def ads(
    session: SessionDep, _: Operator = AnalyticsRead, days: int = Days
) -> list[dict[str, Any]]:
    return await analytics_service.ads_performance(session, days)


@router.get("/timeseries")
async def timeseries(
    session: SessionDep, _: Operator = AnalyticsRead, days: int = Days
) -> list[dict[str, Any]]:
    return await analytics_service.timeseries(session, days)


@router.get("/states")
async def states(session: SessionDep, _: Operator = AnalyticsRead) -> dict[str, int]:
    return await analytics_service.state_distribution(session)
