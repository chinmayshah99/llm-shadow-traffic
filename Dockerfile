FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY config ./config
COPY eval ./eval
COPY logger ./logger
COPY normalizer ./normalizer
COPY proxy ./proxy
COPY utils ./utils

RUN pip install --no-cache-dir .

RUN mkdir -p /app/logs

EXPOSE 8000

CMD ["llm-shadow-serve"]
