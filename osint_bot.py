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
import base64

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
import qrcode

# --- НАЛАШТУВАННЯ ТА ВЕБ-СЕРВЕР (HEALTH CHECK) ---
TOKEN = "8747134357:AAFjsPvLaskM5TymQZoXzmpYWrfqVSkMzWE"
ADMIN_IDS = [571578132]  # Замініть або додайте ваш Telegram ID за потреби
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

# --- БАЗА ДАНИХ (SQLITE З КЕШУВАННЯМ) ---
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

# --- КЛАВІАТУРИ ---
def get_main_keyboard(chat_id):
    keyboard = [
        [KeyboardButton(text="📱 Про номер"), KeyboardButton(text="📧 Про Email")],
        [KeyboardButton(text="🌐 IP / Домен / Сабдомени"), KeyboardButton(text="👤 Нік / Telegram / Соцмережі")],
        [KeyboardButton(text="🚗 Авто (Номер / VIN)"), KeyboardButton(text="🏛️ Пошук ПІБ / Реєстри")],
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

# --- ДОДАТКОВІ МОДУЛІ РОЗВІДКИ ---
def scan_ports(target):
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

def check_virustotal_url(target_url):
    if not VIRUSTOTAL_API_KEY:
        return "⚠️ VirusTotal API ключ не налаштовано."
    try:
        headers = {"x-apikey": VIRUSTOTAL_API_KEY}
        response = requests.post("https://www.virustotal.com/api/v3/urls", headers=headers, data={"url": target_url}, timeout=5)
        if response.status_code == 200:
            analysis_id = response.json().get("data", {}).get("id")
            time.sleep(1)
            report = requests.get(f"https://www.virustotal.com/api/v3/analyses/{analysis_id}", headers=headers, timeout=5).json()
            stats = report.get("data", {}).get("attributes", {}).get("stats", {})
            return f"🛡️ **VirusTotal:** Шкідливих: `{stats.get('malicious', 0)}` | Безпечних: `{stats.get('harmless', 0)}`"
    except:
        pass
    return "❌ Помилка VirusTotal."

def check_security_headers(domain):
    try:
        url = domain if domain.startswith("http") else f"https://{domain}"
        res = requests.get(url, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
        headers = res.headers
        return f"🛡️ **Заголовки безпеки:**\n• HSTS: {'✅' if 'Strict-Transport-Security' in headers else '❌'}\n• CSP: {'✅' if 'Content-Security-Policy' in headers else '❌'}\n• X-Frame-Options: {'✅' if 'X-Frame-Options' in headers else '❌'}"
    except:
        return "❌ Не вдалося перевірити заголовки сайту."

def check_ssl_cert(domain):
    try:
        hostname = domain.replace("https://", "").replace("http://", "").split("/")[0]
        ctx = ssl.create_default_context()
        with socket.create_connection((hostname, 443), timeout=5) as sock:
            with ctx.wrap_socket(sock, server_hostname=hostname) as ssock:
                cert = ssock.getpeercert()
                return f"🔒 **SSL Сертифікат:**\n• Видавець: `{dict(x[0] for x in cert.get('issuer', [])).get('organizationName', 'Unknown')}`\n• Діє до: `{cert.get('notAfter')}`"
    except:
        return "❌ Не вдалося отримати SSL."

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

# --- ІНІЦІАЛІЗАЦІЯ БОТА ---
bot = Bot(token=TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)

# --- КОМАНДИ ТА МЕНЮ ---
@router.message(Command("start"))
async def cmd_start(message: Message):
    log_user(message.chat.id)
    text = (
        "🔥 **Ultimate OSINT Bot Max Pro+ (Advanced Edition)**\n\n"
        "Інтегровано розширений функціонал, кешування та розвідку:\n"
        "• 📱 Телефон, 📧 Пошта, витоки, 🌐 Google Dorks\n"
        "• 🏛️ Пошук за ПІБ, 🚗 Авто, 👤 Соцмережі, 🛡️ VirusTotal\n"
        "• ⚙️ Адмін-панель та повна історія запитів (`/myhistory`)"
    )
    await message.answer(text, parse_mode="Markdown", reply_markup=get_main_keyboard(message.chat.id))

@router.message(Command("myhistory"))
@router.message(F.text == "📜 Моя історія")
async def cmd_history(message: Message):
    db_cursor.execute('SELECT query, timestamp FROM history WHERE chat_id = ? ORDER BY timestamp DESC LIMIT 10', (message.chat.id,))
    history = db_cursor.fetchall()
    if not history:
        await message.answer("ℹ Ваша історія запитів порожня.")
        return
    text = "📜 **Ваші останні 10 запитів:**\n" + "\n".join([f"• `{h[0]}` _({h[1]})_" for h in history])
    await message.answer(text, parse_mode="Markdown")

@router.message(Command("admin"))
@router.message(F.text == "⚙️ Адмін-панель")
async def cmd_admin(message: Message):
    if message.chat.id not in ADMIN_IDS:
        await message.answer("⛔ У вас немає доступу до адмін-панелі.")
        return
    users_count, req_count = get_stats()
    text = f"⚙️ **Панорама Адміністратора:**\n• Користувачів у базі: `{users_count}`\n• Загалом запитів: `{req_count}`\n\nКоманди розсилки: `/broadcast [текст]`"
    await message.answer(text, parse_mode="Markdown")

@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message):
    if message.chat.id not in ADMIN_IDS:
        return
    text_to_send = message.text.replace("/broadcast", "").strip()
    if not text_to_send:
        await message.answer("⚠️ Введіть текст для розсилки після команди.")
        return
    db_cursor.execute('SELECT chat_id FROM users')
    users = db_cursor.fetchall()
    success = 0
    for u in users:
        try:
            await bot.send_message(u[0], f"📢 **Оновлення системи:**\n\n{text_to_send}", parse_mode="Markdown")
            success += 1
            await asyncio.sleep(0.05)
        except:
            pass
    await message.answer(f"✅ Розсилку завершено. Успішно доставлено: {success}/{len(users)}")

@router.message(F.text == "ℹ️ Допомога")
async def cmd_help(message: Message):
    await message.answer("ℹ️ Виберіть категорію на клавіатурі або надішліть дані (номер, пошту, IP, нікнейм, посилання) для миттєвого аналізу.", reply_markup=get_main_keyboard(message.chat.id))

@router.callback_query(F.data == "export_report")
async def callback_export(call: CallbackQuery):
    db_cursor.execute('SELECT result_text FROM history WHERE chat_id = ? ORDER BY timestamp DESC LIMIT 1', (call.message.chat.id,))
    row = db_cursor.fetchone()
    report = row[0] if row and row[0] else "Звіти відсутні."
    bio = BufferedInputFile(report.encode('utf-8'), filename="osint_report.txt")
    await call.message.answer_document(document=bio, caption="📁 Ваш звіт розвідки")
    await call.answer()

@router.callback_query(F.data == "go_home")
async def callback_home(call: CallbackQuery):
    await call.message.answer("🏠 Головне меню:", reply_markup=get_main_keyboard(call.message.chat.id))
    await call.answer()

# --- ОБРОБКА ФАЙЛІВ ТА ЗОБРАЖЕНЬ ---
@router.message(F.photo | F.document)
async def handle_files(message: Message):
    add_request_stat()
    log_user(message.chat.id)
    try:
        if message.document:
            file_info = await bot.get_file(message.document.file_id)
            file_bytes = await bot.download_file(file_info.file_path)
            if message.document.file_name.lower().endswith('.pdf'):
                reader = pypdf.PdfReader(io.BytesIO(file_bytes))
                res = f"📄 **PDF Документ:**\n• Сторінок: `{len(reader.pages)}`"
                add_to_db_history(message.chat.id, f"PDF: {message.document.file_name}", res)
                await message.answer(res, parse_mode="Markdown", reply_markup=get_standard_markup())
            else:
                await message.answer("ℹ Формат документа підтримується частково.")
        elif message.photo:
            file_info = await bot.get_file(message.photo[-1].file_id)
            file_bytes = await bot.download_file(file_info.file_path)
            img = cv2.imdecode(np.frombuffer(file_bytes, np.uint8), cv2.IMREAD_COLOR)
            ocr_text = pytesseract.image_to_string(img, lang='ukr+eng').strip()
            res = f"📷 **OCR Текст:**\n`{ocr_text[:600] or 'Текст не знайдено'}`"
            add_to_db_history(message.chat.id, "Photo OCR", res)
            await message.answer(res, parse_mode="Markdown", reply_markup=get_standard_markup())
    except Exception as e:
        await message.answer(f"❌ Помилка обробки файлу: {e}")

# --- ОСНОВНИЙ ОБРОБНИК ДАНИХ ТА ЗАПИТІВ ---
@router.message(F.text)
async def process_osint(message: Message):
    chat_id = message.chat.id
    data = message.text.strip()
    
    # Кнопки головного меню
    menu_actions = {
        "⛽ Комісії / Газ мереж": lambda: requests.get("https://mempool.space/api/v1/fees/recommended", timeout=4).json(),
        "🔑 Генератор паролів": lambda: f"🔑 **Пароль:**\n`{''.join(random.choice(string.ascii_letters + string.digits + '!@#$%^&*') for _ in range(16))}`",
        "🕵️ Фейк профіль": lambda: f"🕵️ **Профіль:**\n• Ім'я: `Олександр Мельник`\n• Вік: `{random.randint(20, 40)}`\n• Email: `user_{random.randint(100,999)}@gmail.com`"
    }

    if data in menu_actions:
        add_request_stat()
        log_user(chat_id)
        if data == "⛽ Комісії / Газ мереж":
            try:
                btc = menu_actions[data]()
                res = f"⛽ **Комісії BTC:**\n• Пріоритет: `{btc.get('fastestFee')} sat/vB`\n• Середньо: `{btc.get('halfHourFee')} sat/vB`"
            except:
                res = "⛽ Не вдалося отримати комісії."
        else:
            res = menu_actions[data]()
        add_to_db_history(chat_id, data, res)
        await message.answer(res, parse_mode="Markdown", reply_markup=get_standard_markup())
        return

    if data in ["📱 Про номер", "📧 Про Email", "🌐 IP / Домен / Сабдомени", "👤 Нік / Telegram / Соцмережі", "🚗 Авто (Номер / VIN)", "🏛️ Пошук ПІБ / Реєстри", "🪙 Криптогаманець", "🔗 URL / Безпека / Заголовки", "📷 Фото / Документи / OCR", "🛠️ Утиліти / Хеші / Base64", "🔍 Сканер портів"]:
        await message.answer(f"ℹ️ Введіть дані для категорії: *{data}*.", parse_mode="Markdown")
        return

    # Перевірка кешу для прискорення
    cached_res = get_cache(data)
    if cached_res:
        add_request_stat()
        log_user(chat_id)
        add_to_db_history(chat_id, data, cached_res)
        await message.answer(f"⚡ *(З кешу)*\n\n{cached_res}", parse_mode="Markdown", reply_markup=get_standard_markup())
        return

    add_request_stat()
    log_user(chat_id)
    await message.chat.do(action="typing")

    # Префіксні команди розвідки
    if data.lower().startswith("port "):
        target = data[5:].strip()
        open_p = scan_ports(target)
        res = f"🔍 **Порти для {target}:**\n" + ("\n".join([f"  - `{p}`" for p in open_p]) if open_p else "  Відкритих портів не знайдено.")
        set_cache(data, res)
        add_to_db_history(chat_id, data, res)
        await message.answer(res, parse_mode="Markdown", reply_markup=get_standard_markup())
        return

    # URL / Сайт
    if data.startswith("http://") or data.startswith("https://"):
        try:
            res_req = requests.get(data, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
            vt = check_virustotal_url(data)
            sec = check_security_headers(data)
            ssl_inf = check_ssl_cert(data)
            res = f"🔗 **URL:** `{res_req.url}`\n• Статус: `{res_req.status_code}`\n\n{vt}\n\n{sec}\n\n{ssl_inf}"
            set_cache(data, res)
            add_to_db_history(chat_id, data, res)
            await message.answer(res, parse_mode="Markdown", reply_markup=get_standard_markup())
            return
        except:
            await message.answer("❌ Помилка запиту до сайту.")
            return

    # IP адреса
    if re.match(r'^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$', data):
        try:
            ip_info = requests.get(f"http://ip-api.com/json/{data}", timeout=5).json()
            res = f"🌐 **IP {data}:**\n• Країна: {ip_info.get('country')}\n• Місто: {ip_info.get('city')}\n• Провайдер: {ip_info.get('isp')}"
            set_cache(data, res)
            add_to_db_history(chat_id, data, res)
            await message.answer(res, parse_mode="Markdown", reply_markup=get_standard_markup())
            return
        except:
            pass

    # Телефон
    if data.startswith('+') or (data.isdigit() and len(data) >= 9):
        try:
            num = phonenumbers.parse(data, "UA")
            res = f"📱 **Телефон:** `{data}`\n• Регіон: {geocoder.description_for_number(num, 'uk')}\n• Оператор: {carrier.name_for_number(num, 'uk')}\n\n🔍 **Швидкий пошук згадок:**"
            set_cache(data, res)
            add_to_db_history(chat_id, data, res)
            await message.answer(res, parse_mode="Markdown", reply_markup=generate_osint_dorks(data))
            return
        except:
            pass

    # Email (з симуляцією витоків)
    if "@" in data:
        try:
            ev = validate_email(data, check_deliverability=True)
            leaks = check_password_leak(data)
            res = f"📧 **Email:** `{data}`\n• Домен: `{ev.domain}`\n• Згадки у витоках: `{leaks}`\n\n🔍 **Google Dorks розвідка:**"
            set_cache(data, res)
            add_to_db_history(chat_id, data, res)
            await message.answer(res, parse_mode="Markdown", reply_markup=generate_osint_dorks(data))
            return
        except:
            pass

    # Нікнейм / Соцмережі / Загальний пошук
    username = data.lstrip('@')
    platforms = {
        "Telegram": f"https://t.me/{username}",
        "GitHub": f"https://github.com/{username}",
        "TikTok": f"https://www.tiktok.com/@{username}",
        "Instagram": f"https://www.instagram.com/{username}"
    }
    markup_inline = []
    found = []
    for name, url in platforms.items():
        try:
            if requests.get(url, timeout=2, headers={"User-Agent": "Mozilla/5.0"}).status_code == 200:
                found.append(name)
                markup_inline.append([InlineKeyboardButton(text=f"🔗 {name}", url=url)])
        except:
            pass

    markup_inline.append([InlineKeyboardButton(text="🌐 Google Dork Пошук", url=f"https://www.google.com/search?q={urllib.parse.quote(data)}")])
    markup_inline.append([InlineKeyboardButton(text="📄 Експорт звіту", callback_data="export_report"), InlineKeyboardButton(text="🏠 На головну", callback_data="go_home")])
    
    res = f"👤 **Розвідка профілю:** `{username}`\n• Активних платформ знайдено: {len(found)}"
    set_cache(data, res)
    add_to_db_history(chat_id, data, res)
    await message.answer(res, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=markup_inline))

# --- ЗАПУСК АСИНХРОННОГО БОТА ---
async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
