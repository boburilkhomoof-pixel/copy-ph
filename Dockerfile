FROM python:3.11-slim

# Tesseract OCR ni o'rnatish
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-rus \
    tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

# Ishchi papka
WORKDIR /app

# Kerakli fayllarni yuklash
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Botni ishga tushirish
CMD ["python", "bot_render_webhook.py"]
