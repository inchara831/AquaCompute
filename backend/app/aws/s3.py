"""Amazon S3 storage client for reports and AquaMind RAG source documents."""

from __future__ import annotations

import json
import logging
from typing import Any

from app.aws.clients import get_aws_client, translate_aws_error
from app.core.config import Settings
from app.core.exceptions import ConfigurationError

logger = logging.getLogger("aquacompute.aws.s3")


class S3StorageClient:
    """Manages report archives and RAG source documents in Amazon S3."""

    def __init__(self, settings: Settings, *, s3_client: Any | None = None) -> None:
        self._settings = settings
        self._client_override = s3_client

    def _client(self) -> Any:
        if self._client_override is not None:
            return self._client_override
        if not self._settings.is_s3_configured:
            raise ConfigurationError(
                "S3_BUCKET_NAME is not configured.",
                missing_fields=["S3_BUCKET_NAME"],
            )
        return get_aws_client(self._settings, "s3")

    def upload_report_json(self, filename: str, payload: dict[str, Any]) -> str:
        """Archive a JSON snapshot/report to S3 under S3_REPORTS_PREFIX and return the S3 key."""
        if not self._settings.is_s3_configured:
            raise ConfigurationError(
                "S3_BUCKET_NAME must be configured before exporting reports to S3.",
                missing_fields=["S3_BUCKET_NAME"],
            )

        prefix = self._settings.s3_reports_prefix.strip("/")
        key = f"{prefix}/{filename.lstrip('/')}" if prefix else filename.lstrip("/")
        body = json.dumps(payload, indent=2, default=str).encode("utf-8")

        try:
            self._client().put_object(
                Bucket=self._settings.s3_bucket_name.strip(),
                Key=key,
                Body=body,
                ContentType="application/json",
            )
        except Exception as exc:
            raise translate_aws_error(exc, context=f"s3:PutObject({key})") from exc

        logger.info("Uploaded JSON report to S3", extra={"extra_fields": {"s3_key": key}})
        return key

    def list_rag_documents(self, *, max_keys: int = 100) -> list[dict[str, Any]]:
        """List RAG source documents currently stored in S3 under S3_RAG_DOCS_PREFIX."""
        if not self._settings.is_s3_configured:
            raise ConfigurationError(
                "S3_BUCKET_NAME is not configured.",
                missing_fields=["S3_BUCKET_NAME"],
            )

        prefix = self._settings.s3_rag_docs_prefix.lstrip("/")
        try:
            response = self._client().list_objects_v2(
                Bucket=self._settings.s3_bucket_name.strip(),
                Prefix=prefix,
                MaxKeys=max_keys,
            )
        except Exception as exc:
            raise translate_aws_error(exc, context="s3:ListObjectsV2(rag_docs)") from exc

        return [
            {
                "key": obj["Key"],
                "size_bytes": obj.get("Size", 0),
                "last_modified": obj.get("LastModified"),
            }
            for obj in response.get("Contents", [])
            if not obj["Key"].endswith("/")
        ]
