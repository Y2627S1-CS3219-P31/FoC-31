#!/usr/bin/env bash
set -euo pipefail

export AWS_PROFILE="${AWS_PROFILE:-nusisb_IsbUsersPS-986918902548}"
export AWS_REGION="${AWS_REGION:-ap-southeast-1}"

HERE="$(cd "$(dirname "$0")" && pwd)"
TF_DIR="$HERE/../infra/terraform"
ALARM="foc-idle-cpu"

ID=$(terraform -chdir="$TF_DIR" output -raw instance_id)

aws ec2 create-tags --resources "$ID" --tags Key=foc:autostop,Value=disabled
aws cloudwatch disable-alarm-actions --alarm-names "$ALARM"

echo "Autostop disabled for $ID."
