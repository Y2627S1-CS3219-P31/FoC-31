#!/bin/sh
set -eu

# pg_dump each database to S3. DATABASE_URL carries the SQLAlchemy dialect
# (+asyncpg); libpq/pg_dump needs it stripped.
PGURL=$(printf '%s' "$DATABASE_URL" | sed 's/+asyncpg//')
TS=$(date -u +%Y%m%dT%H%M%SZ)
KEY="${DB_NAME}/${DB_NAME}-${TS}.sql.gz"

ENDPOINT=""
[ -n "${S3_ENDPOINT_URL:-}" ] && ENDPOINT="--endpoint-url ${S3_ENDPOINT_URL}"

pg_dump "$PGURL" | gzip | aws s3 cp $ENDPOINT - "s3://${S3_BUCKET}/${KEY}"
echo "backup uploaded: s3://${S3_BUCKET}/${KEY}"
