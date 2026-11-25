"""Tests for secret redaction and CloudWatch Logs handler resilience."""

from __future__ import annotations

import logging
from typing import Any

from app.core.logging import CloudWatchLogHandler, JsonLogFormatter, redact_secrets


def test_redact_secrets_masks_aws_keys_and_tokens() -> None:
    sample = (
        "Failed with AKIAIOSFODNN7EXAMPLE "
        "aws_secret_access_key=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY "
        "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.abc.def"
    )
    cleaned = redact_secrets(sample)
    assert "AKIAIOSFODNN7EXAMPLE" not in cleaned
    assert "wJalrXUtnFEMI" not in cleaned
    assert "eyJhbGciOiJIUzI1NiJ9" not in cleaned
    assert "[REDACTED_AWS_KEY_ID]" in cleaned
    assert "[REDACTED]" in cleaned


def test_cloudwatch_log_handler_swallows_put_errors_safely() -> None:
    class FailingLogsClient:
        def create_log_group(self, **kwargs: Any) -> None:
            raise RuntimeError("No permissions")

        def create_log_stream(self, **kwargs: Any) -> None:
            raise RuntimeError("No permissions")

        def put_log_events(self, **kwargs: Any) -> None:
            raise RuntimeError("CloudWatch unreachable")

    handler = CloudWatchLogHandler(FailingLogsClient(), "/aquacompute/test", "stream-1")
    handler.setFormatter(JsonLogFormatter())
    record = logging.LogRecord(
        name="aquacompute.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="Testing AKIAIOSFODNN7EXAMPLE resilience",
        args=(),
        exc_info=None,
    )
    # Should never raise
    handler.emit(record)
