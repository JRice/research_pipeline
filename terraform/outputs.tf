output "alb_dns_name" {
  description = "Public DNS name of the Application Load Balancer."
  value       = aws_lb.main.dns_name
}

output "api_ecr_repository_url" {
  description = "ECR repository URL for the API image."
  value       = aws_ecr_repository.api.repository_url
}

output "worker_ecr_repository_url" {
  description = "ECR repository URL for the worker image."
  value       = aws_ecr_repository.worker.repository_url
}

output "db_endpoint" {
  description = "RDS PostgreSQL endpoint (host:port)."
  value       = "${aws_db_instance.postgres.address}:${aws_db_instance.postgres.port}"
  sensitive   = true
}

output "ecs_cluster_name" {
  description = "ECS cluster name — use with aws ecs update-service in CI."
  value       = aws_ecs_cluster.main.name
}

output "ecs_api_service_name" {
  description = "ECS service name for the API."
  value       = aws_ecs_service.api.name
}
