output "backup_bucket" {
  value = aws_s3_bucket.backups.id
}

output "backup_access_key_id" {
  value = aws_iam_access_key.backup.id
}

output "backup_secret_access_key" {
  value     = aws_iam_access_key.backup.secret
  sensitive = true
}
