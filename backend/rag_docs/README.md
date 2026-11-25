# AquaMind RAG Source Documents (`rag_docs/`)

Upload authoritative, verifiable sustainability and cloud efficiency documents to your S3 bucket under `S3_RAG_DOCS_PREFIX` (default: `rag-docs/`) before syncing your **Amazon Bedrock Knowledge Base**.

> **Important:** AquaMind never invents citations or source passages. Every citation returned by `/api/v1/aquamind/ask` comes strictly from chunks retrieved from your synced Bedrock Knowledge Base.

## Recommended Public Source Documents to Upload

1. **Data Center Water Usage Effectiveness (WUE)**
   - The Green Grid *WUE (Water Usage Effectiveness): A Green Grid Data Center Sustainability Metric* whitepaper (defines `WUE = Annual Site Water Usage (L) / IT Equipment Energy (kWh)`).
2. **AWS Sustainability & Cloud Efficiency Documentation**
   - *AWS Well-Architected Framework — Sustainability Pillar* (PDF/HTML exported from official AWS documentation): right-sizing EC2 instances, Graviton processors, auto-scaling, storage tiering, and regional carbon/water intensity considerations.
   - *AWS Water Stewardship* public reports (explaining hyperscale cooling, recycled/non-potable water, and direct vs. indirect water use).
3. **Cloud Resource Optimization References**
   - Internal or academic notes documenting your project's methodology for connecting EC2 CPU/network/disk utilization to power draw and cooling water estimates.

## Upload & Sync Steps (Run After S3 & Bedrock KB Approval)

```bash
aws s3 cp ./your-sustainability-docs/ s3://<YOUR_AQUACOMPUTE_S3_BUCKET>/rag-docs/ --recursive
```

Then open the **Amazon Bedrock Console -> Knowledge bases -> Select your KB -> Data source -> Sync**, and set `BEDROCK_KB_ID` in `backend/.env`.
