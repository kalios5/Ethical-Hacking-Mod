#!/bin/bash
set -e

# wait for Postgres to accept connections
until pg_isready -h db -p 5432 -U "${DB_USERNAME}"; do
  echo "Waiting for postgres..."
  sleep 1
done
service cron start
flask db upgrade
exec gunicorn -b :5000 --access-logfile - --error-logfile - "main:app"