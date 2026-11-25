"""Shared pytest fixtures for AquaCompute backend tests."""

from __future__ import annotations

from typing import Any

import pytest
from botocore.exceptions import ClientError

from app.core.config import Settings


def make_client_error(code: str, message: str = "Simulated AWS error") -> ClientError:
    """Construct a genuine botocore ClientError for error-handling tests."""
    return ClientError(
        error_response={"Error": {"Code": code, "Message": message}},
        operation_name="SimulatedOperation",
    )


@pytest.fixture()
def unconfigured_settings() -> Settings:
    """Settings matching `.env.example` placeholders (nothing configured)."""
    return Settings(
        _env_file=None,
        app_env="test",
        aws_region="<YOUR_AWS_REGION>",
        ec2_instance_id="<YOUR_EC2_INSTANCE_ID>",
        s3_bucket_name="<YOUR_AQUACOMPUTE_S3_BUCKET>",
        bedrock_region="<YOUR_BEDROCK_REGION>",
        bedrock_kb_id="",
    )


@pytest.fixture()
def configured_settings() -> Settings:
    """Valid test settings using standard AWS test-safe syntax (not real resources)."""
    return Settings(
        _env_file=None,
        app_env="test",
        aws_region="us-east-1",
        ec2_instance_id="i-0123456789abcdef0",
        s3_bucket_name="aquacompute-test-bucket",
        bedrock_region="us-east-1",
        bedrock_kb_id="KBTEST1234",
        bedrock_model_id="anthropic.claude-3-haiku-20240307-v1:0",
    )


class InMemoryDynamoTable:
    """Minimal in-memory DynamoDB Table double for unit tests."""

    def __init__(self, items: list[dict[str, Any]] | None = None) -> None:
        self.items: list[dict[str, Any]] = list(items or [])

    def put_item(self, Item: dict[str, Any]) -> dict[str, Any]:
        self.items.append(Item)
        return {"ResponseMetadata": {"HTTPStatusCode": 200}}

    def query(self, **kwargs: Any) -> dict[str, Any]:
        limit = kwargs.get("Limit", 25)
        ordered = sorted(self.items, key=lambda x: x.get("collected_at", ""), reverse=True)
        return {"Items": ordered[:limit]}

    def scan(self, **kwargs: Any) -> dict[str, Any]:
        limit = kwargs.get("Limit", 50)
        return {"Items": self.items[:limit]}


class InMemoryDynamoResource:
    """Maps DynamoDB table names to InMemoryDynamoTable instances."""

    def __init__(self) -> None:
        self.tables: dict[str, InMemoryDynamoTable] = {}

    def Table(self, name: str) -> InMemoryDynamoTable:
        if name not in self.tables:
            self.tables[name] = InMemoryDynamoTable()
        return self.tables[name]
