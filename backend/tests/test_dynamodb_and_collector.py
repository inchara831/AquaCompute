"""Tests for DynamoDB persistence, S3 archival, and collection pipeline."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_collection_service
from app.aws.cloudwatch import CloudWatchEc2Client
from app.aws.dynamodb import DynamoDbRepository
from app.aws.s3 import S3StorageClient
from app.core.config import Settings
from app.core.exceptions import AwsPermissionError
from app.main import create_app
from app.services.collector import MetricsCollectionService
from tests.conftest import InMemoryDynamoResource, make_client_error
from tests.test_cloudwatch_metrics import StubCloudWatchClient, StubEc2Client


class StubS3Client:
    def __init__(self) -> None:
        self.uploads: list[dict[str, Any]] = []

    def put_object(self, **kwargs: Any) -> dict[str, Any]:
        self.uploads.append(kwargs)
        return {"ETag": '"test-etag"'}


def test_collect_and_list_collections_with_s3_export(configured_settings: Settings) -> None:
    ts = datetime(2026, 11, 25, 11, 0, tzinfo=timezone.utc)
    cw = CloudWatchEc2Client(
        configured_settings,
        ec2_client=StubEc2Client(),
        cloudwatch_client=StubCloudWatchClient(
            results=[{"Id": "cpu_util", "Timestamps": [ts], "Values": [31.25]}]
        ),
    )
    dynamo_res = InMemoryDynamoResource()
    repo = DynamoDbRepository(configured_settings, dynamodb_resource=dynamo_res)
    s3_stub = StubS3Client()
    s3 = S3StorageClient(configured_settings, s3_client=s3_stub)
    service = MetricsCollectionService(
        configured_settings,
        cloudwatch_client=cw,
        dynamodb_repo=repo,
        s3_client=s3,
    )

    app = create_app(configured_settings)
    app.dependency_overrides[get_collection_service] = lambda: service
    client = TestClient(app)

    post_resp = client.post("/api/v1/collections/collect", json={"export_to_s3": True})
    assert post_resp.status_code == 200
    post_data = post_resp.json()
    assert post_data["run_status"]["status"] == "success"
    assert post_data["record"]["s3_report_key"].startswith("reports/")
    assert len(s3_stub.uploads) == 1

    get_resp = client.get("/api/v1/collections")
    assert get_resp.status_code == 200
    history = get_resp.json()
    assert history["latest_run"]["status"] == "success"
    assert len(history["records"]) == 1
    assert history["records"][0]["metrics"]["CPUUtilization"]["value"] == 31.25


def test_failed_collection_persists_failed_run_status(configured_settings: Settings) -> None:
    cw = CloudWatchEc2Client(
        configured_settings,
        ec2_client=StubEc2Client(error=make_client_error("AccessDenied")),
        cloudwatch_client=StubCloudWatchClient(),
    )
    dynamo_res = InMemoryDynamoResource()
    repo = DynamoDbRepository(configured_settings, dynamodb_resource=dynamo_res)
    service = MetricsCollectionService(
        configured_settings,
        cloudwatch_client=cw,
        dynamodb_repo=repo,
    )

    with pytest.raises(AwsPermissionError):
        service.collect_and_store(trigger="eventbridge_lambda")

    latest = repo.get_latest_run_status(configured_settings.ec2_instance_id)
    assert latest is not None
    assert latest.status == "failed"
    assert latest.trigger == "eventbridge_lambda"
    assert latest.records_stored == 0
