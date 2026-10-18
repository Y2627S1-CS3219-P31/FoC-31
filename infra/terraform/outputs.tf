output "backup_bucket" {
  value = aws_s3_bucket.backups.id
}

output "backup_bucket_arn" {
  value = aws_s3_bucket.backups.arn
}

output "instance_id" {
  value = aws_instance.node.id
}

output "public_ip" {
  value = aws_instance.node.public_ip
}

output "app_url" {
  value = "https://${aws_instance.node.public_ip}.nip.io"
}
