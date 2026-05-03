FROM python:3.11-slim

WORKDIR /app

COPY migrate/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY db/init.sql /app/db/init.sql
COPY migrate/migrate.py /app/migrate.py

CMD ["python", "/app/migrate.py"]
