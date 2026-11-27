variable "region" {
  type    = string
  default = "us-east-1"
}

variable "bucket" {
  type    = string
  default = "chaos-lab-903859731897"
}

variable "package_path" {
  description = "Zip built by pipelines/build_lambda.sh"
  type        = string
  default     = "../../build/chaos-lab-etl-issue-17.zip"
}

variable "subnet_ids" {
  description = "Subnets the function runs in; they must reach the database, S3 and the RDS API"
  type        = list(string)
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
  description = "DbiResourceId of the RDS instance, for the rds-db:connect ARN"
  type        = string
}

variable "memory_size" {
  type    = number
  default = 3008
}

variable "timeout" {
  type    = number
  default = 900
}
