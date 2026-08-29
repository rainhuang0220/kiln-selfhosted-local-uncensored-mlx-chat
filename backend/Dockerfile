FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml schema.sql ./
COPY app ./app
ENV PIP_DEFAULT_TIMEOUT=120 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
RUN pip install --no-cache-dir .
RUN useradd --create-home --uid 10001 kiln
USER kiln
ENV APP_HOST=0.0.0.0 APP_PORT=8787
EXPOSE 8787
CMD ["sh", "-c", "uvicorn app.main:app --host \"${APP_HOST:-0.0.0.0}\" --port \"${APP_PORT:-8787}\""]
