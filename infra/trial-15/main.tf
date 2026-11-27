data "aws_caller_identity" "current" {}

locals {
  issue         = 15
  function_name = "chaos-lab-etl-issue-${local.issue}"
  log_group     = "/aws/lambda/${local.function_name}"
  input_key     = "online-retail-ii/online_retail_II.xlsx"
  output_key    = "online-retail-ii/trials/issue-${local.issue}/online_retail_ii.parquet"
  table         = "trial_issue_${local.issue}.transactions"
  description   = "Function ${local.function_name}; logs ${local.log_group} (a failure logs one line 'etl step=<step> failed: <reason>'); reads s3://${var.bucket}/${local.input_key}; writes s3://${var.bucket}/${local.output_key}; loads ${local.table} in database ${var.db_name} on ${var.db_host}."
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
    resources = ["arn:aws:s3:::${var.bucket}/${local.input_key}"]
  }
  statement {
    actions   = ["s3:PutObject"]
    resources = ["arn:aws:s3:::${var.bucket}/${local.output_key}"]
  }
  statement {
    actions   = ["rds-db:connect"]
    resources = ["arn:aws:rds-db:${var.region}:${data.aws_caller_identity.current.account_id}:dbuser:${var.db_resource_id}/${var.db_user}"]
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
  architectures    = ["x86_64"]
  handler          = "retail_etl.handler.handler"
  filename         = var.lambda_package
  source_code_hash = filebase64sha256(var.lambda_package)
  timeout          = 900
  memory_size      = 3008

  ephemeral_storage {
    size = 2048
  }

  environment {
    variables = {
      DB_HOST = var.db_host
      DB_PORT = tostring(var.db_port)
      DB_NAME = var.db_name
      DB_USER = var.db_user
    }
  }

  vpc_config {
    subnet_ids         = var.subnet_ids
    security_group_ids = var.security_group_ids
  }

  depends_on = [aws_cloudwatch_log_group.etl, aws_iam_role_policy.etl]
}

resource "aws_cloudwatch_event_rule" "daily" {
  name                = "${local.function_name}-daily"
  description         = "Runs ${local.function_name} daily at 06:00 UTC"
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
  alarm_description   = "The ETL raised an error in the last day. ${local.description}"
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions          = { FunctionName = local.function_name }
  statistic           = "Sum"
  period              = 86400
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alarms.arn]
}

resource "aws_cloudwatch_metric_alarm" "no_success" {
  alarm_name          = "${local.function_name}-no-success"
  alarm_description   = "No successful run in 26 hours. ${local.description}"
  comparison_operator = "LessThanThreshold"
  threshold           = 1
  evaluation_periods  = 26
  datapoints_to_alarm = 26
  treat_missing_data  = "breaching"
  alarm_actions       = [aws_sns_topic.alarms.arn]

  metric_query {
    id          = "ok"
    expression  = "invocations - errors"
    label       = "Successful invocations"
    return_data = true
  }

  metric_query {
    id = "invocations"
    metric {
      namespace   = "AWS/Lambda"
      metric_name = "Invocations"
      dimensions  = { FunctionName = local.function_name }
      period      = 3600
      stat        = "Sum"
    }
  }

  metric_query {
    id = "errors"
    metric {
      namespace   = "AWS/Lambda"
      metric_name = "Errors"
      dimensions  = { FunctionName = local.function_name }
      period      = 3600
      stat        = "Sum"
    }
  }
}
