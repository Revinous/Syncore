variable "environment" {
  description = "Deployment environment name"
  type        = string
  default     = "staging"
}

variable "project_name" {
  description = "Project name prefix"
  type        = string
  default     = "syncore"
}

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "vpc_cidr" {
  description = "VPC CIDR"
  type        = string
  default     = "10.20.0.0/16"
}

variable "public_subnet_cidrs" {
  description = "Public subnet CIDRs"
  type        = list(string)
  default     = ["10.20.1.0/24", "10.20.2.0/24"]
}

variable "private_subnet_cidrs" {
  description = "Private subnet CIDRs"
  type        = list(string)
  default     = ["10.20.11.0/24", "10.20.12.0/24"]
}

variable "orchestrator_cpu" {
  type    = number
  default = 512
}

variable "orchestrator_memory" {
  type    = number
  default = 1024
}

variable "web_cpu" {
  type    = number
  default = 512
}

variable "web_memory" {
  type    = number
  default = 1024
}

variable "orchestrator_desired_count" {
  type    = number
  default = 1
}

variable "web_desired_count" {
  type    = number
  default = 1
}

variable "orchestrator_image" {
  description = "Container image URI for orchestrator"
  type        = string
  default     = "public.ecr.aws/docker/library/python:3.11-slim"
}

variable "web_image" {
  description = "Container image URI for web"
  type        = string
  default     = "public.ecr.aws/docker/library/node:20-alpine"
}

variable "db_name" {
  type    = string
  default = "agentos"
}

variable "db_username" {
  type    = string
  default = "agentos"
}

variable "db_password" {
  description = "RDS PostgreSQL password"
  type        = string
  sensitive   = true
  default     = "replace-me-in-tfvars"
}

variable "openai_api_key" {
  description = "OpenAI API key placeholder"
  type        = string
  sensitive   = true
  default     = "replace_me"
}

variable "anthropic_api_key" {
  description = "Anthropic API key placeholder"
  type        = string
  sensitive   = true
  default     = "replace_me"
}
