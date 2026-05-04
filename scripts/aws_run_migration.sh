#!/usr/bin/env bash
set -euo pipefail

AWS_REGION="${AWS_REGION:-us-east-2}"
PROJECT_NAME="${PROJECT_NAME:-research-pipeline}"

SUBNETS="$(terraform -chdir=terraform output -json public_subnet_ids | jq -r 'join(",")')"
SG="$(terraform -chdir=terraform output -raw app_security_group_id)"

aws ecs run-task \
  --cluster "$PROJECT_NAME" \
  --task-definition "${PROJECT_NAME}-migrate" \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNETS],securityGroups=[$SG],assignPublicIp=ENABLED}" \
  --region "$AWS_REGION"
