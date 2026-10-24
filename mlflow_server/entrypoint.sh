
#!/bin/sh
set -eu

: "${MLFLOW_BACKEND_STORE_URI:?Missing MLFLOW_BACKEND_STORE_URI}"
: "${MLFLOW_ADMIN_PASSWORD:?Missing MLFLOW_ADMIN_PASSWORD}" 

BACKEND="$MLFLOW_BACKEND_STORE_URI"

case "$BACKEND" in
  postgres://*)
    BACKEND="postgresql://${BACKEND#postgres://}"
    ;;
esac

cat > /tmp/basic_auth.ini <<EOF
[mlflow]
database_uri = $BACKEND
admin_username = ${MLFLOW_ADMIN_USERNAME:-admin}
admin_password = $MLFLOW_ADMIN_PASSWORD
EOF

export MLFLOW_AUTH_CONFIG_PATH=/tmp/basic_auth.ini

exec mlflow server \
  --host 0.0.0.0 \
  --port "${PORT:-10000}" \
  --backend-store-uri "$BACKEND" \
  --artifacts-destination "${MLFLOW_ARTIFACTS_DESTINATION:-/tmp/mlflow-artifacts}" \
  --serve-artifacts \
  --app-name basic-auth \
  --workers "${MLFLOW_WORKERS:-1}"
