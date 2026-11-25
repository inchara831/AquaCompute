"""Boto3 session/client factory and AWS error translation."""

from __future__ import annotations

import logging
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    NoCredentialsError,
    PartialCredentialsError,
    ProfileNotFound,
)

from app.core.config import Settings
from app.core.exceptions import (
    AquaComputeError,
    AwsCredentialsError,
    AwsPermissionError,
    AwsThrottlingError,
    ConfigurationError,
    ResourceNotFoundError,
)

logger = logging.getLogger("aquacompute.aws.clients")

_DEFAULT_BOTO_CONFIG = Config(
    retries={"max_attempts": 5, "mode": "adaptive"},
    connect_timeout=5,
    read_timeout=15,
)


def create_boto_session(settings: Settings) -> boto3.Session:
    """Create a Boto3 session using configured profile or default AWS credential chain."""
    profile = settings.aws_profile.strip() or None
    region = settings.aws_region.strip() if settings.is_aws_region_configured else None
    try:
        return boto3.Session(profile_name=profile, region_name=region)
    except ProfileNotFound as exc:
        raise ConfigurationError(
            "Configured AWS_PROFILE was not found in local AWS configuration.",
            missing_fields=["AWS_PROFILE"],
        ) from exc


def get_aws_client(
    settings: Settings,
    service_name: str,
    *,
    region_name: str | None = None,
    endpoint_url: str | None = None,
) -> Any:
    """Build a Boto3 service client with adaptive retries."""
    session = create_boto_session(settings)
    target_region = region_name or (
        settings.aws_region.strip() if settings.is_aws_region_configured else None
    )
    if not target_region:
        raise ConfigurationError(
            "AWS_REGION must be configured before calling AWS services.",
            missing_fields=["AWS_REGION"],
        )
    kwargs: dict[str, Any] = {
        "region_name": target_region,
        "config": _DEFAULT_BOTO_CONFIG,
    }
    if endpoint_url:
        kwargs["endpoint_url"] = endpoint_url
    return session.client(service_name, **kwargs)


def translate_aws_error(exc: Exception, *, context: str) -> AquaComputeError:
    """Map Boto3/Botocore exceptions into safe domain errors without leaking secrets."""
    if isinstance(exc, AquaComputeError):
        return exc

    if isinstance(exc, (NoCredentialsError, PartialCredentialsError)):
        logger.warning("AWS credentials unavailable during %s", context)
        return AwsCredentialsError(
            f"AWS credentials are not configured or incomplete for {context}. "
            "Configure an AWS CLI profile, IAM role, or standard AWS environment credentials."
        )

    if isinstance(exc, ProfileNotFound):
        return ConfigurationError(
            "Configured AWS_PROFILE was not found.",
            missing_fields=["AWS_PROFILE"],
        )

    if isinstance(exc, ClientError):
        err = exc.response.get("Error", {})
        code = err.get("Code", "UnknownAwsError")
        msg = err.get("Message", "AWS API call failed.")
        logger.warning("AWS ClientError (%s) during %s: %s", code, context, msg)

        if code in {"AccessDenied", "AccessDeniedException", "UnauthorizedOperation", "AuthFailure"}:
            return AwsPermissionError(
                f"IAM permission denied during {context} ({code}). Verify least-privilege IAM policy."
            )
        if code in {
            "Throttling",
            "ThrottlingException",
            "RequestLimitExceeded",
            "ProvisionedThroughputExceededException",
            "TooManyRequestsException",
        }:
            return AwsThrottlingError(
                f"AWS throttled requests during {context} ({code}). Retry after backoff."
            )
        if code in {
            "InvalidInstanceID.NotFound",
            "InvalidInstanceID.Malformed",
            "ResourceNotFoundException",
            "NoSuchBucket",
            "NoSuchKey",
        }:
            return ResourceNotFoundError(f"Requested AWS resource not found during {context} ({code}).")
        if code in {"ExpiredToken", "ExpiredTokenException", "InvalidClientTokenId"}:
            return AwsCredentialsError(
                f"AWS security token is invalid or expired during {context} ({code}). Please re-authenticate."
            )
        return AquaComputeError(f"AWS error during {context} ({code}): {msg}")

    if isinstance(exc, BotoCoreError):
        logger.warning("Botocore error during %s: %s", context, type(exc).__name__)
        return AquaComputeError(f"AWS SDK transport error during {context}: {type(exc).__name__}")

    logger.error("Unexpected error during %s: %s", context, type(exc).__name__)
    return AquaComputeError(f"Unexpected error during {context}.")
