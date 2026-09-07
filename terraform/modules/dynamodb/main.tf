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

variable "table_name" {
  type    = string
  default = "ToggleMasterAnalytics"
}

resource "aws_dynamodb_table" "analytics" {
  name         = var.table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "event_id"
  range_key    = "timestamp"

  attribute {
    name = "event_id"
    type = "S"
  }

  attribute {
    name = "timestamp"
    type = "S"
  }

  server_side_encryption {
    enabled = true
  }

  tags = {
    Environment = var.environment
    Project     = var.project_name
  }
}

output "table_name" {
  value = aws_dynamodb_table.analytics.name
}

output "table_arn" {
  value = aws_dynamodb_table.analytics.arn
}