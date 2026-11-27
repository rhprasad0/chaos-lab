variable "region" {
  type    = string
  default = "us-east-1"
}

variable "package_path" {
  description = "Zip built by pipelines/package_lambda.sh"
  type        = string
  default     = "../../dist/etl-issue-19.zip"
}

variable "subnet_ids" {
  type = list(string)
}

variable "security_group_ids" {
  type = list(string)
}

variable "db_host" {
  type = string
}

variable "db_port" {
  type    = number
  default = 5432
}

variable "db_name" {
  type    = string
  default = "chaos_lab"
}

variable "db_user" {
  type    = string
  default = "chaos_lab"
}

variable "db_resource_id" {
  description = "RDS DbiResourceId (db-XXXX) of the instance, for rds-db:connect"
  type        = string
}
