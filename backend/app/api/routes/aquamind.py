"""AquaMind RAG assistant endpoints powered by Amazon Bedrock Knowledge Bases."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_aquamind_service
from app.models.rag import AquaMindAskRequest, AquaMindAskResponse, AquaMindStatusResponse
from app.services.aquamind import AquaMindService

router = APIRouter(prefix="/aquamind", tags=["AquaMind RAG"])


@router.get("/status", response_model=AquaMindStatusResponse)
def aquamind_status(
    service: AquaMindService = Depends(get_aquamind_service),
) -> AquaMindStatusResponse:
    """Return Amazon Bedrock Knowledge Base configuration status and setup guidance."""
    return service.get_status()


@router.post("/ask", response_model=AquaMindAskResponse)
def ask_aquamind(
    payload: AquaMindAskRequest,
    service: AquaMindService = Depends(get_aquamind_service),
) -> AquaMindAskResponse:
    """Answer cloud sustainability questions grounded in Bedrock KB passages and live EC2 metrics."""
    return service.ask(payload)
