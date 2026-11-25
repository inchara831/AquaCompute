"""Tests for Person 2's water-footprint calculation integration contract."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.api.deps import get_footprint_service
from app.aws.cloudwatch import CloudWatchEc2Client
from app.core.config import Settings
from app.main import create_app
from app.models.footprint import FootprintEstimateResponse, FootprintInputsSummary
from app.services.footprint_bridge import FootprintBridgeService
from tests.test_cloudwatch_metrics import StubCloudWatchClient, StubEc2Client


class ExamplePerson2Calculator:
    """Test double verifying Person 2's WaterFootprintCalculator contract."""

    methodology_name = "test-documented-wue-method"

    def estimate(self, inputs: FootprintInputsSummary) -> FootprintEstimateResponse:
        energy_kwh = 0.05 * inputs.window_hours
        wue = 1.2
        return FootprintEstimateResponse(
            estimated_water_liters=energy_kwh * wue,
            estimated_energy_kwh=energy_kwh,
            wue_liters_per_kwh=wue,
            pue_factor=1.15,
            methodology_name=self.methodology_name,
            methodology_reference="Person 2 documented formula",
            assumptions=["Test fixture assumption"],
            inputs_used=inputs,
            calculated_at=datetime.now(timezone.utc),
        )


def test_footprint_returns_501_until_person2_integrates(
    configured_settings: Settings,
) -> None:
    app = create_app(configured_settings)
    client = TestClient(app)

    status_resp = client.get("/api/v1/footprint/status")
    assert status_resp.status_code == 200
    assert status_resp.json()["integrated"] is False

    est_resp = client.post("/api/v1/footprint/estimate", json={"window_hours": 1.0})
    assert est_resp.status_code == 501
    assert est_resp.json()["error"] == "footprint_calculator_not_integrated"


def test_footprint_bridge_delegates_when_calculator_registered(
    configured_settings: Settings,
) -> None:
    ts = datetime(2026, 11, 25, 12, 0, tzinfo=timezone.utc)
    cw = CloudWatchEc2Client(
        configured_settings,
        ec2_client=StubEc2Client(),
        cloudwatch_client=StubCloudWatchClient(
            results=[{"Id": "cpu_util", "Timestamps": [ts], "Values": [50.0]}]
        ),
    )
    bridge = FootprintBridgeService(configured_settings, cloudwatch_client=cw)
    bridge.register_calculator(ExamplePerson2Calculator())

    app = create_app(configured_settings)
    app.dependency_overrides[get_footprint_service] = lambda: bridge
    client = TestClient(app)

    resp = client.post("/api/v1/footprint/estimate", json={"window_hours": 2.0})
    assert resp.status_code == 200
    body = resp.json()
    assert body["data_classification"] == "calculated_estimate"
    assert body["is_live_aws_data"] is False
    assert body["is_calculated_estimate"] is True
    assert body["inputs_used"]["cpu_utilization_pct"] == 50.0
    assert body["estimated_water_liters"] == 0.12
