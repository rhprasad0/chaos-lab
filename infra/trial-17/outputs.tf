output "function_name" {
  value = aws_lambda_function.etl.function_name
}

output "alerts_topic_arn" {
  value = aws_sns_topic.alerts.arn
}
