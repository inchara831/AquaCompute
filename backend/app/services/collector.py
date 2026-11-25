"""Orchestrates live CloudWatch collection, DynamoDB persistence, and optional S3 export."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from app.aws.cloudwatch import CloudWatchEc2Client
from app.aws.dynamodb import DynamoDbRepository
from app.aws.s3 import S3StorageClient
from app.core.config import Settings
from app.core.exceptions import AquaComputeError
from app.models.metrics import (
    CollectionHistoryResponse,
    CollectionRecord,
    CollectionRunStatus,
    CurrentMetricsResponse,
)

logger = logging.getLogger("aquacompute.services.collector")


class MetricsCollectionService:
    """Collects live EC2 telemetry from CloudWatch and persists snapshots to DynamoDB/S3."""

    def __init__(
        self,
        settings: Settings,
        *,
        cloudwatch_client: CloudWatchEc2Client,
        dynamodb_repo: DynamoDbRepository,
        s3_client: S3StorageClient | None = None,
    ) -> None:
        self._settings = settings
        self._cw = cloudwatch_client
        self._db = dynamodb_repo
        self._s3 = s3_client

    def collect_and_store(
        self,
        *,
        instance_id: str | None = None,
        trigger: str = "manual_api",
        export_to_s3: bool = False,
    ) -> tuple[CollectionRecord, CollectionRunStatus]:
        """Execute a collection cycle and store both the snapshot and run status."""
        run_id = f"run-{uuid.uuid4().hex[:12]}"
        started_at = datetime.now(timezone.utc)
        target_region = (
            self._settings.aws_region.strip() if self._settings.is_aws_region_configured else None
        )
        target_id = instance_id or (
            self._settings.ec2_instance_id.strip() if self._settings.is_ec2_configured else None
        )

        try:
            snapshot: CurrentMetricsResponse = self._cw.get_current_metrics(instance_id=instance_id)
            record_id = f"rec-{uuid.uuid4().hex[:12]}"
            s3_key: str | None = None

            if export_to_s3 and self._s3 is not None:
                filename = (
                    f"{snapshot.instance.instance_id}/"
                    f"{snapshot.collected_at.strftime('%Y%m%dT%H%M%SZ')}_{record_id}.json"
                )
                s3_key = self._s3.upload_report_json(
                    filename, snapshot.model_dump(mode="json")
                )

            record = CollectionRecord(
                record_id=record_id,
                instance_id=snapshot.instance.instance_id,
                region=snapshot.instance.region,
                instance_type=snapshot.instance.instance_type,
                collected_at=snapshot.collected_at,
                metrics=snapshot.metrics,
                s3_report_key=s3_key,
            )
            self._db.save_reading(record)

            available_count = sum(1 for m in record.metrics.values() if m.status == "available")
            run_status = CollectionRunStatus(
                run_id=run_id,
                trigger="eventbridge_lambda" if trigger == "eventbridge_lambda" else "manual_api",
                status="success" if available_count > 0 else "partial",
                instance_id=record.instance_id,
                region=record.region,
                started_at=started_at,
                completed_at=datetime.now(timezone.utc),
                records_stored=1,
            )
            self._db.save_run_status(run_status)
            return record, run_status

        except Exception as exc:
            error_msg = exc.message if isinstance(exc, AquaComputeError) else str(exc)
            failed_run = CollectionRunStatus(
                run_id=run_id,
                trigger="eventbridge_lambda" if trigger == "eventbridge_lambda" else "manual_api",
                status="failed",
                instance_id=target_id,
                region=target_region,
                started_at=started_at,
                completed_at=datetime.now(timezone.utc),
                records_stored=0,
                error_message=error_msg,
            )
            try:
                self._db.save_run_status(failed_run)
            except Exception:
                # Preserve original collection exception if run status persistence also fails.
                logger.warning("Could not persist failed run status to DynamoDB")
            raise

    def get_collection_history(
        self, *, instance_id: str | None = None, limit: int = 25
    ) -> CollectionHistoryResponse:
        """Read stored DynamoDB metric snapshots and latest collection run status."""
        region, target_id = self._settings.validate_ec2_monitoring_target(instance_id)
        records = self._db.list_readings(target_id, limit=limit)
        latest_run = self._db.get_latest_run_status(target_id)
        return CollectionHistoryResponse(
            instance_id=target_id,
            region=region,
            polling_interval_seconds=self._settings.polling_interval_seconds,
            latest_run=latest_run,
            records=records,
        )
