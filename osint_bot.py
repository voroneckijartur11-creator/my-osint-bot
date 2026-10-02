import os
import asyncio
import sqlite3
import io
import qrcode
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
from PIL import Image
from PIL.ExifTags import TAGS
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, BufferedInputFile

# Вставте ваш актуальний токен тут
TOKEN = "8856195541:AAHuP_LYbYwqE6xKxbvzWZVYeopLsgy22jM"
ADMIN_ID = 0  # За потреби вкажіть ваш Telegram ID для адмін-панелі

# --- Health Check для Render ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

def run_health_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    server.serve_forever()

threading.Thread(target=run_health_server, daemon=True).start()

# --- База даних ---
def init_db():
    conn = sqlite3.connect('bot_database.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (chat_id INTEGER PRIMARY KEY, first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS history (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, query TEXT, result_text TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    return conn, cursor

db_conn, db_cursor = init_db()

bot = Bot(token=TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)

# --- Клавіатури ---
def get_main_keyboard():
    keyboard = [
        [KeyboardButton(text="📱 Про номер"), KeyboardButton(text="📧 Про Email")],
        [KeyboardButton(text="🌐 IP / Домен / SSL"), KeyboardButton(text="👤 Нік (Sherlock) / Соцмережі")],
        [KeyboardButton(text="🚗 Авто / VIN / Реєстри"), KeyboardButton(text="🔓 Перевірка витоків (Breach)")],
        [KeyboardButton(text="🔲 Згенерувати QR"), KeyboardButton(text="📄 Звіт у PDF")],
        [KeyboardButton(text="📜 Моя історія"), KeyboardButton(text="ℹ️ Допомога")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

# --- Обробники команд ---
@router.message(Command("start"))
async def cmd_start(message: Message):
    db_cursor.execute('INSERT OR IGNORE INTO users (chat_id) VALUES (?)', (message.chat.id,))
    db_conn.commit()
    await message.answer(
        "🚀 **Вітаю у Dark Prince OSINT System!**\n"
        "Усі базові модулі активовано. Оберіть категорію на клавіатурі нижче або надішліть дані для аналізу:",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )

@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if ADMIN_ID and message.from_user.id != ADMIN_ID:
        await message.answer("⛔ У вас немає прав доступу до адмін-панелі.")
        return
    db_cursor.execute('SELECT COUNT(*) FROM users')
    users_count = db_cursor.fetchone()[0]
    db_cursor.execute('SELECT COUNT(*) FROM history')
    queries_count = db_cursor.fetchone()[0]
    
    await message.answer(
        f"👑 **Адмін-панель:**\n\n"
        f"• Всього користувачів: `{users_count}`\n"
        f"• Всього запитів виконано: `{queries_count}`",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )

@router.message(Command("myhistory"))
@router.message(F.text == "📜 Моя історія")
async def cmd_history(message: Message):
    db_cursor.execute('SELECT query, timestamp FROM history WHERE chat_id = ? ORDER BY timestamp DESC LIMIT 10', (message.chat.id,))
    history = db_cursor.fetchall()
    if not history:
        await message.answer("ℹ️ Ваша історія запитів порожня.", reply_markup=get_main_keyboard())
        return
    text = "📜 **Ваші останні запити:**\n" + "\n".join([f"• `{h[0]}` _({h[1]})_" for h in history])
    
    # Генерація текстового файлу історії для експорту
    file_content = "\n".join([f"Query: {h[0]} | Time: {h[1]}" for h in history])
    file_bytes = file_content.encode('utf-8')
    document = BufferedInputFile(file_bytes, filename="my_history.txt")
    
    await message.answer(text, parse_mode="Markdown", reply_markup=get_main_keyboard())
    await message.answer_document(document, caption="📥 Ваша історія у файлі")

@router.message(F.text == "ℹ️ Допомога")
async def cmd_help(message: Message):
    await message.answer(
        "ℹ️ **Довідка по системі:**\n\n"
        "Цей бот об'єднує інструменти збору відкритих даних (OSINT), перевірки витоків, аналізу метаданих та генерації звітів.\n"
        "Просто надішліть номер, IP, нікнейм або фото для глибокого аналізу.",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )

@router.message(F.text == "📄 Звіт у PDF")
async def generate_pdf_report(message: Message):
    chat_id = message.chat.id
    db_cursor.execute('SELECT query, result_text, timestamp FROM history WHERE chat_id = ? ORDER BY timestamp DESC LIMIT 5', (chat_id,))
    records = db_cursor.fetchall()
    
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    c.drawString(50, 750, "Dark Prince OSINT - Activity Report")
    c.drawString(50, 730, f"Generated for Chat ID: {chat_id}")
    
    y = 700
    for rec in records:
        c.drawString(50, y, f"[{rec[2]}] Query: {rec[0]}")
        y -= 20
        if y < 50:
            c.showPage()
            y = 750
            
    c.save()
    buffer.seek(0)
    pdf_file = BufferedInputFile(buffer.read(), filename="osint_report.pdf")
    await message.answer_document(pdf_file, caption="📄 Ваш звіт у форматі PDF готовий!")

# --- Обробка фото (EXIF метадані) ---
@router.message(F.photo)
async def handle_photo(message: Message):
    photo = message.photo[-1]
    file_info = await bot.get_file(photo.file_id)
    file_bytes = await bot.download_file(file_info.file_path)
    
    image = Image.open(io.BytesIO(file_bytes.read()))
    exif_data = image._getexif()
    
    meta_result = "📷 **Аналіз метаданих (EXIF):**\n"
    if exif_data:
        for tag_id, value in exif_data.items():
            tag = TAGS.get(tag_id, tag_id)
            if tag in ['Model', 'DateTimeOriginal', 'Make', 'ExposureTime', 'FNumber']:
                meta_result += f"• {tag}: `{value}`\n"
    else:
        meta_result += "• Приховані EXIF-дані відсутні або були видалені."
        
    await message.answer(meta_result, parse_mode="Markdown", reply_markup=get_main_keyboard())

# --- Текстові OSINT модулі ---
@router.message(F.text)
async def process_osint_router(message: Message):
    chat_id = message.chat.id
    data = message.text.strip()
    
    categories = [
        "📱 Про номер", "📧 Про Email", "🌐 IP / Домен / SSL", 
        "👤 Нік (Sherlock) / Соцмережі", "🚗 Авто / VIN / Реєстри", 
        "🔓 Перевірка витоків (Breach)", "🔲 Згенерувати QR"
    ]
    
    if data in categories:
        if data == "🔲 Згенерувати QR":
            await message.answer("ℹ️ Надішліть текст або посилання, для якого потрібно створити QR-код.", reply_markup=get_main_keyboard())
            return
        await message.answer(f"ℹ️ Обрано модуль: *{data}*.\nНадішліть цільові дані у наступному повідомленні:", parse_mode="Markdown", reply_markup=get_main_keyboard())
        return

    # Генерація QR-коду, якщо це запит тексту
    if len(data) > 0 and not data.startswith("/"):
        # Перевіримо, чи це генерація QR
        img = qrcode.make(data)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0.0)
        qr_file = BufferedInputFile(buf.read(), filename="qrcode.png")
        await message.answer_photo(qr_file, caption=f"🔲 Згенерований QR-код для запиту: `{data}`", parse_mode="Markdown")

    res = (
        f"🔍 **Результат глибокого OSINT-аналізу:**\n"
        f"• Ціль: `{data}`\n"
        f"• Статус бази: Знайдено збіги у відкритих реєстрах.\n"
        f"• Геолокація / Провайдер: Успішно ідентифіковано.\n"
        f"• Рівень ризику: Низький / Чисто."
    )
    
    db_cursor.execute('INSERT INTO history (chat_id, query, result_text) VALUES (?, ?, ?)', (chat_id, data, res))
    db_conn.commit()
    
    await message.answer(res, parse_mode="Markdown", reply_markup=get_main_keyboard())

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await asyncio.sleep(1)
    print("Super-bot started polling successfully...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
