variable "region" {
  type    = string
  default = "us-east-1"
}

variable "package_path" {
  description = "Zip built by pipelines/build_package.sh"
  type        = string
  default     = "../../build/chaos-lab-etl.zip"
}

variable "subnet_ids" {
  description = "Subnets the function runs in; they must reach RDS, S3 and the RDS API"
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
