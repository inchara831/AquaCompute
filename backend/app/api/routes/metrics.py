"""Live Amazon CloudWatch EC2 metrics endpoints."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_cloudwatch_client
from app.aws.cloudwatch import CloudWatchEc2Client
from app.models.metrics import CurrentMetricsResponse, HistoricalMetricsResponse

router = APIRouter(prefix="/metrics", tags=["EC2 CloudWatch Metrics"])


@router.get("/current", response_model=CurrentMetricsResponse)
def get_current_metrics(
    instance_id: str | None = Query(
        default=None,
        description="Optional EC2 instance ID (i-...). Defaults to configured EC2_INSTANCE_ID.",
    ),
    cw: CloudWatchEc2Client = Depends(get_cloudwatch_client),
) -> CurrentMetricsResponse:
    """Fetch live EC2 metadata and latest CloudWatch telemetry."""
    return cw.get_current_metrics(instance_id=instance_id)


@router.get("/history", response_model=HistoricalMetricsResponse)
def get_historical_metrics(
    instance_id: str | None = Query(
        default=None,
        description="Optional EC2 instance ID (i-...). Defaults to configured EC2_INSTANCE_ID.",
    ),
    start_time: datetime | None = Query(
        default=None,
        description="ISO-8601 UTC start timestamp (defaults to 6 hours ago).",
    ),
    end_time: datetime | None = Query(
        default=None,
        description="ISO-8601 UTC end timestamp (defaults to now).",
    ),
    period_seconds: int | None = Query(
        default=None,
        ge=60,
        le=3600,
        description="CloudWatch aggregation period in seconds (multiple of 60).",
    ),
    cw: CloudWatchEc2Client = Depends(get_cloudwatch_client),
) -> HistoricalMetricsResponse:
    """Fetch time-series CloudWatch metrics for the requested time range."""
    try:
        return cw.get_historical_metrics(
            instance_id=instance_id,
            start_time=start_time,
            end_time=end_time,
            period_seconds=period_seconds,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
