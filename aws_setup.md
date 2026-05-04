Step-by-step AWS bootstrap from zero:

1. Create/enable your AWS account and choose one region: `us-east-2`.

2. Enable IAM Identity Center for your own CLI access. Create a user for yourself, assign that user to the AWS account, and grant the `AdministratorAccess` permission set. Then configure AWS CLI v2 with `aws configure sso`; AWS documents this as the recommended CLI authentication path for IAM Identity Center. ([AWS Documentation][1])

3. In WSL, authenticate locally:

```bash
aws sso login --profile research_pipeline
export AWS_PROFILE=research_pipeline
aws sts get-caller-identity
```

4. In IAM, create the GitHub OIDC identity provider:

```text
Provider URL: https://token.actions.githubusercontent.com
Audience: sts.amazonaws.com
```

GitHub documents OIDC as the way Actions can access AWS without long-lived AWS secrets. ([GitHub Docs][2])

5. Create an IAM role for GitHub Actions to assume. Trust only your repo/environment, ideally:

```text
repo:JRice/research_pipeline:environment:production
```

Give it enough permissions to push to ECR and update ECS. This is not what you would want to do in production, but should be acceptable for this demonstration scope.

6. In GitHub, create:

```text
Environment: production
Environment secret:
  AWS_ROLE_ARN=<the role ARN>

Repository variable:
  AWS_REGION=us-east-2
```

7. Locally, create ignored Terraform secrets:

```hcl
# terraform/terraform.tfvars
aws_region  = "us-east-2"
db_password = "long-random-password"
```

8. Apply infrastructure:

```bash
terraform -chdir=terraform init
terraform -chdir=terraform fmt
terraform -chdir=terraform validate
terraform -chdir=terraform plan -out=tfplan
terraform -chdir=terraform apply tfplan
```

Terraform should create the VPC, subnets, security groups, RDS PostgreSQL, ECR repos, ECS cluster/services/task definitions, Secrets Manager secret, S3 input bucket, CloudWatch logs, and IAM roles. ECS task roles are the correct way for containers to access AWS services such as S3. ([AWS Documentation][3])

9. Build and push images:

```bash
bash scripts/push_images.sh
```

10. Initialize the database schema:

```bash
bash scripts/aws_run_migration.sh
```

11. Generate/upload sample data and run the worker:

```bash
python generate_data.py -n 10000 -o data/sample_data.csv --seed 42

BUCKET="$(terraform -chdir=terraform output -raw data_bucket_name)"
aws s3 cp data/sample_data.csv "s3://${BUCKET}/sample_data.csv" --region us-east-2

bash scripts/aws_run_worker.sh
```

12. Get the running app URL:

```bash
bash scripts/aws_app_url.sh
```

Then test:

```text
/nginx-health
/api/health
/
```

Nothing else should need manual AWS console setup after steps 1–6. Everything application-specific should be recreated by Terraform plus the three scripts: push images, migrate DB, run worker.

[1]: https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sso.html?utm_source=chatgpt.com "Configuring IAM Identity Center authentication with the ..."
[2]: https://docs.github.com/actions/security-for-github-actions/security-hardening-your-deployments/configuring-openid-connect-in-amazon-web-services?utm_source=chatgpt.com "Configuring OpenID Connect in Amazon Web Services"
[3]: https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-iam-roles.html?utm_source=chatgpt.com "Amazon ECS task IAM role - Amazon Elastic Container Service"
