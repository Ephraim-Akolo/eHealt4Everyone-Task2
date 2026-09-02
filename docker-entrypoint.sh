#!/bin/sh
set -e

echo "Waiting for Redis at ${REDIS_HOST:-redis}:${REDIS_PORT:-6379}..."
until python -c "
import socket, os, sys
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(1)
try:
    s.connect((os.environ.get('REDIS_HOST', 'redis'), int(os.environ.get('REDIS_PORT', 6379))))
except OSError:
    sys.exit(1)
"; do
  sleep 1
done
echo "Redis is up."

python manage.py migrate --noinput

exec "$@"