FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    SERVICE_HOST=0.0.0.0

WORKDIR /app
COPY backend/requirements.txt /tmp/requirements/backend.txt
COPY execution/requirements.txt /tmp/requirements/execution.txt
COPY mocks/requirements.txt /tmp/requirements/mocks.txt
RUN pip install --no-cache-dir \
    -r /tmp/requirements/backend.txt \
    -r /tmp/requirements/execution.txt \
    -r /tmp/requirements/mocks.txt

COPY backend/ /app/backend/
COPY execution/ /app/execution/
COPY mocks/ /app/mocks/
COPY docker/ /app/docker/

RUN useradd --create-home --uid 10001 app \
    && mkdir /data \
    && chown app:app /data
USER app
