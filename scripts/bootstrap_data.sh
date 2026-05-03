#!/usr/bin/env bash
python generate_data.py -n 10000 -o data/sample_data.csv --seed 42

BUCKET="$(terraform -chdir=terraform output -raw data_bucket_name)"

aws s3 cp data/sample_data.csv "s3://${BUCKET}/sample_data.csv" \
  --region us-east-2

echo "you should run scripts/aws_run_worker.sh next"
