data "aws_caller_identity" "current" {}

data "aws_partition" "current" {}

locals {
  bucket_arn = "arn:${data.aws_partition.current.partition}:s3:::${var.bucket}"
}

resource "aws_security_group" "etl" {
  name        = var.name
  description = "Retail ETL Lambda ENIs"
  vpc_id      = var.vpc_id
}

resource "aws_vpc_security_group_egress_rule" "database" {
  security_group_id            = aws_security_group.etl.id
  referenced_security_group_id = var.db_security_group_id
  ip_protocol                  = "tcp"
  from_port                    = var.db_port
  to_port                      = var.db_port
}

data "aws_ec2_managed_prefix_list" "s3" {
  name = "com.amazonaws.${var.region}.s3"
}

resource "aws_vpc_security_group_egress_rule" "s3" {
  security_group_id = aws_security_group.etl.id
  prefix_list_id    = data.aws_ec2_managed_prefix_list.s3.id
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
}

resource "aws_vpc_security_group_ingress_rule" "database_from_etl" {
  security_group_id            = var.db_security_group_id
  referenced_security_group_id = aws_security_group.etl.id
  ip_protocol                  = "tcp"
  from_port                    = var.db_port
  to_port                      = var.db_port
  description                  = "chaos-lab retail ETL"
}

resource "aws_s3_object" "package" {
  bucket      = var.artifact_bucket
  key         = "chaos-lab/${var.name}/etl.zip"
  source      = var.package_path
  source_hash = filemd5(var.package_path)
}

resource "aws_cloudwatch_log_group" "etl" {
  name              = "/aws/lambda/${var.name}"
  retention_in_days = 30
}

data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "etl" {
  name               = var.name
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

resource "aws_iam_role_policy_attachment" "vpc" {
  role       = aws_iam_role.etl.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

data "aws_iam_policy_document" "etl" {
  statement {
    sid       = "ReadWorkbook"
    actions   = ["s3:GetObject"]
    resources = ["${local.bucket_arn}/${var.input_key}"]
  }
  statement {
    sid       = "ListWorkbook"
    actions   = ["s3:ListBucket"]
    resources = [local.bucket_arn]
  }
  statement {
    sid       = "WriteParquet"
    actions   = ["s3:PutObject"]
    resources = ["${local.bucket_arn}/${var.output_key}"]
  }
  statement {
    sid       = "ConnectDatabase"
    actions   = ["rds-db:connect"]
    resources = ["arn:${data.aws_partition.current.partition}:rds-db:${var.region}:${data.aws_caller_identity.current.account_id}:dbuser:${var.db_resource_id}/${var.db_user}"]
  }
  statement {
    sid       = "WriteLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.etl.arn}:*"]
  }
}

resource "aws_iam_role_policy" "etl" {
  name   = var.name
  role   = aws_iam_role.etl.id
  policy = data.aws_iam_policy_document.etl.json
}

resource "aws_lambda_function" "etl" {
  function_name    = var.name
  role             = aws_iam_role.etl.arn
  runtime          = "python3.13"
  architectures    = ["x86_64"]
  handler          = "etl.handler"
  s3_bucket        = aws_s3_object.package.bucket
  s3_key           = aws_s3_object.package.key
  source_code_hash = filebase64sha256(var.package_path)
  memory_size      = 3008
  timeout          = 900

  ephemeral_storage {
    size = 2048
  }

  vpc_config {
    subnet_ids         = var.subnet_ids
    security_group_ids = [aws_security_group.etl.id]
  }

  environment {
    variables = {
      HOME       = "/tmp"
      BUCKET     = var.bucket
      INPUT_KEY  = var.input_key
      OUTPUT_KEY = var.output_key
      DB_HOST    = var.db_host
      DB_PORT    = tostring(var.db_port)
      DB_NAME    = var.db_name
      DB_USER    = var.db_user
    }
  }

  depends_on = [aws_cloudwatch_log_group.etl, aws_iam_role_policy.etl, aws_iam_role_policy_attachment.vpc]
}

resource "aws_lambda_function_event_invoke_config" "etl" {
  function_name          = aws_lambda_function.etl.function_name
  maximum_retry_attempts = 0
}

resource "aws_cloudwatch_event_rule" "daily" {
  name                = var.name
  schedule_expression = var.schedule
}

resource "aws_cloudwatch_event_target" "daily" {
  rule = aws_cloudwatch_event_rule.daily.name
  arn  = aws_lambda_function.etl.arn
}

resource "aws_lambda_permission" "daily" {
  statement_id  = "AllowDailySchedule"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.etl.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.daily.arn
}
