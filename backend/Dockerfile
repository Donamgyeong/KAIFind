FROM python:3.11.18-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

COPY requirements.txt ./requirements.txt

RUN apt-get update && apt-get install -y --no-install-recommends gcc build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --no-cache-dir -r requirements.txt

CMD ["fastapi", "dev", "--reload", "--host", "0.0.0.0"]

EXPOSE 8000
