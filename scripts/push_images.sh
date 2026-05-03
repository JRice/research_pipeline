#!/usr/bin/env bash
set -euo pipefail

AWS_REGION="${AWS_REGION:-us-east-2}"
PROJECT_NAME="${PROJECT_NAME:-research-pipeline}"
AWS_ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin "$REGISTRY"

for svc in nginx api worker migrate; do
  image="${REGISTRY}/${PROJECT_NAME}-${svc}:latest"

  if [[ "$svc" == "migrate" ]]; then
    docker build -f "./migrate/Dockerfile" -t "$image" "."
  else
    docker build -t "$image" "./${svc}"
  fi

  docker push "$image"
done

aws ecs update-service \
  --cluster "$PROJECT_NAME" \
  --service "${PROJECT_NAME}-app" \
  --force-new-deployment \
  --region "$AWS_REGION"
