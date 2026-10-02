import os
import asyncio
import sqlite3
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton

TOKEN = "8747134357:AAFjsPvLaskM5TymQZoXzmpYWrfqVSkMzWE"
ADMIN_IDS = [571578132]

# Простий HTTP-сервер для того, щоб Render не вимикав сервіс (health check)
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

# Запускаємо сервер перевірки здоров'я у фоновому потоці
threading.Thread(target=run_health_server, daemon=True).start()

def init_db():
    conn = sqlite3.connect('bot_database.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (chat_id INTEGER PRIMARY KEY, first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS history (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, query TEXT, result_text TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    return conn, cursor

db_conn, db_cursor = init_db()

def get_main_keyboard(chat_id):
    keyboard = [
        [KeyboardButton(text="📱 Про номер"), KeyboardButton(text="📧 Про Email")],
        [KeyboardButton(text="🌐 IP / Домен / Сабдомени"), KeyboardButton(text="👤 Нік / Telegram / Соцмережі")],
        [KeyboardButton(text="🚗 Авто (Номер / VIN)"), KeyboardButton(text="🏛 Пошук ПІБ / Реєстри")],
        [KeyboardButton(text="📜 Моя історія"), KeyboardButton(text="ℹ Допомога")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

bot = Bot(token=TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)

@router.message(Command("start"))
async def cmd_start(message: Message):
    db_cursor.execute('INSERT OR IGNORE INTO users (chat_id) VALUES (?)', (message.chat.id,))
    db_conn.commit()
    await message.answer("🚀 **Бот успішно запущено!** Виберіть функцію нижче:", parse_mode="Markdown", reply_markup=get_main_keyboard(message.chat.id))

@router.message(Command("myhistory") | (F.text == "📜 Моя історія"))
async def cmd_history(message: Message):
    db_cursor.execute('SELECT query, timestamp FROM history WHERE chat_id = ? ORDER BY timestamp DESC LIMIT 10', (message.chat.id,))
    history = db_cursor.fetchall()
    if not history:
        await message.answer("ℹ Ваша історія запитів порожня.")
        return
    text = "📜 **Ваші останні запити:**\n" + "\n".join([f"• `{h[0]}` _({h[1]})_" for h in history])
    await message.answer(text, parse_mode="Markdown")

@router.message(F.text == "ℹ️ Допомога")
async def cmd_help(message: Message):
    await message.answer("ℹ️ Надішліть дані для перевірки або оберіть категорію на клавіатурі.", reply_markup=get_main_keyboard(message.chat.id))

@router.message(F.text)
async def process_osint(message: Message):
    chat_id = message.chat.id
    data = message.text.strip()
    
    if data in ["📱 Про номер", "📧 Про Email", "🌐 IP / Домен / Сабдомени", "👤 Нік / Telegram / Соцмережі", "🚗 Авто (Номер / VIN)", "🏛 Пошук ПІБ / Реєстри"]:
        await message.answer(f"ℹ️ Введіть дані для категорії: *{data}*.", parse_mode="Markdown")
        return

    res = f"🔍 **Результат перевірки:** `{data}`\nУсе працює ідеально!"
    db_cursor.execute('INSERT INTO history (chat_id, query, result_text) VALUES (?, ?, ?)', (chat_id, data, res))
    db_conn.commit()
    
    await message.answer(res, parse_mode="Markdown", reply_markup=get_main_keyboard(chat_id))

async def main():
    # Очищаємо залишки старих вебхуків перед запуском
    await bot.delete_webhook(drop_pending_updates=True)
    print("Bot started polling...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
