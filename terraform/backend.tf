terraform {
  backend "s3" {
    bucket      = "togglemaster-tfstate-185796529499"
    key         = "toggle-master/terraform.tfstate"
    region      = "us-east-1"
    use_lockfile = true
    encrypt     = true
  }
}