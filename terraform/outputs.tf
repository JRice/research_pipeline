output "nginx_ecr_repository_url" {
  description = "ECR repository URL for the nginx gateway image."
  value       = aws_ecr_repository.nginx.repository_url
}

output "api_ecr_repository_url" {
  description = "ECR repository URL for the API image."
  value       = aws_ecr_repository.api.repository_url
}

output "worker_ecr_repository_url" {
  description = "ECR repository URL for the worker image."
  value       = aws_ecr_repository.worker.repository_url
}

output "data_bucket_name" {
  description = "S3 bucket used for worker CSV input."
  value       = aws_s3_bucket.data.bucket
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

output "ecs_app_service_name" {
  description = "ECS service name for the combined nginx+api app."
  value       = aws_ecs_service.app.name
}

output "worker_task_family" {
  value = aws_ecs_task_definition.worker.family
}

output "public_subnet_ids" {
  value = aws_subnet.public[*].id
}

output "app_security_group_id" {
  value = aws_security_group.app.id
}

output "app_public_ip_note" {
  description = "How to find the app's public IP after deployment."
  value       = "Run: aws ecs list-tasks --cluster ${aws_ecs_cluster.main.name} --service-name ${aws_ecs_service.app.name} | xargs aws ecs describe-tasks --cluster ${aws_ecs_cluster.main.name} --tasks | jq -r '.tasks[].attachments[].details[] | select(.name==\"networkInterfaceId\") | .value' | xargs aws ec2 describe-network-interfaces --network-interface-ids | jq -r '.NetworkInterfaces[].Association.PublicIp'"
}
