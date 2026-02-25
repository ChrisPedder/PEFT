# PEFT — Obama Q&A Model

![CI](https://github.com/ChrisPedder/PEFT/actions/workflows/ci.yml/badge.svg)

Fine-tuned Mistral-7B model that answers questions in Barack Obama's speaking style, using QLoRA (Parameter-Efficient Fine-Tuning).

## Architecture

- **Data pipeline**: Web scraping + Claude API for synthetic Q&A generation
- **Training**: QLoRA fine-tuning on SageMaker (ml.g5.xlarge)
- **Inference**: SageMaker endpoint with scale-to-zero + Lambda proxy (SSE streaming)
- **Frontend**: TypeScript + Vite, served via CloudFront
- **Infrastructure**: AWS CDK (TypeScript)

## Development

```bash
# Backend tests
cd backend && pip install -e ".[dev,inference]" && pytest --cov

# Frontend tests
cd frontend && npm ci && npm test

# CDK tests
cd infra && npm ci && npm test
```

## Workflows

| Workflow | Trigger | Description |
|----------|---------|-------------|
| CI | Push/PR to main | Python tests, TypeScript tests, CDK synth |
| Deploy | After CI passes on main | CDK deploy all stacks |
| Scrape | Manual dispatch | Scrape speeches, optionally clean & upload |
| Train | Manual dispatch | Launch SageMaker training job |
| Update Model | Manual dispatch | Swap SageMaker endpoint to new model |
