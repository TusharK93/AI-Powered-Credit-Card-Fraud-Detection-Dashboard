
#!/bin/sh
# Starts a password-protected MLflow tracking server.

set -eu

: "${MLFLOW_BACKEND_STORE_URI:?Set MLFLOW_BACKEND_STORE_URI to your Postgres connection string}"
: "${MLFLOW_ADMIN_PASSWORD:?Set MLFLOW_ADMIN_PASSWORD}"
: "${MLFLOW_ADMIN_USERNAME:=admin}"

# Configure artifact storage.
ARTIFACTS="${MLFLOW_ARTIFACTS_DESTINATION:-/tmp/mlflow-artifacts}"
mkdir -p "$ARTIFACTS"

# Normalize Render's postgres:// URL for SQLAlchemy.
BACKEND="$(printf '%s' "$MLFLOW_BACKEND_STORE_URI" |
    tr -d ' \t\r\n"'"'"' |
    sed 's#^postgres://#postgresql://#')"

export BACKEND

# Validate the database URL and test connectivity.
python - <<'PY'
import os
import sys
import time
from urllib.parse import urlsplit

url = os.environ["BACKEND"]
p = urlsplit(url)
host = p.hostname or ""

print(
    f"[entrypoint] database host={host!r} "
    f"port={p.port or 5432} "
    f"db={p.path.lstrip('/')!r} "
    f"user={p.username!r}",
    flush=True,
)

if p.scheme not in ("postgresql", "postgresql+psycopg2"):
    sys.exit("[entrypoint] ERROR: Expected a postgresql:// database URL.")

if not host or not p.path.strip("/"):
    sys.exit("[entrypoint] ERROR: Database URL is missing its host or database name.")

import psycopg2

last = None

for attempt in range(1, 7):
    try:
        connection = psycopg2.connect(url, connect_timeout=10)
        connection.close()
        print("[entrypoint] database connection OK", flush=True)
        break
    except Exception as exc:
        last = exc
        print(
            f"[entrypoint] database connection failed "
            f"(attempt {attempt}/6): {str(exc).strip()[:200]}",
            flush=True,
        )
        time.sleep(5)
else:
    sys.exit(f"[entrypoint] ERROR: Cannot connect to database: {last}")
PY

# Create MLflow basic authentication configuration.
cat > /tmp/basic_auth.ini <<INI
[mlflow]
default_permission = NO_PERMISSIONS
database_uri = ${BACKEND}
admin_username = ${MLFLOW_ADMIN_USERNAME}
admin_password = ${MLFLOW_ADMIN_PASSWORD}
authorization_function = mlflow.server.auth:authenticate_request_basic_auth
INI

export MLFLOW_AUTH_CONFIG_PATH=/tmp/basic_auth.ini

# Start MLflow.
exec mlflow server \
    --host 0.0.0.0 \
    --port "${PORT:-10000}" \
    --workers "${MLFLOW_WORKERS:-1}" \
    --backend-store-uri "$BACKEND" \
    --artifacts-destination "$ARTIFACTS" \
    --serve-artifacts \
    --app-name basic-auth
