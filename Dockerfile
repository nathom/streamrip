FROM python:3.12-alpine@sha256:c5ba3deef00c7758561a0f03c26f44f10589263d40e732b8748e0d1f38f6dd89 AS builder

ENV POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_NO_INTERACTION=1

WORKDIR /app

RUN pip install --no-cache-dir poetry==2.5.2

COPY poetry.lock pyproject.toml README.md ./
RUN poetry install --only main --no-root

COPY streamrip/ ./streamrip/
RUN poetry install --only-root

FROM python:3.12-alpine@sha256:c5ba3deef00c7758561a0f03c26f44f10589263d40e732b8748e0d1f38f6dd89 AS runtime

RUN apk add --no-cache ca-certificates su-exec \
    && mkdir -p /music /config \
    && chown 1029:100 /music /config

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/streamrip /app/streamrip
COPY shell/streamrip.sh /streamrip.sh
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /streamrip.sh /docker-entrypoint.sh

USER root
ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["/streamrip.sh"]
