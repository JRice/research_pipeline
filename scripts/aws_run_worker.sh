#!/usr/bin/env bash
set -euo pipefail

AWS_REGION="${AWS_REGION:-us-east-2}"
TF_DIR="${TF_DIR:-terraform}"
DATA_FILE="${DATA_FILE:-data/sample_data.csv}"
DATA_KEY="${DATA_KEY:-sample_data.csv}"
ECS_CLUSTER="${ECS_CLUSTER:-research-pipeline}"
TASK_FAMILY="${TASK_FAMILY:-$(terraform -chdir="$TF_DIR" output -raw worker_task_family)}"

if [[ ! -f "$DATA_FILE" ]]; then
  echo "Data file not found: $DATA_FILE" >&2
  exit 1
fi

BUCKET="$(terraform -chdir="$TF_DIR" output -raw data_bucket_name)"
SUBNETS="$(
  terraform -chdir="$TF_DIR" output -json public_subnet_ids \
    | jq -r 'join(",")'
)"
SECURITY_GROUP="$(terraform -chdir="$TF_DIR" output -raw app_security_group_id)"

aws s3 cp "$DATA_FILE" "s3://${BUCKET}/${DATA_KEY}" --region "$AWS_REGION"

aws ecs run-task \
  --cluster "$ECS_CLUSTER" \
  --task-definition "$TASK_FAMILY" \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNETS],securityGroups=[$SECURITY_GROUP],assignPublicIp=ENABLED}" \
  --region "$AWS_REGION"
