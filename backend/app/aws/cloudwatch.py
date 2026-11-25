"""Amazon EC2 metadata and Amazon CloudWatch metric retrieval."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from app.aws.clients import get_aws_client, translate_aws_error
from app.core.config import Settings
from app.core.exceptions import MetricUnavailableError, ResourceNotFoundError
from app.models.metrics import (
    CurrentMetricsResponse,
    Ec2InstanceMetadata,
    HistoricalMetricsResponse,
    MetricHistorySeries,
    MetricPoint,
    MetricSeriesSample,
)

logger = logging.getLogger("aquacompute.aws.cloudwatch")


@dataclass(frozen=True)
class MetricSpec:
    metric_name: str
    statistic: str
    query_id: str


EC2_METRIC_SPECS: tuple[MetricSpec, ...] = (
    MetricSpec("CPUUtilization", "Average", "cpu_util"),
    MetricSpec("NetworkIn", "Sum", "net_in"),
    MetricSpec("NetworkOut", "Sum", "net_out"),
    MetricSpec("DiskReadOps", "Sum", "disk_read_ops"),
    MetricSpec("DiskWriteOps", "Sum", "disk_write_ops"),
    MetricSpec("DiskReadBytes", "Sum", "disk_read_bytes"),
    MetricSpec("DiskWriteBytes", "Sum", "disk_write_bytes"),
    MetricSpec("StatusCheckFailed", "Maximum", "status_check_failed"),
)

_METRIC_UNITS: dict[str, str] = {
    "CPUUtilization": "Percent",
    "NetworkIn": "Bytes",
    "NetworkOut": "Bytes",
    "DiskReadOps": "Count",
    "DiskWriteOps": "Count",
    "DiskReadBytes": "Bytes",
    "DiskWriteBytes": "Bytes",
    "StatusCheckFailed": "Count",
}


class CloudWatchEc2Client:
    """Reads live EC2 instance metadata and CloudWatch metrics via Boto3."""

    def __init__(
        self,
        settings: Settings,
        *,
        ec2_client: Any | None = None,
        cloudwatch_client: Any | None = None,
    ) -> None:
        self._settings = settings
        self._ec2_override = ec2_client
        self._cw_override = cloudwatch_client

    def _ec2(self, region: str) -> Any:
        return self._ec2_override or get_aws_client(self._settings, "ec2", region_name=region)

    def _cw(self, region: str) -> Any:
        return self._cw_override or get_aws_client(
            self._settings, "cloudwatch", region_name=region
        )

    def describe_instance(self, instance_id: str, region: str) -> Ec2InstanceMetadata:
        """Fetch real EC2 metadata using DescribeInstances."""
        try:
            response = self._ec2(region).describe_instances(InstanceIds=[instance_id])
        except Exception as exc:
            raise translate_aws_error(exc, context=f"ec2:DescribeInstances({instance_id})") from exc

        reservations = response.get("Reservations", [])
        if not reservations or not reservations[0].get("Instances"):
            raise ResourceNotFoundError(
                f"EC2 instance '{instance_id}' was not found in region '{region}'."
            )

        inst = reservations[0]["Instances"][0]
        return Ec2InstanceMetadata(
            instance_id=inst.get("InstanceId", instance_id),
            region=region,
            instance_type=inst.get("InstanceType"),
            state=(inst.get("State") or {}).get("Name"),
            availability_zone=(inst.get("Placement") or {}).get("AvailabilityZone"),
            platform_details=inst.get("PlatformDetails"),
        )

    @staticmethod
    def _build_metric_queries(instance_id: str, period_seconds: int) -> list[dict[str, Any]]:
        return [
            {
                "Id": spec.query_id,
                "MetricStat": {
                    "Metric": {
                        "Namespace": "AWS/EC2",
                        "MetricName": spec.metric_name,
                        "Dimensions": [{"Name": "InstanceId", "Value": instance_id}],
                    },
                    "Period": period_seconds,
                    "Stat": spec.statistic,
                },
                "ReturnData": True,
            }
            for spec in EC2_METRIC_SPECS
        ]

    def _fetch_metric_data(
        self,
        instance_id: str,
        region: str,
        start_time: datetime,
        end_time: datetime,
        period_seconds: int,
    ) -> dict[str, dict[str, Any]]:
        queries = self._build_metric_queries(instance_id, period_seconds)
        try:
            response = self._cw(region).get_metric_data(
                MetricDataQueries=queries,
                StartTime=start_time,
                EndTime=end_time,
                ScanBy="TimestampAscending",
            )
        except Exception as exc:
            translated = translate_aws_error(
                exc, context=f"cloudwatch:GetMetricData({instance_id})"
            )
            if type(translated).__name__ == "AquaComputeError":
                raise MetricUnavailableError(translated.message) from exc
            raise translated from exc

        results_by_id: dict[str, dict[str, Any]] = {}
        for item in response.get("MetricDataResults", []):
            results_by_id[item["Id"]] = item
        return results_by_id

    def get_current_metrics(self, instance_id: str | None = None) -> CurrentMetricsResponse:
        """Fetch latest available CloudWatch metrics and EC2 metadata."""
        region, target_id = self._settings.validate_ec2_monitoring_target(instance_id)
        period = self._settings.cloudwatch_metric_period_seconds
        now = datetime.now(timezone.utc)
        # Look back 3x period (at least 20 minutes) so basic 5-minute CloudWatch metrics are captured.
        lookback = max(period * 3, 1200)
        start_time = now - timedelta(seconds=lookback)

        metadata = self.describe_instance(target_id, region)
        results = self._fetch_metric_data(target_id, region, start_time, now, period)

        metrics: dict[str, MetricPoint] = {}
        unavailable_names: list[str] = []

        for spec in EC2_METRIC_SPECS:
            raw = results.get(spec.query_id, {})
            timestamps = raw.get("Timestamps") or []
            values = raw.get("Values") or []
            if timestamps and values:
                latest_ts, latest_val = max(zip(timestamps, values), key=lambda pair: pair[0])
                if latest_ts.tzinfo is None:
                    latest_ts = latest_ts.replace(tzinfo=timezone.utc)
                metrics[spec.metric_name] = MetricPoint(
                    metric_name=spec.metric_name,
                    statistic=spec.statistic,
                    unit=_METRIC_UNITS.get(spec.metric_name),
                    value=float(latest_val),
                    timestamp=latest_ts,
                    status="available",
                )
            else:
                unavailable_names.append(spec.metric_name)
                metrics[spec.metric_name] = MetricPoint(
                    metric_name=spec.metric_name,
                    statistic=spec.statistic,
                    unit=_METRIC_UNITS.get(spec.metric_name),
                    value=None,
                    timestamp=None,
                    status="unavailable",
                )

        notes = [
            "Metrics reflect live AWS CloudWatch telemetry; CloudWatch does not directly measure water consumption."
        ]
        if unavailable_names:
            notes.append(
                "Some metrics returned no datapoints in the lookback window (common for stopped instances or EBS-backed DiskReadOps/DiskWriteOps): "
                + ", ".join(unavailable_names)
            )

        logger.info(
            "Fetched live CloudWatch metrics",
            extra={
                "extra_fields": {
                    "instance_id": target_id,
                    "region": region,
                    "available_metrics": len(metrics) - len(unavailable_names),
                    "unavailable_metrics": len(unavailable_names),
                }
            },
        )

        return CurrentMetricsResponse(
            collected_at=now,
            period_seconds=period,
            polling_interval_seconds=self._settings.polling_interval_seconds,
            instance=metadata,
            metrics=metrics,
            notes=notes,
        )

    def get_historical_metrics(
        self,
        *,
        instance_id: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        period_seconds: int | None = None,
    ) -> HistoricalMetricsResponse:
        """Fetch time-series CloudWatch datapoints for a requested time window."""
        region, target_id = self._settings.validate_ec2_monitoring_target(instance_id)
        now = datetime.now(timezone.utc)
        resolved_end = end_time or now
        resolved_start = start_time or (resolved_end - timedelta(hours=6))

        if resolved_start.tzinfo is None:
            resolved_start = resolved_start.replace(tzinfo=timezone.utc)
        if resolved_end.tzinfo is None:
            resolved_end = resolved_end.replace(tzinfo=timezone.utc)

        if resolved_start >= resolved_end:
            raise ValueError("start_time must be strictly earlier than end_time.")

        max_window = timedelta(hours=self._settings.max_history_hours)
        if resolved_end - resolved_start > max_window:
            raise ValueError(
                f"Requested range exceeds MAX_HISTORY_HOURS ({self._settings.max_history_hours}h)."
            )

        period = period_seconds or self._settings.cloudwatch_metric_period_seconds
        if period < 60 or period % 60 != 0:
            raise ValueError("period_seconds must be >= 60 and a multiple of 60.")

        results = self._fetch_metric_data(target_id, region, resolved_start, resolved_end, period)
        series: dict[str, MetricHistorySeries] = {}

        for spec in EC2_METRIC_SPECS:
            raw = results.get(spec.query_id, {})
            timestamps = raw.get("Timestamps") or []
            values = raw.get("Values") or []
            pairs = sorted(zip(timestamps, values), key=lambda p: p[0])
            samples = [
                MetricSeriesSample(
                    timestamp=ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts,
                    value=float(val),
                )
                for ts, val in pairs
            ]
            series[spec.metric_name] = MetricHistorySeries(
                metric_name=spec.metric_name,
                unit=_METRIC_UNITS.get(spec.metric_name),
                statistic=spec.statistic,
                datapoints=samples,
            )

        return HistoricalMetricsResponse(
            instance_id=target_id,
            region=region,
            start_time=resolved_start,
            end_time=resolved_end,
            period_seconds=period,
            series=series,
        )
