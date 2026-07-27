# syntax=docker/dockerfile:1.7

FROM mcr.microsoft.com/playwright/python:v1.61.0-noble

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

COPY requirements.txt .

RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install -r requirements.txt

COPY . .

CMD ["python", "get_page_data.py"]
