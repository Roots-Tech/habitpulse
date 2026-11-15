#!/bin/sh
set -e

echo "==> [HabitPulse] Checking PostgreSQL database connection..."
until pg_isready -h db -p 5432 -U "${DB_USER:-habit_user}"; do
  echo "==> [HabitPulse] Waiting for PostgreSQL database to accept connections..."
  sleep 2
done
echo "==> [HabitPulse] Database is ready!"

echo "==> [HabitPulse] Applying safe database migrations..."
python manage.py migrate --noinput

echo "==> [HabitPulse] Collecting static files..."
python manage.py collectstatic --noinput

echo "==> [HabitPulse] Starting application server..."
exec "$@"
