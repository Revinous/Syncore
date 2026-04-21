# Environment Guide

This project is local-first and now includes Phase 4 AWS placeholders for staging/production.

## Local (current default)

Purpose: fast iteration, debugging, and milestone development.

### Runtime
- Orchestrator: Docker Compose service (`orchestrator`)
- Web: Docker Compose service (`web`)
- PostgreSQL: Docker Compose service (`postgres`)
- Redis: Docker Compose service (`redis`)

### Configuration
- Source file: `.env`
- Template: `.env.example`
- Key endpoints:
  - Orchestrator: `http://localhost:8000`
  - Web: `http://localhost:3000`

### Commands
```bash
bash scripts/bootstrap.sh
make check
```

## Staging (AWS placeholder)

Purpose: integration verification in cloud-like runtime.

### Proposed AWS services
- ECS Fargate for `orchestrator` and `web`
- RDS PostgreSQL 16
- ElastiCache Redis 7
- ECR for container images
- Secrets Manager for runtime secrets
- ALB for inbound HTTP routing

### Terraform
- Variable set: `infra/terraform/environments/staging.tfvars`
- Plan command:
```bash
cd infra/terraform
terraform init
terraform plan -var-file=environments/staging.tfvars
```

### CI/CD
- Build and test workflow: `.github/workflows/build-test.yml`
- Terraform validation workflow: `.github/workflows/infra-validate.yml`
- Image publishing workflow: `.github/workflows/publish-images.yml`

## Production (AWS placeholder)

Purpose: resilient customer-facing deployment.

### Baseline differences vs staging
- Increased ECS desired counts.
- Hardened secrets and IAM policies.
- Strict networking (private subnets + least privilege).
- Monitoring/alerting policy enforcement.

### Terraform
- Variable set: `infra/terraform/environments/production.tfvars`
- Plan command:
```bash
cd infra/terraform
terraform init
terraform plan -var-file=environments/production.tfvars
```

## Required secret inputs (staging/production)
- `db_password`
- `openai_api_key`
- `anthropic_api_key`

## Guardrail
Local Docker Compose workflow remains authoritative for development and must continue to work as cloud assets evolve.
