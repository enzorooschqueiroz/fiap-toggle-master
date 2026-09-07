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

variable "queue_name" {
  type    = string
  default = "toggle-master-analytics"
}

variable "receive_wait_time_seconds" {
  type    = number
  default = 0
}

resource "aws_sqs_queue" "analytics" {
  name                      = var.queue_name
  delay_seconds             = 0
  max_message_size          = 262144
  message_retention_seconds = 86400
  receive_wait_time_seconds = var.receive_wait_time_seconds

  policy = <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowServicePublish",
      "Effect": "Allow",
      "Principal": "*",
      "Action": "sqs:SendMessage",
      "Resource": "*",
      "Condition": {
        "ArnLike": {
          "aws:SourceArn": "arn:aws:events:${var.environment}:*"
        }
      }
    }
  ]
}
EOF

  tags = {
    Environment = var.environment
    Project     = var.project_name
  }
}

output "queue_url" {
  value = aws_sqs_queue.analytics.id
}

output "queue_arn" {
  value = aws_sqs_queue.analytics.arn
}