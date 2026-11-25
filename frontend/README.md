# AquaCompute Frontend (Person 2 Workspace)

This directory is reserved for **Person 2's React frontend**. No frontend application code is implemented here yet (Person 1 scope covers the backend, AWS pipeline, and AquaMind RAG only).

## Connecting React to Person 1's Backend

1. Start the backend locally (`http://localhost:8000`) or use the deployed **API Gateway `HttpApiUrl`** output from `backend/infra/template.yaml`.
2. Ensure your React dev origin (default `http://localhost:5173` for Vite or `http://localhost:3000`) is listed in `CORS_ALLOW_ORIGINS` inside `backend/.env`.
3. Consume the versioned REST API under `/api/v1`:

| UI Feature | Backend Endpoint | Notes |
| :--- | :--- | :--- |
| System / AWS Readiness Banner | `GET /api/v1/config/status` & `GET /api/v1/health` | Check `configured_ready_for_live_ec2` and `configured_ready_for_aquamind` before calling AWS endpoints |
| Live EC2 Telemetry Cards | `GET /api/v1/metrics/current` | Render `value` when `status === "available"`, or `"Unavailable"` when `null` |
| Time-Series Charts | `GET /api/v1/metrics/history?start_time=...&end_time=...` | Plots live CloudWatch datapoints per metric |
| Stored Snapshots & Poll Status | `GET /api/v1/collections` & `POST /api/v1/collections/collect` | Displays DynamoDB history and latest EventBridge/manual run status |
| Water Footprint Dashboard | `GET /api/v1/footprint/status` & `POST /api/v1/footprint/estimate` | Returns `501` until Person 2 registers `WaterFootprintCalculator` in `backend/` |
| AquaMind Sustainability Chat | `GET /api/v1/aquamind/status` & `POST /api/v1/aquamind/ask` | Display `answer`, expandable `citations` (`source_uri`, `excerpt`), and `provenance_note` |

## UI Data Labeling Requirement

Keep the UI visually unambiguous between data types using the backend's classification fields:

- **`data_classification === "live_aws_data"`** (`is_live_aws_data: true`): Badge as **Live AWS Telemetry (CloudWatch)**.
- **`data_classification === "calculated_estimate"`** (`is_calculated_estimate: true`): Badge as **Calculated Estimate** and display `methodology_name` + `assumptions`.
- **Unconfigured / `503` / `501` responses**: Surface the backend's `message` and `setup_instructions` rather than falling back to fake readings.
