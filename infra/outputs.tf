output "function_name" {
  value = aws_lambda_function.etl.function_name
}

output "alarm_topic_arn" {
  value = aws_sns_topic.alarms.arn
}
