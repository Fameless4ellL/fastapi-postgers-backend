# Use a smaller base image
FROM python:3.9-slim

# Set work directory
WORKDIR /app

# Set environment variables to prevent cache files
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# environment
ENV ENVIRONMENT=${ENVIRONMENT:-dev}

COPY pyproject.toml poetry.lock ./


# Install dependencies only if required
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libpq-dev && \
    pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir poetry && \
    poetry config virtualenvs.create false && \
    poetry install --no-root $(if [ "$ENVIRONMENT" != "dev" ]; then echo "--without dev"; fi) && \
    apt-get remove -y && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy project files last to optimize caching
COPY . .

