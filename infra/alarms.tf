locals {
  alarm_context = "Function ${var.function_name}, log group ${local.log_group_name} (each failure logs one line 'step=<extract|clean|write|load> failed: <reason>'). Reads s3://${var.bucket}/${var.source_key}, writes s3://${var.bucket}/${var.clean_key}, replaces table retail.transactions in database ${var.db_name}."
}

resource "aws_sns_topic" "alarms" {
  name = "${var.function_name}-alarms"
}

resource "aws_cloudwatch_metric_alarm" "errors" {
  alarm_name          = "${var.function_name}-errors"
  alarm_description   = "The daily ETL raised an error. ${local.alarm_context}"
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions          = { FunctionName = var.function_name }
  statistic           = "Sum"
  period              = 86400
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alarms.arn]

  depends_on = [aws_lambda_function.etl]
}

resource "aws_cloudwatch_metric_alarm" "no_success" {
  alarm_name          = "${var.function_name}-no-success"
  alarm_description   = "The daily ETL has not succeeded in 26 hours: the schedule may be broken or the function not invoked. ${local.alarm_context}"
  comparison_operator = "LessThanThreshold"
  threshold           = 1
  evaluation_periods  = 26
  datapoints_to_alarm = 26
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
      dimensions  = { FunctionName = var.function_name }
      period      = 3600
      stat        = "Sum"
    }
  }

  metric_query {
    id = "errors"
    metric {
      namespace   = "AWS/Lambda"
      metric_name = "Errors"
      dimensions  = { FunctionName = var.function_name }
      period      = 3600
      stat        = "Sum"
    }
  }

  depends_on = [aws_lambda_function.etl]
}
