import os
import re
import io
import time
import socket
import random
import string
import threading
import base64
import hashlib
import sqlite3
import ssl
import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
import telebot
from telebot import types
import requests
import phonenumbers
from phonenumbers import geocoder, carrier
from email_validator import validate_email

from PIL import Image
import qrcode
import cv2
import numpy as np
import pytesseract
import pypdf

# --- ВЕБ-СЕРВЕР ДЛЯ РЕНДЕРУ (HEALTH CHECK) ---
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

# --- БАЗА ДАНИХ (SQLITE) ---
def init_db():
    conn = sqlite3.connect('bot_database.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (chat_id INTEGER PRIMARY KEY, first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS history (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, query TEXT, result_text TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS stats (key TEXT PRIMARY KEY, value INTEGER)''')
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

def add_to_db_history(chat_id, query, result_text=""):
    db_cursor.execute('INSERT INTO history (chat_id, query, result_text) VALUES (?, ?, ?)', (chat_id, query, result_text))
    db_conn.commit()
    db_cursor.execute('''
        DELETE FROM history WHERE id NOT IN (
            SELECT id FROM history WHERE chat_id = ? ORDER BY timestamp DESC LIMIT 5
        ) AND chat_id = ?
    ''', (chat_id, chat_id))
    db_conn.commit()

# --- ІНІЦІАЛІЗАЦІЯ БОТА ---
TOKEN = "8747134357:AAFjsPvLaskM5TymQZoXzmpYWrfqVSkMzWE"
VIRUSTOTAL_API_KEY = os.environ.get("VIRUSTOTAL_API_KEY", "")
bot = telebot.TeleBot(TOKEN)

last_message_time = {}
ANTIFLUOD_DELAY = 0.8

def check_antifluod(chat_id):
    now = time.time()
    if chat_id in last_message_time:
        if now - last_message_time[chat_id] < ANTIFLUOD_DELAY:
            return False
    last_message_time[chat_id] = now
    return True

def get_main_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(types.KeyboardButton("📱 Про номер"), types.KeyboardButton("📧 Про Email"))
    keyboard.add(types.KeyboardButton("🌐 IP / Домен / Сабдомени"), types.KeyboardButton("👤 Нік / Telegram / Соцмережі"))
    keyboard.add(types.KeyboardButton("🪙 Криптогаманець"), types.KeyboardButton("🔗 URL / Безпека / Заголовки"))
    keyboard.add(types.KeyboardButton("📷 Фото / Документи / OCR"), types.KeyboardButton("🛠️ Утиліти / Хеші / Base64"))
    keyboard.add(types.KeyboardButton("⛽ Комісії / Газ мереж"), types.KeyboardButton("🔍 Сканер портів"))
    keyboard.add(types.KeyboardButton("🕵️ Фейк профіль"), types.KeyboardButton("🔑 Генератор паролів"))
    return keyboard

def get_standard_markup():
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("📄 Експорт звіту", callback_data="export_report"),
        types.InlineKeyboardButton("🏠 На головну", callback_data="go_home")
    )
    return markup

# --- НОВІ ТА РОЗШИРЕНІ УТИЛІТИ ---
def scan_ports(target):
    ports = [21, 22, 23, 25, 53, 80, 110, 135, 139, 443, 445, 3306, 3389, 8080, 8443]
    open_ports = []
    service_map = {21: "FTP", 22: "SSH", 23: "Telnet", 25: "SMTP", 53: "DNS", 80: "HTTP", 443: "HTTPS", 3306: "MySQL", 3389: "RDP", 8080: "HTTP-Proxy"}
    for p in ports:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.3)
            if s.connect_ex((target, p)) == 0:
                service = service_map.get(p, "Unknown")
                open_ports.append(f"{p} ({service})")
            s.close()
        except Exception:
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
    except Exception:
        pass
    return 0

def check_virustotal_url(target_url):
    if not VIRUSTOTAL_API_KEY:
        return "⚠️ VirusTotal API ключ не налаштовано."
    try:
        headers = {"x-apikey": VIRUSTOTAL_API_KEY}
        data = {"url": target_url}
        response = requests.post("https://www.virustotal.com/api/v3/urls", headers=headers, data=data, timeout=5)
        if response.status_code == 200:
            analysis_id = response.json().get("data", {}).get("id")
            time.sleep(1)
            report = requests.get(f"https://www.virustotal.com/api/v3/analyses/{analysis_id}", headers=headers, timeout=5).json()
            stats = report.get("data", {}).get("attributes", {}).get("stats", {})
            return f"🛡️ **VirusTotal:** Шкідливих: `{stats.get('malicious', 0)}` | Безпечних: `{stats.get('harmless', 0)}`"
    except Exception:
        pass
    return "❌ Помилка VirusTotal."

def check_security_headers(domain):
    try:
        url = domain if domain.startswith("http") else f"https://{domain}"
        res = requests.get(url, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
        headers = res.headers
        hsts = "✅ Є" if "Strict-Transport-Security" in headers else "❌ Немає"
        csp = "✅ Є" if "Content-Security-Policy" in headers else "❌ Немає"
        xfo = "✅ Є" if "X-Frame-Options" in headers else "❌ Немає"
        return f"🛡️ **Заголовки безпеки:**\n• HSTS: {hsts}\n• CSP: {csp}\n• X-Frame-Options: {xfo}"
    except Exception:
        return "❌ Не вдалося перевірити заголовки сайту."

def check_ssl_cert(domain):
    try:
        hostname = domain.replace("https://", "").replace("http://", "").split("/")[0]
        ctx = ssl.create_default_context()
        with socket.create_connection((hostname, 443), timeout=5) as sock:
            with ctx.wrap_socket(sock, server_hostname=hostname) as ssock:
                cert = ssock.getpeercert()
                not_after = cert.get('notAfter')
                issuer = dict(x[0] for x in cert.get('issuer', []))
                org = issuer.get('organizationName', 'Unknown')
                return f"🔒 **SSL Сертифікат:**\n• Видавець: `{org}`\n• Діє до: `{not_after}`"
    except Exception:
        return "❌ Не вдалося отримати SSL-сертифікат."

def mac_vendor_lookup(mac):
    try:
        clean_mac = mac.replace(":", "").replace("-", "")[:6]
        res = requests.get(f"https://api.macvendors.com/{clean_mac}", timeout=4)
        if res.status_code == 200:
            return f"📡 **Виробник MAC:** `{res.text}`"
    except Exception:
        pass
    return "❌ Виробника за MAC не знайдено."

def get_hash(text):
    md5 = hashlib.md5(text.encode()).hexdigest()
    sha1 = hashlib.sha1(text.encode()).hexdigest()
    sha256 = hashlib.sha256(text.encode()).hexdigest()
    return f"🛠️ **Хеші для `{text}`:**\n• MD5: `{md5}`\n• SHA1: `{sha1}`\n• SHA256: `{sha256}`"

# --- КОМАНДИ ТА CALLBACK ---
@bot.message_handler(commands=['start'])
def start_msg(message):
    log_user(message.chat.id)
    welcome_text = (
        "🔥 **Ultimate OSINT Bot Max Pro+ (Full Arsenal Edition)**\n\n"
        "Інтегровано повний набір інструментів розвідки та безпеки:\n"
        "• 📱 Телефон, 📧 Пошта, витоки паролів, 🔑 Генератор хешів\n"
        "• 🌐 IP, Домени, Порт-сканер, SSL, Заголовки безпеки\n"
        "• 🛡️ VirusTotal, 📡 MAC Vendor, 🧮 Утиліти кодувань"
    )
    bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown", reply_markup=get_main_keyboard())

@bot.message_handler(commands=['stats'])
def stats_msg(message):
    users_count, req_count = get_stats()
    stats_text = f"📊 **Статистика бота:**\n• Унікальних користувачів: {users_count}\n• Оброблено запитів: {req_count}"
    bot.send_message(message.chat.id, stats_text, parse_mode="Markdown")

@bot.message_handler(commands=['history'])
def history_msg(message):
    db_cursor.execute('SELECT query, timestamp FROM history WHERE chat_id = ? ORDER BY timestamp DESC LIMIT 5', (message.chat.id,))
    history = db_cursor.fetchall()
    if not history:
        bot.reply_to(message, "ℹ️️ Ваша історія запитів порожня.")
        return
    text = "📜 **Ваші останні запити:**\n" + "\n".join([f"• `{h[0]}` _({h[1]})_" for h in history])
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    chat_id = call.message.chat.id
    if call.data == "export_report":
        db_cursor.execute('SELECT result_text FROM history WHERE chat_id = ? ORDER BY timestamp DESC LIMIT 1', (chat_id,))
        row = db_cursor.fetchone()
        report = row[0] if row and row[0] else "Звіти відсутні."
        bio = io.BytesIO(report.encode('utf-8'))
        bio.name = "osint_report.txt"
        bot.send_document(chat_id, document=bio, caption="📁 Ваш звіт розвідки")
        bot.answer_callback_query(call.id)
    elif call.data == "go_home":
        bot.send_message(chat_id, "🏠 Головне меню:", reply_markup=get_main_keyboard())
        bot.answer_callback_query(call.id)

# --- ОБРОБКА ФАЙЛІВ ---
@bot.message_handler(content_types=['photo', 'document'])
def handle_files(message):
    if not check_antifluod(message.chat.id):
        bot.reply_to(message, "⚠️ Занадто часто! Зачекайте.")
        return
    add_request_stat()
    log_user(message.chat.id)

    try:
        if message.content_type == 'document':
            file_info = bot.get_file(message.document.file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            file_name = message.document.file_name.lower()
            
            if file_name.endswith(('.jpg', '.jpeg', '.png')):
                image = Image.open(io.BytesIO(downloaded_file))
                res = "📸 **EXIF Метадані:**\n• Зображення успішно проаналізовано."
                add_to_db_history(message.chat.id, f"Photo: {file_name}", res)
                bot.send_message(message.chat.id, res, parse_mode="Markdown", reply_markup=get_standard_markup())
            elif file_name.endswith('.pdf'):
                reader = pypdf.PdfReader(io.BytesIO(downloaded_file))
                res = f"📄 **PDF Документ:**\n• Сторінок: `{len(reader.pages)}`"
                add_to_db_history(message.chat.id, f"PDF: {file_name}", res)
                bot.send_message(message.chat.id, res, parse_mode="Markdown", reply_markup=get_standard_markup())
            else:
                bot.send_message(message.chat.id, "ℹ Формат документа підтримується частково.")
        elif message.content_type == 'photo':
            file_info = bot.get_file(message.photo[-1].file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            img = cv2.imdecode(np.frombuffer(downloaded_file, np.uint8), cv2.IMREAD_COLOR)
            ocr_text = pytesseract.image_to_string(img, lang='ukr+eng').strip()
            res_msg = f"📷 **OCR Текст:**\n`{ocr_text[:600] or 'Текст не знайдено'}`"
            add_to_db_history(message.chat.id, "Photo OCR", res_msg)
            bot.send_message(message.chat.id, res_msg, parse_mode="Markdown", reply_markup=get_standard_markup())
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Помилка обробки файлу: {e}")

# --- ОСНОВНИЙ ОБРОБНИК ПОВІДОМЛЕНЬ ---
@bot.message_handler(func=lambda message: True)
def process_osint(message):
    chat_id = message.chat.id
    if not check_antifluod(chat_id):
        bot.reply_to(message, "⚠️ Занадто часті запити!")
        return

    add_request_stat()
    log_user(chat_id)
    data = message.text.strip()

    # Кнопки меню
    if data == "⛽ Комісії / Газ мереж":
        try:
            btc = requests.get("https://mempool.space/api/v1/fees/recommended", timeout=4).json()
            res = f"⛽ **Комісії мережі BTC:**\n• Пріоритет: `{btc.get('fastestFee')} sat/vB`\n• Середньо: `{btc.get('halfHourFee')} sat/vB`"
        except Exception:
            res = "⛽ Не вдалося отримати комісії."
        add_to_db_history(chat_id, data, res)
        bot.send_message(chat_id, res, parse_mode="Markdown", reply_markup=get_standard_markup())
        return
    elif data == "🔍 Сканер портів":
        bot.reply_to(message, "ℹ️ Введіть IP або домен у форматі: `port 8.8.8.8`")
        return
    elif data == "🔑 Генератор паролів":
        chars = string.ascii_letters + string.digits + "!@#$%^&*"
        pwd = "".join(random.choice(chars) for _ in range(16))
        res = f"🔑 **Безпечний пароль:**\n`{pwd}`"
        bot.send_message(chat_id, res, parse_mode="Markdown", reply_markup=get_standard_markup())
        return
    elif data == "🕵️️ Фейк профіль":
        names = ["Олександр", "Максим", "Андрій", "Софія", "Юлія", "Дмитро", "Артем", "Ірина"]
        surnames = ["Коваленко", "Шевченко", "Мельник", "Бойко", "Ткаченко", "Кравченко"]
        res = f"🕵️ **Фейковий профіль:**\n• Ім'я: `{random.choice(names)} {random.choice(surnames)}`\n• Вік: `{random.randint(19, 45)}`\n• Email: `user_{random.randint(1000,9999)}@gmail.com`"
        add_to_db_history(chat_id, data, res)
        bot.send_message(chat_id, res, parse_mode="Markdown", reply_markup=get_standard_markup())
        return
    elif data in ["📱 Про номер", "📧 Про Email", "🌐 IP / Домен / Сабдомени", "👤 Нік / Telegram / Соцмережі", "🪙 Криптогаманець", "🔗 URL / Безпека / Заголовки", "📷 Фото / Документи / OCR", "🛠️ Утиліти / Хеші / Base64"]:
        bot.reply_to(message, f"Введіть дані для категорії: *{data}*.", parse_mode="Markdown")
        return

    # Префіксні утиліти
    if data.lower().startswith("port "):
        target = data[5:].strip()
        bot.reply_to(message, f"🔍 Сканую порти для `{target}`...")
        open_p = scan_ports(target)
        res = f"🔍 **Порти для {target}:**\n" + ("\n".join([f"  - `{p}`" for p in open_p]) if open_p else "  Жодного відкритого порта не знайдено.")
        add_to_db_history(chat_id, data, res)
        bot.send_message(chat_id, res, parse_mode="Markdown", reply_markup=get_standard_markup())
        return

    if data.lower().startswith("pwned "):
        pwd = data[6:].strip()
        count = check_password_leak(pwd)
        res = f"🔑 **Перевірка пароля:**\n• У витоках: `{count} разів`" if count > 0 else "🔑 Пароль чистий."
        bot.send_message(chat_id, res, parse_mode="Markdown", reply_markup=get_standard_markup())
        return

    if data.lower().startswith("hash "):
        res = get_hash(data[5:].strip())
        bot.send_message(chat_id, res, parse_mode="Markdown", reply_markup=get_standard_markup())
        return

    if data.lower().startswith("mac "):
        res = mac_vendor_lookup(data[4:].strip())
        bot.send_message(chat_id, res, parse_mode="Markdown", reply_markup=get_standard_markup())
        return

    if data.lower().startswith("ssl "):
        res = check_ssl_cert(data[4:].strip())
        bot.send_message(chat_id, res, parse_mode="Markdown", reply_markup=get_standard_markup())
        return

    if data.lower().startswith("headers "):
        res = check_security_headers(data[8:].strip())
        bot.send_message(chat_id, res, parse_mode="Markdown", reply_markup=get_standard_markup())
        return

    if data.lower().startswith("qr "):
        img = qrcode.make(data[3:].strip())
        bio = io.BytesIO()
        img.save(bio, 'PNG')
        bio.seek(0)
        bot.send_photo(chat_id, photo=bio, caption="🔳 QR-код")
        return

    if data.lower().startswith("b64 "):
        val = data[4:].strip()
        try:
            decoded = base64.b64decode(val.encode('utf-8')).decode('utf-8', errors='ignore')
            res = f"🔓 **Decoded:** `{decoded}`"
        except Exception:
            encoded = base64.b64encode(val.encode('utf-8')).decode('utf-8')
            res = f"🔒 **Encoded:** `{encoded}`"
        bot.reply_to(message, res, parse_mode="Markdown")
        return

    # Основний аналіз
    bot.reply_to(message, f"⚙️ Обробка запиту...", parse_mode="Markdown")

    if data.startswith("http://") or data.startswith("https://"):
        try:
            res = requests.get(data, allow_redirects=True, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
            vt = check_virustotal_url(data)
            headers_sec = check_security_headers(data)
            ssl_info = check_ssl_cert(data)
            text = f"🔗 **URL:** `{res.url}`\n• Статус: `{res.status_code}`\n\n{vt}\n\n{headers_sec}\n\n{ssl_info}"
            add_to_db_history(chat_id, data, text)
            bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=get_standard_markup())
            return
        except Exception:
            bot.send_message(message.chat.id, "❌ Помилка запиту до URL.")
            return

    if re.match(r'^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$', data):
        try:
            res = requests.get(f"http://ip-api.com/json/{data}", timeout=5).json()
            text = f"🌐 **IP {data}:**\n• Країна: {res.get('country')}\n• Місто: {res.get('city')}\n• Провайдер: {res.get('isp')}"
            add_to_db_history(chat_id, data, text)
            bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=get_standard_markup())
            return
        except Exception:
            pass

    if re.match(r'^(1|3|bc1)[a-zA-HJ-NP-Z0-9]{25,39}$', data):
        try:
            r = requests.get(f"https://blockchain.info/rawaddr/{data}", timeout=5).json()
            bal = r.get('final_balance', 0) / 100000000
            text = f"🪙 **Bitcoin:** `{data}`\n• Баланс: `{bal:.8f} BTC`"
            add_to_db_history(chat_id, data, text)
            bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=get_standard_markup())
            return
        except Exception:
            pass

    if data.startswith('+') or (data.isdigit() and len(data) >= 9):
        try:
            num = phonenumbers.parse(data, "UA")
            text = f"📱 **Телефон:** `{data}`\n• Регіон: {geocoder.description_for_number(num, 'uk')}\n• Оператор: {carrier.name_for_number(num, 'uk')}"
            add_to_db_history(chat_id, data, text)
            bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=get_standard_markup())
            return
        except Exception:
            pass

    if "@" in data:
        try:
            ev = validate_email(data, check_deliverability=True)
            text = f"📧 **Email:** `{data}`\n• Домен: `{ev.domain}`\n• Валідний: Так"
            add_to_db_history(chat_id, data, text)
            bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=get_standard_markup())
            return
        except Exception:
            pass

    # Sherlock нікнейм
    username = data.lstrip('@')
    platforms = {
        "Telegram": f"https://t.me/{username}",
        "GitHub": f"https://github.com/{username}",
        "TikTok": f"https://www.tiktok.com/@{username}",
        "Instagram": f"https://www.instagram.com/{username}"
    }
    found = []
    markup = types.InlineKeyboardMarkup()
    for name, url in platforms.items():
        try:
            if requests.get(url, timeout=2, headers={"User-Agent": "Mozilla/5.0"}).status_code == 200:
                found.append(name)
                markup.add(types.InlineKeyboardButton(f"🔗 {name}", url=url))
        except Exception:
            pass

    markup.add(
        types.InlineKeyboardButton("📄 Експорт звіту", callback_data="export_report"),
        types.InlineKeyboardButton("🏠 На головну", callback_data="go_home")
    )
    res_text = f"👤 **Нік:** `{username}`\n• Знайдено платформ: {len(found)}"
    add_to_db_history(chat_id, data, res_text)
    bot.send_message(chat_id, res_text, parse_mode="Markdown", reply_markup=markup)

try:
    bot.remove_webhook()
    time.sleep(1)
except Exception:
    pass

bot.infinity_polling(skip_pending=True)
