"""Amazon DynamoDB repository for timestamped EC2 readings and collection runs."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from boto3.dynamodb.conditions import Key

from app.aws.clients import create_boto_session, translate_aws_error
from app.core.config import Settings
from app.core.exceptions import ConfigurationError
from app.models.metrics import CollectionRecord, CollectionRunStatus, MetricPoint

logger = logging.getLogger("aquacompute.aws.dynamodb")


def _to_dynamodb_value(val: Any) -> Any:
    """Recursively convert floats to Decimal for DynamoDB serialization."""
    if isinstance(val, float):
        return Decimal(str(val))
    if isinstance(val, dict):
        return {k: _to_dynamodb_value(v) for k, v in val.items()}
    if isinstance(val, list):
        return [_to_dynamodb_value(v) for v in val]
    return val


def _from_dynamodb_value(val: Any) -> Any:
    """Recursively convert Decimal back to float for Pydantic deserialization."""
    if isinstance(val, Decimal):
        return float(val)
    if isinstance(val, dict):
        return {k: _from_dynamodb_value(v) for k, v in val.items()}
    if isinstance(val, list):
        return [_from_dynamodb_value(v) for v in val]
    return val


class DynamoDbRepository:
    """Persists and queries AquaCompute metric snapshots and run status records."""

    def __init__(
        self,
        settings: Settings,
        *,
        dynamodb_resource: Any | None = None,
    ) -> None:
        self._settings = settings
        self._resource_override = dynamodb_resource

    def _resource(self) -> Any:
        if self._resource_override is not None:
            return self._resource_override
        if not self._settings.is_aws_region_configured and not self._settings.dynamodb_endpoint_url:
            raise ConfigurationError(
                "AWS_REGION must be configured to access DynamoDB.",
                missing_fields=["AWS_REGION"],
            )
        session = create_boto_session(self._settings)
        kwargs: dict[str, Any] = {}
        if self._settings.is_aws_region_configured:
            kwargs["region_name"] = self._settings.aws_region.strip()
        if self._settings.dynamodb_endpoint_url.strip():
            kwargs["endpoint_url"] = self._settings.dynamodb_endpoint_url.strip()
        return session.resource("dynamodb", **kwargs)

    def save_reading(self, record: CollectionRecord) -> None:
        """Persist a single timestamped metric snapshot."""
        table = self._resource().Table(self._settings.dynamodb_readings_table)
        item = {
            "instance_id": record.instance_id,
            "collected_at": record.collected_at.astimezone(timezone.utc).isoformat(),
            "record_id": record.record_id,
            "region": record.region,
            "instance_type": record.instance_type,
            "data_classification": record.data_classification,
            "s3_report_key": record.s3_report_key,
            "metrics": {
                name: _to_dynamodb_value(point.model_dump(mode="json"))
                for name, point in record.metrics.items()
            },
        }
        try:
            table.put_item(Item=item)
        except Exception as exc:
            raise translate_aws_error(exc, context="dynamodb:PutItem(readings)") from exc

    def list_readings(self, instance_id: str, *, limit: int = 25) -> list[CollectionRecord]:
        """Retrieve most recent stored readings for an EC2 instance."""
        table = self._resource().Table(self._settings.dynamodb_readings_table)
        try:
            response = table.query(
                KeyConditionExpression=Key("instance_id").eq(instance_id),
                ScanIndexForward=False,
                Limit=limit,
            )
        except Exception as exc:
            raise translate_aws_error(exc, context="dynamodb:Query(readings)") from exc

        records: list[CollectionRecord] = []
        for raw_item in response.get("Items", []):
            clean = _from_dynamodb_value(raw_item)
            metrics_dict = {
                name: MetricPoint.model_validate(payload)
                for name, payload in clean.get("metrics", {}).items()
            }
            records.append(
                CollectionRecord(
                    record_id=clean["record_id"],
                    instance_id=clean["instance_id"],
                    region=clean["region"],
                    instance_type=clean.get("instance_type"),
                    collected_at=datetime.fromisoformat(clean["collected_at"]),
                    data_classification=clean.get("data_classification", "live_aws_data"),
                    metrics=metrics_dict,
                    s3_report_key=clean.get("s3_report_key"),
                )
            )
        return records

    def save_run_status(self, run: CollectionRunStatus) -> None:
        """Persist collection execution status (manual or EventBridge Lambda)."""
        table = self._resource().Table(self._settings.dynamodb_runs_table)
        item = {
            "run_id": run.run_id,
            "started_at": run.started_at.astimezone(timezone.utc).isoformat(),
            "completed_at": (
                run.completed_at.astimezone(timezone.utc).isoformat() if run.completed_at else None
            ),
            "trigger": run.trigger,
            "status": run.status,
            "instance_id": run.instance_id,
            "region": run.region,
            "records_stored": run.records_stored,
            "error_message": run.error_message,
        }
        try:
            table.put_item(Item=item)
        except Exception as exc:
            raise translate_aws_error(exc, context="dynamodb:PutItem(runs)") from exc

    def get_latest_run_status(self, instance_id: str | None = None) -> CollectionRunStatus | None:
        """Fetch latest collection run status from DynamoDB runs table."""
        table = self._resource().Table(self._settings.dynamodb_runs_table)
        try:
            response = table.scan(Limit=50)
        except Exception as exc:
            raise translate_aws_error(exc, context="dynamodb:Scan(runs)") from exc

        items = [_from_dynamodb_value(it) for it in response.get("Items", [])]
        if instance_id:
            items = [it for it in items if it.get("instance_id") in (instance_id, None)]
        if not items:
            return None

        items.sort(key=lambda it: it.get("started_at", ""), reverse=True)
        latest = items[0]
        return CollectionRunStatus(
            run_id=latest["run_id"],
            trigger=latest["trigger"],
            status=latest["status"],
            instance_id=latest.get("instance_id"),
            region=latest.get("region"),
            started_at=datetime.fromisoformat(latest["started_at"]),
            completed_at=(
                datetime.fromisoformat(latest["completed_at"])
                if latest.get("completed_at")
                else None
            ),
            records_stored=int(latest.get("records_stored", 0)),
            error_message=latest.get("error_message"),
        )
