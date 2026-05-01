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

Sounds like we should use ECS/Fargate.


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

I'm not yet sure whether I want the worker running constantly or spun up on-demand. I'll decide later. I could imagine
simply running something like this, periodically:

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

## Duplicate Data

As we keep re-running the worker ingestion process, we need to consider idempotency. We could have it truncate the
data and reload when it runs, but that doesn't help us simulate longer time-spans. We could check the CSV id (and
maybe sensor ID) on insert and make it an upsert... but, again, I'm not sure that's a great simulation of how it
would work in the real world. We could also just implement a --reset flag on the worker process, so we can manually
trigger a refresh, which I think is reasonable.


## A Note on Python

I'm adding a local venv just to help iterate on logic without rebuilding containers. I'm picking version 3.11 just
because it's adequate and stable; I'd _like_ to use a newer version, but with the time constraint, I'd rather not
risk it. So, for docker containers we probably want:

```docker
FROM python:3.11-slim
```

While I personally prefer uv (it seems faster and more ruby-gem-like for me), I think we should stick with pip here,
just to keep things simpler/more standard and lower-risk.

## Working Pattern

Ideally, we want it to look something like:

```bash
git clone <something, todo>
cd research_pipeline
docker compose up --build
terraform -chdir=tarraform init
terraform -chdir=tarraform plan
```
