import os
import json
import asyncio
import sqlite3
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, Update

TOKEN = "8747134357:AAFjsPvLaskM5TymQZoXzmpYWrfqVSkMzWE"
ADMIN_IDS = [571578132]

bot = Bot(token=TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)

# Зберігаємо головний цикл подій для обробки вебхуків
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

class WebhookHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running via Webhooks!")

    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        try:
            update_data = json.loads(post_data.decode('utf-8'))
            update = Update.model_validate(update_data, context={"bot": bot})
            asyncio.run_coroutine_threadsafe(dp.feed_update(bot, update), loop)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(str(e).encode('utf-8'))

def run_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), WebhookHandler)
    server.serve_forever()

# Запускаємо HTTP сервер у фоновому потоці
threading.Thread(target=run_server, daemon=True).start()

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

@router.message(Command("start"))
async def cmd_start(message: Message):
    db_cursor.execute('INSERT OR IGNORE INTO users (chat_id) VALUES (?)', (message.chat.id,))
    db_conn.commit()
    await message.answer("🚀 **Бот запущено через вебхуки! Жодних конфліктів і підписок.** Виберіть функцію нижче:", parse_mode="Markdown", reply_markup=get_main_keyboard(message.chat.id))

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

async def setup_webhook():
    render_url = os.environ.get("RENDER_EXTERNAL_URL")
    if render_url:
        webhook_url = f"{render_url}"
        await bot.set_webhook(webhook_url)
        print(f"Webhook successfully set to {webhook_url}")
    else:
        print("RENDER_EXTERNAL_URL not found, webhook not set automatically.")

if __name__ == "__main__":
    loop.run_until_complete(setup_webhook())
    # Тримаємо цикл живим
    loop.run_forever()
