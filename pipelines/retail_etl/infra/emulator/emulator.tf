variable "emulator_url" {
  type = string
}

resource "aws_s3_bucket" "emulator_artifacts" {
  bucket = var.artifact_bucket
}
