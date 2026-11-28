resource "aws_s3_object" "package" {
  bucket = aws_s3_bucket.emulator_artifacts.bucket
}
