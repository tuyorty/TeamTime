# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Сначала зависимости: слой переиспользуется, пока не меняется pyproject.toml.
COPY pyproject.toml ./
RUN mkdir -p src/teamtime && touch src/teamtime/__init__.py \
    && pip install . \
    && pip uninstall -y teamtime

COPY src ./src
COPY alembic.ini ./
COPY migrations ./migrations
RUN pip install --no-deps .

# Версия — в самом конце сборки, чтобы новый тег не сбрасывал кэш слоёв.
ARG XTIME_VERSION=dev
ENV XTIME_VERSION=${XTIME_VERSION}

COPY docker/entrypoint.sh /usr/local/bin/entrypoint
# Убираем CRLF и в существующих рабочих копиях Windows.
RUN sed -i 's/\r$//' /usr/local/bin/entrypoint \
    && chmod +x /usr/local/bin/entrypoint \
    && useradd --system --uid 10001 --home /app teamtime \
    && chown -R teamtime /app
USER teamtime

EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=5 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=2).status == 200 else 1)"

ENTRYPOINT ["entrypoint"]
CMD ["api"]
