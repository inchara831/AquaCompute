"""Pluggable bridge for Person 2's water-footprint calculation module."""

from __future__ import annotations

from app.aws.cloudwatch import CloudWatchEc2Client
from app.core.config import Settings
from app.core.exceptions import FootprintNotIntegratedError
from app.models.footprint import (
    FootprintEstimateRequest,
    FootprintEstimateResponse,
    FootprintInputsSummary,
    FootprintStatusResponse,
    WaterFootprintCalculator,
)


class FootprintBridgeService:
    """Routes footprint requests to Person 2's calculator when registered.

    Person 1 intentionally does NOT invent a water-consumption formula or output
    synthetic water numbers before Person 2 integrates a documented model.
    """

    def __init__(
        self,
        settings: Settings,
        *,
        cloudwatch_client: CloudWatchEc2Client,
        calculator: WaterFootprintCalculator | None = None,
    ) -> None:
        self._settings = settings
        self._cw = cloudwatch_client
        self._calculator = calculator

    def register_calculator(self, calculator: WaterFootprintCalculator) -> None:
        """Allow Person 2's module to plug in an implementation at startup."""
        self._calculator = calculator

    def get_status(self) -> FootprintStatusResponse:
        if self._calculator is None:
            return FootprintStatusResponse(
                integrated=False,
                methodology_name=None,
                message=(
                    "Water-footprint calculation module is not yet integrated (Person 2 scope). "
                    "No water-consumption values are fabricated by the backend."
                ),
                integration_instructions=(
                    "Implement `WaterFootprintCalculator` from `app.models.footprint` with a "
                    "documented WUE/PUE power-to-water methodology and register it via "
                    "`FootprintBridgeService.register_calculator(...)`."
                ),
            )
        return FootprintStatusResponse(
            integrated=True,
            methodology_name=self._calculator.methodology_name,
            message="Person 2 water-footprint calculator is integrated and ready.",
            integration_instructions="POST /api/v1/footprint/estimate with window_hours and instance_id.",
        )

    def estimate(self, request: FootprintEstimateRequest) -> FootprintEstimateResponse:
        if self._calculator is None:
            raise FootprintNotIntegratedError(
                "Water-footprint calculation module is not integrated yet. "
                "Person 2 must implement and register `WaterFootprintCalculator` before water estimates can be computed.",
                details={
                    "contract": "app.models.footprint.WaterFootprintCalculator",
                    "status_endpoint": "/api/v1/footprint/status",
                },
            )

        if request.use_live_metrics:
            live = self._cw.get_current_metrics(instance_id=request.instance_id)
            cpu_point = live.metrics.get("CPUUtilization")
            inputs = FootprintInputsSummary(
                instance_id=live.instance.instance_id,
                region=live.instance.region,
                instance_type=live.instance.instance_type,
                cpu_utilization_pct=cpu_point.value if cpu_point else None,
                window_hours=request.window_hours,
                metrics_timestamp=cpu_point.timestamp if cpu_point else live.collected_at,
                metrics_source="live_aws_cloudwatch",
            )
        else:
            region = request.region or self._settings.aws_region.strip()
            instance_id = request.instance_id or self._settings.ec2_instance_id.strip()
            inputs = FootprintInputsSummary(
                instance_id=instance_id,
                region=region,
                instance_type=None,
                cpu_utilization_pct=request.custom_cpu_utilization_pct,
                window_hours=request.window_hours,
                metrics_timestamp=None,
                metrics_source="caller_supplied",
            )

        return self._calculator.estimate(inputs)
