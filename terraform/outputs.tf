# Outputs principais do projeto - Fase 3 ToggleMaster

output "vpc_id" {
  value = module.networking.vpc_id
}

output "cluster_name" {
  value = module.eks.cluster_name
}

output "cluster_endpoint" {
  value = module.eks.cluster_endpoint
}

output "rds_auth_endpoint" {
  value = module.rds_auth.endpoint
}

output "rds_flags_endpoint" {
  value = module.rds_flags.endpoint
}

output "rds_targeting_endpoint" {
  value = module.rds_targeting.endpoint
}

output "redis_endpoint" {
  value = module.redis.endpoint
}

output "sqs_queue_url" {
  value = module.sqs.queue_url
}

output "dynamodb_table" {
  value = module.dynamodb.table_name
}

output "ecr_repository_urls" {
  value = module.ecr.repository_urls
}