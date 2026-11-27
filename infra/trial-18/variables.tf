variable "region" {
  type    = string
  default = "us-east-1"
}

variable "subnet_ids" {
  type        = list(string)
  description = "Subnets the function runs in; they must reach the database and S3."
}

variable "security_group_ids" {
  type        = list(string)
  description = "Security groups for the function; they must be allowed to reach the database port."
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
  type        = string
  description = "The RDS instance's DbiResourceId (db-XXXX), used in the rds-db:connect ARN."
}

variable "package_path" {
  type        = string
  default     = "../../build/chaos-lab-etl.zip"
  description = "Lambda zip built by pipelines/package.sh."
}
