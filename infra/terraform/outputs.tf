output "backup_bucket" {
  value = aws_s3_bucket.backups.id
}

output "backup_bucket_arn" {
  value = aws_s3_bucket.backups.arn
}
