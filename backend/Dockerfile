FROM python:3.10.21-slim

WORKDIR /app

COPY requirements.txt ./requirements.txt

RUN apt-get update && apt-get install -y --no-install-recommends gcc build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN pip install -r requirements.txt

CMD ["fastapi", "dev", "--reload", "--host", "0.0.0.0"]

EXPOSE 8000