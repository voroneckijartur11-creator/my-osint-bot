import os
import asyncio
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton

TOKEN = "8747134357:AAFjsPvLaskM5TymQZoXzmpYWrfqVSkMzWE"

# 1. Фоновий HTTP-сервер для задоволення вимог Render до портів
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

# Запускаємо сервер у фоні
threading.Thread(target=run_health_server, daemon=True).start()

bot = Bot(token=TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)

@router.message(Command("start"))
async def cmd_start(message: Message):
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⚙️ Тест")]], resize_keyboard=True)
    await message.answer("🚀 Повна перевірка! Жодних каналів.", reply_markup=kb)

@router.message(F.text)
async def all_text(message: Message):
    await message.answer(f"Отримано: {message.text}")

async def main():
    # drop_pending_updates=True скидає старі пакети і допомагає уникнути конфліктів
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
