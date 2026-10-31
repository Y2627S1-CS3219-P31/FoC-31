variable "region" {
  type    = string
  default = "ap-southeast-1"
}

variable "project" {
  type    = string
  default = "cs3219-g31"
}

variable "backup_bucket_prefix" {
  type        = string
  description = "Prefix for the backups bucket; a random suffix makes it globally unique."
  default     = "cs3219-g31-foc-backups"
}

variable "backup_retention_days" {
  type    = number
  default = 30
}

variable "instance_type" {
  type    = string
  default = "t3.large"
}

variable "root_volume_size" {
  type    = number
  default = 30
}

variable "vpc_cidr" {
  type    = string
  default = "10.42.0.0/16"
}

variable "subnet_cidr" {
  type    = string
  default = "10.42.1.0/24"
}

variable "az" {
  type    = string
  default = "ap-southeast-1a"
}

variable "allowed_http_cidr" {
  type    = string
  default = "0.0.0.0/0"
}

variable "alert_email" {
  type    = string
  default = "e1138485@u.nus.edu"
}

variable "budget_limit_usd" {
  type    = number
  default = 30
}

variable "nightly_stop_cron" {
  type    = string
  default = "cron(0 2 * * ? *)"
}
