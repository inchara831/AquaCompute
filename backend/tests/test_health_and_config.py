"""Tests for health checks, placeholder validation, and configuration status."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings
from app.main import create_app


def test_placeholders_reported_as_unconfigured(unconfigured_settings: Settings) -> None:
    app = create_app(unconfigured_settings)
    client = TestClient(app)

    health = client.get("/api/v1/health")
    assert health.status_code == 200
    body = health.json()
    assert body["checks"]["aws_ec2_target"] == "not_configured"
    assert body["checks"]["s3_bucket"] == "not_configured"
    assert body["checks"]["bedrock_kb"] == "not_configured"
    assert body["checks"]["footprint_calculator"] == "not_integrated"

    cfg = client.get("/api/v1/config/status")
    assert cfg.status_code == 200
    cfg_body = cfg.json()
    assert cfg_body["configured_ready_for_live_ec2"] is False
    assert cfg_body["configured_ready_for_aquamind"] is False
    assert "AWS_REGION" in cfg_body["missing_configuration"]
    assert "EC2_INSTANCE_ID" in cfg_body["missing_configuration"]
    assert cfg_body["settings"]["ec2_instance_id"] is None


def test_configured_settings_status(configured_settings: Settings) -> None:
    app = create_app(configured_settings)
    client = TestClient(app)

    cfg = client.get("/api/v1/config/status")
    assert cfg.status_code == 200
    data = cfg.json()
    assert data["configured_ready_for_live_ec2"] is True
    assert data["configured_ready_for_aquamind"] is True
    assert data["missing_configuration"] == []


def test_invalid_cloudwatch_period_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, cloudwatch_metric_period_seconds=45)
