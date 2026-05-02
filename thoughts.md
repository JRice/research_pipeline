# Thoughts on the Process

## Decision 1: Where to Host?

Locally, we're clearly going to want docker compose.

EC2:
- simpler mental model
- more manual server setup
- less cloud-native
- easier to accidentally make fragile

ECS/Fargate:
- more Terraform resources
- no server administration
- better match for Dockerized services
- more "cloud-ready"

Sounds like we should use ECS/Fargate. ECR for images, S3 for Terraform remote stuff. Whether we should replace nginx
with an ALB... but we should focus more on getting things working locally, first.


## Containers

The next decision is probably whether or not to host the anomaly detector as a separate process, or as part of the
API. I'm inclined to keep it separate, just because that's more "docker-minded" and should allow a little additional
flexibility (easier to swap out either part). The compromise is that we'd have to either have a separate python lib
for the model logic, or duplicate it. I think for this limited scope, duplication is appropriate; I can mention that
this is something worth generalizing in a larger context. So I think that leaves us with:

- postgres (this will be a PostgresSQL RDS on AWS)
- api (health checks, sensor queries, read anomaly data)
- worker (csv ingestion, insert readings, call anomaly detector, insert anomaly records)
- frontend
- nginx

I'm not yet sure whether I want the worker running constantly or spun up on-demand. I'll decide later. If the data
were supposed to be constant, we could stream it, but that's overkill for this project. Thinking simply, I could
imagine simply running something like this, periodically:

```bash
docker compose run --rm worker python ingest_and_process.py /data/sample_data_2026_05_01.csv
```

Which does something like:
- starts
- waits for Postgres
- loads CSV from mounted /data
- bulk inserts readings
- runs detector
- bulk inserts anomalies
- exits successfully

...Then again, it might be nice to just expose a simple HTTP trigger to do the load/insert/detect/insert.

## Duplicate Data

As we keep re-running the worker ingestion process, we need to consider idempotency. We could have it truncate the
data and reload when it runs, but that doesn't help us simulate longer time-spans. We could check the CSV id (and
maybe sensor ID) on insert and make it an upsert... but, again, I'm not sure that's a great simulation of how it
would work in the real world. We could also just implement a --reset flag on the worker process, so we can manually
trigger a refresh, which I think is reasonable.

That said, we should ALSO upsert against keys; we certanily don't want duplicate data.


## A Note on Python

I'm adding a local venv just to help iterate on logic without rebuilding containers. I'm picking version 3.11 just
because it's adequate and stable; I'd _like_ to use a newer version, but with the time constraint, I'd rather not
risk it. So, for docker containers we probably want:

```docker
FROM python:3.11-slim
```

### Packages

While I personally prefer uv (it seems faster and more ruby-gem-like for me), I think we should stick with pip here,
just to keep things simpler/more standard and lower-risk.

### API

Probably FastAPI rather than Flask. Auto-docs, pydantic, and async-safe. Should be simple to write, though we need
to think about pagination, given we're looking at 10K+ datasets.

### Frontend

Not worth building something in React here, since we're asked for a "simple table." In fact, I think we should try
and just keep this a simple static HTML file served by nginx and we can fetch() the data.

## The data:

Two clean tables: sensor_readings and anomalies (FK to sensor_data_id). The API query is "by date range and sensor
ID", but anomalies don't directly carry sensor_id or timestamp, so we're always joining. Options: pure normalized
with composite index on sensor_readings(sensor_id, timestamp). ...A "cleaner" option, but CPKs are always tricky
and don't scale especially well. We could also add sensor_id and timestamp as *denormalized* columns on anomalies
to avoid the join on every API call. Given the query pattern, I actually think it's worth it: it costs almost
nothing in schema complexity with this simple setup and will certainly increase speed and lower complexity.


## Terraform

Ideally, we want it to look something like:

```bash
git clone <something, todo>
cd research_pipeline
docker compose up --build
terraform -chdir=tarraform init
terraform -chdir=tarraform plan
```

...I don't think at this scope it makes sense for Terraform to run as part of the CI: apply manually once, use ECS
for re-deployment. The tarraform plan might be worth it as a check if we have time.

## Other Possibilities

For a production version, ECS Express Mode could reduce deployment boilerplate for the stateless API/frontend layer,
but we were asked to use Terraform.

RDS PostgreSQL or Aurora Serverless v2 would also make appropriate managed database options, if this were headed for
an AWS-specific deployment. I understand AWS _had_ TimeStream, which would have made an interesting alternative
choice for sensor data, but apparently that service is being sunsetted.

## Priorities

1. working Docker Compose
2. ingest + detection pipeline
3. API endpoints
4. Terraform scaffolding
5. GitHub Actions
6. nicer frontend
