FROM python:3.13.1-slim

# set work directory
WORKDIR /app

# set env variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV REDIS_HOST=redis
ENV REDIS_PORT=6379

RUN apt-get update
RUN apt-get install -y python3-dev gcc libc-dev libffi-dev
RUN apt-get -y install libpq-dev gcc 

# install dependencies
COPY blocker/requirements.txt .
RUN pip install --upgrade pip
# copy project
COPY blocker/. .
RUN pip install -r requirements.txt

CMD ["python", "app.py"]
