import os
import re
import io
import time
import asyncio
import hashlib
import sqlite3
import ssl
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import random
import string

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, BufferedInputFile
import requests
import phonenumbers
from phonenumbers import geocoder, carrier
from email_validator import validate_email
import pypdf
import cv2
import numpy as np
import pytesseract

TOKEN = "8747134357:AAFjsPvLaskM5TymQZoXzmpYWrfqVSkMzWE"
ADMIN_IDS = [571578132]
VIRUSTOTAL_API_KEY = os.environ.get("VIRUSTOTAL_API_KEY", "")

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

def init_db():
    conn = sqlite3.connect('bot_database.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (chat_id INTEGER PRIMARY KEY, first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS history (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, query TEXT, result_text TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS stats (key TEXT PRIMARY KEY, value INTEGER)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS cache (query TEXT PRIMARY KEY, result_text TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    cursor.execute('INSERT OR IGNORE INTO stats (key, value) VALUES ("total_requests", 0)')
    conn.commit()
    return conn, cursor

db_conn, db_cursor = init_db()

def log_user(chat_id):
    db_cursor.execute('INSERT OR IGNORE INTO users (chat_id) VALUES (?)', (chat_id,))
    db_conn.commit()

def add_request_stat():
    db_cursor.execute('UPDATE stats SET value = value + 1 WHERE key = "total_requests"')
    db_conn.commit()

def get_stats():
    db_cursor.execute('SELECT COUNT(*) FROM users')
    users_count = db_cursor.fetchone()[0]
    db_cursor.execute('SELECT value FROM stats WHERE key = "total_requests"')
    req_count = db_cursor.fetchone()[0]
    return users_count, req_count

def get_cache(query):
    db_cursor.execute('SELECT result_text FROM cache WHERE query = ?', (query,))
    row = db_cursor.fetchone()
    return row[0] if row else None

def set_cache(query, result_text):
    db_cursor.execute('INSERT OR REPLACE INTO cache (query, result_text) VALUES (?, ?)', (query, result_text))
    db_conn.commit()

def add_to_db_history(chat_id, query, result_text):
    db_cursor.execute('INSERT INTO history (chat_id, query, result_text) VALUES (?, ?, ?)', (chat_id, query, result_text))
    db_conn.commit()

def get_main_keyboard(chat_id):
    keyboard = [
        [KeyboardButton(text="📱 Про номер"), KeyboardButton(text="📧 Про Email")],
        [KeyboardButton(text="🌐 IP / Домен / Сабдомени"), KeyboardButton(text="👤 Нік / Telegram / Соцмережі")],
        [KeyboardButton(text="🚗 Авто (Номер / VIN)"), KeyboardButton(text="🏛️️ Пошук ПІБ / Реєстри")],
        [KeyboardButton(text="🪙 Криптогаманець"), KeyboardButton(text="🔗 URL / Безпека / Заголовки")],
        [KeyboardButton(text="📷 Фото / Документи / OCR"), KeyboardButton(text="🛠️ Утиліти / Хеші / Base64")],
        [KeyboardButton(text="⛽ Комісії / Газ мереж"), KeyboardButton(text="🔍 Сканер портів")],
        [KeyboardButton(text="🕵️ Фейк профіль"), KeyboardButton(text="🔑 Генератор паролів")],
        [KeyboardButton(text="📜 Моя історія"), KeyboardButton(text="ℹ️ Допомога")]
    ]
    if chat_id in ADMIN_IDS:
        keyboard.append([KeyboardButton(text="⚙️ Адмін-панель")])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_standard_markup():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📄 Експорт звіту", callback_data="export_report"),
         InlineKeyboardButton(text="🏠 На головну", callback_data="go_home")]
    ])

def scan_ports(target):
    import socket
    ports = [21, 22, 23, 25, 53, 80, 110, 135, 139, 443, 445, 3306, 3389, 8080]
    open_ports = []
    service_map = {21: "FTP", 22: "SSH", 23: "Telnet", 25: "SMTP", 53: "DNS", 80: "HTTP", 443: "HTTPS", 3306: "MySQL", 3389: "RDP"}
    for p in ports:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.3)
            if s.connect_ex((target, p)) == 0:
                open_ports.append(f"{p} ({service_map.get(p, 'Unknown')})")
            s.close()
        except:
            pass
    return open_ports

def check_password_leak(pwd):
    sha1pwd = hashlib.sha1(pwd.encode('utf-8')).hexdigest().upper()
    prefix, suffix = sha1pwd[:5], sha1pwd[5:]
    try:
        res = requests.get(f"https://api.pwnedpasswords.com/range/{prefix}", timeout=4)
        if res.status_code == 200:
            for line in res.text.splitlines():
                h, count = line.split(':')
                if h == suffix:
                    return int(count)
    except:
        pass
    return 0

def generate_osint_dorks(query):
    encoded = urllib.parse.quote(query)
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌐 Google Search", url=f"https://www.google.com/search?q={encoded}"),
         InlineKeyboardButton(text="📁 OLX / Оголошення", url=f"https://www.google.com/search?q=site:olx.ua+{encoded}")],
        [InlineKeyboardButton(text="💬 Telegram Public", url=f"https://www.google.com/search?q=site:t.me+{encoded}"),
         InlineKeyboardButton(text="📘 Facebook", url=f"https://www.google.com/search?q=site:facebook.com+{encoded}")],
        [InlineKeyboardButton(text="📄 Експорт звіту", callback_data="export_report"),
         InlineKeyboardButton(text="🏠 На головну", callback_data="go_home")]
    ])

bot = Bot(token=TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)

@router.message(Command("start"))
async def cmd_start(message: Message):
    log_user(message.chat.id)
    await message.answer("🔥 **Бот повністю оновлено та працює напряму!** Виберіть потрібну функцію нижче:", parse_mode="Markdown", reply_markup=get_main_keyboard(message.chat.id))

@router.message(Command("myhistory") | (F.text == "📜 Моя історія"))
async def cmd_history(message: Message):
    db_cursor.execute('SELECT query, timestamp FROM history WHERE chat_id = ? ORDER BY timestamp DESC LIMIT 10', (message.chat.id,))
    history = db_cursor.fetchall()
    if not history:
        await message.answer("ℹ Ваша історія запитів порожня.")
        return
    text = "📜 **Ваші останні 10 запитів:**\n" + "\n".join([f"• `{h[0]}` _({h[1]})_" for h in history])
    await message.answer(text, parse_mode="Markdown")

@router.message(Command("admin") | (F.text == "⚙️ Адмін-панель"))
async def cmd_admin(message: Message):
    if message.chat.id not in ADMIN_IDS:
        await message.answer("⛔ У вас немає доступу.")
        return
    users_count, req_count = get_stats()
    await message.answer(f"⚙️ **Адмін-панель:**\n• Користувачів: `{users_count}`\n• Запитів: `{req_count}`", parse_mode="Markdown")

@router.message(F.text == "ℹ️ Допомога")
async def cmd_help(message: Message):
    await message.answer("ℹ️ Надішліть дані для аналізу або виберіть категорію на клавіатурі.", reply_markup=get_main_keyboard(message.chat.id))

@router.callback_query(F.data == "export_report")
async def callback_export(call: CallbackQuery):
    db_cursor.execute('SELECT result_text FROM history WHERE chat_id = ? ORDER BY timestamp DESC LIMIT 1', (call.message.chat.id,))
    row = db_cursor.fetchone()
    report = row[0] if row and row[0] else "Звіти відсутні."
    bio = BufferedInputFile(report.encode('utf-8'), filename="osint_report.txt")
    await call.message.answer_document(document=bio, caption="📁 Ваш звіт")
    await call.answer()

@router.callback_query(F.data == "go_home")
async def callback_home(call: CallbackQuery):
    await call.message.answer("🏠 Головне меню:", reply_markup=get_main_keyboard(call.message.chat.id))
    await call.answer()

@router.message(F.text)
async def process_osint(message: Message):
    chat_id = message.chat.id
    data = message.text.strip()
    
    if data in ["📱 Про номер", "📧 Про Email", "🌐 IP / Домен / Сабдомени", "👤 Нік / Telegram / Соцмережі", "🚗 Авто (Номер / VIN)", "🏛️ Пошук ПІБ / Реєстри", "🪙 Криптогаманець", "🔗 URL / Безпека / Заголовки", "📷 Фото / Документи / OCR", "🛠️ Утиліти / Хеші / Base64", "🔍 Сканер портів"]:
        await message.answer(f"ℹ️ Введіть дані для категорії: *{data}*.", parse_mode="Markdown")
        return

    add_request_stat()
    log_user(chat_id)

    if data.startswith('+') or (data.isdigit() and len(data) >= 9):
        try:
            num = phonenumbers.parse(data, "UA")
            res = f"📱 **Телефон:** `{data}`\n• Регіон: {geocoder.description_for_number(num, 'uk')}\n• Оператор: {carrier.name_for_number(num, 'uk')}"
            add_to_db_history(chat_id, data, res)
            await message.answer(res, parse_mode="Markdown", reply_markup=generate_osint_dorks(data))
            return
        except:
            pass

    if "@" in data:
        res = f"📧 **Email:** `{data}`\n• Згадки у витоках: `{check_password_leak(data)}`"
        add_to_db_history(chat_id, data, res)
        await message.answer(res, parse_mode="Markdown", reply_markup=generate_osint_dorks(data))
        return

    res = f"🔍 **Результат пошуку за запитом:** `{data}`\nДані опрацьовано успішно."
    add_to_db_history(chat_id, data, res)
    await message.answer(res, parse_mode="Markdown", reply_markup=get_standard_markup())

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
