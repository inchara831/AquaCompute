"""Schemas for live AWS EC2 CloudWatch metrics, history, and DynamoDB collection records."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class MetricPoint(BaseModel):
    """Single CloudWatch metric reading; null value means CloudWatch returned no datapoint."""

    metric_name: str
    namespace: str = "AWS/EC2"
    statistic: str = "Average"
    unit: str | None = None
    value: float | None = None
    timestamp: datetime | None = None
    status: Literal["available", "unavailable"]


class Ec2InstanceMetadata(BaseModel):
    """Metadata retrieved from EC2 DescribeInstances."""

    instance_id: str
    region: str
    instance_type: str | None = None
    state: str | None = None
    availability_zone: str | None = None
    platform_details: str | None = None


class CurrentMetricsResponse(BaseModel):
    """Current live EC2 metrics fetched directly from Amazon CloudWatch."""

    data_classification: Literal["live_aws_data"] = "live_aws_data"
    is_live_aws_data: bool = True
    is_calculated_estimate: bool = False
    is_demo_data: bool = False
    source: str = "Amazon CloudWatch + Amazon EC2"
    collected_at: datetime
    period_seconds: int
    polling_interval_seconds: int
    instance: Ec2InstanceMetadata
    metrics: dict[str, MetricPoint]
    notes: list[str] = Field(default_factory=list)


class MetricSeriesSample(BaseModel):
    timestamp: datetime
    value: float


class MetricHistorySeries(BaseModel):
    metric_name: str
    unit: str | None = None
    statistic: str = "Average"
    datapoints: list[MetricSeriesSample] = Field(default_factory=list)


class HistoricalMetricsResponse(BaseModel):
    """Time-series CloudWatch metrics over a requested window."""

    data_classification: Literal["live_aws_data"] = "live_aws_data"
    is_live_aws_data: bool = True
    is_calculated_estimate: bool = False
    source: str = "Amazon CloudWatch"
    instance_id: str
    region: str
    start_time: datetime
    end_time: datetime
    period_seconds: int
    series: dict[str, MetricHistorySeries]


class CollectionRecord(BaseModel):
    """Stored timestamped metric snapshot persisted in DynamoDB."""

    record_id: str
    instance_id: str
    region: str
    instance_type: str | None = None
    collected_at: datetime
    data_classification: Literal["live_aws_data"] = "live_aws_data"
    metrics: dict[str, MetricPoint]
    s3_report_key: str | None = None


class CollectionRunStatus(BaseModel):
    """Status record of a scheduled or manual collection run."""

    run_id: str
    trigger: Literal["manual_api", "eventbridge_lambda"]
    status: Literal["success", "partial", "failed"]
    instance_id: str | None = None
    region: str | None = None
    started_at: datetime
    completed_at: datetime | None = None
    records_stored: int = 0
    error_message: str | None = None


class CollectionHistoryResponse(BaseModel):
    instance_id: str
    region: str
    polling_interval_seconds: int
    latest_run: CollectionRunStatus | None = None
    records: list[CollectionRecord] = Field(default_factory=list)


class CollectNowRequest(BaseModel):
    instance_id: str | None = Field(
        default=None,
        description="Optional EC2 instance ID override; defaults to EC2_INSTANCE_ID in config.",
    )
    export_to_s3: bool = Field(
        default=False,
        description="When true and S3_BUCKET_NAME is configured, also archives snapshot JSON to S3.",
    )
