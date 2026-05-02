variable "aws_region" {
  description = "AWS region for all resources."
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Prefix applied to every resource name."
  type        = string
  default     = "research-pipeline"
}

variable "environment" {
  description = "Deployment environment tag (e.g. prod, staging)."
  type        = string
  default     = "prod"
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC."
  type        = string
  default     = "10.0.0.0/16"
}

variable "db_instance_class" {
  description = "RDS instance type."
  type        = string
  default     = "db.t3.micro"
}

variable "db_name" {
  description = "Name of the PostgreSQL database."
  type        = string
  default     = "sensor_pipeline"
}

variable "db_username" {
  description = "Master username for RDS."
  type        = string
  default     = "pipeline"
}

variable "db_password" {
  description = "Master password for RDS. Supply via TF_VAR_db_password or a secrets backend."
  type        = string
  sensitive   = true
}

variable "image_tag" {
  description = "Docker image tag to deploy for all services (api, nginx, worker)."
  type        = string
  default     = "latest"
}

variable "app_cpu" {
  description = "Fargate CPU units for the combined nginx+api task (256 = 0.25 vCPU)."
  type        = number
  default     = 512 # shared across nginx and api containers
}

variable "app_memory" {
  description = "Fargate memory (MiB) for the combined nginx+api task."
  type        = number
  default     = 1024
}
