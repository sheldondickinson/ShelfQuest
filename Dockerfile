FROM python:3.12-slim

WORKDIR /app

# Pillow does not always provide prebuilt wheels for linux/arm/v7.
# These packages allow Pillow to compile cleanly on QNAP/Raspberry Pi-style targets.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        zlib1g-dev \
        libjpeg-dev

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

ENV LIBRARY_DB=/data/library.db
ENV DEFAULT_LOAN_DAYS=7

EXPOSE 8000
CMD ["uvicorn", "app.asgi:app", "--host", "0.0.0.0", "--port", "8000"]
