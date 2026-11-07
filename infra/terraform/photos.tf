resource "random_id" "photo_suffix" {
  byte_length = 4
}

resource "aws_s3_bucket" "photos" {
  bucket = "${var.photo_bucket_prefix}-${random_id.photo_suffix.hex}"
}

resource "aws_s3_bucket_public_access_block" "photos" {
  bucket                  = aws_s3_bucket.photos.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "photos" {
  bucket = aws_s3_bucket.photos.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_ownership_controls" "photos" {
  bucket = aws_s3_bucket.photos.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

data "aws_iam_policy_document" "photos_bucket" {
  statement {
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.photos.arn, "${aws_s3_bucket.photos.arn}/*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "photos" {
  bucket = aws_s3_bucket.photos.id
  policy = data.aws_iam_policy_document.photos_bucket.json
}

resource "aws_s3_bucket_lifecycle_configuration" "photos" {
  count  = var.photo_retention_days == null ? 0 : 1
  bucket = aws_s3_bucket.photos.id
  rule {
    id     = "expire-proof-of-delivery"
    status = "Enabled"
    filter {
      prefix = "proof-of-delivery/"
    }
    expiration {
      days = var.photo_retention_days
    }
  }
}
