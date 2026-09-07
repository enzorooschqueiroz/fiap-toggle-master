terraform {
  backend "s3" {
    bucket         = "togglemaster-terraform-state"
    key            = "toggle-master/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "terraform-lock"
    encrypt        = true
  }
}