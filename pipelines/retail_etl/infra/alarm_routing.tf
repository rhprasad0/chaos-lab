locals {
  etl_alarm_arns = [aws_cloudwatch_metric_alarm.errors.arn, aws_cloudwatch_metric_alarm.no_success.arn]
}

resource "aws_sns_topic_subscription" "email" {
  count     = var.alarm_email == null ? 0 : 1
  topic_arn = aws_sns_topic.alarms.arn
  protocol  = "email"
  endpoint  = var.alarm_email
}

resource "aws_cloudwatch_event_rule" "alarm" {
  name        = "${var.name}-alarm"
  description = "The retail ETL alarms moving into ALARM"

  event_pattern = jsonencode({
    source      = ["aws.cloudwatch"]
    detail-type = ["CloudWatch Alarm State Change"]
    resources   = local.etl_alarm_arns
    detail      = { state = { value = ["ALARM"] } }
  })
}

resource "aws_cloudwatch_event_connection" "github" {
  name               = "${var.name}-github"
  authorization_type = "API_KEY"

  auth_parameters {
    api_key {
      key   = "Authorization"
      value = "Bearer ${var.github_dispatch_token}"
    }
  }
}

resource "aws_cloudwatch_event_api_destination" "github" {
  name                = "${var.name}-github-dispatch"
  connection_arn      = aws_cloudwatch_event_connection.github.arn
  invocation_endpoint = "https://api.github.com/repos/rhprasad0/chaos-lab/dispatches"
  http_method         = "POST"
}

data "aws_iam_policy_document" "events_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["events.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "alarm_dispatch" {
  name               = "${var.name}-alarm-dispatch"
  assume_role_policy = data.aws_iam_policy_document.events_assume.json
}

resource "aws_iam_role_policy" "alarm_dispatch" {
  name = "invoke-github-dispatch"
  role = aws_iam_role.alarm_dispatch.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "events:InvokeApiDestination"
      Resource = aws_cloudwatch_event_api_destination.github.arn
    }]
  })
}

resource "aws_sqs_queue" "alarm_dlq" {
  name                      = "${var.name}-alarm-dlq"
  message_retention_seconds = 1209600
}

resource "aws_sqs_queue_policy" "alarm_dlq" {
  queue_url = aws_sqs_queue.alarm_dlq.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "OnlyTheAlarmRuleMaySend"
      Effect    = "Allow"
      Principal = { Service = "events.amazonaws.com" }
      Action    = "sqs:SendMessage"
      Resource  = aws_sqs_queue.alarm_dlq.arn
      Condition = { ArnEquals = { "aws:SourceArn" = aws_cloudwatch_event_rule.alarm.arn } }
    }]
  })
}

resource "aws_cloudwatch_event_target" "github" {
  rule     = aws_cloudwatch_event_rule.alarm.name
  arn      = aws_cloudwatch_event_api_destination.github.arn
  role_arn = aws_iam_role.alarm_dispatch.arn

  http_target {
    header_parameters = {
      Accept                 = "application/vnd.github+json"
      "X-GitHub-Api-Version" = "2022-11-28"
    }
  }

  input_transformer {
    input_paths = {
      alarm   = "$.detail.alarmName"
      state   = "$.detail.state.value"
      reason  = "$.detail.state.reason"
      time    = "$.time"
      account = "$.account"
      region  = "$.region"
    }
    input_template = "{\"event_type\":\"etl-alarm\",\"client_payload\":{\"alarm\":\"<alarm>\",\"state\":\"<state>\",\"reason\":\"<reason>\",\"time\":\"<time>\",\"account\":\"<account>\",\"region\":\"<region>\"}}"
  }

  dead_letter_config {
    arn = aws_sqs_queue.alarm_dlq.arn
  }

  depends_on = [aws_sqs_queue_policy.alarm_dlq]
}

resource "aws_cloudwatch_metric_alarm" "dispatch_failed" {
  alarm_name          = "${var.name}-dispatch-failed"
  alarm_description   = "EventBridge could not deliver an ETL alarm to GitHub (rule ${aws_cloudwatch_event_rule.alarm.name}). Check the API destination ${aws_cloudwatch_event_api_destination.github.name} and the github_dispatch_token."
  namespace           = "AWS/Events"
  metric_name         = "FailedInvocations"
  dimensions          = { RuleName = aws_cloudwatch_event_rule.alarm.name }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alarms.arn]
}

resource "aws_cloudwatch_metric_alarm" "dispatch_dead_letters" {
  alarm_name          = "${var.name}-dispatch-dead-letters"
  alarm_description   = "An ETL alarm event is waiting in the dead-letter queue ${aws_sqs_queue.alarm_dlq.name}: GitHub never received it."
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = aws_sqs_queue.alarm_dlq.name }
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alarms.arn]
}
