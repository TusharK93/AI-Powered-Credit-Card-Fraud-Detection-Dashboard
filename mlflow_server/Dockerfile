
FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1
RUN pip install --no-cache-dir "mlflow[auth]==2.22.4" "psycopg2-binary>=2.9"
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]


FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN pip install --no-cache-dir "sqlalchemy==2.0.41" "mlflow[auth]==2.22.4" "psycopg2-binary>=2.9"
RUN python -c "import sqlalchemy; print('SQLAlchemy version:', sqlalchemy.__version__)"

COPY mlflow_server/entrypoint.sh /app/entrypoint.sh

# Normalize line endings and remove a possible UTF-8 BOM
RUN python -c "from pathlib import Path; p=Path('/app/entrypoint.sh'); b=p.read_bytes(); b=b.removeprefix(bytes.fromhex('efbbbf')).replace(bytes.fromhex('0d0a'), bytes.fromhex('0a')).replace(bytes.fromhex('0d'), bytes.fromhex('0a')); p.write_bytes(b)" \
    && chmod +x /app/entrypoint.sh

EXPOSE 10000

CMD ["/bin/sh", "/app/entrypoint.sh"]
