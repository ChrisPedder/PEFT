FROM public.ecr.aws/docker/library/python:3.12-slim

# Install Lambda Web Adapter
COPY --from=public.ecr.aws/awsguru/aws-lambda-web-adapter:0.8.4 /lambda-adapter /opt/extensions/lambda-adapter

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY app.py .

# Lambda Web Adapter listens on port 8080 by default
ENV PORT=8080

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
