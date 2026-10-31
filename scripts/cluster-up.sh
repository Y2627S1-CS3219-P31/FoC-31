#!/usr/bin/env bash
set -euo pipefail

export AWS_PROFILE="${AWS_PROFILE:-nusisb_IsbUsersPS-986918902548}"
export AWS_REGION="${AWS_REGION:-ap-southeast-1}"

HERE="$(cd "$(dirname "$0")" && pwd)"
TF_DIR="$HERE/../infra/terraform"

ID=$(terraform -chdir="$TF_DIR" output -raw instance_id)

echo "Starting $ID ..."
aws ec2 start-instances --instance-ids "$ID" >/dev/null
aws ec2 wait instance-running --instance-ids "$ID"
aws ec2 wait instance-status-ok --instance-ids "$ID"

IP=$(aws ec2 describe-instances --instance-ids "$ID" \
  --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)

echo "Instance running."
echo "URL: https://$IP.nip.io"
