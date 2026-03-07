# bot_group_test.py
import os
import sqlite3
import hashlib
import logging
import time
from PIL import Image, ImageEnhance, ImageFilter
import imagehash
import pytesseract
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

# Tesseract yo'nalishini sozlash
pytesseract.pytesseract.tesseract_cmd = r'D:\ocr\tesseract.exe'

# Logging sozlamalari
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot tokeni va admin ID
BOT_TOKEN = "8748172609:AAHxLbjPl8grc-K76IDb80A6tHy9hkwF5FI"
ADMIN_ID = "6995658625"  # Sizning ID ingiz

# Guruh sozlamalari
NOTIFY_GROUP = True  # Guruhga ham xabar yuborish
DELETE_DUPLICATES = False  # Takroriy rasmlarni o'chirish

def extract_text_from_image(image_path):
    """Rasmdan matn ajratib olish"""
    try:
        img = Image.open(image_path)
        
        # Rasmni yaxshilash
        width, height = img.size
        if width < 1000:
            scale = 1500 / width
            new_size = (int(width * scale), int(height * scale))
            img = img.resize(new_size, Image.Resampling.LANCZOS)
        
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(2.0)
        img = img.filter(ImageFilter.SHARPEN)
        img = img.convert('L')
        img = img.point(lambda x: 0 if x < 180 else 255, '1')
        
        # OCR
        custom_config = r'--oem 3 --psm 6 -l rus+eng -c tessedit_char_whitelist="0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZабвгдеёжзийклмнопрстуфхцчшщъыьэюяАБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ.|/- "'
        text = pytesseract.image_to_string(img, config=custom_config)
        
        # Matnni tozalash
        lines = []
        for line in text.split('\n'):
            line = line.strip()
            if line and len(line) > 1:
                lines.append(line)
        
        return '\n'.join(lines)[:500]
        
    except Exception as e:
        logger.error(f"OCR xatolik: {e}")
        return ""

# Database class (avvalgidek)
class Database:
    def __init__(self, db_name='group_images.db'):
        self.db_name = db_name
        self.init_db()
    
    def get_connection(self):
        conn = sqlite3.connect(self.db_name, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn
    
    def init_db(self):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS images
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      file_id TEXT UNIQUE,
                      file_hash TEXT,
                      phash TEXT,
                      ocr_text TEXT,
                      username TEXT,
                      user_id INTEGER,
                      chat_id INTEGER,
                      message_id INTEGER,
                      date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        conn.commit()
        conn.close()
        logger.info("✅ Ma'lumotlar bazasi tayyor")
    
    def save_image(self, file_id, file_hash, phash, ocr_text, username, user_id, chat_id, message_id):
        conn = self.get_connection()
        c = conn.cursor()
        try:
            c.execute('''INSERT INTO images 
                        (file_id, file_hash, phash, ocr_text, username, user_id, chat_id, message_id)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                     (file_id, file_hash, phash, ocr_text, username, user_id, chat_id, message_id))
            conn.commit()
        except:
            pass
        finally:
            conn.close()
    
    def find_exact_duplicate(self, file_hash):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("SELECT username FROM images WHERE file_hash=?", (file_hash,))
        result = c.fetchone()
        conn.close()
        return result
    
    def find_similar_by_phash(self, phash, threshold=10):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("SELECT phash, username FROM images WHERE phash IS NOT NULL")
        images = c.fetchall()
        conn.close()
        
        matches = []
        for db_phash, username in images:
            if db_phash and phash:
                try:
                    bin1 = bin(int(phash, 16))[2:].zfill(64)
                    bin2 = bin(int(db_phash, 16))[2:].zfill(64)
                    distance = sum(c1 != c2 for c1, c2 in zip(bin1, bin2))
                    if distance < threshold:
                        similarity = 100 - (distance * 100 / 64)
                        matches.append({'username': username, 'similarity': similarity})
                except:
                    continue
        return matches[:3]

db = Database()

def get_user_info(user):
    if user.username:
        return f"@{user.username}"
    elif user.first_name:
        return user.first_name
    else:
        return f"User(ID:{user.id})"

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        logger.info(f"📸 Guruh rasmi: {update.message.chat_id}")
        
        user = update.message.from_user
        user_display = get_user_info(user)
        
        # Rasmni yuklash
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        file_path = f"temp_{time.time()}.jpg"
        await file.download_to_drive(file_path)
        
        # Hash hisoblash
        with open(file_path, 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()
        
        img = Image.open(file_path)
        phash = str(imagehash.phash(img))
        
        # OCR
        ocr_text = extract_text_from_image(file_path)
        
        # Takroriy tekshirish
        exact = db.find_exact_duplicate(file_hash)
        
        if exact:
            # Takroriy rasm
            msg = f"⚠️ {user_display} takroriy rasm yubordi! (avval {exact[0]} tashlagan)"
            await context.bot.send_message(chat_id=ADMIN_ID, text=msg)
            
            if NOTIFY_GROUP:
                await context.bot.send_message(chat_id=update.message.chat_id, text=f"⚠️ Takroriy rasm! @{user.username if user.username else ''}")
            
            if DELETE_DUPLICATES:
                await update.message.delete()
                logger.info(f"🗑 Takroriy rasm o'chirildi")
                
        else:
            # O'xshashlikni tekshirish
            similar = db.find_similar_by_phash(phash)
            
            if similar:
                best = similar[0]
                msg = f"⚠️ {user_display} yuborgan rasm avvalgi rasmga {best['similarity']:.1f}% o'xshaydi (muallif: {best['username']})"
                await context.bot.send_message(chat_id=ADMIN_ID, text=msg)
                
                if NOTIFY_GROUP:
                    await context.bot.send_message(chat_id=update.message.chat_id, text=f"⚠️ Diqqat! Bu rasm avvalgi rasmga o'xshaydi!")
            else:
                # Yangi rasm
                msg = f"✅ Yangi rasm: {user_display}"
                if ocr_text:
                    msg += f"\n📝 {ocr_text[:100]}"
                await context.bot.send_message(chat_id=ADMIN_ID, text=msg)
            
            # Saqlash
            db.save_image(photo.file_id, file_hash, phash, ocr_text, user_display, 
                         user.id, update.message.chat_id, update.message.message_id)
        
        # Tozalash
        if os.path.exists(file_path):
            os.remove(file_path)
            
    except Exception as e:
        logger.error(f"Xatolik: {e}")

def main():
    print("=" * 50)
    print("🚀 GURUH BOTI ISHGA TUSHMOQDA")
    print("=" * 50)
    print(f"📢 Guruhga xabar: {'HA' if NOTIFY_GROUP else 'YOQ'}")
    print(f"🗑 Avtomatik o'chirish: {'HA' if DELETE_DUPLICATES else 'YOQ'}")
    print("=" * 50)
    
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    
    print("✅ Bot ishga tushdi!")
    print("⏳ Guruhdan rasmlar kutilmoqda...")
    
    app.run_polling()

if __name__ == "__main__":
    main()