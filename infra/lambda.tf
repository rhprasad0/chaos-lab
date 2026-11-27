locals {
  log_group_name = "/aws/lambda/${var.function_name}"
  clean_prefix   = join("/", slice(split("/", var.clean_key), 0, length(split("/", var.clean_key)) - 1))
}

resource "aws_cloudwatch_log_group" "etl" {
  name              = local.log_group_name
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
  name               = var.function_name
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

resource "aws_iam_role_policy_attachment" "vpc_access" {
  role       = aws_iam_role.etl.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

data "aws_iam_policy_document" "etl" {
  statement {
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.etl.arn}:*"]
  }
  statement {
    actions   = ["s3:GetObject"]
    resources = ["arn:aws:s3:::${var.bucket}/${var.source_key}"]
  }
  statement {
    actions   = ["s3:PutObject"]
    resources = ["arn:aws:s3:::${var.bucket}/${local.clean_prefix}/*"]
  }
}

resource "aws_iam_role_policy" "etl" {
  name   = "etl"
  role   = aws_iam_role.etl.id
  policy = data.aws_iam_policy_document.etl.json
}

resource "aws_lambda_function" "etl" {
  function_name    = var.function_name
  role             = aws_iam_role.etl.arn
  runtime          = "python3.13"
  architectures    = ["x86_64"]
  handler          = "retail_etl.handler.handler"
  filename         = var.package_path
  source_code_hash = filebase64sha256(var.package_path)
  timeout          = 900
  memory_size      = 3008

  ephemeral_storage {
    size = 2048
  }

  environment {
    variables = {
      S3_BUCKET  = var.bucket
      SOURCE_KEY = var.source_key
      CLEAN_KEY  = var.clean_key
      PGHOST     = var.db_host
      PGPORT     = tostring(var.db_port)
      PGDATABASE = var.db_name
      PGUSER     = var.db_user
      PGPASSWORD = var.db_password
    }
  }

  vpc_config {
    subnet_ids         = var.subnet_ids
    security_group_ids = var.security_group_ids
  }

  depends_on = [aws_cloudwatch_log_group.etl, aws_iam_role_policy.etl, aws_iam_role_policy_attachment.vpc_access]
}

resource "aws_cloudwatch_event_rule" "daily" {
  name                = "${var.function_name}-daily"
  schedule_expression = "cron(0 6 * * ? *)"
}

resource "aws_cloudwatch_event_target" "daily" {
  rule = aws_cloudwatch_event_rule.daily.name
  arn  = aws_lambda_function.etl.arn
}

resource "aws_lambda_permission" "daily" {
  statement_id  = "AllowEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.etl.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.daily.arn
}
