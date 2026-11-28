variable "region" {
  type    = string
  default = "us-east-1"
}

variable "name" {
  type    = string
  default = "chaos-lab-retail-etl"
}

variable "bucket" {
  type    = string
  default = "chaos-lab-903859731897"
}

variable "input_key" {
  type    = string
  default = "online-retail-ii/online_retail_II.xlsx"
}

variable "output_key" {
  type    = string
  default = "online-retail-ii/clean/online_retail_ii.parquet"
}

variable "artifact_bucket" {
  type        = string
  description = "Bucket that holds the Lambda zip, which is over the 50 MB direct-upload limit."
}

variable "package_path" {
  type        = string
  description = "Zip built by package.sh."
  default     = "../build/etl.zip"
}

variable "subnet_ids" {
  type        = list(string)
  description = "Private subnets with a route to RDS and to S3 (gateway endpoint or NAT)."
}

variable "vpc_id" {
  type = string
}

variable "db_security_group_id" {
  type        = string
  description = "The RDS instance's security group; the function's group gets an ingress rule on it."
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
  description = "The RDS instance's DbiResourceId, which scopes rds-db:connect."
}

variable "schedule" {
  type    = string
  default = "cron(0 6 * * ? *)"
}

variable "github_dispatch_token" {
  type        = string
  sensitive   = true
  description = "Fine-grained GitHub token with Contents read/write on rhprasad0/chaos-lab; EventBridge sends it as the Authorization header of the repository_dispatch call."
}

variable "alarm_email" {
  type        = string
  default     = null
  description = "Address to subscribe to the alarm topic; no subscription when null."
}
