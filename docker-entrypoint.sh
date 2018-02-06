#!/bin/bash

TIMEOUT=120

python manage.py migrate                  # Apply database migrations
python manage.py collectstatic --noinput  # Collect static files
python manage.py graphql_schema

# Prepare log files and start outputting logs to stdout
touch /srv/logs/gunicorn.log
touch /srv/logs/access.log
touch /srv/logs/error.log
tail -n 0 -f /srv/logs/*.log &

# Start Gunicorn processes
echo Starting Gunicorn.
exec gunicorn saleor.wsgi:application \
    --name saleor \
    --bind 127.0.0.1:8000 \
    --workers 10 \
    --log-level=info \
    --timeout $TIMEOUT \
    --log-file=/srv/logs/gunicorn.log \
    --access-logfile=/srv/logs/access.log \
    --error-logfile=/srv/logs/error.log \
    "$@"
