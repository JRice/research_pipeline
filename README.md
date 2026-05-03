# Research Sensor Pipeline

A containerised pipeline that ingests environmental sensor readings (CSV), runs
rolling-window anomaly detection, stores results in PostgreSQL, and serves them
through a FastAPI backend and a static HTML dashboard.

---

## Architecture

```
                          +------------------------------------------+
                          |             Docker Compose               |
                          |                                          |
  browser --------------> |  nginx :8080                            |
                          |    +- /api/*  ----------------> api :8000|
                          |    +- /static/  (index.html)            |
                          |                    |                     |
                          |                    v                     |
                          |             postgres :5432               |
                          |                    ^                     |
                          |             worker (one-shot)            |
                          |              +- reads CSV                |
                          |              +- inserts sensor_readings  |
                          |              +- inserts anomalies        |
                          +------------------------------------------+

  AWS (Terraform scaffold)
  ------------------------------------------------------------------
  Internet -> ECS Fargate task (nginx :80 -> localhost:8000 <- api) -> RDS PostgreSQL
  nginx and api run as sidecars in one task; nginx holds the public IP.
  Worker runs as a separate ECS RunTask (on-demand, not a service).
  ECR stores nginx, api, and worker images.
```

---

## Quickstart

### 1. Generate sample data

```bash
# Install generator dependencies (numpy is enough locally)
pip install numpy pandas
python generate_data.py -n 5000 --anomaly-rate 0.05 -o data/sample_data.csv
```

### 2. Start all services

```bash
docker compose up --build
```

The first run initialises the database schema from `db/init.sql` automatically.

### 3. Run the ingestion worker

```bash
docker compose run --rm worker
# or point at a different file:
docker compose run --rm worker python ingest.py /data/my_data.csv
# wipe and reload:
docker compose run --rm worker python ingest.py --reset
```

### 4. Open the dashboard

Navigate to **http://localhost:8080** -- the table populates from the API.

### 5. Trigger ingest from the UI

Click **Trigger Ingest** in the dashboard (calls `POST /api/ingest`). This
requires the Docker socket to be mounted into the API container (already
configured in `compose.yml`).

---

## Environment variables

| Variable        | Default (compose)                                      | Description                                 |
|-----------------|--------------------------------------------------------|---------------------------------------------|
| `DATABASE_URL`  | `postgresql://pipeline:pipeline@postgres:5432/...`    | Full Postgres connection URL                |
| `INPUT_CSV`     | `/data/sample_data.csv`                               | CSV path inside the worker container        |
| `COMPOSE_FILE`  | `/app/compose.yml`                                    | Compose file path seen by API (ingest only) |
| `AWS_REGION`    | `us-east-1`                                           | AWS region for Terraform / CI               |
| `AWS_ROLE_ARN`  | (none)                                                | IAM role for GitHub Actions OIDC auth       |

Copy `.env.example` to `.env` and edit before running locally outside Docker.

---

## API reference

All endpoints are available at `http://localhost:8080/api/` through nginx, or
directly at `http://localhost:8000/` if you expose the API port.

| Method | Path          | Description                                           |
|--------|---------------|-------------------------------------------------------|
| GET    | `/health`     | Liveness + DB check -> `{"status":"ok","db":"ok"}`    |
| GET    | `/sensors`    | Distinct sensor IDs with reading counts               |
| GET    | `/anomalies`  | Paginated anomaly list (see params below)             |
| POST   | `/ingest`     | Trigger worker (202 Accepted + `job_id`)              |

### GET /anomalies query parameters

| Param       | Type     | Default | Description               |
|-------------|----------|---------|---------------------------|
| `sensor_id` | string   | (none)  | Filter by sensor ID       |
| `start`     | ISO 8601 | (none)  | Timestamp lower bound     |
| `end`       | ISO 8601 | (none)  | Timestamp upper bound     |
| `page`      | int >= 1 | 1       | Page number               |
| `page_size` | 1-200    | 50      | Results per page          |

---

## Terraform deployment

> **Note**: Terraform is a scaffold -- `plan` works; `apply` is manual.
> CI/CD handles image updates once the infrastructure is in place.

### Prerequisites

- AWS account with appropriate permissions
- OIDC trust relationship between the repo and the `AWS_ROLE_ARN` IAM role
- (Optional) S3 bucket for remote state -- uncomment the `backend "s3"` block in
  `terraform/main.tf` and fill in your bucket name

### Steps

```bash
# 1. Initialise
terraform -chdir=terraform init

# 2. Review the plan (no AWS changes yet)
terraform -chdir=terraform plan -var="db_password=CHANGEME"

# 3. Apply (creates VPC, RDS, ECR, ECS, IAM)
terraform -chdir=terraform apply -var="db_password=CHANGEME"

# 4. Push initial Docker images to the ECR repos shown in outputs
# (GitHub Actions handles subsequent pushes)
```

### CI/CD flow (GitHub Actions)

1. **test** -- runs `pytest` against `api/tests/` and `worker/tests/` (no DB required)
2. **deploy** (main branch only) -- builds and pushes nginx, API, and worker images to
   ECR, then forces a new ECS deployment via `aws ecs update-service`

Required GitHub secrets/variables:

| Name           | Kind     | Value                          |
|----------------|----------|--------------------------------|
| `AWS_ROLE_ARN` | Secret   | IAM role ARN for OIDC          |
| `AWS_REGION`   | Variable | e.g. `us-east-1`              |

---

## Known simplifications

- **nginx as gateway (no ALB)** -- both locally and in AWS, nginx is the public
  entry point. In ECS, nginx and api run as sidecars in one Fargate task and
  communicate over localhost. This keeps the architecture consistent across
  environments. The trade-off vs. an ALB is no built-in health-based routing or
  TLS termination at the load-balancer layer; add an NLB or ALB in front of the
  ECS service if you need those.
- **Dynamic public IP** -- without an ALB there's no stable DNS name; the task's
  public IP changes on redeploy. Use an Elastic IP or Route 53 with a health check
  in production.
- **Single-AZ RDS** -- `multi_az = false` keeps costs low in the scaffold; flip it
  for production.
- **No Secrets Manager** -- `DATABASE_URL` is passed as a plain ECS environment
  variable. In production, store credentials in AWS Secrets Manager and reference
  them via the task definition's `secrets` block.
- **Terraform not wired into CI** -- infrastructure is applied manually once;
  `aws ecs update-service` handles rolling image updates.
- **POST /ingest mounts the Docker socket** -- this is intentionally a demo
  convenience. In production, use ECS RunTask, Step Functions, or a proper job
  scheduler instead.
- **No message queue** -- the pipeline is batch/on-demand. Adding SQS/Kafka would
  be the natural next step for streaming ingest.
- The RDS instance is in a private subnet, but the app task is in a public subnet
  with a public IP and no NAT. ...Okay for the app reaching RDS because both are
  inside the VPC and the RDS security group allows traffic from the app security
  group. However, if we later move the ECS task to private subnets, it will need
  NAT or VPC endpoints for ECR/CloudWatch.