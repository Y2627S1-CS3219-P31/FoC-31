resource "random_id" "backup_suffix" {
  byte_length = 4
}

resource "aws_s3_bucket" "backups" {
  bucket = "${var.backup_bucket_prefix}-${random_id.backup_suffix.hex}"
}

resource "aws_s3_bucket_versioning" "backups" {
  bucket = aws_s3_bucket.backups.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_public_access_block" "backups" {
  bucket                  = aws_s3_bucket.backups.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "backups" {
  bucket = aws_s3_bucket.backups.id
  rule {
    id     = "expire-old-backups"
    status = "Enabled"
    filter {}
    expiration {
      days = var.backup_retention_days
    }
    noncurrent_version_expiration {
      noncurrent_days = var.backup_retention_days
    }
  }
}

# S3 write access is granted to the EC2 instance role (Phase E); iam:CreateUser
# is denied on this account, so there is no dedicated backup user.
