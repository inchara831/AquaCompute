"""Health check and non-secret configuration status schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    service: str
    version: str
    environment: str
    timestamp: datetime
    checks: dict[str, str] = Field(default_factory=dict)


class ConfigStatusResponse(BaseModel):
    configured_ready_for_live_ec2: bool
    configured_ready_for_aquamind: bool
    settings: dict[str, Any]
    missing_configuration: list[str] = Field(default_factory=list)
    setup_instructions: list[str] = Field(default_factory=list)
