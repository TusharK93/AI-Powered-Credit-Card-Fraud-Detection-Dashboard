#!/bin/sh
<<<<<<< HEAD
# Starts a password-protected MLflow tracking server that also proxies artifact uploads.
set -eu
: "${MLFLOW_BACKEND_STORE_URI:?Set MLFLOW_BACKEND_STORE_URI to your Postgres connection string}"
: "${MLFLOW_ADMIN_PASSWORD:?Set MLFLOW_ADMIN_PASSWORD (letters and digits only)}"

ARTIFACTS="${MLFLOW_ARTIFACTS_DESTINATION:-/tmp/mlflow-artifacts}"
mkdir -p "$ARTIFACTS"

# Render hands out postgres://, SQLAlchemy needs postgresql://
BACKEND="$(printf '%s' "$MLFLOW_BACKEND_STORE_URI" | sed 's#^postgres://#postgresql://#')"
=======
set -eu

: "${MLFLOW_BACKEND_STORE_URI:?Missing MLFLOW_BACKEND_STORE_URI}"
: "${MLFLOW_ADMIN_PASSWORD:?Missing MLFLOW_ADMIN_PASSWORD (letters and digits only)}"

# Strip spaces/quotes that are easy to paste by accident, then postgres:// -> postgresql://
BACKEND="$(printf '%s' "$MLFLOW_BACKEND_STORE_URI" | tr -d ' \t\r\n"'"'")"
case "$BACKEND" in
  postgres://*) BACKEND="postgresql://${BACKEND#postgres://}" ;;
esac

# Pre-flight: verify the URL is complete and the database answers, with a readable error.
BACKEND="$BACKEND" python - <<'PY'
import os, sys, time
from urllib.parse import urlsplit

url = os.environ["BACKEND"]
p = urlsplit(url)
host = p.hostname or ""
print(f"[entrypoint] database host={host!r} port={p.port or 5432} db={p.path.lstrip('/')!r} user={p.username!r}", flush=True)
if p.scheme not in ("postgresql", "postgresql+psycopg2"):
    sys.exit(f"[entrypoint] ERROR: URL must start with postgresql:// (got {p.scheme!r}).")
if not host or not p.path.strip("/"):
    sys.exit("[entrypoint] ERROR: URL is incomplete (missing host or database name).")
if host.startswith("dpg-") and host.endswith("-"):
    sys.exit("[entrypoint] ERROR: database host looks cut off (ends with '-'). Internal hosts end with '-a'.")

import psycopg2
last = None
for attempt in range(1, 7):
    try:
        psycopg2.connect(url, connect_timeout=10).close()
        print("[entrypoint] database connection OK", flush=True)
        break
    except Exception as exc:
        last = exc
        print(f"[entrypoint] database not reachable (attempt {attempt}/6): {str(exc).strip()[:200]}", flush=True)
        time.sleep(5)
else:
    sys.exit(f"[entrypoint] ERROR: cannot connect to the database: {last}")
PY
>>>>>>> f339c19469c5a76f6e33e0968448b505cfb384cc

cat > /tmp/basic_auth.ini <<INI
[mlflow]
default_permission = NO_PERMISSIONS
database_uri = ${BACKEND}
admin_username = ${MLFLOW_ADMIN_USERNAME:-admin}
admin_password = ${MLFLOW_ADMIN_PASSWORD}
authorization_function = mlflow.server.auth:authenticate_request_basic_auth
INI
export MLFLOW_AUTH_CONFIG_PATH=/tmp/basic_auth.ini

<<<<<<< HEAD
exec mlflow server \
  --host 0.0.0.0 --port "${PORT:-10000}" \
  --workers "${MLFLOW_WORKERS:-1}" \
  --backend-store-uri "$BACKEND" \
  --artifacts-destination "$ARTIFACTS" --serve-artifacts \
=======
ARTIFACTS="${MLFLOW_ARTIFACTS_DESTINATION:-/tmp/mlflow-artifacts}"
mkdir -p "$ARTIFACTS"

exec mlflow server \
  --host 0.0.0.0 \
  --port "${PORT:-10000}" \
  --workers "${MLFLOW_WORKERS:-1}" \
  --backend-store-uri "$BACKEND" \
  --artifacts-destination "$ARTIFACTS" \
  --serve-artifacts \
>>>>>>> f339c19469c5a76f6e33e0968448b505cfb384cc
  --app-name basic-auth
