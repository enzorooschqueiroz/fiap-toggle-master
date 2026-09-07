terraform {
  # backend "s3" configurado em backend.tf
}

provider "aws" {
  region = "us-east-1"
}

provider "kubernetes" {
  host                   = module.eks.cluster_endpoint
  cluster_ca_certificate = base64decode(module.eks.cluster_certificate_authority_data)
  token                  = data.aws_eks_cluster_auth.cluster.token
}

provider "helm" {
  kubernetes {
    host                   = module.eks.cluster_endpoint
    cluster_ca_certificate = base64decode(module.eks.cluster_certificate_authority_data)
    token                  = data.aws_eks_cluster_auth.cluster.token
  }
}

data "aws_eks_cluster_auth" "cluster" {
  name = module.eks.cluster_name
}

variable "environment" {
  type    = string
  default = "dev"
}

variable "project_name" {
  type    = string
  default = "togglemaster"
}

locals {
  environment = var.environment
}

module "networking" {
  source       = "./modules/networking"
  project_name = var.project_name
  environment  = local.environment
  vpc_cidr     = "10.0.0.0/16"
  cluster_name = "${var.project_name}-${local.environment}-eks"
}

module "eks" {
  source             = "./modules/eks"
  project_name       = var.project_name
  environment        = local.environment
  cluster_name       = "${var.project_name}-${local.environment}-eks"
  vpc_id             = module.networking.vpc_id
  private_subnet_ids = module.networking.private_subnet_ids
  public_subnet_ids  = module.networking.public_subnet_ids
}

module "rds_auth" {
  source                     = "./modules/rds"
  project_name               = var.project_name
  environment                = local.environment
  identifier                 = "auth"
  db_name                    = "auth"
  db_username                = "toggle_user"
  db_password                = var.auth_db_password
  vpc_id                     = module.networking.vpc_id
  private_subnet_ids         = module.networking.private_subnet_ids
  allowed_security_group_ids = [module.eks.cluster_security_group_id]
}

module "rds_flags" {
  source                     = "./modules/rds"
  project_name               = var.project_name
  environment                = local.environment
  identifier                 = "flags"
  db_name                    = "flags"
  db_username                = "toggle_user"
  db_password                = var.flags_db_password
  vpc_id                     = module.networking.vpc_id
  private_subnet_ids         = module.networking.private_subnet_ids
  allowed_security_group_ids = [module.eks.cluster_security_group_id]
}

module "rds_targeting" {
  source                     = "./modules/rds"
  project_name               = var.project_name
  environment                = local.environment
  identifier                 = "targeting"
  db_name                    = "targeting"
  db_username                = "toggle_user"
  db_password                = var.targeting_db_password
  vpc_id                     = module.networking.vpc_id
  private_subnet_ids         = module.networking.private_subnet_ids
  allowed_security_group_ids = [module.eks.cluster_security_group_id]
}

module "redis" {
  source                     = "./modules/elasticache"
  project_name               = var.project_name
  environment                = local.environment
  vpc_id                     = module.networking.vpc_id
  private_subnet_ids         = module.networking.private_subnet_ids
  allowed_security_group_ids = [module.eks.cluster_security_group_id]
}

module "dynamodb" {
  source       = "./modules/dynamodb"
  project_name = var.project_name
  environment  = local.environment
  table_name   = "ToggleMasterAnalytics"
}

module "sqs" {
  source       = "./modules/sqs"
  project_name = var.project_name
  environment  = local.environment
  queue_name   = "toggle-master-analytics"
}

module "ecr" {
  source       = "./modules/ecr"
  project_name = var.project_name
  environment  = local.environment
}

variable "auth_db_password" {
  type      = string
  sensitive = true
}

variable "flags_db_password" {
  type      = string
  sensitive = true
}

variable "targeting_db_password" {
  type      = string
  sensitive = true
}