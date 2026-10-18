# Database backups and restore

Each database has a Kubernetes CronJob (`<db>-backup`) in its own namespace that
streams `pg_dump | gzip` to S3 at `s3://<bucket>/<db>/<db>-<timestamp>.sql.gz`.
Default schedule is `30 1 * * *` Asia/Singapore, before the 02:00 nightly
instance stop. Backups only run while the cluster is up.

The in-cluster CronJobs use a least-privilege IAM user (write-only to the
bucket, from `infra/terraform`). Restores below use an operator's own admin AWS
credentials, not that user.

## Provision the bucket and credentials (one time)

```
cd infra/terraform
terraform init
terraform apply          # creates the bucket + backup IAM user
BUCKET=$(terraform output -raw backup_bucket)
AKID=$(terraform output -raw backup_access_key_id)
SECRET=$(terraform output -raw backup_secret_access_key)
```

Create the in-cluster secret from those outputs, then deploy:

```
BACKUP_S3_BUCKET="$BUCKET" \
BACKUP_AWS_ACCESS_KEY_ID="$AKID" \
BACKUP_AWS_SECRET_ACCESS_KEY="$SECRET" \
  bash infra/k8s/secrets/secrets.template.sh
```

## Trigger a backup now

```
kubectl create job --from=cronjob/supplier-db-backup supplier-db-backup-manual -n foc-supplier
kubectl logs -f job/supplier-db-backup-manual -n foc-supplier
```

## List backups

```
aws s3 ls s3://$BUCKET/supplier_db/
```

## Restore (into a scratch database first)

Restoring into a scratch DB avoids clobbering live data. Use your own admin AWS
credentials.

```
aws s3 cp s3://$BUCKET/supplier_db/supplier_db-<timestamp>.sql.gz /tmp/dump.sql.gz
kubectl exec -n foc-supplier supplier-db-0 -- createdb -U foc supplier_db_restore
gunzip -c /tmp/dump.sql.gz | kubectl exec -i -n foc-supplier supplier-db-0 -- psql -U foc -d supplier_db_restore
kubectl exec -n foc-supplier supplier-db-0 -- psql -U foc -d supplier_db_restore -c "select count(*) from suppliers;"
```

To restore over the live database instead, scale the service to 0, drop and
recreate the live DB, restore into it, then scale back up.

## Local test against MinIO

Set `global.backup.s3EndpointUrl` to a MinIO service URL and point the
`backup-s3` secret at MinIO credentials. Everything else is identical.
