# Move2link Web — Flask + Playwright Chromium
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Chromium deps + p7zip (untuk extract .7z/.rar) + curl
RUN apt-get update && apt-get install -y --no-install-recommends \
    p7zip-full \
    curl \
    libnss3 libnspr4 libdbus-1-3 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libxcb1 libxkbcommon0 libatspi2.0-0 libx11-6 \
    libxcomposite1 libxdamage1 libxext6 libxfixes3 libxrandr2 \
    libgbm1 libpango-1.0-0 libcairo2 libasound2 \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt \
 && playwright install chromium --with-deps || playwright install chromium

COPY . .

ENV M2L_PORT=5000 \
    M2L_DOWNLOADS=/app/downloads
VOLUME ["/app/downloads"]
EXPOSE 5000

CMD ["python3", "app.py"]
