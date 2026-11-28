output "function_name" {
  value = aws_lambda_function.etl.function_name
}

output "alarm_topic_arn" {
  value = aws_sns_topic.alarms.arn
}

output "alarm_names" {
  value = [aws_cloudwatch_metric_alarm.errors.alarm_name, aws_cloudwatch_metric_alarm.no_success.alarm_name]
}
