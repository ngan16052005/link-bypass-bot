FROM python:3.12-slim

WORKDIR /app

# Cài đặt các gói hệ thống
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install --with-deps chromium

COPY . .

# Mở cổng chạy 24/7 (Hugging Face dùng 7860, Render dùng 8080 hoặc $PORT)
ENV PORT=7860
EXPOSE 7860

CMD ["python", "main.py"]
