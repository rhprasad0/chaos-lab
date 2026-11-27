variable "region" {
  type    = string
  default = "us-east-1"
}

variable "bucket" {
  type    = string
  default = "chaos-lab-903859731897"
}

variable "lambda_package" {
  description = "Zip built by pipelines/build_package.sh, containing retail_etl and its dependencies."
  type        = string
  default     = "../../build/retail_etl.zip"
}

variable "subnet_ids" {
  description = "Subnets the function runs in; they need a route to S3 and to the database."
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
  description = "DbiResourceId of the RDS instance (db-XXXX), used in the rds-db:connect ARN."
  type        = string
}
