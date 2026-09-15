FROM python:3.12-slim

WORKDIR /app

# وابستگی‌های سیستمی: tesseract برای OCR و libpq برای psycopg2
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY . /app

RUN pip install --no-cache-dir psycopg2-binary pytesseract pillow

ENV SARRAFI_PORT=8000

EXPOSE 8000

CMD ["sh", "-c", "python run.py --reset --seed || true; python run.py"]
