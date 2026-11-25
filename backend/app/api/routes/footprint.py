"""Water footprint estimation API contract (Person 2 integration point)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_footprint_service
from app.models.footprint import (
    FootprintEstimateRequest,
    FootprintEstimateResponse,
    FootprintStatusResponse,
)
from app.services.footprint_bridge import FootprintBridgeService

router = APIRouter(prefix="/footprint", tags=["Water Footprint (Person 2 Contract)"])


@router.get("/status", response_model=FootprintStatusResponse)
def footprint_status(
    service: FootprintBridgeService = Depends(get_footprint_service),
) -> FootprintStatusResponse:
    """Check whether Person 2's water-footprint calculation module is integrated."""
    return service.get_status()


@router.post("/estimate", response_model=FootprintEstimateResponse)
def estimate_footprint(
    payload: FootprintEstimateRequest,
    service: FootprintBridgeService = Depends(get_footprint_service),
) -> FootprintEstimateResponse:
    """Compute estimated water footprint via Person 2's registered module (returns 501 until integrated)."""
    return service.estimate(payload)
