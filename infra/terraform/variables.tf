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
