#!/usr/bin/env bash
aws ecr describe-repositories \
  --region us-east-2 \
  --query "repositories[].repositoryName" \
  --output table
