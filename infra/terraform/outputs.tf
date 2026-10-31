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
  value = aws_eip.node.public_ip
}

output "app_url" {
  value = "https://${aws_eip.node.public_ip}.nip.io"
}

output "argocd_url" {
  value = "https://argocd.${aws_eip.node.public_ip}.nip.io"
}
