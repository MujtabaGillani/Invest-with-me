# Backend image.
#
# Two stages. The builder installs dependencies into a virtualenv; the runtime copies
# that venv and the application in. The point is that the compilers and build headers
# needed to install psycopg never reach the shipped image - a smaller image with less
# in it to be vulnerable.

# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

# Never write .pyc files, never buffer stdout (so container logs appear immediately).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# Dependency metadata first, and on its own layer: this layer is only rebuilt when
# pyproject.toml changes, so an application-code edit reuses the cached install.
COPY pyproject.toml ./
# A package directory has to exist for an editable-style install to resolve, but the
# real source is copied in the runtime stage.
RUN mkdir -p app && touch app/__init__.py

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install .

# ---------------------------------------------------------------------------
# Runtime
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# Non-root. If the process is ever compromised it should not own the filesystem.
RUN groupadd --system --gid 1001 psx \
    && useradd --system --uid 1001 --gid psx --create-home psx

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY --chown=psx:psx alembic.ini ./
COPY --chown=psx:psx alembic ./alembic
COPY --chown=psx:psx scripts ./scripts
COPY --chown=psx:psx app ./app

USER psx

EXPOSE 8000

# Hits the real health endpoint, which runs a SELECT 1 - so an unreachable database
# marks the container unhealthy rather than leaving it "up" and failing every request.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=4).status == 200 else 1)"

# No --reload, and no shell form: the process is PID 1 and must receive SIGTERM
# directly so it can shut down cleanly rather than being killed after a timeout.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
