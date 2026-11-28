locals {
  diagnosis = "Function ${var.name}, logs ${aws_cloudwatch_log_group.etl.name} (the failing step logs 'step=<name> failed'), input s3://${var.bucket}/${var.input_key}, output s3://${var.bucket}/${var.output_key}, table ${var.db_name}.retail.transactions."
}

resource "aws_sns_topic" "alarms" {
  name = "${var.name}-alarms"
}

resource "aws_cloudwatch_metric_alarm" "errors" {
  alarm_name          = "${var.name}-errors"
  alarm_description   = "The daily retail ETL failed. ${local.diagnosis}"
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions          = { FunctionName = aws_lambda_function.etl.function_name }
  statistic           = "Sum"
  period              = 3600
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alarms.arn]
  ok_actions          = [aws_sns_topic.alarms.arn]
}

resource "aws_cloudwatch_metric_alarm" "no_success" {
  alarm_name          = "${var.name}-no-success"
  alarm_description   = "The daily retail ETL has not succeeded in 26 hours: the schedule, the function or its invocations are broken. ${local.diagnosis}"
  evaluation_periods  = 26
  datapoints_to_alarm = 26
  threshold           = 1
  comparison_operator = "LessThanThreshold"
  treat_missing_data  = "breaching"
  alarm_actions       = [aws_sns_topic.alarms.arn]
  ok_actions          = [aws_sns_topic.alarms.arn]

  metric_query {
    id          = "successes"
    expression  = "FILL(invocations, 0) - FILL(errors, 0)"
    return_data = true
  }

  metric_query {
    id = "invocations"
    metric {
      namespace   = "AWS/Lambda"
      metric_name = "Invocations"
      dimensions  = { FunctionName = aws_lambda_function.etl.function_name }
      stat        = "Sum"
      period      = 3600
    }
  }

  metric_query {
    id = "errors"
    metric {
      namespace   = "AWS/Lambda"
      metric_name = "Errors"
      dimensions  = { FunctionName = aws_lambda_function.etl.function_name }
      stat        = "Sum"
      period      = 3600
    }
  }
}
