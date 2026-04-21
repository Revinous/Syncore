# AWS Terraform (Phase 4)

This directory contains Phase 4 infrastructure placeholders for AWS deployment.

## Scope
- Networking: VPC, public/private subnets, routing.
- Compute: ECS cluster + Fargate services for `orchestrator` and `web`.
- Data: RDS PostgreSQL and ElastiCache Redis placeholders.
- Registry: ECR repositories.
- Secrets: Secrets Manager placeholder.

## Notes
- This is intentionally explicit and minimal for milestone scaffolding.
- Resource defaults are non-production placeholders and must be hardened before live use.
- Local Docker Compose workflow remains the primary development path.

## Quick start
```bash
cd infra/terraform
terraform init
terraform plan -var-file=environments/staging.tfvars
```

## Required variables (examples)
- `db_password`
- `openai_api_key`
- `anthropic_api_key`
- `orchestrator_image`
- `web_image`
