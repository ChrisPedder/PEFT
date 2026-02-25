FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml .
COPY scraper/ scraper/

RUN pip install --no-cache-dir -e "."
