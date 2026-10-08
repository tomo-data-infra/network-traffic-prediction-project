# syntax=docker/dockerfile:1
#
# Build: docker build -f calendar_api.Dockerfile -t netops-backend:local .
# (build context must be the repo root -- this Dockerfile COPYs calendar_api/ and config/
# explicitly, nothing else, so unrelated directories never reach the final image regardless
# of what .dockerignore excludes from the build context)

# ---- Stage 1: install dependencies into an isolated venv ----
# Pinned to 3.12, not 3.14 (.python-version's local dev version) -- 3.14 is new enough that
# several dependencies don't ship prebuilt wheels for it yet, which was failing `pip install`
# during build (falling back to source compilation, which then failed). This means the image's
# Python version now diverges from local dev -- worth knowing if something passes locally on
# 3.14 but behaves differently in the container; revisit once wheel coverage catches up.
FROM python:3.12-slim AS builder

WORKDIR /build

# Build-time toolchain only -- discarded entirely once this stage ends; nothing here reaches
# the final image. psycopg2-binary ships prebuilt wheels for this base image, so this is a
# defensive fallback for any transitive dependency that doesn't, not a hard requirement.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# ---- Stage 2: minimal runtime image ----
FROM python:3.12-slim AS runtime

# Non-root, no login shell, no home directory -- least-privilege by default
RUN groupadd --system app && useradd --system --gid app --no-create-home --shell /usr/sbin/nologin app

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=config.settings

# Only the Django app itself -- no venv/, .git/, network-ui/, docs/, infrastructure-simulation/,
# .env, or anything else from the repo root reaches this image.
COPY manage.py ./
COPY config/ ./config/
COPY calendar_api/ ./calendar_api/

RUN chown -R app:app /app
USER app

EXPOSE 8000

# No dedicated /health endpoint exists in this app yet -- this checks the port accepts TCP
# connections, which is a real but shallow liveness signal, not a true readiness check.
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import socket; socket.create_connection(('127.0.0.1', 8000), 2).close()" || exit 1

# Run Django's own migrations (the 4 app models are all managed=False / mapped onto a
# pre-existing schema -- this only ever touches Django's built-in auth/admin/sessions tables)
# before handing off to gunicorn. `exec` replaces the shell so gunicorn receives SIGTERM
# directly for a clean shutdown, instead of the shell swallowing it.
#
# --no-control-socket: gunicorn >=25.1 defaults to a control socket under $HOME/.gunicorn/;
# the `app` user has --no-create-home (no $HOME to write to), which otherwise logs
# "Control server error: Permission denied" on every start. Not used by this deployment
# (single sync worker, nothing drives gunicornc), so disabling it is a clean fix, not a
# workaround for a capability we actually need.
CMD ["sh", "-c", "python manage.py migrate --noinput && exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers ${WEB_CONCURRENCY:-3} --no-control-socket"]
