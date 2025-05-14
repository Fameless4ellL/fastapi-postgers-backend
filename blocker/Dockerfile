FROM python:3.13.1-slim

# set work directory
WORKDIR /app

# set env variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    REDIS_HOST=redis \
    REDIS_PORT=6379


RUN apt-get update && apt-get install -y \
    gcc \
    libc-dev \
    libffi-dev \
    libpq-dev \
    python3-dev && \
    apt-get clean && rm -rf /var/lib/apt/lists/*


# install dependencies
COPY blocker/requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# copy project
COPY blocker/. .


CMD ["python", "app.py"]
