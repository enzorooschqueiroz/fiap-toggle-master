variable "project_name" {
  type    = string
  default = "togglemaster"
}

variable "environment" {
  type    = string
  default = "dev"
}

variable "vpc_cidr" {
  type    = string
  default = "10.0.0.0/16"
}

variable "availability_zones" {
  type    = list(string)
  default = ["us-east-1a", "us-east-1b", "us-east-1c"]
}

variable "nat_gateway_count" {
  type    = number
  default = 1
}

variable "cluster_name" {
  type = string
}