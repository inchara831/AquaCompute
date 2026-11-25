"""Amazon Bedrock Knowledge Bases client for AquaMind RAG retrieval and generation."""

from __future__ import annotations

import logging
from typing import Any

from app.aws.clients import get_aws_client, translate_aws_error
from app.core.config import Settings
from app.core.exceptions import BedrockNotConfiguredError
from app.models.rag import SourceCitation

logger = logging.getLogger("aquacompute.aws.bedrock")


class BedrockKnowledgeBaseClient:
    """Retrieves grounded passages from Bedrock KB and invokes Bedrock Converse API."""

    def __init__(
        self,
        settings: Settings,
        *,
        agent_runtime_client: Any | None = None,
        bedrock_runtime_client: Any | None = None,
    ) -> None:
        self._settings = settings
        self._agent_runtime_override = agent_runtime_client
        self._bedrock_runtime_override = bedrock_runtime_client

    def ensure_configured(self) -> tuple[str, str, str]:
        """Validate Bedrock KB configuration or raise BedrockNotConfiguredError."""
        if not self._settings.is_bedrock_configured:
            missing: list[str] = []
            if not self._settings.effective_bedrock_region:
                missing.append("BEDROCK_REGION (or AWS_REGION)")
            if not self._settings.bedrock_kb_id.strip():
                missing.append("BEDROCK_KB_ID")
            if not self._settings.bedrock_model_id.strip():
                missing.append("BEDROCK_MODEL_ID")
            raise BedrockNotConfiguredError(
                "AquaMind RAG is not configured yet. Set BEDROCK_KB_ID, BEDROCK_MODEL_ID, and BEDROCK_REGION after provisioning an Amazon Bedrock Knowledge Base.",
                details={
                    "missing_fields": missing,
                    "setup_docs": "See backend/rag_docs/README.md and README.md for Bedrock Knowledge Base setup.",
                },
            )
        return (
            self._settings.effective_bedrock_region,
            self._settings.bedrock_kb_id.strip(),
            self._settings.bedrock_model_id.strip(),
        )

    def _agent_runtime(self, region: str) -> Any:
        return self._agent_runtime_override or get_aws_client(
            self._settings, "bedrock-agent-runtime", region_name=region
        )

    def _bedrock_runtime(self, region: str) -> Any:
        return self._bedrock_runtime_override or get_aws_client(
            self._settings, "bedrock-runtime", region_name=region
        )

    def retrieve_passages(self, query: str, *, top_k: int | None = None) -> list[SourceCitation]:
        """Query Bedrock Knowledge Base and extract exact source citations."""
        region, kb_id, _ = self.ensure_configured()
        k = top_k or self._settings.bedrock_top_k

        try:
            response = self._agent_runtime(region).retrieve(
                knowledgeBaseId=kb_id,
                retrievalQuery={"text": query},
                retrievalConfiguration={
                    "vectorSearchConfiguration": {"numberOfResults": k}
                },
            )
        except Exception as exc:
            raise translate_aws_error(exc, context="bedrock-agent-runtime:Retrieve") from exc

        citations: list[SourceCitation] = []
        for result in response.get("retrievalResults", []):
            content = (result.get("content") or {}).get("text", "").strip()
            if not content:
                continue
            location = result.get("location") or {}
            source_type = location.get("type")
            source_uri: str | None = None
            if source_type == "S3":
                source_uri = (location.get("s3Location") or {}).get("uri")
            elif source_type == "WEB":
                source_uri = (location.get("webLocation") or {}).get("url")

            raw_meta = result.get("metadata") or {}
            clean_meta = {str(key): str(val) for key, val in raw_meta.items()}

            citations.append(
                SourceCitation(
                    source_uri=source_uri,
                    source_type=source_type,
                    excerpt=content,
                    score=float(result["score"]) if result.get("score") is not None else None,
                    metadata=clean_meta,
                )
            )
        return citations

    def generate_grounded_answer(
        self,
        *,
        question: str,
        citations: list[SourceCitation],
        live_metrics_context: str | None = None,
    ) -> str:
        """Generate an answer grounded strictly in retrieved passages and optional live metrics."""
        region, _, model_id = self.ensure_configured()

        passages_block = "\n\n".join(
            f"[Source {idx + 1}] URI={c.source_uri or 'unspecified'}\n{c.excerpt}"
            for idx, c in enumerate(citations)
        )
        if not passages_block:
            passages_block = "(No matching passages were returned by the Knowledge Base.)"

        metrics_block = (
            f"\n\nLive AquaCompute EC2 Telemetry (from Amazon CloudWatch):\n{live_metrics_context}"
            if live_metrics_context
            else "\n\nLive AquaCompute EC2 Telemetry: Not attached or not yet configured."
        )

        system_prompt = (
            "You are AquaMind, the cloud sustainability and water-efficiency assistant for AquaCompute. "
            "Rules you MUST follow:\n"
            "1. Ground every factual claim in the provided Knowledge Base passages and/or the attached Live EC2 Telemetry.\n"
            "2. Cite source numbers like [Source 1] corresponding to the retrieved passages.\n"
            "3. NEVER claim that Amazon CloudWatch directly measures liters of water consumed by an EC2 instance.\n"
            "4. NEVER invent citations, documents, metrics, or water-footprint numbers that are not in the context.\n"
            "5. If the retrieved passages do not contain enough information to answer, state that clearly."
        )

        user_prompt = (
            f"Question:\n{question}\n\n"
            f"Retrieved Knowledge Base Passages:\n{passages_block}"
            f"{metrics_block}"
        )

        try:
            response = self._bedrock_runtime(region).converse(
                modelId=model_id,
                system=[{"text": system_prompt}],
                messages=[{"role": "user", "content": [{"text": user_prompt}]}],
                inferenceConfig={
                    "maxTokens": self._settings.bedrock_max_tokens,
                    "temperature": self._settings.bedrock_temperature,
                },
            )
        except Exception as exc:
            raise translate_aws_error(exc, context="bedrock-runtime:Converse") from exc

        blocks = (((response.get("output") or {}).get("message") or {}).get("content")) or []
        text_parts = [b["text"] for b in blocks if isinstance(b, dict) and "text" in b]
        return "\n".join(text_parts).strip()
