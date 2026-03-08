import os
import sqlite3
import hashlib
import logging
import json
import platform
import asyncio
from flask import Flask, request
from PIL import Image
import imagehash
import pytesseract
from telegram import Bot, Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

# Tesseract yo'nalishini OS ga qarab sozlash
if platform.system() == "Windows":
    pytesseract.pytesseract.tesseract_cmd = r'D:\ocr\tesseract.exe'
else:
    pytesseract.pytesseract.tesseract_cmd = r'/usr/bin/tesseract'

# Bot sozlamalari
BOT_TOKEN = os.environ.get('BOT_TOKEN')
ADMIN_ID = os.environ.get('ADMIN_ID')

# Flask app
app = Flask(__name__)
bot = Bot(token=BOT_TOKEN)

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database
def init_db():
    conn = sqlite3.connect('/tmp/images.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS images
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  file_id TEXT UNIQUE,
                  file_hash TEXT,
                  phash TEXT,
                  username TEXT,
                  user_id INTEGER,
                  chat_id INTEGER,
                  date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()
    logger.info("✅ Ma'lumotlar bazasi tayyor")

init_db()

def get_user_info(user):
    if user.username:
        return f"@{user.username}"
    elif user.first_name:
        return user.first_name
    else:
        return f"User(ID:{user.id})"

def hamming_distance(hash1, hash2):
    if not hash1 or not hash2 or len(hash1) != len(hash2):
        return 64
    return sum(c1 != c2 for c1, c2 in zip(hash1, hash2))

def extract_text_from_image(image_path):
    try:
        if not os.path.exists(pytesseract.pytesseract.tesseract_cmd):
            return ""
        img = Image.open(image_path)
        img.thumbnail((1000, 1000))
        text = pytesseract.image_to_string(img, lang='rus+eng')
        return text[:500]
    except Exception as e:
        logger.error(f"OCR xatolik: {e}")
        return ""

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = update.message.from_user
        user_display = get_user_info(user)
        
        logger.info(f"📸 Rasm keldi: {user_display}")
        
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        file_path = f"/tmp/{photo.file_id}.jpg"
        await file.download_to_drive(file_path)
        
        with open(file_path, 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()
        
        img = Image.open(file_path)
        phash = str(imagehash.phash(img))
        
        ocr_text = extract_text_from_image(file_path)
        
        conn = sqlite3.connect('/tmp/images.db')
        c = conn.cursor()
        
        c.execute("SELECT username FROM images WHERE file_hash=?", (file_hash,))
        exact = c.fetchone()
        
        if exact:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"⚠️ Takroriy rasm!\n👤 {user_display}\n🔍 Avval: {exact[0]}"
            )
            logger.info("❌ Takroriy rasm!")
        else:
            c.execute("SELECT username, phash FROM images WHERE phash IS NOT NULL")
            images = c.fetchall()
            
            best_similarity = 0
            best_user = ""
            
            for db_user, db_phash in images:
                if db_phash:
                    distance = hamming_distance(phash, db_phash)
                    if distance < 10:
                        similarity = 100 - (distance * 100 / 64)
                        if similarity > best_similarity:
                            best_similarity = similarity
                            best_user = db_user
            
            if best_similarity > 0:
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"⚠️ O'xshash rasm!\n👤 {user_display}\n📊 {best_similarity:.1f}% o'xshash\n🔍 Avval: {best_user}"
                )
                logger.info(f"⚠️ O'xshash rasm {best_similarity:.1f}%")
            else:
                msg = f"✅ Yangi rasm\n👤 {user_display}"
                if ocr_text:
                    msg += f"\n📝 {ocr_text[:100]}"
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=msg
                )
                logger.info("✅ Yangi rasm")
            
            c.execute("INSERT INTO images (file_id, file_hash, phash, username, user_id, chat_id) VALUES (?, ?, ?, ?, ?, ?)",
                     (photo.file_id, file_hash, phash, user_display, user.id, update.message.chat_id))
            conn.commit()
        
        conn.close()
        os.remove(file_path)
        
    except Exception as e:
        logger.error(f"Xatolik: {e}")

# Application yaratish (global)
application = Application.builder().bot(bot).build()

# Handler qo'shish
application.add_handler(MessageHandler(filters.PHOTO, handle_photo))

# Initialize qilish (MUHIM: handlerlardan KEYIN!)
application.initialize()

# Webhook endpoint
@app.route(f'/{BOT_TOKEN}', methods=['POST'])
def webhook():
    try:
        json_str = request.get_data().decode('UTF-8')
        update = Update.de_json(json.loads(json_str), bot)
        
        # Update ni qayta ishlash
        asyncio.run(application.process_update(update))
        
        return 'OK', 200
    except Exception as e:
        logger.error(f"Webhook xatolik: {e}")
        return 'Error', 500

# Health check
@app.route('/health')
def health():
    return 'OK', 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
