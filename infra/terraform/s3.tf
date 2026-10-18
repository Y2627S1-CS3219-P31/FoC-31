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

# Write-only to this bucket; restores use an operator's admin credentials.
resource "aws_iam_user" "backup" {
  name = "${var.project}-backup"
}

resource "aws_iam_access_key" "backup" {
  user = aws_iam_user.backup.name
}

resource "aws_iam_user_policy" "backup" {
  name = "${var.project}-backup-s3-put"
  user = aws_iam_user.backup.name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "PutBackups"
        Effect   = "Allow"
        Action   = ["s3:PutObject"]
        Resource = "${aws_s3_bucket.backups.arn}/*"
      },
      {
        Sid      = "ListBucket"
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = aws_s3_bucket.backups.arn
      }
    ]
  })
}
