# ---- Base ----
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# psycopg2-binary needs libpq at runtime; curl for healthchecks
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 curl postgresql-client \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app.py seed.py init_db.sql init_db_sqlite.sql migrate_features2.sql migrate_legacy_catchup.sql migrate_categories.sql migrate_settings.sql migrate_activity.sql migrate_purchases.sql ./
COPY kirana/ ./kirana/
COPY templates/ ./templates/
COPY static/ ./static/
COPY docker-entrypoint.sh ./docker-entrypoint.sh
RUN chmod +x ./docker-entrypoint.sh

# ---- Non-root runtime ----
# Never run the app as root: dedicated user owns the code + uploads dir
# (port 5000 needs no privileges, so this is drop-in safe).
RUN useradd -r -m -d /app -s /usr/sbin/nologin appuser \
 && mkdir -p /app/static/uploads \
 && chown -R appuser:appuser /app
USER appuser

# Uploaded logos survive restarts via named volume
VOLUME ["/app/static/uploads"]

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:5000/api/health || exit 1

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT:-5000} --workers ${WEB_WORKERS:-2} --timeout 60 app:app"]
