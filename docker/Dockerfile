ARG PYTHON_IMAGE=python:3.12-slim-bookworm
ARG PLAYWRIGHT_IMAGE=mcr.microsoft.com/playwright/python:v1.61.0-noble

FROM ${PYTHON_IMAGE} AS python-base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=0 \
    HOME=/home/appuser

WORKDIR /app

RUN groupadd --gid 10001 appuser \
    && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin appuser \
    && mkdir -p /data/auth /data/temp \
    && chown -R appuser:appuser /app /data /home/appuser

COPY requirements/constraints.txt requirements/base.txt /tmp/requirements/
RUN --mount=type=cache,id=crawler-pip,target=/root/.cache/pip,sharing=locked \
    python -m pip install -r /tmp/requirements/base.txt


FROM python-base AS control
COPY requirements/control.txt /tmp/requirements/control.txt
RUN --mount=type=cache,id=crawler-pip,target=/root/.cache/pip,sharing=locked \
    python -m pip install -r /tmp/requirements/control.txt
COPY --chown=appuser:appuser app /app/app
COPY --chown=appuser:appuser migrations /app/migrations
COPY --chown=appuser:appuser alembic.ini /app/alembic.ini
USER appuser
CMD ["python", "-m", "app.control"]


FROM python-base AS orchestrator
COPY --chown=appuser:appuser app /app/app
USER appuser
CMD ["python", "-m", "app.orchestration"]


FROM python-base AS extractor
COPY requirements/extractor.txt /tmp/requirements/extractor.txt
RUN --mount=type=cache,id=crawler-pip,target=/root/.cache/pip,sharing=locked \
    python -m pip install -r /tmp/requirements/extractor.txt
COPY --chown=appuser:appuser app /app/app
USER appuser
CMD ["python", "-m", "app.extractor"]


FROM python-base AS learn
RUN --mount=type=cache,id=crawler-apt,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,id=crawler-apt-lists,target=/var/lib/apt/lists,sharing=locked \
    apt-get update \
    && apt-get install -y --no-install-recommends nodejs npm
COPY requirements/learn.txt /tmp/requirements/learn.txt
RUN --mount=type=cache,id=crawler-pip,target=/root/.cache/pip,sharing=locked \
    python -m pip install -r /tmp/requirements/learn.txt
COPY package.json package-lock.json /app/
RUN --mount=type=cache,id=crawler-npm,target=/root/.npm,sharing=locked \
    npm ci --omit=dev --ignore-scripts --no-audit --no-fund \
    && chown -R appuser:appuser /app/node_modules
COPY --chown=appuser:appuser app /app/app
USER appuser
CMD ["python", "-m", "app.learn"]


FROM ${PLAYWRIGHT_IMAGE} AS scraper

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=0 \
    HOME=/home/appuser \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

RUN groupadd --gid 10001 appuser \
    && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin appuser \
    && mkdir -p /data/auth /data/temp \
    && chown -R appuser:appuser /app /data /home/appuser

COPY requirements/constraints.txt requirements/base.txt requirements/scraper.txt /tmp/requirements/
RUN --mount=type=cache,id=crawler-pip,target=/root/.cache/pip,sharing=locked \
    python -m pip install -r /tmp/requirements/base.txt -r /tmp/requirements/scraper.txt
COPY --chown=appuser:appuser app /app/app
USER appuser
CMD ["python", "-m", "app.scraper"]
