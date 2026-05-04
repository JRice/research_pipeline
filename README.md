# Research Sensor Pipeline

A containerized environmental sensor pipeline. It generates or ingests CSV sensor readings, stores them in PostgreSQL, detects rolling-window anomalies, exposes results through a FastAPI API, and serves a small static dashboard through nginx.

The repository supports two execution modes:

- local development with Docker Compose
- AWS deployment with Terraform, ECR, ECS Fargate, RDS PostgreSQL, S3, Secrets Manager, CloudWatch, and GitHub Actions

---

## Architecture

```text
Local Docker Compose
--------------------

browser
  |
  v
nginx :8080
  |-- /              -> static dashboard from nginx/static/index.html
  |-- /static/*      -> static assets
  |-- /api/*         -> api :8000, with /api stripped before proxying
                         |
                         v
                      postgres :5432
                         ^
                         |
                      worker, run on demand
                      - reads local CSV from /data/sample_data.csv by default
                      - inserts sensor_readings
                      - runs anomaly detection
                      - inserts anomalies

AWS
---

Internet
  |
  v
ECS Fargate app task, public subnet, public IP, no ALB
  |
  |-- nginx container :80, public entry point
  |-- api container :8000, internal to the same task network namespace
        |
        v
     RDS PostgreSQL, private subnet

Additional AWS components:
- ECR repositories for nginx, api, worker, and migrate images
- S3 data bucket for worker CSV input
- Secrets Manager secret containing DATABASE_URL
- ECS RunTask worker task for one-shot ingestion
- ECS RunTask migrate task for schema initialization/migration
- CloudWatch log groups for nginx, api, worker, and migrate
```

In Compose, nginx proxies to the `api` service name. In ECS, nginx and the API run as sidecars in the same Fargate task, so nginx proxies to `localhost:8000`.

---

## Repository layout

```text
api/                  FastAPI application and API tests
worker/               One-shot CSV ingestion worker, anomaly detector, worker tests
migrate/              One-shot schema initializer/migration image
db/init.sql           PostgreSQL schema for sensor_readings and anomalies
nginx/                nginx gateway and static dashboard
terraform/            AWS infrastructure definition
data/                 Local sample-data mount point
scripts/              AWS helper scripts, including worker RunTask helper
compose.yml           Local Docker Compose stack
generate_data.py      Synthetic sensor CSV generator
.env.example          Example local/AWS environment variables
```

---

## Local quickstart

### 1. Generate sample data

```bash
pip install numpy
python generate_data.py -n 5000 --anomaly-rate 0.05 --seed 42 -o data/sample_data.csv
```

The generator writes CSV columns expected by the worker:

```text
id,timestamp,sensor_id,temperature,humidity,pressure,location
```

It generates readings for five configured sensors and can inject spikes, drifts, sensor failures, and noise bursts. Useful options include:

```bash
python generate_data.py --help
python generate_data.py -n 1000 -o data/sample_data.csv
python generate_data.py -n 50000 -o data/large_dataset.csv --anomaly-rate 0.05
python generate_data.py -n 500 --seed 42 --start-time 2024-01-01T00:00:00Z
```

### 2. Start the stack

```bash
docker compose up --build
```

The PostgreSQL container initializes the schema from `db/init.sql` on first database creation.

### 3. Run ingestion

In another shell:

```bash
docker compose run --rm worker
```

To ingest a specific file mounted under `./data`:

```bash
docker compose run --rm worker python ingest.py /data/my_data.csv
```

To truncate both tables and reload:

```bash
docker compose run --rm worker python ingest.py --reset
```

The worker waits for PostgreSQL, loads the CSV, inserts readings with `ON CONFLICT DO NOTHING`, fetches prior per-sensor history for rolling-window context, runs anomaly detection, inserts new anomalies with `ON CONFLICT DO NOTHING`, and prints a summary.

### 4. Open the dashboard

Open:

```text
http://localhost:8080
```

The dashboard loads sensor options from `/api/sensors`, loads anomaly rows from `/api/anomalies`, supports sensor and datetime filtering, and paginates 50 results per page.

### 5. Trigger ingestion from the dashboard or API

Click **Trigger Ingest** in the dashboard, or call:

```bash
curl -X POST http://localhost:8080/api/ingest
```

This starts a background thread in the API container that runs:

```bash
docker compose -f /app/compose.yml run --rm worker
```

This is a local demo convenience. It requires the API image to contain the Docker CLI and requires the host Docker socket plus `compose.yml` to be mounted into the API container, as configured in `compose.yml`.

---

## API reference

Through nginx, use:

```text
http://localhost:8080/api/...
```

If talking directly to the API container, use:

```text
http://localhost:8000/...
```

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/health` | Checks that the API can connect to PostgreSQL and that both expected tables exist. Returns `{"status":"ok","db":"ok"}` on success. |
| `GET` | `/sensors` | Returns distinct sensor IDs and reading counts. |
| `GET` | `/anomalies` | Returns paginated anomaly records. |
| `POST` | `/ingest` | Starts the local Docker Compose worker asynchronously and returns `202 Accepted` with a `job_id`. |

### `GET /anomalies` query parameters

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `sensor_id` | string | none | Filter by sensor ID. |
| `start` | ISO datetime | none | Inclusive lower timestamp bound. |
| `end` | ISO datetime | none | Inclusive upper timestamp bound. |
| `page` | integer, `>= 1` | `1` | Result page. |
| `page_size` | integer, `1..200` | `50` | Results per page. |

Example:

```bash
curl 'http://localhost:8080/api/anomalies?sensor_id=TEMP_001&page=1&page_size=25'
```

The response shape is:

```json
{
  "total": 123,
  "page": 1,
  "page_size": 25,
  "results": []
}
```

---

## Database schema

`db/init.sql` creates two tables.

`sensor_readings` stores the raw readings:

```text
id, timestamp, sensor_id, temperature, humidity, pressure, location
```

`anomalies` stores detected anomalies:

```text
id, sensor_data_id, sensor_id, timestamp, anomaly_type, confidence_score, detected_at
```

Notable schema details:

- `sensor_readings.id` is the primary key and comes from the CSV.
- `anomalies.sensor_data_id` references `sensor_readings.id`.
- `anomalies` denormalizes `sensor_id` and `timestamp` so the API can filter anomalies without joining for every predicate.
- `UNIQUE (sensor_data_id, anomaly_type)` prevents duplicate anomaly rows when the same data is reprocessed.
- Indexes exist on `(sensor_id, timestamp)` for both readings and anomalies.

---

## Anomaly detection behavior

The worker uses `worker/anomaly_detection.py`.

Current behavior:

- processes each `sensor_id` independently
- checks `temperature`, `humidity`, and `pressure`
- computes rolling mean and standard deviation over prior readings only, using `shift(1)`
- uses a default rolling window of 20 readings
- requires at least 4 prior readings before evaluating a point
- flags readings whose absolute z-score is greater than the default threshold of 2.0
- emits anomaly types named `temperature_anomaly`, `humidity_anomaly`, and `pressure_anomaly`
- stores the absolute z-score as `confidence_score`

For incremental ingestion, the worker fetches up to `window_size` prior rows per sensor from the database, prepends that history to the new batch for detection, then discards any anomalies that belong to historical rows. This allows rolling-window detection to span multiple ingests without re-inserting old anomalies.

---

## Environment variables

| Variable | Local default / source | Description |
| --- | --- | --- |
| `DATABASE_URL` | `postgresql://pipeline:pipeline@postgres:5432/sensor_pipeline` in Compose | Full PostgreSQL connection URL. Required by API, worker, and migrate task. In ECS it is injected from Secrets Manager. |
| `INPUT_CSV` | `/data/sample_data.csv` in Compose | Local worker CSV path. Used when `INPUT_S3_URI` is not set and no CLI path is supplied. |
| `INPUT_S3_URI` | unset locally; set in Terraform worker task | S3 URI for AWS worker input. Takes precedence over `INPUT_CSV`. |
| `COMPOSE_FILE` | `/app/compose.yml` in Compose | Compose file path as seen from inside the API container for `POST /ingest`. |
| `API_HOST` | `api` in Compose; `localhost` in ECS | nginx upstream host for API proxying. |
| `AWS_REGION` | Terraform default is `us-east-2`; deploy workflow also uses `us-east-2` | AWS region used by Terraform, scripts, and deployment. Keep `.env`, Terraform, scripts, and workflow values aligned. |
| `AWS_ROLE_ARN` | GitHub secret | IAM role assumed by GitHub Actions via OIDC. |
| `ECS_CLUSTER` | `research-pipeline` | ECS cluster name used by deployment/helper scripts. |
| `ECS_APP_SERVICE` | `research-pipeline-app` | ECS service name for the combined nginx+api app task. |

Copy `.env.example` to `.env` when running local commands outside Compose, but note that Compose itself sets the important container environment variables directly in `compose.yml`.

---

## Tests and local validation

Run API tests:

```bash
pip install -r api/requirements.txt httpx requests pytest
DATABASE_URL=postgresql://test:test@localhost:5432/test pytest api/tests/ -v
```

Run worker tests:

```bash
pip install -r worker/requirements.txt pytest
DATABASE_URL=postgresql://test:test@localhost:5432/test pytest worker/tests/ -v
```

The GitHub Actions CI workflow starts a PostgreSQL 16 service container, installs API and worker dependencies separately, runs both test suites, and then verifies that the nginx, api, worker, and migrate Docker images build successfully.

---

## Terraform deployment

Terraform manages the AWS infrastructure.

### What Terraform creates

- VPC with two public and two private subnets
- Internet gateway and public route table
- security group for public HTTP access to nginx on port 80
- security group allowing RDS PostgreSQL access from the app security group
- private, single-AZ RDS PostgreSQL 16 instance
- ECR repositories for api, worker, migrate, and nginx
- private S3 data bucket with public access blocked and `force_destroy = true`
- Secrets Manager secret for `DATABASE_URL`
- ECS task execution role and task role
- S3 read permissions for the worker task role
- ECS Fargate cluster with container insights enabled
- CloudWatch log groups with 7-day retention
- ECS app task definition containing nginx and API sidecars
- ECS worker task definition for one-shot `run-task` ingestion
- ECS migrate task definition for one-shot schema initialization
- ECS service for the app task

### Prerequisites

- AWS account and credentials with permission to create the above resources
- Terraform `>= 1.6`
- AWS CLI and `jq` for helper scripts
- Docker for building images
- GitHub Actions OIDC role stored as the `AWS_ROLE_ARN` repository secret
- ECR repositories created by Terraform before the first deploy workflow expects to push images

### Apply infrastructure

```bash
terraform -chdir=terraform init
terraform -chdir=terraform plan -var="db_password=CHANGEME"
terraform -chdir=terraform apply -var="db_password=CHANGEME"
```

Alternatively, provide the password through an environment variable:

```bash
export TF_VAR_db_password='CHANGEME'
terraform -chdir=terraform apply
```

The optional remote-state backend is commented out in `terraform/main.tf`. For a shared or long-lived environment, configure that backend before running `terraform init`.

### Find useful outputs

```bash
terraform -chdir=terraform output
terraform -chdir=terraform output -raw data_bucket_name
terraform -chdir=terraform output -raw worker_task_family
terraform -chdir=terraform output -raw migrate_task_family
```

The `app_public_ip_note` output contains an AWS CLI pipeline for finding the current public IP of the ECS app task.

---

## Initial and subsequent image deployment

The deployment workflow runs on pushes to `main`. It:

1. assumes the AWS role from `secrets.AWS_ROLE_ARN`
2. logs in to ECR
3. builds and pushes nginx, api, worker, and migrate images tagged with both the Git commit SHA and `latest`
4. runs the migrate ECS task and waits for it to stop
5. fails the deployment if the migrate container exits nonzero
6. forces a new deployment of the app ECS service
7. writes a short deployment summary to the GitHub Actions job summary

The workflow currently uses fixed environment values:

```text
AWS_REGION=us-east-2
ECR_API_REPO=research-pipeline-api
ECR_WORKER_REPO=research-pipeline-worker
ECR_MIGRATE_REPO=research-pipeline-migrate
ECR_NGINX_REPO=research-pipeline-nginx
ECS_CLUSTER=research-pipeline
ECS_APP_SERVICE=research-pipeline-app
```

These names must stay aligned with Terraform variables and outputs. If `project_name`, `environment`, or `aws_region` changes in Terraform, update the workflow or parameterize it before relying on CI/CD.

---

## Running the AWS worker task

Generate or choose a CSV locally:

```bash
python generate_data.py -n 10000 -o data/sample_data.csv --seed 42
```

Upload it to the Terraform-created S3 bucket and run the worker task:

```bash
scripts/aws_run_worker.sh
```

The script defaults to:

```text
AWS_REGION=us-east-2
TF_DIR=terraform
DATA_FILE=data/sample_data.csv
DATA_KEY=sample_data.csv
ECS_CLUSTER=research-pipeline
TASK_FAMILY=$(terraform -chdir=terraform output -raw worker_task_family)
```

It uploads the file to:

```text
s3://<terraform data_bucket_name>/sample_data.csv
```

Then it starts the ECS worker task in the public subnets using the app security group. The worker task definition reads:

```text
INPUT_S3_URI=s3://<data bucket>/sample_data.csv
```

Watch worker logs with:

```bash
aws logs tail /ecs/research-pipeline-worker \
  --region us-east-2 \
  --since 15m \
  --follow
```

---

## Destroying AWS resources

Because the Terraform S3 data bucket has `force_destroy = true`, `terraform destroy` can delete the bucket even if it contains uploaded CSV objects.

```bash
terraform -chdir=terraform destroy -var="db_password=CHANGEME"
```

For anything beyond a short-lived exercise environment, remove `force_destroy = true` or set it to `false` before storing data you intend to retain.

---

## Known simplifications and trade-offs

- **No load balancer.** nginx is the public gateway in both Compose and ECS. In AWS, the ECS task receives a public IP directly. This avoids ALB setup but means there is no ALB health routing, TLS termination, or stable load-balancer DNS name.
- **Dynamic public IP.** Redeploying the ECS service can change the public IP. Add an ALB, NLB, Elastic IP pattern, or Route 53 automation for a production-style endpoint.
- **Single-AZ RDS.** `multi_az = false` keeps the environment smaller and cheaper, but it is not a highly available production database setup.
- **RDS final snapshot is skipped.** `skip_final_snapshot = true` and `deletion_protection = false` make teardown easy but unsafe for durable data.
- **S3 bucket is force-destroyed.** `force_destroy = true` is intentional for easy teardown, not for retained datasets.
- **The database password is still in Terraform state.** The runtime `DATABASE_URL` is injected through Secrets Manager, but the password originates from Terraform input and is present in Terraform state. Use remote encrypted state and tighter secret handling for production.
- **Terraform is not applied by CI/CD.** Terraform provisions infrastructure manually. GitHub Actions handles image builds, migration, and ECS service redeploys after infrastructure exists.
- **`POST /ingest` is local-demo oriented.** It shells out to Docker Compose from inside the API container. In AWS, ingestion is handled by ECS RunTask, not by that endpoint.
- **No message queue or streaming path.** Ingestion is batch/on-demand. SQS, Kafka, EventBridge, Step Functions, or scheduled ECS tasks would be natural extensions.
- **No TLS.** The current public AWS entry point is HTTP on port 80. Add an ALB/ACM or another TLS termination layer for HTTPS.
- **App task runs in public subnets.** It can reach private RDS through VPC routing and security groups. Moving the app to private subnets would require NAT or VPC endpoints for ECR, CloudWatch Logs, and other AWS APIs.
- One AWS-specific teardown gotcha is Secrets Manager name retention. If a secret is scheduled for deletion rather than force-deleted, the name remains reserved and Terraform cannot recreate it.  I set `recovery_window_in_days = 0` so future destroys remove it immediately, but if a prior delete scheduled recovery, we still have to manually restore and force-delete the secret before rebuilding, e.g.:
  Delete:
    aws secretsmanager delete-secret \
	  --secret-id research-pipeline/database-url \
	  --force-delete-without-recovery \
	  --region us-east-2
  Restore:
    aws secretsmanager restore-secret \
	  --secret-id research-pipeline/database-url \
	  --region us-east-2
- One thing I'd improve is anomaly explainability. The current table stores the anomaly type and confidence score, but not the observed value or rolling baseline that produced it. The observed value can be added cheaply from the joined sensor reading, but the more complete fix is to persist the detector’s rolling mean and standard deviation alongside each anomaly, so downstream users can see not just that something was anomalous, but _why._
- Because I skipped an ALB for scope and cost, the public entry point is the task's public IP. That keeps infrastructure small, but the IP is **not stable**. A production version would put an ALB in front, attach Route 53/ACM, and use ECS service discovery or target groups instead of asking users to chase task IPs. As a result, you should be careful to **run scripts/aws_app_url.sh** before you make requests to the site.

---

## Typical Local Workflow

```bash
source .venv/bin/activate
pip install -r requirements.txt  # IF NEEDED
python generate_data.py -n 5000 --anomaly-rate 0.05 --seed 42 -o data/sample_data.csv
docker compose up -d --build # YOU ONLY NEED THE BUILD if things have changed since you last ran it, ofc
docker compose run --rm worker

# Check app status:
curl http://localhost:8080/api/health
curl http://localhost:8080/api/sensors
curl "http://localhost:8080/api/anomalies?page=1&page_size=5"
curl "http://localhost:8080/api/anomalies?sensor_id=TEMP_001&page=1&page_size=10"
# You can also bypass nginx and hit the API directly, e.g.:
curl http://localhost:8000/health

# Check container statuses:
docker compose ps
docker compose logs api
docker compose logs nginx
docker compose logs postgres

# Prove idempotent rows:
docker compose run --rm worker python ingest.py --reset
docker compose run --rm worker # THIS SHOULD SAY 0 READINGS INSERTED.
open http://localhost:8080
```

A typical AWS workflow is:

```bash
# Enter your password for the database:
read -sp "Enter MySQL Password: " TF_VAR_db_password
export TF_VAR_db_password
# If this is your first time:
terraform -chdir=terraform init
# Otherwise:
terraform -chdir=terraform plan
terraform -chdir=terraform apply

# Next, EITHER push to main to let GitHub Actions build/push/deploy images, OR, manually:
scripts/push_images.sh
scripts/aws_run_migration.sh

# Then continue:
python generate_data.py -n 10000 -o data/sample_data.csv --seed 42
BUCKET="$(terraform -chdir=terraform output -raw data_bucket_name)"
aws s3 cp data/sample_data.csv "s3://${BUCKET}/sample_data.csv" --region <region code> # REPLACE REGION AS NEEDED
scripts/aws_run_worker.sh
scripts/aws_app_url.sh # THIS WILL TELL YOU WHERE TO GO TO VISIT THE SITE
```
