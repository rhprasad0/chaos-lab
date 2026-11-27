provider "aws" {
  region = var.region
}

data "aws_caller_identity" "current" {}

locals {
  issue         = 16
  bucket        = "chaos-lab-903859731897"
  function_name = "chaos-lab-etl-issue-${local.issue}"
  input_key     = "online-retail-ii/online_retail_II.xlsx"
  output_key    = "online-retail-ii/trials/issue-${local.issue}/online_retail_ii.parquet"
  table         = "trial_issue_${local.issue}.transactions"
  log_group     = "/aws/lambda/${local.function_name}"

  alarm_context = <<-EOT
    Function: ${local.function_name}. Log group: ${local.log_group} (failure lines read "ETL step <extract|clean|write|load|check> failed: <reason>").
    Reads s3://${local.bucket}/${local.input_key}; writes s3://${local.bucket}/${local.output_key}; loads table ${local.table} in database ${var.db_name} on ${var.db_host} as ${var.db_user}.
  EOT
}

resource "aws_cloudwatch_log_group" "etl" {
  name              = local.log_group
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
  name               = local.function_name
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

data "aws_iam_policy_document" "etl" {
  statement {
    actions   = ["s3:GetObject"]
    resources = ["arn:aws:s3:::${local.bucket}/${local.input_key}"]
  }
  statement {
    actions   = ["s3:PutObject"]
    resources = ["arn:aws:s3:::${local.bucket}/${local.output_key}"]
  }
  statement {
    actions = ["rds-db:connect"]
    resources = [
      "arn:aws:rds-db:${var.region}:${data.aws_caller_identity.current.account_id}:dbuser:${var.db_resource_id}/${var.db_user}",
    ]
  }
  statement {
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.etl.arn}:*"]
  }
  statement {
    actions = [
      "ec2:CreateNetworkInterface",
      "ec2:DescribeNetworkInterfaces",
      "ec2:DeleteNetworkInterface",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "etl" {
  name   = "etl"
  role   = aws_iam_role.etl.id
  policy = data.aws_iam_policy_document.etl.json
}

resource "aws_lambda_function" "etl" {
  function_name    = local.function_name
  role             = aws_iam_role.etl.arn
  runtime          = "python3.13"
  handler          = "retail_etl.handler.handler"
  filename         = var.package_path
  source_code_hash = filebase64sha256(var.package_path)
  timeout          = 900
  memory_size      = 4096

  ephemeral_storage {
    size = 1024
  }

  vpc_config {
    subnet_ids         = var.subnet_ids
    security_group_ids = var.security_group_ids
  }

  environment {
    variables = {
      DB_HOST = var.db_host
      DB_PORT = tostring(var.db_port)
      DB_NAME = var.db_name
      DB_USER = var.db_user
    }
  }

  logging_config {
    log_format = "Text"
    log_group  = aws_cloudwatch_log_group.etl.name
  }

  depends_on = [aws_iam_role_policy.etl]
}

resource "aws_cloudwatch_event_rule" "daily" {
  name                = "${local.function_name}-daily"
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

resource "aws_sns_topic" "alarms" {
  name = "${local.function_name}-alarms"
}

resource "aws_cloudwatch_metric_alarm" "errors" {
  alarm_name          = "${local.function_name}-errors"
  alarm_description   = "The daily ETL raised an error. ${local.alarm_context}"
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions          = { FunctionName = aws_lambda_function.etl.function_name }
  statistic           = "Sum"
  period              = 86400
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alarms.arn]
}

resource "aws_cloudwatch_metric_alarm" "stale" {
  alarm_name          = "${local.function_name}-no-success"
  alarm_description   = "The daily ETL has not succeeded in 26 hours. ${local.alarm_context}"
  evaluation_periods  = 26
  datapoints_to_alarm = 26
  threshold           = 1
  comparison_operator = "LessThanThreshold"
  treat_missing_data  = "breaching"
  alarm_actions       = [aws_sns_topic.alarms.arn]

  metric_query {
    id          = "successes"
    expression  = "invocations - errors"
    label       = "Successful invocations"
    return_data = true
  }

  metric_query {
    id = "invocations"
    metric {
      namespace   = "AWS/Lambda"
      metric_name = "Invocations"
      dimensions  = { FunctionName = aws_lambda_function.etl.function_name }
      period      = 3600
      stat        = "Sum"
    }
  }

  metric_query {
    id = "errors"
    metric {
      namespace   = "AWS/Lambda"
      metric_name = "Errors"
      dimensions  = { FunctionName = aws_lambda_function.etl.function_name }
      period      = 3600
      stat        = "Sum"
    }
  }
}
