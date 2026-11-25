"""Contract and schemas for Person 2's water-footprint calculation module."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class FootprintEstimateRequest(BaseModel):
    """Inputs for calculating estimated water footprint from live or supplied EC2 telemetry."""

    instance_id: str | None = None
    region: str | None = None
    use_live_metrics: bool = True
    window_hours: float = Field(default=1.0, gt=0.0, le=720.0)
    custom_cpu_utilization_pct: float | None = Field(default=None, ge=0.0, le=100.0)


class FootprintInputsSummary(BaseModel):
    instance_id: str
    region: str
    instance_type: str | None = None
    cpu_utilization_pct: float | None = None
    window_hours: float
    metrics_timestamp: datetime | None = None
    metrics_source: Literal["live_aws_cloudwatch", "caller_supplied"]


class FootprintEstimateResponse(BaseModel):
    """Output contract that Person 2's calculator must populate with documented methodology."""

    data_classification: Literal["calculated_estimate"] = "calculated_estimate"
    is_live_aws_data: bool = False
    is_calculated_estimate: bool = True
    estimated_water_liters: float = Field(..., ge=0.0)
    estimated_energy_kwh: float = Field(..., ge=0.0)
    wue_liters_per_kwh: float = Field(..., gt=0.0)
    pue_factor: float = Field(..., ge=1.0)
    methodology_name: str
    methodology_reference: str
    assumptions: list[str] = Field(default_factory=list)
    inputs_used: FootprintInputsSummary
    calculated_at: datetime


class FootprintStatusResponse(BaseModel):
    integrated: bool
    methodology_name: str | None = None
    message: str
    integration_instructions: str


@runtime_checkable
class WaterFootprintCalculator(Protocol):
    """Interface Person 2 implements and registers in `footprint_bridge.py`."""

    methodology_name: str

    def estimate(self, inputs: FootprintInputsSummary) -> FootprintEstimateResponse:
        """Compute documented water-footprint estimate from validated inputs."""
        ...
