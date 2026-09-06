FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/opt/playwright \
    TZ=Asia/Tokyo
WORKDIR /app
COPY requirements.txt ./
RUN pip install -r requirements.txt \
    && python -m playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*
COPY . .
EXPOSE 8080
CMD ["sh", "-c", "exec gunicorn -b 0.0.0.0:${PORT:-8080} app:app --workers 1 --threads 4 --timeout 300 --access-logfile - --error-logfile -"]
