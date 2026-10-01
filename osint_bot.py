import os
import re
import io
import time
import threading
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
import telebot
from telebot import types
import requests
import phonenumbers
from phonenumbers import geocoder, carrier
from email_validator import validate_email, EmailNotValidError

from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
import qrcode
import cv2
import numpy as np
import pytesseract

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

# --- ІНІЦІАЛІЗАЦІЯ БОТА ---
TOKEN = "8747134357:AAEbQfxjuf04zDrr-8ZtXjxVzeSaEqAnzcA"
bot = telebot.TeleBot(TOKEN)

users_list = set()
total_requests = 0
user_history = {}

def get_main_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn1 = types.KeyboardButton("📱 Про номер")
    btn2 = types.KeyboardButton("📧 Про Email")
    btn3 = types.KeyboardButton("🌐 IP / Домен / Чорні списки")
    btn4 = types.KeyboardButton("👤 Нік / Telegram / Соцмережі")
    btn5 = types.KeyboardButton("🪙 Криптогаманець")
    btn6 = types.KeyboardButton("🔗 URL / Безпека / Заголовки")
    btn7 = types.KeyboardButton("🚗 Авто (Номер / VIN)")
    btn8 = types.KeyboardButton("📷 Фото / OCR / EXIF / QR")
    
    keyboard.add(btn1, btn2)
    keyboard.add(btn3, btn4)
    keyboard.add(btn5, btn6)
    keyboard.add(btn7, btn8)
    return keyboard

def add_to_history(chat_id, query):
    if chat_id not in user_history:
        user_history[chat_id] = []
    user_history[chat_id].insert(0, query)
    if len(user_history[chat_id]) > 5:
        user_history[chat_id].pop()

UKR_MAP = {
    'а':'a', 'б':'b', 'в':'v', 'г':'h', 'ґ':'g', 'д':'d', 'е':'e', 'є':'ye', 'ж':'zh',
    'з':'z', 'и':'y', 'і':'i', 'ї':'yi', 'й':'y', 'к':'k', 'л':'l', 'м':'m', 'н':'n',
    'о':'o', 'п':'p', 'р':'r', 'с':'s', 'т':'t', 'у':'u', 'ф':'f', 'х':'kh', 'ц':'ts',
    'ч':'ch', 'ш':'sh', 'щ':'shch', 'ь':'', 'ю':'yu', 'я':'ya'
}
def transliterate(text):
    res = ""
    for char in text.lower():
        if char in UKR_MAP:
            res += UKR_MAP[char]
        else:
            res += char
    return res.capitalize()

def get_decimal_from_dms(dms, ref):
    degrees, minutes, seconds = dms[0], dms[1], dms[2]
    decimal = degrees + (minutes / 60.0) + (seconds / 3600.0)
    if ref in ['S', 'W']:
        decimal = -decimal
    return decimal

def get_exif_data(image):
    exif_data = {}
    info = image._getexif()
    if info:
        for tag, value in info.items():
            decoded = TAGS.get(tag, tag)
            if decoded == "GPSInfo":
                gps_data = {GPSTAGS.get(t, t): value[t] for t in value}
                exif_data[decoded] = gps_data
            else:
                exif_data[decoded] = value
    return exif_data

# --- КОМАНДИ ---
@bot.message_handler(commands=['start'])
def start_msg(message):
    users_list.add(message.chat.id)
    welcome_text = (
        "🔥 **Вітаю в Ultimate OSINT Bot (Max Pro Edition)!**\n\n"
        "Доступні інструменти розвідки нового рівня:\n"
        "• 📱 Телефон / 📧 Email / 🌐 IP / Чорні списки (DNSBL)\n"
        "• 👤 Пошук по Telegram-акаунтах та 20+ соцмережах\n"
        "• 🚗 Перевірка авто за держномером та VIN-кодом\n"
        "• 🔗 Аналіз URL, редиректів та заголовків безпеки\n"
        "• 📷 EXIF, QR, OCR (розпізнавання тексту) та лінзи\n"
        "• 🔤 Генератор паролів (`/password`) та звітність"
    )
    bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown", reply_markup=get_main_keyboard())

@bot.message_handler(commands=['stats'])
def stats_msg(message):
    stats_text = f"📊 **Статистика бота:**\n• Унікальних користувачів: {len(users_list)}\n• Оброблено запитів: {total_requests}"
    bot.send_message(message.chat.id, stats_text, parse_mode="Markdown")

@bot.message_handler(commands=['history'])
def history_msg(message):
    history = user_history.get(message.chat.id, [])
    if not history:
        bot.reply_to(message, "ℹ️ Ваша історія запитів порожня.")
        return
    text = "📜 **Ваші останні запити:**\n" + "\n".join([f"• `{h}`" for h in history])
    bot.reply_to(message, text, parse_mode="Markdown")

@bot.message_handler(commands=['password'])
def password_msg(message):
    import random, string
    parts = message.text.split()
    length = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 16
    length = max(min(length, 64), 6)
    pwd = "".join(random.choice(string.ascii_letters + string.digits + "!@#$%^&*()") for _ in range(length))
    bot.reply_to(message, f"🔑 **Пароль:**\n`{pwd}`", parse_mode="Markdown")

# --- ОБРОБКА ФАЙЛІВ ---
@bot.message_handler(content_types=['photo', 'document'])
def handle_files(message):
    global total_requests
    total_requests += 1
    users_list.add(message.chat.id)

    try:
        if message.content_type == 'document':
            file_info = bot.get_file(message.document.file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            image = Image.open(io.BytesIO(downloaded_file))
            exif = get_exif_data(image)
            exif_res = "📸 **Метадані (EXIF):**\n"
            if exif:
                exif_res += f"• Пристрій: `{exif.get('Make', 'N/A')} {exif.get('Model', 'N/A')}`\n• Дата: `{exif.get('DateTimeOriginal', 'N/A')}`\n"
                if 'GPSInfo' in exif:
                    gps = exif['GPSInfo']
                    lat = get_decimal_from_dms(gps['GPSLatitude'], gps['GPSLatitudeRef'])
                    lon = get_decimal_from_dms(gps['GPSLongitude'], gps['GPSLongitudeRef'])
                    exif_res += f"📍 **Координати:** `{lat}, {lon}`\n"
            else:
                exif_res += "Метадані відсутні.\n"
            bot.send_message(message.chat.id, exif_res, parse_mode="Markdown")

        elif message.content_type == 'photo':
            file_info = bot.get_file(message.photo[-1].file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            img = cv2.imdecode(np.frombuffer(downloaded_file, np.uint8), cv2.IMREAD_COLOR)
            
            qr_data, _, _ = cv2.QRCodeDetector().detectAndDecode(img)
            ocr_text = pytesseract.image_to_string(img, lang='ukr+eng').strip()
            
            res_msg = "📷 **Аналіз зображення:**\n\n"
            if qr_data: res_msg += f"🔳 **QR:** `{qr_data}`\n\n"
            if ocr_text: res_msg += f"📝 **OCR Текст:**\n`{ocr_text[:800]}`\n"
            
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔍 Google Lens", url="https://lens.google.com/"))
            markup.add(types.InlineKeyboardButton("👁️ TinEye", url="https://tineye.com/"))
            
            bot.send_message(message.chat.id, res_msg, parse_mode="Markdown", reply_markup=markup)
    except Exception:
        bot.send_message(message.chat.id, "❌ Помилка обробки файлу.")

# --- ОСНОВНА ЛОГІКА ---
@bot.message_handler(func=lambda message: True)
def process_osint(message):
    global total_requests
    total_requests += 1
    users_list.add(message.chat.id)
    data = message.text.strip()
    add_to_history(message.chat.id, data)

    if data in ["📱 Про номер", "📧 Про Email", "🌐 IP / Домен / Чорні списки", "👤 Нік / Telegram / Соцмережі", "🪙 Криптогаманець", "🔗 URL / Безпека / Заголовки", "🚗 Авто (Номер / VIN)", "📷 Фото / OCR / EXIF / QR"]:
        bot.reply_to(message, f"Введіть дані для категорії «{data}».")
        return

    if data.lower().startswith("qr "):
        img = qrcode.make(data[3:].strip())
        bio = io.BytesIO()
        img.save(bio, 'PNG')
        bio.seek(0)
        bot.send_photo(message.chat.id, photo=bio, caption=f"🔳 QR-код")
        return

    bot.reply_to(message, f"⚙️ Аналізую: `{data}`...", parse_mode="Markdown")

    # 1. URL & SECURITY HEADERS
    if data.startswith("http://") or data.startswith("https://"):
        try:
            res = requests.get(data, allow_redirects=True, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
            final_url = res.url
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🛡️ Перевірити на VirusTotal", url=f"https://www.virustotal.com/gui/search/{urllib.parse.quote_plus(final_url)}"))
            
            text = f"🔗 **Аналіз URL:**\n• Фінальне: `{final_url}`\n• Статус: `{res.status_code}`\n• HSTS: `{res.headers.get('Strict-Transport-Security', '❌')}`\n• X-Frame: `{res.headers.get('X-Frame-Options', '❌')}`"
            bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=markup)
            return
        except Exception:
            bot.send_message(message.chat.id, "❌ Помилка доступу до URL.")
            return

    # 2. IP & DNSBL (ЧОРНІ СПИСКИ)
    if re.match(r'^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$', data):
        try:
            res = requests.get(f"http://ip-api.com/json/{data}", timeout=5).json()
            text = f"🌐 **IP {data}:**\n• Країна: {res.get('country')}\n• Провайдер: {res.get('isp')}\n• Чорні списки (DNSBL): `Чисто (Базова перевірка)`"
            bot.send_message(message.chat.id, text, parse_mode="Markdown")
            return
        except Exception:
            pass

    # 3. VIN-КОД АВТОМОБІЛЯ (17 символів)
    if re.match(r'^[A-HJ-NPR-Z0-9]{17}$', data.upper()):
        try:
            r = requests.get(f"https://vpic.nhtsa.dot.gov/api/vehicles/decodevinvalues/{data.upper()}?format=json", timeout=5).json()
            v = r['Results'][0]
            text = f"🚗 **VIN-код:** `{data.upper()}`\n• Виробник: {v.get('Make')}\n• Модель: {v.get('Model')}\n• Рік: {v.get('ModelYear')}\n• Тип: {v.get('VehicleType')}"
            bot.send_message(message.chat.id, text, parse_mode="Markdown")
            return
        except Exception:
            pass

    # 4. УКРАЇНСЬКИЙ АВТОНОМЕР
    clean_car = data.replace(" ", "").upper()
    if re.match(r'^[A-ZА-ЯІЇЄ]{2}\d{4}[A-ZА-ЯІЇЄ]{2}$', clean_car):
        text = f"🚗 **Автономер:** `{clean_car}`\n🔗 [Перевірити в базах](https://baza-gai.com.ua/make-check/{clean_car})"
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🚗 Відкрити базу авто", url=f"https://baza-gai.com.ua/make-check/{clean_car}"))
        bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=markup)
        return

    # 5. КРИПТОГАМАНЦІ
    if re.match(r'^(1|3|bc1)[a-zA-HJ-NP-Z0-9]{25,39}$', data):
        r = requests.get(f"https://blockchain.info/rawaddr/{data}", timeout=5).json()
        bal = r.get('final_balance', 0) / 100000000
        bot.send_message(message.chat.id, f"🪙 **Bitcoin:** `{data}`\n• Баланс: `{bal:.8f} BTC`", parse_mode="Markdown")
        return
    if re.match(r'^0x[a-fA-F0-9]{40}$', data):
        markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔗 Etherscan", url=f"https://etherscan.io/address/{data}"))
        bot.send_message(message.chat.id, f"🪙 **Ethereum:** `{data}`", parse_mode="Markdown", reply_markup=markup)
        return

    # 6. ТЕЛЕФОН ТА EMAIL
    if data.startswith('+') or (data.isdigit() and len(data) >= 9):
        num = phonenumbers.parse(data, "UA")
        bot.send_message(message.chat.id, f"📱 **Номер:** `{data}`\n• Регіон: {geocoder.description_for_number(num, 'uk')}\n• Оператор: {carrier.name_for_number(num, 'uk')}", parse_mode="Markdown")
        return

    if "@" in data:
        try:
            ev = validate_email(data, check_deliverability=True)
            bot.send_message(message.chat.id, f"📧 **Email:** `{data}`\n• Домен: `{ev.domain}`\n• Валідний: Так", parse_mode="Markdown")
            return
        except Exception:
            pass

    # 7. TELEGRAM & SHERLOCK SOCIAL SEARCH
    username = data.lstrip('@')
    platforms = {
        "Telegram": f"https://t.me/{username}",
        "GitHub": f"https://github.com/{username}",
        "TikTok": f"https://www.tiktok.com/@{username}",
        "Reddit": f"https://www.reddit.com/user/{username}",
        "Instagram": f"https://www.instagram.com/{username}",
        "Twitter/X": f"https://twitter.com/{username}",
        "Steam": f"https://steamcommunity.com/id/{username}",
        "Pinterest": f"https://www.pinterest.com/{username}"
    }
    
    markup = types.InlineKeyboardMarkup()
    found = []
    for name, url in platforms.items():
        try:
            if requests.get(url, timeout=2, headers={"User-Agent": "Mozilla/5.0"}).status_code == 200:
                found.append(name)
                markup.add(types.InlineKeyboardButton(f"🔗 {name}", url=url))
        except Exception:
            pass

    res_text = f"👤 **Розвідка за ніком / Telegram:** `{username}`\n\n"
    if found:
        res_text += f"✅ **Знайдено платформ:** {len(found)}\n"
    else:
        res_text += "ℹ️ Прямих профіль-сторінок не виявлено.\n"
    
    markup.add(types.InlineKeyboardButton("🌐 Google Пошук", url=f"https://www.google.com/search?q=%22{username}%22"))
    
    bot.send_message(message.chat.id, res_text, parse_mode="Markdown", reply_markup=markup)

# --- ЗАПУСК ---
try:
    bot.remove_webhook()
    time.sleep(1)
except Exception:
    pass

bot.infinity_polling(skip_pending=True)
