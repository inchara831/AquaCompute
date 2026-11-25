"""Service health and non-secret configuration status endpoints."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from app.api.deps import get_footprint_service
from app.core.config import Settings, get_settings
from app.models.health import ConfigStatusResponse, HealthResponse
from app.services.footprint_bridge import FootprintBridgeService

router = APIRouter(tags=["Health & Configuration"])


@router.get("/health", response_model=HealthResponse)
def health_check(
    settings: Settings = Depends(get_settings),
    footprint: FootprintBridgeService = Depends(get_footprint_service),
) -> HealthResponse:
    """Report backend liveness and readiness of AWS/Bedrock/Person 2 integrations."""
    ec2_ready = settings.is_aws_region_configured and settings.is_ec2_configured
    footprint_status = footprint.get_status()
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.app_env,
        timestamp=datetime.now(timezone.utc),
        checks={
            "api": "ok",
            "aws_ec2_target": "configured" if ec2_ready else "not_configured",
            "s3_bucket": "configured" if settings.is_s3_configured else "not_configured",
            "bedrock_kb": "configured" if settings.is_bedrock_configured else "not_configured",
            "footprint_calculator": "integrated" if footprint_status.integrated else "not_integrated",
        },
    )


@router.get("/config/status", response_model=ConfigStatusResponse)
def config_status(settings: Settings = Depends(get_settings)) -> ConfigStatusResponse:
    """Expose sanitized configuration readiness and setup steps without secrets."""
    missing: list[str] = []
    instructions: list[str] = []

    if not settings.is_aws_region_configured:
        missing.append("AWS_REGION")
        instructions.append("Set AWS_REGION to your authorized AWS region (e.g., us-east-1).")
    if not settings.is_ec2_configured:
        missing.append("EC2_INSTANCE_ID")
        instructions.append("Set EC2_INSTANCE_ID to your target EC2 instance ID (i-...).")
    if not settings.is_s3_configured:
        missing.append("S3_BUCKET_NAME")
        instructions.append("Set S3_BUCKET_NAME to store reports and AquaMind RAG documents.")
    if not settings.is_bedrock_configured:
        missing.append("BEDROCK_KB_ID")
        instructions.append(
            "Set BEDROCK_KB_ID, BEDROCK_MODEL_ID, and BEDROCK_REGION after provisioning your Bedrock Knowledge Base."
        )

    return ConfigStatusResponse(
        configured_ready_for_live_ec2=(
            settings.is_aws_region_configured and settings.is_ec2_configured
        ),
        configured_ready_for_aquamind=settings.is_bedrock_configured,
        settings=settings.safe_status_summary(),
        missing_configuration=missing,
        setup_instructions=instructions,
    )
