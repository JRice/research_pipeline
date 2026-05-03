#!/usr/bin/env bash
set -euo pipefail

AWS_REGION="${AWS_REGION:-us-east-2}"
ECS_CLUSTER="${ECS_CLUSTER:-research-pipeline}"
ECS_SERVICE="${ECS_SERVICE:-research-pipeline-app}"

TASK_ARN="$(
  aws ecs list-tasks \
    --cluster "$ECS_CLUSTER" \
    --service-name "$ECS_SERVICE" \
    --desired-status RUNNING \
    --region "$AWS_REGION" \
    --query 'taskArns[0]' \
    --output text
)"

if [[ "$TASK_ARN" == "None" || -z "$TASK_ARN" ]]; then
  echo "No running ECS task found for $ECS_SERVICE in cluster $ECS_CLUSTER" >&2
  exit 1
fi

ENI_ID="$(
  aws ecs describe-tasks \
    --cluster "$ECS_CLUSTER" \
    --tasks "$TASK_ARN" \
    --region "$AWS_REGION" \
    --query "tasks[0].attachments[0].details[?name=='networkInterfaceId'].value | [0]" \
    --output text
)"

PUBLIC_IP="$(
  aws ec2 describe-network-interfaces \
    --network-interface-ids "$ENI_ID" \
    --region "$AWS_REGION" \
    --query "NetworkInterfaces[0].Association.PublicIp" \
    --output text
)"

echo "http://${PUBLIC_IP}"
