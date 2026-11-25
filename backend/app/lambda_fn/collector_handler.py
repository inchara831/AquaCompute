"""AWS Lambda handler triggered by Amazon EventBridge Scheduler."""

from __future__ import annotations

import logging
from typing import Any

from app.aws.cloudwatch import CloudWatchEc2Client
from app.aws.dynamodb import DynamoDbRepository
from app.aws.s3 import S3StorageClient
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.services.collector import MetricsCollectionService

logger = logging.getLogger("aquacompute.lambda.collector")


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Collect live EC2 CloudWatch metrics on schedule and store them in DynamoDB/S3."""
    settings = get_settings()
    configure_logging(settings.log_level)

    instance_id = event.get("instance_id") if isinstance(event, dict) else None
    export_to_s3 = (
        bool(event.get("export_to_s3", settings.is_s3_configured))
        if isinstance(event, dict)
        else settings.is_s3_configured
    )

    service = MetricsCollectionService(
        settings,
        cloudwatch_client=CloudWatchEc2Client(settings),
        dynamodb_repo=DynamoDbRepository(settings),
        s3_client=S3StorageClient(settings) if settings.is_s3_configured else None,
    )

    record, run_status = service.collect_and_store(
        instance_id=instance_id,
        trigger="eventbridge_lambda",
        export_to_s3=export_to_s3,
    )
    logger.info(
        "Scheduled EC2 collection finished",
        extra={
            "extra_fields": {
                "run_id": run_status.run_id,
                "record_id": record.record_id,
                "instance_id": record.instance_id,
                "status": run_status.status,
            }
        },
    )
    return {
        "statusCode": 200,
        "run_id": run_status.run_id,
        "record_id": record.record_id,
        "instance_id": record.instance_id,
        "status": run_status.status,
        "s3_report_key": record.s3_report_key,
    }
