"""AquaCompute FastAPI application entrypoint."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import aquamind, collections, footprint, health, metrics
from app.aws.clients import get_aws_client
from app.core.config import Settings, get_settings
from app.core.exceptions import AquaComputeError
from app.core.logging import CloudWatchLogHandler, configure_logging, redact_secrets

logger = logging.getLogger("aquacompute.main")


def _build_cloudwatch_handler(settings: Settings) -> CloudWatchLogHandler | None:
    if not settings.cloudwatch_logs_enabled:
        return None
    if not settings.is_aws_region_configured:
        return None
    try:
        logs_client = get_aws_client(settings, "logs")
        return CloudWatchLogHandler(
            logs_client,
            settings.cloudwatch_log_group,
            settings.cloudwatch_log_stream,
        )
    except Exception:
        return None


def create_app(settings: Settings | None = None) -> FastAPI:
    """Application factory enabling isolated test configuration."""
    resolved = settings or get_settings()
    cw_handler = _build_cloudwatch_handler(resolved)
    configure_logging(resolved.log_level, cloudwatch_handler=cw_handler)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        logger.info(
            "Starting AquaCompute backend",
            extra={
                "extra_fields": {
                    "environment": resolved.app_env,
                    "aws_region_configured": resolved.is_aws_region_configured,
                    "ec2_configured": resolved.is_ec2_configured,
                    "bedrock_configured": resolved.is_bedrock_configured,
                }
            },
        )
        yield

    application = FastAPI(
        title="AquaCompute Backend API",
        description=(
            "Person 1 Cloud, Backend & RAG API for monitoring real AWS EC2 CloudWatch telemetry "
            "and grounding sustainability insights with Amazon Bedrock Knowledge Bases."
        ),
        version=resolved.app_version,
        lifespan=lifespan,
    )

    if settings is not None:
        application.dependency_overrides[get_settings] = lambda: resolved

    application.add_middleware(
        CORSMiddleware,
        allow_origins=resolved.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.exception_handler(AquaComputeError)
    async def handle_domain_error(_: Request, exc: AquaComputeError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": exc.error_code,
                "message": redact_secrets(exc.message),
                "details": exc.details,
            },
        )

    @application.get("/", include_in_schema=False)
    def root() -> dict[str, str]:
        return {
            "service": resolved.app_name,
            "docs": "/docs",
            "health": "/api/v1/health",
        }

    api_prefix = "/api/v1"
    application.include_router(health.router, prefix=api_prefix)
    application.include_router(metrics.router, prefix=api_prefix)
    application.include_router(collections.router, prefix=api_prefix)
    application.include_router(footprint.router, prefix=api_prefix)
    application.include_router(aquamind.router, prefix=api_prefix)

    return application


app = create_app()
