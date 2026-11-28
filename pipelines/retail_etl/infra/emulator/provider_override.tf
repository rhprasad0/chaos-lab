terraform {
  backend "local" {}
}

provider "aws" {
  region                      = var.region
  access_key                  = "test"
  secret_key                  = "test"
  skip_credentials_validation = true
  skip_requesting_account_id  = true
  skip_metadata_api_check     = true
  s3_use_path_style           = true

  endpoints {
    cloudwatch = var.emulator_url
    ec2        = var.emulator_url
    events     = var.emulator_url
    iam        = var.emulator_url
    lambda     = var.emulator_url
    logs       = var.emulator_url
    s3         = var.emulator_url
    sns        = var.emulator_url
    sts        = var.emulator_url
  }
}
