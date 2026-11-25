"""Tests for AquaMind Bedrock Knowledge Base RAG behavior and unconfigured fallback."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi.testclient import TestClient

from app.api.deps import get_aquamind_service
from app.aws.bedrock_kb import BedrockKnowledgeBaseClient
from app.aws.cloudwatch import CloudWatchEc2Client
from app.core.config import Settings
from app.main import create_app
from app.services.aquamind import AquaMindService
from tests.conftest import make_client_error
from tests.test_cloudwatch_metrics import StubCloudWatchClient, StubEc2Client


class StubAgentRuntime:
    def __init__(self, *, error: Exception | None = None) -> None:
        self._error = error

    def retrieve(self, **kwargs: Any) -> dict[str, Any]:
        if self._error:
            raise self._error
        return {
            "retrievalResults": [
                {
                    "content": {
                        "text": "Water Usage Effectiveness (WUE) is defined as annual site water usage divided by IT equipment energy."
                    },
                    "location": {
                        "type": "S3",
                        "s3Location": {
                            "uri": "s3://aquacompute-test-bucket/rag-docs/green-grid-wue.pdf"
                        },
                    },
                    "score": 0.91,
                    "metadata": {"topic": "wue"},
                }
            ]
        }


class StubBedrockRuntime:
    def __init__(self) -> None:
        self.last_messages: list[dict[str, Any]] = []

    def converse(self, **kwargs: Any) -> dict[str, Any]:
        self.last_messages = kwargs.get("messages", [])
        return {
            "output": {
                "message": {
                    "content": [
                        {
                            "text": (
                                "WUE measures liters of cooling water per kWh of IT energy [Source 1]. "
                                "Note that Amazon CloudWatch does not directly measure liters of water."
                            )
                        }
                    ]
                }
            }
        }


def test_aquamind_unconfigured_returns_503_and_setup_steps(
    unconfigured_settings: Settings,
) -> None:
    app = create_app(unconfigured_settings)
    client = TestClient(app)

    status_resp = client.get("/api/v1/aquamind/status")
    assert status_resp.status_code == 200
    assert status_resp.json()["status"] == "not_configured"
    assert len(status_resp.json()["setup_instructions"]) >= 3

    ask_resp = client.post(
        "/api/v1/aquamind/ask",
        json={"question": "What is WUE in cloud data centers?"},
    )
    assert ask_resp.status_code == 503
    assert ask_resp.json()["error"] == "bedrock_not_configured"


def test_aquamind_returns_grounded_citations_and_live_metrics(
    configured_settings: Settings,
) -> None:
    ts = datetime(2026, 11, 25, 12, 0, tzinfo=timezone.utc)
    bedrock_rt = StubBedrockRuntime()
    bedrock_client = BedrockKnowledgeBaseClient(
        configured_settings,
        agent_runtime_client=StubAgentRuntime(),
        bedrock_runtime_client=bedrock_rt,
    )
    cw_client = CloudWatchEc2Client(
        configured_settings,
        ec2_client=StubEc2Client(),
        cloudwatch_client=StubCloudWatchClient(
            results=[{"Id": "cpu_util", "Timestamps": [ts], "Values": [12.5]}]
        ),
    )
    service = AquaMindService(
        configured_settings,
        bedrock_client=bedrock_client,
        cloudwatch_client=cw_client,
    )

    app = create_app(configured_settings)
    app.dependency_overrides[get_aquamind_service] = lambda: service
    client = TestClient(app)

    resp = client.post(
        "/api/v1/aquamind/ask",
        json={"question": "How does my EC2 CPU relate to WUE?", "include_live_metrics": True},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["live_metrics_included"] is True
    assert body["live_metrics_summary"]["metrics"]["CPUUtilization"]["value"] == 12.5
    assert len(body["citations"]) == 1
    assert body["citations"][0]["source_uri"].endswith("green-grid-wue.pdf")
    assert "CloudWatch does not directly measure liters" in body["provenance_note"]


def test_aquamind_bedrock_permission_error_returns_403(
    configured_settings: Settings,
) -> None:
    bedrock_client = BedrockKnowledgeBaseClient(
        configured_settings,
        agent_runtime_client=StubAgentRuntime(error=make_client_error("AccessDeniedException")),
        bedrock_runtime_client=StubBedrockRuntime(),
    )
    cw_client = CloudWatchEc2Client(
        configured_settings,
        ec2_client=StubEc2Client(),
        cloudwatch_client=StubCloudWatchClient(),
    )
    service = AquaMindService(
        configured_settings,
        bedrock_client=bedrock_client,
        cloudwatch_client=cw_client,
    )

    app = create_app(configured_settings)
    app.dependency_overrides[get_aquamind_service] = lambda: service
    client = TestClient(app)

    resp = client.post("/api/v1/aquamind/ask", json={"question": "Explain WUE"})
    assert resp.status_code == 403
    assert resp.json()["error"] == "aws_permission_denied"
