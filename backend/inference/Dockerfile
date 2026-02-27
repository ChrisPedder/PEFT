FROM public.ecr.aws/docker/library/python:3.12-slim

# Install Lambda Web Adapter
COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:0.9.1 /lambda-adapter /opt/extensions/lambda-adapter

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY app.py .

# Run as non-root user
RUN adduser --disabled-password --gecos '' --home /app appuser && \
    chown -R appuser:appuser /app
USER appuser

# Lambda Web Adapter listens on port 8080 by default
ENV PORT=8080

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
