"""Schemas for AquaMind RAG assistant powered by Amazon Bedrock Knowledge Bases."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class AquaMindAskRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=2000)
    include_live_metrics: bool = Field(
        default=True,
        description="Attach current EC2 CloudWatch metrics (when configured) as grounding context.",
    )
    top_k: int | None = Field(default=None, ge=1, le=20)


class SourceCitation(BaseModel):
    """Exact citation returned from Amazon Bedrock Knowledge Base retrieval."""

    source_uri: str | None = None
    source_type: str | None = None
    excerpt: str
    score: float | None = None
    metadata: dict[str, str] = Field(default_factory=dict)


class AquaMindAskResponse(BaseModel):
    answer: str
    citations: list[SourceCitation] = Field(default_factory=list)
    live_metrics_included: bool = False
    live_metrics_summary: dict[str, object] | None = None
    bedrock_model_id: str
    knowledge_base_id_configured: bool = True
    provenance_note: str = (
        "Answers combine retrieved Knowledge Base passages with optional live CloudWatch metrics. "
        "CloudWatch does not directly measure liters of water consumed by an EC2 instance."
    )
    answered_at: datetime


class AquaMindStatusResponse(BaseModel):
    status: Literal["configured", "not_configured"]
    bedrock_region: str | None = None
    knowledge_base_configured: bool
    model_id: str | None = None
    setup_instructions: list[str] = Field(default_factory=list)
