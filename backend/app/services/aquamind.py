"""AquaMind RAG service combining Amazon Bedrock Knowledge Bases with live EC2 metrics."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from app.aws.bedrock_kb import BedrockKnowledgeBaseClient
from app.aws.cloudwatch import CloudWatchEc2Client
from app.core.config import Settings
from app.core.exceptions import AquaComputeError
from app.models.rag import AquaMindAskRequest, AquaMindAskResponse, AquaMindStatusResponse

logger = logging.getLogger("aquacompute.services.aquamind")


class AquaMindService:
    """Grounded RAG assistant for cloud sustainability, WUE, and EC2 efficiency."""

    def __init__(
        self,
        settings: Settings,
        *,
        bedrock_client: BedrockKnowledgeBaseClient,
        cloudwatch_client: CloudWatchEc2Client,
    ) -> None:
        self._settings = settings
        self._bedrock = bedrock_client
        self._cw = cloudwatch_client

    def get_status(self) -> AquaMindStatusResponse:
        if self._settings.is_bedrock_configured:
            return AquaMindStatusResponse(
                status="configured",
                bedrock_region=self._settings.effective_bedrock_region,
                knowledge_base_configured=True,
                model_id=self._settings.bedrock_model_id.strip(),
                setup_instructions=[],
            )
        return AquaMindStatusResponse(
            status="not_configured",
            bedrock_region=self._settings.effective_bedrock_region or None,
            knowledge_base_configured=False,
            model_id=self._settings.bedrock_model_id.strip() or None,
            setup_instructions=[
                "1. Upload curated sustainability/WUE/cloud-efficiency docs to S3 under S3_RAG_DOCS_PREFIX.",
                "2. Create an Amazon Bedrock Knowledge Base pointing to that S3 prefix and sync it.",
                "3. Enable model access in Amazon Bedrock for your chosen model (e.g., Claude 3 Haiku).",
                "4. Set BEDROCK_KB_ID, BEDROCK_MODEL_ID, and BEDROCK_REGION in backend/.env.",
            ],
        )

    def _try_get_live_metrics_summary(self) -> tuple[dict[str, Any] | None, str | None]:
        if not (self._settings.is_aws_region_configured and self._settings.is_ec2_configured):
            return None, None
        try:
            current = self._cw.get_current_metrics()
        except AquaComputeError as exc:
            logger.info("Skipping live metrics context in AquaMind: %s", exc.message)
            return None, None

        summary: dict[str, Any] = {
            "instance_id": current.instance.instance_id,
            "instance_type": current.instance.instance_type,
            "region": current.instance.region,
            "state": current.instance.state,
            "collected_at": current.collected_at.isoformat(),
            "metrics": {
                name: {
                    "value": point.value,
                    "unit": point.unit,
                    "status": point.status,
                    "timestamp": point.timestamp.isoformat() if point.timestamp else None,
                }
                for name, point in current.metrics.items()
            },
        }
        return summary, json.dumps(summary, indent=2)

    def ask(self, request: AquaMindAskRequest) -> AquaMindAskResponse:
        _, _, model_id = self._bedrock.ensure_configured()

        citations = self._bedrock.retrieve_passages(
            request.question, top_k=request.top_k
        )

        metrics_summary: dict[str, Any] | None = None
        metrics_text: str | None = None
        if request.include_live_metrics:
            metrics_summary, metrics_text = self._try_get_live_metrics_summary()

        answer = self._bedrock.generate_grounded_answer(
            question=request.question,
            citations=citations,
            live_metrics_context=metrics_text,
        )

        return AquaMindAskResponse(
            answer=answer,
            citations=citations,
            live_metrics_included=metrics_summary is not None,
            live_metrics_summary=metrics_summary,
            bedrock_model_id=model_id,
            knowledge_base_id_configured=True,
            answered_at=datetime.now(timezone.utc),
        )
