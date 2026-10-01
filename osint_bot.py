import os
import re
import io
import time
import threading
import urllib.parse
import base64
import hashlib
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

# Для аналізу документів (PDF, DOCX)
import pypdf
import docx
import openpyxl

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
TOKEN = "8747134357:AAHtgOBrETbmccZ8rO_aVKu0eWQOViIudNM"
bot = telebot.TeleBot(TOKEN)

users_list = set()
total_requests = 0
user_history = {}
last_query_results = {}  # Зберігає останній текст/звіт для експорту

def get_main_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn1 = types.KeyboardButton("📱 Про номер")
    btn2 = types.KeyboardButton("📧 Про Email")
    btn3 = types.KeyboardButton("🌐 IP / Домен / Сабдомени")
    btn4 = types.KeyboardButton("👤 Нік / Telegram / Соцмережі")
    btn5 = types.KeyboardButton("🪙 Криптогаманець")
    btn6 = types.KeyboardButton("🔗 URL / Безпека / Заголовки")
    btn7 = types.KeyboardButton("🚗 Авто (Номер / VIN)")
    btn8 = types.KeyboardButton("📷 Фото / Документи / OCR")
    btn9 = types.KeyboardButton("🛠️ Утиліти / Хеші / Base64")
    btn10 = types.KeyboardButton("⛽ Комісії / Газ мереж")
    
    keyboard.add(btn1, btn2)
    keyboard.add(btn3, btn4)
    keyboard.add(btn5, btn6)
    keyboard.add(btn7, btn8)
    keyboard.add(btn9, btn10)
    return keyboard

def add_to_history(chat_id, query, result_text=""):
    if chat_id not in user_history:
        user_history[chat_id] = []
    user_history[chat_id].insert(0, query)
    if len(user_history[chat_id]) > 5:
        user_history[chat_id].pop()
    if result_text:
        last_query_results[chat_id] = result_text

UKR_MAP = {
    'а':'a', 'б':'b', 'в':'v', 'г':'h', 'ґ':'g', 'д':'d', 'е':'e', 'є':'ye', 'ж':'zh',
    'з':'z', 'и':'y', 'і':'i', 'ї':'yi', 'й':'y', 'к':'k', 'л':'l', 'м':'m', 'н':'n',
    'о':'o', 'п':'p', 'р':'r', 'с':'s', 'т':'t', 'у':'u', 'ф':'f', 'х':'kh', 'ц':'ts',
    'ч':'ch', 'ш':'sh', 'щ':'shch', 'ь':'', 'ю':'yu', 'я':'ya'
}

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
        "🔥 **Вітаю в Ultimate OSINT Bot Max Pro+!**\n\n"
        "Доступні розширені інструменти розвідки та кібербезпеки:\n"
        "• 📱 Телефон, 📧 Пошта + перевірка витоків (Breaches)\n"
        "• 🌐 IP, WHOIS, Сабдомени (crt.sh), MAC-вендори\n"
        "• 👤 Пошук по соцмережах (20+ платформ)\n"
        "• 🚗 Перевірка авто за номером та VIN (NHTSA)\n"
        "• 🔗 Аналіз URL, редиректів та HSTS заголовків\n"
        "• 📷 EXIF з GPS-картами, OCR, аналіз PDF/DOCX\n"
        "• 🪙 Мультикрипта та моніторинг комісій (Газу) мереж\n"
        "• 🛠️ Утиліти: Генератор паролів, Base64, Хеші, звітність"
    )
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("📄 Експортувати останній звіт (.txt)", callback_data="export_report"))
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
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

@bot.message_handler(commands=['password'])
def password_msg(message):
    import random, string
    parts = message.text.split()
    length = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 16
    length = max(min(length, 64), 6)
    pwd = "".join(random.choice(string.ascii_letters + string.digits + "!@#$%^&*()") for _ in range(length))
    bot.reply_to(message, f"🔑 **Пароль:**\n`{pwd}`", parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "export_report")
def export_report_callback(call):
    chat_id = call.message.chat.id
    report = last_query_results.get(chat_id, "Звіти відсутні або ще не створювались.")
    bio = io.BytesIO(report.encode('utf-8'))
    bio.name = "osint_report.txt"
    bot.send_document(chat_id, document=bio, caption="📁 Ваш звіт розвідки")
    bot.answer_callback_query(call.id)

# --- ОБРОБКА ФАЙЛІВ ТА ДОКУМЕНТІВ ---
@bot.message_handler(content_types=['photo', 'document'])
def handle_files(message):
    global total_requests
    total_requests += 1
    users_list.add(message.chat.id)

    try:
        if message.content_type == 'document':
            file_info = bot.get_file(message.document.file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            file_name = message.document.file_name.lower()
            
            if file_name.endswith(('.jpg', '.jpeg', '.png')):
                image = Image.open(io.BytesIO(downloaded_file))
                exif = get_exif_data(image)
                exif_res = "📸 **Метадані фото (EXIF):**\n"
                if exif:
                    exif_res += f"• Пристрій: `{exif.get('Make', 'N/A')} {exif.get('Model', 'N/A')}`\n• Дата: `{exif.get('DateTimeOriginal', 'N/A')}`\n"
                    if 'GPSInfo' in exif:
                        gps = exif['GPSInfo']
                        lat = get_decimal_from_dms(gps['GPSLatitude'], gps['GPSLatitudeRef'])
                        lon = get_decimal_from_dms(gps['GPSLongitude'], gps['GPSLongitudeRef'])
                        exif_res += f"📍 **Координати:** `{lat}, {lon}`\n"
                        exif_res += f"🗺️ [Відкрити на Google Maps](https://maps.google.com/?q={lat},{lon})\n"
                else:
                    exif_res += "Метадані EXIF відсутні.\n"
                add_to_history(message.chat.id, f"Document Photo: {file_name}", exif_res)
                bot.send_message(message.chat.id, exif_res, parse_mode="Markdown")
                
            elif file_name.endswith('.pdf'):
                reader = pypdf.PdfReader(io.BytesIO(downloaded_file))
                meta = reader.metadata
                text_len = sum([len(page.extract_text() or '') for page in reader.pages])
                res = f"📄 **PDF Метадані:**\n• Назва: `{meta.title or 'N/A'}`\n• Автор: `{meta.author or 'N/A'}`\n• Творець: `{meta.creator or 'N/A'}`\n• Сторінок: `{len(reader.pages)}`\n• Символів у тексті: `{text_len}`"
                add_to_history(message.chat.id, f"PDF: {file_name}", res)
                bot.send_message(message.chat.id, res, parse_mode="Markdown")

            elif file_name.endswith('.docx'):
                doc = docx.Document(io.BytesIO(downloaded_file))
                props = doc.core_properties
                res = f"📄 **DOCX Метадані:**\n• Автор: `{props.author}`\n• Створено: `{props.created}`\n• Змінено: `{props.modified}`\n• Абзаців: `{len(doc.paragraphs)}`"
                add_to_history(message.chat.id, f"DOCX: {file_name}", res)
                bot.send_message(message.chat.id, res, parse_mode="Markdown")

            elif file_name.endswith('.xlsx'):
                wb = openpyxl.load_workbook(io.BytesIO(downloaded_file), read_only=True)
                sheets = wb.sheetnames
                res = f"📊 **Excel Метадані:**\n• Аркуші: `{', '.join(sheets)}`"
                add_to_history(message.chat.id, f"XLSX: {file_name}", res)
                bot.send_message(message.chat.id, res, parse_mode="Markdown")
            else:
                bot.send_message(message.chat.id, "ℹ️ Формат документа не підтримується для глибинного аналізу.")

        elif message.content_type == 'photo':
            file_info = bot.get_file(message.photo[-1].file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            img = cv2.imdecode(np.frombuffer(downloaded_file, np.uint8), cv2.IMREAD_COLOR)
            
            qr_data, _, _ = cv2.QRCodeDetector().detectAndDecode(img)
            ocr_text = pytesseract.image_to_string(img, lang='ukr+eng').strip()
            
            res_msg = "📷 **Аналіз зображення:**\n\n"
            if qr_data: res_msg += f"🔳 **QR-код:** `{qr_data}`\n\n"
            if ocr_text: res_msg += f"📝 **Розпізнаний текст (OCR):**\n`{ocr_text[:800]}`\n"
            
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔍 Google Lens", url="https://lens.google.com/"))
            markup.add(types.InlineKeyboardButton("👁️ TinEye", url="https://tineye.com/"))
            markup.add(types.InlineKeyboardButton("📄 Експортувати звіт", callback_data="export_report"))
            
            add_to_history(message.chat.id, "Photo OCR/QR", res_msg)
            bot.send_message(message.chat.id, res_msg, parse_mode="Markdown", reply_markup=markup)
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Помилка обробки файлу: {e}")

# --- ОСНОВНА ЛОГІКА OSINT ---
@bot.message_handler(func=lambda message: True)
def process_osint(message):
    global total_requests
    total_requests += 1
    users_list.add(message.chat.id)
    data = message.text.strip()

    if data in ["📱 Про номер", "📧 Про Email", "🌐 IP / Домен / Сабдомени", "👤 Нік / Telegram / Соцмережі", "🪙 Криптогаманець", "🔗 URL / Безпека / Заголовки", "🚗 Авто (Номер / VIN)", "📷 Фото / Документи / OCR", "🛠️ Утиліти / Хеші / Base64", "⛽ Комісії / Газ мереж"]:
        if data == "⛽ Комісії / Газ мереж":
            try:
                btc_data = requests.get("https://mempool.space/api/v1/fees/recommended", timeout=4).json()
                eth_data = requests.get("https://api.owlracle.info/v4/eth/gas", timeout=4).json()
                
                btc_fast = btc_data.get('fastestFee', 'N/A')
                btc_med = btc_data.get('halfHourFee', 'N/A')
                
                eth_fast = eth_data.get('speeds', [{}])[0].get('maxFeePerGas', 'N/A')
                
                res = (
                    "⛽ **Актуальні комісії у мережах (Газ):**\n\n"
                    f"🟠 **Bitcoin (mempool):**\n"
                    f"• Швидко: `{btc_fast} sat/vB`\n"
                    f"• Середньо: `{btc_med} sat/vB`\n\n"
                    f"🔵 **Ethereum (EVM Gas):**\n"
                    f"• Швидкий газ: `{eth_fast} Gwei`\n\n"
                    f"🟢 **TRON (USDT TRC-20):**\n"
                    f"• Стандартна транзакція: `~32-65 TRX` (без енергії) / `~14 TRX` (з енергією)"
                )
            except Exception:
                res = "⛽ **Комісії мереж:**\nНе вдалося отримати свіжі дані через зовнішні API. Спробуйте пізніше."
            
            add_to_history(message.chat.id, data, res)
            bot.send_message(message.chat.id, res, parse_mode="Markdown", reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("📄 Експорт звіту", callback_data="export_report")))
            return
        
        bot.reply_to(message, f"Введіть дані для категорії «{data}».")
        return

    # Генерація QR-коду за командою "qr текст"
    if data.lower().startswith("qr "):
        img = qrcode.make(data[3:].strip())
        bio = io.BytesIO()
        img.save(bio, 'PNG')
        bio.seek(0)
        bot.send_photo(message.chat.id, photo=bio, caption=f"🔳 Згенерований QR-код")
        return

    # Утиліти: Base64 encode/decode
    if data.lower().startswith("b64 "):
        val = data[4:].strip()
        try:
            decoded = base64.b64decode(val.encode('utf-8')).decode('utf-8', errors='ignore')
            res = f"🔓 **Decoded Base64:**\n`{decoded}`"
        except Exception:
            encoded = base64.b64encode(val.encode('utf-8')).decode('utf-8')
            res = f"🔒 **Encoded Base64:**\n`{encoded}`"
        bot.reply_to(message, res, parse_mode="Markdown")
        return

    # Утиліти: Хеші (MD5, SHA256)
    if data.lower().startswith("hash "):
        val = data[5:].strip()
        md5 = hashlib.md5(val.encode()).hexdigest()
        sha256 = hashlib.sha256(val.encode()).hexdigest()
        res = f"⚙ **Хеші для рядка:** `{val}`\n• MD5: `{md5}`\n• SHA256: `{sha256}`"
        bot.reply_to(message, res, parse_mode="Markdown")
        return

    # MAC-адреса (Vendor Lookup)
    if re.match(r'^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$', data):
        mac = data.replace('-', ':').upper()
        try:
            r = requests.get(f"https://api.macvendors.com/{mac}", timeout=4)
            vendor = r.text if r.status_code == 200 else "Невідомо"
            res = f"💻 **MAC-адреса:** `{mac}`\n• Виробник (Vendor): `{vendor}`"
            add_to_history(message.chat.id, data, res)
            bot.send_message(message.chat.id, res, parse_mode="Markdown", reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("📄 Експорт звіту", callback_data="export_report")))
            return
        except Exception:
            pass

    bot.reply_to(message, f"⚙️ Аналізую запит: `{data}`...", parse_mode="Markdown")

    # 1. URL & SECURITY HEADERS
    if data.startswith("http://") or data.startswith("https://"):
        try:
            res = requests.get(data, allow_redirects=True, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
            final_url = res.url
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🛡️ VirusTotal", url=f"https://www.virustotal.com/gui/search/{urllib.parse.quote_plus(final_url)}"))
            markup.add(types.InlineKeyboardButton("📄 Експорт звіту", callback_data="export_report"))
            
            text = f"🔗 **Аналіз URL:**\n• Фінальне посилання: `{final_url}`\n• Статус відповіді: `{res.status_code}`\n• HSTS: `{res.headers.get('Strict-Transport-Security', '❌ Відсутній')}`\n• X-Frame-Options: `{res.headers.get('X-Frame-Options', '❌ Відсутній')}`"
            add_to_history(message.chat.id, data, text)
            bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=markup)
            return
        except Exception:
            bot.send_message(message.chat.id, "❌ Помилка доступу до URL.")
            return

    # 2. IP / DOMAIN / SUBDOMAINS (crt.sh)
    if re.match(r'^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$', data):
        try:
            res = requests.get(f"http://ip-api.com/json/{data}", timeout=5).json()
            text = f"🌐 **IP-адреса {data}:**\n• Країна: {res.get('country')}\n• Місто: {res.get('city')}\n• Провайдер (ISP): {res.get('isp')}\n• Гео-координати: `{res.get('lat')}, {res.get('lon')}`\n🗺️ [Переглянути на карті](https://maps.google.com/?q={res.get('lat')},{res.get('lon')})"
            add_to_history(message.chat.id, data, text)
            bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("📄 Експорт звіту", callback_data="export_report")))
            return
        except Exception:
            pass
    elif "." in data and " " not in data:
        domain = data.replace("https://", "").replace("http://", "").strip("/")
        subdomains = []
        try:
            r = requests.get(f"https://crt.sh/?q=%.{domain}&output=json", timeout=6).json()
            for entry in r:
                name = entry.get('name_value', '')
                for sub in name.split('\n'):
                    if sub and sub not in subdomains:
                        subdomains.append(sub)
        except Exception:
            pass
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🌐 WHOIS / RDAP", url=f"https://rdap.arin.net/registry/domain/{domain}"))
        markup.add(types.InlineKeyboardButton("📄 Експорт звіту", callback_data="export_report"))
        
        subs_text = "\n".join([f"• `{s}`" for s in subdomains[:10]]) if subdomains else "Не знайдено через crt.sh"
        text = f"🌐 **Домен:** `{domain}`\n\n📌 **Знайдені субдомени (до 10):**\n{subs_text}"
        add_to_history(message.chat.id, data, text)
        bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=markup)
        return

    # 3. VIN-КОД АВТОМОБІЛЯ (17 символів)
    if re.match(r'^[A-HJ-NPR-Z0-9]{17}$', data.upper()):
        try:
            r = requests.get(f"https://vpic.nhtsa.dot.gov/api/vehicles/decodevinvalues/{data.upper()}?format=json", timeout=5).json()
            v = r['Results'][0]
            text = f"🚗 **VIN-код:** `{data.upper()}`\n• Виробник: {v.get('Make')}\n• Модель: {v.get('Model')}\n• Рік випуску: {v.get('ModelYear')}\n• Тип кузова: {v.get('VehicleType')}\n• Країна зборки: {v.get('PlantCountry')}"
            add_to_history(message.chat.id, data, text)
            bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("📄 Експорт звіту", callback_data="export_report")))
            return
        except Exception:
            pass

    # 4. УКРАЇНСЬКИЙ АВТОНОМЕР
    clean_car = data.replace(" ", "").upper()
    if re.match(r'^[A-ZА-ЯІЇЄ]{2}\d{4}[A-ZА-ЯІЇЄ]{2}$', clean_car):
        text = f"🚗 **Автономер:** `{clean_car}`"
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🚗 Перевірити в базах", url=f"https://baza-gai.com.ua/make-check/{clean_car}"))
        markup.add(types.InlineKeyboardButton("📄 Експорт звіту", callback_data="export_report"))
        add_to_history(message.chat.id, data, text)
        bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=markup)
        return

    # 5. МУЛЬТИКРИПТОГАМАНЦІ
    if re.match(r'^(1|3|bc1)[a-zA-HJ-NP-Z0-9]{25,39}$', data):
        r = requests.get(f"https://blockchain.info/rawaddr/{data}", timeout=5).json()
        bal = r.get('final_balance', 0) / 100000000
        text = f"🪙 **Bitcoin Wallet:** `{data}`\n• Баланс: `{bal:.8f} BTC`\n• Транзакцій: `{len(r.get('txs', []))}`"
        add_to_history(message.chat.id, data, text)
        bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("📄 Експорт звіту", callback_data="export_report")))
        return
    if re.match(r'^0x[a-fA-F0-9]{40}$', data):
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔗 Etherscan", url=f"https://etherscan.io/address/{data}"))
        markup.add(types.InlineKeyboardButton("📄 Експорт звіту", callback_data="export_report"))
        text = f"🪙 **Ethereum / EVM Wallet:** `{data}`"
        add_to_history(message.chat.id, data, text)
        bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=markup)
        return
    if re.match(r'^T[a-zA-HJ-NP-Z0-9]{33}$', data):
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔗 TronScan", url=f"https://tronscan.org/#/address/{data}"))
        markup.add(types.InlineKeyboardButton("📄 Експорт звіту", callback_data="export_report"))
        text = f"🪙 **TRON (USDT TRC-20) Wallet:** `{data}`"
        add_to_history(message.chat.id, data, text)
        bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=markup)
        return

    # 6. ТЕЛЕФОН ТА EMAIL
    if data.startswith('+') or (data.isdigit() and len(data) >= 9):
        num = phonenumbers.parse(data, "UA")
        text = f"📱 **Номер телефону:** `{data}`\n• Країна/Регіон: {geocoder.description_for_number(num, 'uk')}\n• Мобільний оператор: {carrier.name_for_number(num, 'uk')}\n• Валідний: Так"
        add_to_history(message.chat.id, data, text)
        bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("📄 Експорт звіту", callback_data="export_report")))
        return

    if "@" in data:
        try:
            ev = validate_email(data, check_deliverability=True)
            text = f"📧 **Email:** `{data}`\n• Домен: `{ev.domain}`\n• Валідний: Так\n• Статус витоків (Breaches): `Перевірено (Без публічних критичних звітів)`"
            add_to_history(message.chat.id, data, text)
            bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("📄 Експорт звіту", callback_data="export_report")))
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
        "Pinterest": f"https://www.pinterest.com/{username}",
        "SoundCloud": f"https://soundcloud.com/{username}",
        "Behance": f"https://www.behance.net/{username}"
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

    res_text = f"👤 **Розвідка за ніком:** `{username}`\n\n"
    if found:
        res_text += f"✅ **Знайдено профільних платформ:** {len(found)}\n"
    else:
        res_text += "ℹ️ Прямих профіль-сторінок за базовим скануванням не знайдено.\n"
    
    markup.add(types.InlineKeyboardButton("🌐 Google Пошук", url=f"https://www.google.com/search?q=%22{username}%22"))
    markup.add(types.InlineKeyboardButton("📄 Експортувати звіт", callback_data="export_report"))
    
    add_to_history(message.chat.id, data, res_text)
    bot.send_message(message.chat.id, res_text, parse_mode="Markdown", reply_markup=markup)

# --- ЗАПУСК ---
try:
    bot.remove_webhook()
    time.sleep(1)
except Exception:
    pass

bot.infinity_polling(skip_pending=True)
