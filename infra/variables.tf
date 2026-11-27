variable "region" {
  type    = string
  default = "us-east-1"
}

variable "function_name" {
  type    = string
  default = "chaos-lab-retail-etl"
}

variable "bucket" {
  type    = string
  default = "chaos-lab-903859731897"
}

variable "source_key" {
  type    = string
  default = "online-retail-ii/online_retail_II.xlsx"
}

variable "clean_key" {
  type    = string
  default = "online-retail-ii/clean/online_retail_ii.parquet"
}

variable "package_path" {
  type        = string
  description = "Zip built by pipelines/package.sh."
}

variable "subnet_ids" {
  type        = list(string)
  description = "Subnets that can reach the database, S3 and the internet or VPC endpoints."
}

variable "security_group_ids" {
  type        = list(string)
  description = "Security groups for the function; the database must allow them."
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

variable "db_password" {
  type      = string
  sensitive = true
}
