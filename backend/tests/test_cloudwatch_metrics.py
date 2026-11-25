"""Tests for CloudWatch EC2 metrics retrieval, missing datapoints, and AWS error handling."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from botocore.exceptions import NoCredentialsError
from fastapi.testclient import TestClient

from app.api.deps import get_cloudwatch_client
from app.aws.cloudwatch import CloudWatchEc2Client
from app.core.config import Settings
from app.main import create_app
from tests.conftest import make_client_error


class StubEc2Client:
    def __init__(self, *, error: Exception | None = None) -> None:
        self._error = error

    def describe_instances(self, InstanceIds: list[str]) -> dict[str, Any]:
        if self._error:
            raise self._error
        return {
            "Reservations": [
                {
                    "Instances": [
                        {
                            "InstanceId": InstanceIds[0],
                            "InstanceType": "t3.micro",
                            "State": {"Name": "running"},
                            "Placement": {"AvailabilityZone": "us-east-1a"},
                            "PlatformDetails": "Linux/UNIX",
                        }
                    ]
                }
            ]
        }


class StubCloudWatchClient:
    def __init__(
        self,
        *,
        results: list[dict[str, Any]] | None = None,
        error: Exception | None = None,
    ) -> None:
        self._results = results or []
        self._error = error

    def get_metric_data(self, **kwargs: Any) -> dict[str, Any]:
        if self._error:
            raise self._error
        return {"MetricDataResults": self._results}


def test_current_metrics_handles_partial_and_unavailable_metrics(
    configured_settings: Settings,
) -> None:
    ts = datetime(2026, 11, 25, 10, 0, tzinfo=timezone.utc)
    cw_stub = StubCloudWatchClient(
        results=[
            {"Id": "cpu_util", "Timestamps": [ts], "Values": [24.5]},
            {"Id": "net_in", "Timestamps": [ts], "Values": [102400.0]},
            {"Id": "disk_read_ops", "Timestamps": [], "Values": []},
        ]
    )
    service = CloudWatchEc2Client(
        configured_settings,
        ec2_client=StubEc2Client(),
        cloudwatch_client=cw_stub,
    )

    app = create_app(configured_settings)
    app.dependency_overrides[get_cloudwatch_client] = lambda: service
    client = TestClient(app)

    resp = client.get("/api/v1/metrics/current")
    assert resp.status_code == 200
    body = resp.json()
    assert body["data_classification"] == "live_aws_data"
    assert body["is_live_aws_data"] is True
    assert body["is_calculated_estimate"] is False
    assert body["is_demo_data"] is False
    assert body["instance"]["instance_type"] == "t3.micro"
    assert body["metrics"]["CPUUtilization"]["status"] == "available"
    assert body["metrics"]["CPUUtilization"]["value"] == 24.5
    assert body["metrics"]["DiskReadOps"]["status"] == "unavailable"
    assert body["metrics"]["DiskReadOps"]["value"] is None


def test_missing_permissions_returns_403(configured_settings: Settings) -> None:
    service = CloudWatchEc2Client(
        configured_settings,
        ec2_client=StubEc2Client(error=make_client_error("UnauthorizedOperation")),
        cloudwatch_client=StubCloudWatchClient(),
    )
    app = create_app(configured_settings)
    app.dependency_overrides[get_cloudwatch_client] = lambda: service
    client = TestClient(app)

    resp = client.get("/api/v1/metrics/current")
    assert resp.status_code == 403
    assert resp.json()["error"] == "aws_permission_denied"


def test_missing_credentials_returns_503(configured_settings: Settings) -> None:
    service = CloudWatchEc2Client(
        configured_settings,
        ec2_client=StubEc2Client(error=NoCredentialsError()),
        cloudwatch_client=StubCloudWatchClient(),
    )
    app = create_app(configured_settings)
    app.dependency_overrides[get_cloudwatch_client] = lambda: service
    client = TestClient(app)

    resp = client.get("/api/v1/metrics/current")
    assert resp.status_code == 503
    assert resp.json()["error"] == "aws_credentials_unavailable"


def test_throttling_returns_429(configured_settings: Settings) -> None:
    service = CloudWatchEc2Client(
        configured_settings,
        ec2_client=StubEc2Client(),
        cloudwatch_client=StubCloudWatchClient(error=make_client_error("ThrottlingException")),
    )
    app = create_app(configured_settings)
    app.dependency_overrides[get_cloudwatch_client] = lambda: service
    client = TestClient(app)

    resp = client.get("/api/v1/metrics/current")
    assert resp.status_code == 429
    assert resp.json()["error"] == "aws_throttled"


def test_instance_not_found_returns_404(configured_settings: Settings) -> None:
    service = CloudWatchEc2Client(
        configured_settings,
        ec2_client=StubEc2Client(error=make_client_error("InvalidInstanceID.NotFound")),
        cloudwatch_client=StubCloudWatchClient(),
    )
    app = create_app(configured_settings)
    app.dependency_overrides[get_cloudwatch_client] = lambda: service
    client = TestClient(app)

    resp = client.get("/api/v1/metrics/current")
    assert resp.status_code == 404
    assert resp.json()["error"] == "resource_not_found"


def test_unconfigured_instance_returns_503(unconfigured_settings: Settings) -> None:
    app = create_app(unconfigured_settings)
    client = TestClient(app)

    resp = client.get("/api/v1/metrics/current")
    assert resp.status_code == 503
    assert resp.json()["error"] == "configuration_required"


def test_historical_metrics_invalid_time_range_returns_422(
    configured_settings: Settings,
) -> None:
    service = CloudWatchEc2Client(
        configured_settings,
        ec2_client=StubEc2Client(),
        cloudwatch_client=StubCloudWatchClient(),
    )
    app = create_app(configured_settings)
    app.dependency_overrides[get_cloudwatch_client] = lambda: service
    client = TestClient(app)

    now = datetime.now(timezone.utc)
    resp = client.get(
        "/api/v1/metrics/history",
        params={
            "start_time": (now + timedelta(hours=1)).isoformat(),
            "end_time": now.isoformat(),
        },
    )
    assert resp.status_code == 422
