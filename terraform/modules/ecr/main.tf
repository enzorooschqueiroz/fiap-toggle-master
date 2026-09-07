terraform {
  required_version = ">= 1.5"
}

variable "project_name" {
  type    = string
  default = "togglemaster"
}

variable "environment" {
  type    = string
  default = "dev"
}

variable "repositories" {
  type    = list(string)
  default = ["auth-service", "flag-service", "targeting-service", "evaluation-service", "analytics-service"]
}

resource "aws_ecr_repository" "services" {
  for_each = toset(var.repositories)

  name                 = "${var.project_name}/${each.value}"
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = {
    Environment = var.environment
    Project     = var.project_name
  }
}

output "repository_urls" {
  value = {
    for name, repo in aws_ecr_repository.services : name => repo.repository_url
  }
}

output "repository_names" {
  value = [for repo in aws_ecr_repository.services : repo.name]
}