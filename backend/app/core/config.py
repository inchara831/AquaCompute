"""Application configuration loaded from environment variables or .env."""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_PLACEHOLDER_PATTERN = re.compile(r"^<YOUR_.*>$")
_EC2_ID_PATTERN = re.compile(r"^i-[0-9a-fA-F]{8,17}$")
_AWS_REGION_PATTERN = re.compile(r"^[a-z]{2}(-[a-z]+)+-\d+$")


def _is_placeholder(value: str | None) -> bool:
    if value is None:
        return True
    stripped = value.strip()
    return not stripped or bool(_PLACEHOLDER_PATTERN.match(stripped))


class Settings(BaseSettings):
    """Environment-driven settings with non-secret status helpers."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "AquaCompute"
    app_env: Literal["development", "staging", "production", "test"] = "development"
    app_version: str = "0.1.0"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    cors_allow_origins: str = "http://localhost:5173,http://localhost:3000"

    # AWS auth & target EC2
    aws_region: str = ""
    aws_profile: str = ""
    ec2_instance_id: str = ""
    polling_interval_seconds: int = Field(default=300, ge=60, le=86400)
    cloudwatch_metric_period_seconds: int = Field(default=300, ge=60, le=3600)
    max_history_hours: int = Field(default=168, ge=1, le=720)

    # DynamoDB
    dynamodb_readings_table: str = "AquaComputeReadings"
    dynamodb_runs_table: str = "AquaComputeCollectionRuns"
    dynamodb_endpoint_url: str = ""

    # S3
    s3_bucket_name: str = ""
    s3_reports_prefix: str = "reports/"
    s3_rag_docs_prefix: str = "rag-docs/"

    # CloudWatch Logs
    cloudwatch_logs_enabled: bool = False
    cloudwatch_log_group: str = "/aquacompute/backend"
    cloudwatch_log_stream: str = "api-service"

    # Amazon Bedrock Knowledge Bases (AquaMind RAG)
    bedrock_region: str = ""
    bedrock_kb_id: str = ""
    bedrock_model_id: str = "anthropic.claude-3-haiku-20240307-v1:0"
    bedrock_top_k: int = Field(default=5, ge=1, le=20)
    bedrock_max_tokens: int = Field(default=700, ge=64, le=4096)
    bedrock_temperature: float = Field(default=0.2, ge=0.0, le=1.0)

    @field_validator("cloudwatch_metric_period_seconds")
    @classmethod
    def validate_cloudwatch_period(cls, v: int) -> int:
        if v % 60 != 0:
            raise ValueError("CLOUDWATCH_METRIC_PERIOD_SECONDS must be a multiple of 60.")
        return v

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]

    @property
    def is_aws_region_configured(self) -> bool:
        return not _is_placeholder(self.aws_region) and bool(
            _AWS_REGION_PATTERN.match(self.aws_region.strip())
        )

    @property
    def is_ec2_configured(self) -> bool:
        return not _is_placeholder(self.ec2_instance_id) and bool(
            _EC2_ID_PATTERN.match(self.ec2_instance_id.strip())
        )

    @property
    def is_s3_configured(self) -> bool:
        return not _is_placeholder(self.s3_bucket_name)

    @property
    def effective_bedrock_region(self) -> str:
        if not _is_placeholder(self.bedrock_region):
            return self.bedrock_region.strip()
        return self.aws_region.strip() if self.is_aws_region_configured else ""

    @property
    def is_bedrock_configured(self) -> bool:
        return (
            not _is_placeholder(self.bedrock_kb_id)
            and not _is_placeholder(self.bedrock_model_id)
            and bool(self.effective_bedrock_region)
            and bool(_AWS_REGION_PATTERN.match(self.effective_bedrock_region))
        )

    def validate_ec2_monitoring_target(self, instance_id: str | None = None) -> tuple[str, str]:
        """Return validated (region, instance_id) or raise ConfigurationError."""
        from app.core.exceptions import ConfigurationError

        if not self.is_aws_region_configured:
            raise ConfigurationError(
                "AWS_REGION is not configured with a valid AWS region (e.g., us-east-1).",
                missing_fields=["AWS_REGION"],
            )

        target_id = (instance_id or self.ec2_instance_id or "").strip()
        if _is_placeholder(target_id) or not _EC2_ID_PATTERN.match(target_id):
            raise ConfigurationError(
                "EC2_INSTANCE_ID is missing or invalid. Provide a real EC2 instance ID (i-...).",
                missing_fields=["EC2_INSTANCE_ID"],
            )
        return self.aws_region.strip(), target_id

    def safe_status_summary(self) -> dict[str, object]:
        """Return configuration status without exposing credentials or sensitive details."""
        return {
            "app_name": self.app_name,
            "app_env": self.app_env,
            "app_version": self.app_version,
            "aws_region_configured": self.is_aws_region_configured,
            "aws_region": self.aws_region.strip() if self.is_aws_region_configured else None,
            "aws_auth_mode": "profile" if self.aws_profile.strip() else "default_credential_chain",
            "ec2_instance_configured": self.is_ec2_configured,
            "ec2_instance_id": self.ec2_instance_id.strip() if self.is_ec2_configured else None,
            "polling_interval_seconds": self.polling_interval_seconds,
            "cloudwatch_metric_period_seconds": self.cloudwatch_metric_period_seconds,
            "dynamodb_readings_table": self.dynamodb_readings_table,
            "dynamodb_runs_table": self.dynamodb_runs_table,
            "s3_configured": self.is_s3_configured,
            "s3_bucket_name": self.s3_bucket_name.strip() if self.is_s3_configured else None,
            "cloudwatch_logs_enabled": self.cloudwatch_logs_enabled,
            "bedrock_configured": self.is_bedrock_configured,
            "bedrock_region": self.effective_bedrock_region or None,
            "bedrock_model_id": self.bedrock_model_id if self.is_bedrock_configured else None,
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached Settings instance (clear cache in tests when env changes)."""
    return Settings()
