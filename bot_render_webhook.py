import os
import platform
import logging
from PIL import Image
import pytesseract

# Tesseract yo'nalishini OS ga qarab sozlash
if platform.system() == "Windows":
    # Lokal Windows uchun
    pytesseract.pytesseract.tesseract_cmd = r'D:\ocr\tesseract.exe'
else:
    # Render Linux (Docker) uchun
    pytesseract.pytesseract.tesseract_cmd = r'/usr/bin/tesseract'

# OCR funksiyasini yaxshilash
def extract_text_from_image(image_path):
    """Rasmdan matn ajratib olish"""
    try:
        # Tesseract mavjudligini tekshirish
        if not os.path.exists(pytesseract.pytesseract.tesseract_cmd):
            logging.warning("Tesseract topilmadi, OCR ishlamaydi")
            return ""
        
        img = Image.open(image_path)
        # Rasmni yaxshilash
        img.thumbnail((1000, 1000))
        # OCR ishlatish (rus va ingliz tillarida)
        text = pytesseract.image_to_string(img, lang='rus+eng')
        return text[:500]  # 500 belgidan oshmasin
    except Exception as e:
        logging.error(f"OCR xatolik: {e}")
        return ""
