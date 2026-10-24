#!/bin/sh
# Starts a password-protected MLflow tracking server that also proxies artifact uploads.
set -eu
: "${MLFLOW_BACKEND_STORE_URI:?Set MLFLOW_BACKEND_STORE_URI to your Postgres connection string}"
: "${MLFLOW_ADMIN_PASSWORD:?Set MLFLOW_ADMIN_PASSWORD (letters and digits only)}"

ARTIFACTS="${MLFLOW_ARTIFACTS_DESTINATION:-/data/artifacts}"
mkdir -p "$ARTIFACTS"

# Render hands out postgres://, SQLAlchemy needs postgresql://
BACKEND="$(printf '%s' "$MLFLOW_BACKEND_STORE_URI" | sed 's#^postgres://#postgresql://#')"

cat > /tmp/basic_auth.ini <<INI
[mlflow]
default_permission = NO_PERMISSIONS
database_uri = ${BACKEND}
admin_username = ${MLFLOW_ADMIN_USERNAME:-admin}
admin_password = ${MLFLOW_ADMIN_PASSWORD}
authorization_function = mlflow.server.auth:authenticate_request_basic_auth
INI
export MLFLOW_AUTH_CONFIG_PATH=/tmp/basic_auth.ini

exec mlflow server \
  --host 0.0.0.0 --port "${PORT:-10000}" \
  --workers 2 \
  --backend-store-uri "$BACKEND" \
  --artifacts-destination "$ARTIFACTS" --serve-artifacts \
  --app-name basic-auth
