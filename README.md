# AquaCompute — Cloud-Based Water Footprint Monitoring and Optimization System

AquaCompute monitors real AWS EC2 compute telemetry via Amazon CloudWatch, persists timestamped snapshots in DynamoDB/S3, and pairs live metrics with **AquaMind**, an Amazon Bedrock Knowledge Base RAG assistant for cloud sustainability and Water Usage Effectiveness (WUE) guidance.

## Repository Structure

```text
AquaCompute/
├── backend/                  # Person 1: FastAPI, Boto3 AWS pipeline, AquaMind RAG, SAM & IAM
│   ├── app/
│   ├── infra/                # IAM policy templates + AWS SAM deployment template
│   ├── rag_docs/             # Guidance for uploading RAG source docs to S3
│   ├── tests/                # Pytest suite (error handling, permissions, contracts, security)
│   ├── .env.example
│   ├── requirements.txt
│   └── README.md
├── frontend/
│   └── README.md             # Person 2 handoff guide for the future React UI
├── .gitignore
└── README.md
```

## Division of Scope (Person 1 vs. Person 2)

| Owner | Scope | Status |
| :--- | :--- | :--- |
| **Person 1 — Cloud, Backend & RAG Engineer** | FastAPI backend, Boto3 CloudWatch EC2 telemetry, DynamoDB & S3 storage, EventBridge + Lambda collector, API Gateway SAM template, IAM policies, CloudWatch logging/alarms, AquaMind Bedrock KB RAG, API contracts | **Implemented** |
| **Person 2 — Frontend, Analytics & ML Engineer** | React frontend UI, water-footprint calculation formula (`WaterFootprintCalculator`), ML forecasting, anomaly detection, what-if optimization simulator | **Contract ready (`frontend/` & `/api/v1/footprint/*`)** |

## Data Provenance Policy (Live vs. Calculated vs. Unconfigured)

AquaCompute strictly separates real AWS telemetry from downstream calculations:

1. **`live_aws_data` (`is_live_aws_data: true`)**: Real EC2 metadata (`DescribeInstances`) and CloudWatch metrics (`CPUUtilization`, `NetworkIn`, `NetworkOut`, `DiskReadOps`, `DiskWriteOps`, `DiskReadBytes`, `DiskWriteBytes`, `StatusCheckFailed`). If CloudWatch has no datapoints for a metric, the backend returns `status: "unavailable"` and `value: null`—never synthetic numbers.
2. **`calculated_estimate` (`is_calculated_estimate: true`)**: Reserved exclusively for Person 2's `WaterFootprintCalculator` module once integrated with a documented WUE/PUE formula. Until then, `POST /api/v1/footprint/estimate` returns HTTP `501`.
3. **Important limitation**: Amazon CloudWatch **does not directly measure liters of water** consumed by an EC2 instance. AquaMind and API responses explicitly enforce this distinction.

## AWS Architecture & Services

- **Amazon EC2 & Amazon CloudWatch**: Live instance metadata and standard metrics (plus structured JSON backend logs and recommended alarms).
- **AWS Lambda + Amazon EventBridge Scheduler**: Periodic metric collection (`app.lambda_fn.collector_handler.handler`) and optional serverless API hosting (`app.lambda_fn.api_handler.handler`).
- **Amazon DynamoDB**: `AquaComputeReadings` (partition key `instance_id`, sort key `collected_at`) and `AquaComputeCollectionRuns` (partition key `run_id`).
- **Amazon S3**: Stores archived JSON metric reports (`reports/`) and curated RAG documents (`rag-docs/`).
- **Amazon API Gateway (HTTP API)**: Exposes FastAPI routes when deployed via AWS SAM.
- **Amazon Bedrock + Knowledge Bases (AquaMind)**: Grounded Q&A via `bedrock-agent-runtime:Retrieve` and `bedrock-runtime:Converse` with exact source citations.
- **Amazon Athena *(Optional / Not Provisioned)***: Omitted from the default stack to keep prototype costs minimal; can be added later over S3 `reports/` if large multi-month historical Parquet/JSON queries are needed (\$5/TB scanned).

## Least-Privilege IAM Permissions

Policy templates are located in [backend/infra/iam-policies/](backend/infra/iam-policies/):

- [backend-runtime-policy.json](backend/infra/iam-policies/backend-runtime-policy.json): `ec2:DescribeInstances`, `cloudwatch:GetMetricData`/`GetMetricStatistics`/`ListMetrics`, `dynamodb:PutItem`/`GetItem`/`Query`/`Scan` on AquaCompute tables, scoped `s3:ListBucket`/`GetObject`/`PutObject` on `reports/*` and `rag-docs/*`, `logs:CreateLogGroup`/`CreateLogStream`/`PutLogEvents` on `/aquacompute/*`, and `bedrock:Retrieve`/`InvokeModel`.
- [lambda-collector-policy.json](backend/infra/iam-policies/lambda-collector-policy.json): Scoped read on EC2/CloudWatch + write-only `dynamodb:PutItem`, `s3:PutObject` (`reports/*`), and Lambda CloudWatch Logs.
- [bedrock-kb-service-policy.json](backend/infra/iam-policies/bedrock-kb-service-policy.json): Read-only `s3:GetObject`/`ListBucket` on `rag-docs/*` and `bedrock:InvokeModel` for embeddings.

## Recommended CloudWatch Alarms & Dashboard Metrics

Defined in [backend/infra/template.yaml](backend/infra/template.yaml):

- **Alarms**:
  - `aquacompute-collector-errors-*`: `AWS/Lambda` `Errors >= 1` over 5 minutes.
  - `aquacompute-api-5xx-*`: `AWS/ApiGateway` `5XXError >= 3` over 5 minutes.
  - *(Recommended for target EC2)*: `AWS/EC2` `StatusCheckFailed >= 1` and sustained low/idle `CPUUtilization < 5%` for right-sizing alerts.
- **Dashboard widgets**:
  - Target EC2 `CPUUtilization`, `NetworkIn`/`NetworkOut`, `StatusCheckFailed`
  - Collector Lambda `Invocations`, `Duration`, `Errors`
  - DynamoDB `ConsumedReadCapacityUnits` / `ConsumedWriteCapacityUnits` & `ThrottledRequests`
  - API Gateway `Count`, `4XXError`, `5XXError`, `Latency`

## Cost Considerations (Account `584120133247` / `Inchara-Cloud`)

- **Free / Very Low Cost**: IAM (free), DynamoDB on-demand/free tier, EventBridge Scheduler (14M/month free tier), Lambda (1M requests/month free tier), S3 (5 GB free in first 12 months), basic 5-minute EC2 CloudWatch metrics (free).
- **Watch Out For**:
  - **Detailed EC2 monitoring (1-min)**: Incurs per-metric charges if enabled on EC2. Keep `CLOUDWATCH_METRIC_PERIOD_SECONDS=300` unless 1-minute resolution is needed.
  - **Bedrock Knowledge Base vector store**: Provisioning an **Amazon OpenSearch Serverless** collection carries minimum OCU hourly charges (~$175–$350+/month if left active). Only provision when ready, consider lower-cost vector backends (e.g., S3 Vectors where supported in your region), and tear down after demos.
  - **Bedrock model inference**: Pay-per-token (no AWS free tier).

## Quick Start (Local Development)

See [backend/README.md](backend/README.md) for full environment setup, API examples, and pytest instructions, and [frontend/README.md](frontend/README.md) for Person 2 integration steps.
