# PEFT — Obama Q&A Model

![CI](https://github.com/ChrisPedder/PEFT/actions/workflows/ci.yml/badge.svg)
[![codecov](https://codecov.io/gh/ChrisPedder/PEFT/graph/badge.svg)](https://codecov.io/gh/ChrisPedder/PEFT)

Fine-tuned Mistral-7B model that answers questions in Barack Obama's speaking style, using QLoRA (Parameter-Efficient Fine-Tuning). Served via Amazon Bedrock Custom Model Import with a streaming FastAPI proxy.

## Architecture

```
Speeches (web) ──► Scraper (Batch) ──► Raw JSONL (S3)
                                            │
                              Claude API ◄──┘
                                  │
                          Q&A pairs (S3)
                                  │
                     SageMaker Training Job
                       (QLoRA, ml.g5.xlarge)
                                  │
                        LoRA adapter (S3)
                                  │
                   Merge adapter + base model
                                  │
                    Bedrock Custom Model Import
                                  │
        User ──► CloudFront ──► Lambda (FastAPI) ──► Bedrock converse_stream
                  │                                        │
                  └─ static assets (S3)              SSE stream ──► Frontend
```

- **Data pipeline**: Web scraping of Obama speeches + Claude API for synthetic Q&A generation
- **Training**: QLoRA fine-tuning on SageMaker with Mistral-7B-Instruct-v0.3
- **Inference**: Bedrock Custom Model Import + Lambda proxy with SSE streaming
- **Auth**: Cognito user pool with JWT validation
- **Frontend**: TypeScript + Vite SPA, served via CloudFront
- **Infrastructure**: AWS CDK (TypeScript), 6 stacks

## End-to-End Workflow

### Prerequisites

- AWS account with CDK bootstrapped
- GitHub repo secrets: `AWS_DEPLOY_ROLE_ARN` (OIDC role for CI/CD)
- Python 3.11+, Node.js 18+, [uv](https://docs.astral.sh/uv/) for Python package management

### 1. Deploy infrastructure

```bash
cd infra && npm ci && npm run deploy
```

This deploys all CDK stacks: Storage, Auth, Training, Inference, Frontend, and ScraperBatch.

### 2. Scrape speeches

Trigger the **Scrape** workflow from GitHub Actions, or run the Batch job directly:

```bash
# Via GitHub Actions
gh workflow run scrape.yml

# Or locally
cd backend
uv run python -m scraper.scrape_speeches --bucket peft-speech-data-{ACCOUNT_ID}
```

This scrapes Obama speeches from the American Presidency Project and White House Archives, storing raw JSONL files in S3.

### 3. Generate Q&A training pairs

Trigger the **Process** workflow, or run directly:

```bash
# Via GitHub Actions (sample_size=0 processes all speeches)
gh workflow run process.yml -f sample_size=0

# Or locally
cd backend
uv run python -m scraper.clean_and_format \
  --bucket peft-speech-data-{ACCOUNT_ID} \
  --output-bucket peft-training-data-{ACCOUNT_ID}
```

This sends each speech to Claude, which generates 3-5 Q&A pairs in Obama's speaking style. Output format:

```json
{"instruction": "What is your position on healthcare reform?", "input": "", "output": "Look, let me be clear..."}
```

**Note**: For good fine-tuning results, aim for 500-1,000+ Q&A pairs. 12 samples is far too few — you'll get diminishing returns beyond ~10,000 for a narrow domain like this.

### 4. Train the model

Trigger the **Train** workflow, or run directly:

```bash
# Via GitHub Actions
gh workflow run train.yml -f epochs=3 -f batch_size=4 -f learning_rate=2e-4

# Or locally
cd backend
uv run python scripts/launch_training.py --epochs 3 --batch-size 4 --learning-rate 2e-4
```

This launches a SageMaker training job that:
- Loads Mistral-7B-Instruct-v0.3 in 4-bit quantization
- Applies LoRA adapters (r=16, alpha=32) to all attention and MLP projections
- Trains on the Q&A pairs using SFTTrainer with packing
- Saves adapter weights to `s3://peft-model-artifacts-{ACCOUNT_ID}/{JOB_NAME}/output/`
- Writes metrics to the `peft-training-metrics` DynamoDB table

### 5. Merge and import to Bedrock

Trigger the **Update Model** workflow:

```bash
gh workflow run update-model.yml -f model_name=peft-obama
```

This workflow:
1. Downloads the latest adapter weights from S3
2. Creates 16GB swap on the runner (the 7B model needs more than 7GB RAM)
3. Merges the LoRA adapter into the base Mistral model
4. Fixes tokenizer files for Bedrock compatibility (adds `tokenizer.model`, sets `tokenizer_class` to `LlamaTokenizerFast`)
5. Uploads the merged model (~14GB) to `s3://.../merged-model/`
6. Imports into Bedrock as a custom model
7. Writes the model ARN to DynamoDB

You can also specify a particular training job: `-f training_job_name=peft-obama-20260226-175829`

### 6. Set the model ID on the Lambda

After the Bedrock import completes, update the Lambda to point at the new model:

```bash
# Get the imported model ARN
aws bedrock list-imported-models --query 'modelSummaries[0].modelArn' --output text

# Update the Lambda
aws lambda update-function-configuration \
  --function-name peft-inference-proxy \
  --environment "Variables={
    BEDROCK_MODEL_ID=arn:aws:bedrock:eu-central-1:{ACCOUNT_ID}:imported-model/{MODEL_ID},
    AWS_LWA_INVOKE_MODE=RESPONSE_STREAM,
    COGNITO_USER_POOL_ID={USER_POOL_ID},
    COGNITO_REGION=eu-central-1
  }"
```

### 7. Add users

Users are managed via a CLI script (self-signup is disabled):

```bash
cd backend

# Create a user
uv run python scripts/manage_users.py create --email user@example.com --password 'MyPassword123!'

# List users
uv run python scripts/manage_users.py list

# Reset password
uv run python scripts/manage_users.py reset-password --email user@example.com --password 'NewPass456!'

# Delete user
uv run python scripts/manage_users.py delete --email user@example.com
```

Password requirements: 8+ characters, at least one uppercase letter and one digit.

### 8. Use the frontend

Find the frontend URL from CDK stack outputs:

```bash
# CloudFront URL (if PeftFrontendStack is deployed)
aws cloudformation describe-stacks --stack-name PeftFrontendStack \
  --query 'Stacks[0].Outputs[?OutputKey==`DistributionDomainName`].OutputValue' --output text

# Or the Lambda Function URL directly (always available)
aws cloudformation describe-stacks --stack-name PeftInferenceStack \
  --query 'Stacks[0].Outputs[?OutputKey==`LambdaFunctionUrl`].OutputValue' --output text
```

Open the URL, log in with the credentials created in step 7, and ask questions to get streaming responses in Obama's speaking style.

## Project Structure

```
├── backend/
│   ├── scraper/              # Speech scraping and Q&A generation
│   │   ├── scrape_speeches.py
│   │   └── clean_and_format.py
│   ├── training/             # SageMaker training code
│   │   ├── train.py          # QLoRA training script
│   │   └── merge_adapter.py  # Merge LoRA into base model
│   ├── inference/            # Lambda proxy (FastAPI + Docker)
│   │   └── app.py
│   ├── scripts/              # Operational CLI tools
│   │   ├── launch_training.py
│   │   ├── import_to_bedrock.py
│   │   └── manage_users.py
│   └── tests/
├── frontend/                 # TypeScript + Vite SPA
│   └── src/
│       ├── app.ts            # Main app logic
│       ├── auth.ts           # Cognito authentication
│       └── lib.ts            # SSE parsing utilities
├── infra/                    # AWS CDK (TypeScript)
│   ├── bin/app.ts
│   └── lib/
│       ├── storage-stack.ts
│       ├── training-stack.ts
│       ├── auth-stack.ts
│       ├── inference-stack.ts
│       ├── frontend-stack.ts
│       └── scraper-batch-stack.ts
└── .github/workflows/
    ├── ci.yml                # Lint + test on push/PR
    ├── deploy.yml            # CDK deploy after CI
    ├── scrape.yml            # Batch scraping job
    ├── process.yml           # Batch Q&A generation job
    ├── train.yml             # SageMaker training job
    └── update-model.yml      # Merge + Bedrock import
```

## Development

```bash
# Backend tests
cd backend && uv sync && uv run pytest --cov

# Frontend tests
cd frontend && npm ci && npm test

# CDK tests
cd infra && npm ci && npm test
```

## Workflows

| Workflow | Trigger | Description |
|----------|---------|-------------|
| CI | Push/PR to main | Lint (black, tsc, shellcheck) + tests (pytest, vitest, CDK) |
| Deploy | After CI passes on main | CDK deploy all stacks |
| Scrape | Manual dispatch | Scrape speeches to S3 via AWS Batch |
| Process | Manual dispatch | Generate Q&A pairs via Claude on AWS Batch |
| Train | Manual dispatch | Launch SageMaker QLoRA training job |
| Update Model | Manual dispatch | Merge adapter, upload, import to Bedrock |
