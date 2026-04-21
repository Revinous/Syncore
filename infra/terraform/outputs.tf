output "alb_dns_name" {
  value       = aws_lb.main.dns_name
  description = "Public ALB DNS name"
}

output "ecs_cluster_name" {
  value       = aws_ecs_cluster.main.name
  description = "ECS cluster name"
}

output "rds_endpoint" {
  value       = aws_db_instance.postgres.address
  description = "RDS endpoint address"
}

output "redis_primary_endpoint" {
  value       = aws_elasticache_replication_group.redis.primary_endpoint_address
  description = "Primary Redis endpoint"
}

output "secrets_manager_secret_arn" {
  value       = aws_secretsmanager_secret.app.arn
  description = "Secrets Manager secret ARN"
}

output "ecr_orchestrator_repository_url" {
  value       = aws_ecr_repository.orchestrator.repository_url
  description = "ECR URL for orchestrator image"
}

output "ecr_web_repository_url" {
  value       = aws_ecr_repository.web.repository_url
  description = "ECR URL for web image"
}
