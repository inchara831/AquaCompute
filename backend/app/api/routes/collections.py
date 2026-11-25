"""Stored collection records and on-demand collection trigger endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.api.deps import get_collection_service
from app.models.metrics import (
    CollectionHistoryResponse,
    CollectionRecord,
    CollectionRunStatus,
    CollectNowRequest,
)
from app.services.collector import MetricsCollectionService

router = APIRouter(prefix="/collections", tags=["Collection Pipeline"])


class CollectNowResponse(BaseModel):
    record: CollectionRecord
    run_status: CollectionRunStatus


@router.get("", response_model=CollectionHistoryResponse)
def list_collections(
    instance_id: str | None = Query(default=None),
    limit: int = Query(default=25, ge=1, le=200),
    service: MetricsCollectionService = Depends(get_collection_service),
) -> CollectionHistoryResponse:
    """List stored DynamoDB metric snapshots and latest collection run status."""
    return service.get_collection_history(instance_id=instance_id, limit=limit)


@router.post("/collect", response_model=CollectNowResponse)
def trigger_collection(
    payload: CollectNowRequest,
    service: MetricsCollectionService = Depends(get_collection_service),
) -> CollectNowResponse:
    """Collect live CloudWatch metrics now and persist the snapshot to DynamoDB/S3."""
    record, run_status = service.collect_and_store(
        instance_id=payload.instance_id,
        trigger="manual_api",
        export_to_s3=payload.export_to_s3,
    )
    return CollectNowResponse(record=record, run_status=run_status)
