# AquaCompute Backend (Person 1)

Python + FastAPI backend for live AWS EC2 CloudWatch monitoring, DynamoDB/S3 persistence, scheduled Lambda collection, and AquaMind RAG via Amazon Bedrock Knowledge Bases.

## 1. Setup & Run Locally

```bash
cd backend
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS/Linux:
# source .venv/bin/activate

pip install -r requirements.txt
copy .env.example .env   # Windows (or `cp .env.example .env`)
```

Edit `backend/.env` with your **real** values (never commit `.env`):
- `AWS_REGION`: e.g., `us-east-1` or `ap-south-1`
- `AWS_PROFILE`: your local AWS CLI SSO/named profile (leave empty if using IAM role or env credentials)
- `EC2_INSTANCE_ID`: real EC2 instance ID (`i-...`) in your account
- `S3_BUCKET_NAME`: your AquaCompute S3 bucket (optional until S3/RAG is provisioned)
- `BEDROCK_KB_ID` & `BEDROCK_REGION`: set after provisioning your Bedrock Knowledge Base

Run the API server:

```bash
uvicorn app.main:app --reload --port 8000
```

Interactive OpenAPI docs: `http://localhost:8000/docs`

## 2. Run Automated Tests

```bash
cd backend
pytest
```

The test suite covers:
- Placeholder/invalid configuration rejection (`503 configuration_required`)
- Missing CloudWatch datapoints (`status: "unavailable"`, `value: null`, zero fabricated readings)
- Missing IAM permissions (`403 aws_permission_denied`)
- Missing AWS credentials (`503 aws_credentials_unavailable`)
- AWS API throttling (`429 aws_throttled`) and missing EC2 instance (`404`)
- DynamoDB snapshot & collection run status persistence + S3 export
- AquaMind unconfigured fallback (`503`) vs. grounded Bedrock KB citations + live metrics
- Person 2 `WaterFootprintCalculator` contract (`501` before integration, `200` after registration)
- Secret redaction in structured JSON logs and CloudWatch Logs error resilience

## 3. API Endpoints & Examples

| Method | Endpoint | Purpose |
| :--- | :--- | :--- |
| `GET` | `/api/v1/health` | Service liveness & integration readiness summary |
| `GET` | `/api/v1/config/status` | Non-secret config status & missing setup checklist |
| `GET` | `/api/v1/metrics/current` | Live EC2 metadata + latest CloudWatch metrics |
| `GET` | `/api/v1/metrics/history` | Time-series CloudWatch metrics (`start_time`, `end_time`, `period_seconds`) |
| `GET` | `/api/v1/collections` | Stored DynamoDB snapshots & latest collection run status |
| `POST` | `/api/v1/collections/collect` | Trigger on-demand collection to DynamoDB (+ optional S3 export) |
| `GET` | `/api/v1/footprint/status` | Check whether Person 2's calculator is integrated |
| `POST` | `/api/v1/footprint/estimate` | Run Person 2's water-footprint calculation (`501` until integrated) |
| `GET` | `/api/v1/aquamind/status` | Bedrock Knowledge Base readiness & setup steps |
| `POST` | `/api/v1/aquamind/ask` | Grounded RAG Q&A with exact source citations & live EC2 context |

### Example: Current Live EC2 Metrics (`GET /api/v1/metrics/current`)

```json
{
  "data_classification": "live_aws_data",
  "is_live_aws_data": true,
  "is_calculated_estimate": false,
  "is_demo_data": false,
  "source": "Amazon CloudWatch + Amazon EC2",
  "collected_at": "2026-11-25T10:00:00Z",
  "period_seconds": 300,
  "polling_interval_seconds": 300,
  "instance": {
    "instance_id": "i-0123456789abcdef0",
    "region": "us-east-1",
    "instance_type": "t3.micro",
    "state": "running",
    "availability_zone": "us-east-1a",
    "platform_details": "Linux/UNIX"
  },
  "metrics": {
    "CPUUtilization": {
      "metric_name": "CPUUtilization",
      "namespace": "AWS/EC2",
      "statistic": "Average",
      "unit": "Percent",
      "value": 18.4,
      "timestamp": "2026-11-25T09:55:00Z",
      "status": "available"
    }
  },
  "notes": [
    "Metrics reflect live AWS CloudWatch telemetry; CloudWatch does not directly measure water consumption."
  ]
}
```

### Example: AquaMind RAG (`POST /api/v1/aquamind/ask`)

Request:
```json
{
  "question": "What does WUE mean and how can reducing idle EC2 CPU help?",
  "include_live_metrics": true,
  "top_k": 5
}
```

## 4. Integrating Person 2's Water-Footprint Module

1. Implement `WaterFootprintCalculator` defined in [app/models/footprint.py](app/models/footprint.py).
2. Document your exact power/PUE/WUE formula, parameters, and source references inside `methodology_name`, `methodology_reference`, and `assumptions`.
3. Register the instance inside `get_footprint_service` in [app/api/deps.py](app/api/deps.py) (e.g., `service.register_calculator(YourCalculator())`).

## 5. Deploying with AWS SAM (After Approval)

Review [infra/template.yaml](infra/template.yaml) before deploying—no resources are created automatically.

```bash
cd backend/infra
sam build
sam deploy --guided
```
