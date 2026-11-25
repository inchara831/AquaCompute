"""FastAPI dependency injection providers."""

from __future__ import annotations

from fastapi import Depends

from app.aws.bedrock_kb import BedrockKnowledgeBaseClient
from app.aws.cloudwatch import CloudWatchEc2Client
from app.aws.dynamodb import DynamoDbRepository
from app.aws.s3 import S3StorageClient
from app.core.config import Settings, get_settings
from app.services.aquamind import AquaMindService
from app.services.collector import MetricsCollectionService
from app.services.footprint_bridge import FootprintBridgeService


def get_cloudwatch_client(
    settings: Settings = Depends(get_settings),
) -> CloudWatchEc2Client:
    return CloudWatchEc2Client(settings)


def get_dynamodb_repo(
    settings: Settings = Depends(get_settings),
) -> DynamoDbRepository:
    return DynamoDbRepository(settings)


def get_s3_client(
    settings: Settings = Depends(get_settings),
) -> S3StorageClient:
    return S3StorageClient(settings)


def get_bedrock_client(
    settings: Settings = Depends(get_settings),
) -> BedrockKnowledgeBaseClient:
    return BedrockKnowledgeBaseClient(settings)


def get_collection_service(
    settings: Settings = Depends(get_settings),
    cw: CloudWatchEc2Client = Depends(get_cloudwatch_client),
    db: DynamoDbRepository = Depends(get_dynamodb_repo),
    s3: S3StorageClient = Depends(get_s3_client),
) -> MetricsCollectionService:
    return MetricsCollectionService(
        settings,
        cloudwatch_client=cw,
        dynamodb_repo=db,
        s3_client=s3 if settings.is_s3_configured else None,
    )


def get_footprint_service(
    settings: Settings = Depends(get_settings),
    cw: CloudWatchEc2Client = Depends(get_cloudwatch_client),
) -> FootprintBridgeService:
    return FootprintBridgeService(settings, cloudwatch_client=cw)


def get_aquamind_service(
    settings: Settings = Depends(get_settings),
    bedrock: BedrockKnowledgeBaseClient = Depends(get_bedrock_client),
    cw: CloudWatchEc2Client = Depends(get_cloudwatch_client),
) -> AquaMindService:
    return AquaMindService(settings, bedrock_client=bedrock, cloudwatch_client=cw)
