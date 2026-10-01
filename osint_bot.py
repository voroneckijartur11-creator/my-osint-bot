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
ADMIN_ID = 0  # Вкажіть ваш Telegram ID

bot = telebot.TeleBot(TOKEN)

# База даних в пам'яті
users_list = set()
total_requests = 0
user_history = {}  # {chat_id: [list of recent queries]}

# --- МЕНЮ БОТА ---
def get_main_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn1 = types.KeyboardButton("📱 Про номер")
    btn2 = types.KeyboardButton("📧 Про Email")
    btn3 = types.KeyboardButton("🌐 IP / Домен / WHOIS")
    btn4 = types.KeyboardButton("👤 Нік / Соцмережі / Dorks")
    btn5 = types.KeyboardButton("🪙 Криптогаманець")
    btn6 = types.KeyboardButton("🔗 URL / Безпека / Заголовки")
    btn7 = types.KeyboardButton("🔤 Хеш / Base64 / Пароль")
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

# --- ТРАНСЛІТЕРАЦІЯ УКРАЇНСЬКИХ ІМЕН ---
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

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ EXIF ---
def get_decimal_from_dms(dms, ref):
    degrees = dms[0]
    minutes = dms[1]
    seconds = dms[2]
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
                gps_data = {}
                for t in value:
                    sub_tag = GPSTAGS.get(t, t)
                    gps_data[sub_tag] = value[t]
                exif_data[decoded] = gps_data
            else:
                exif_data[decoded] = value
    return exif_data

# --- КОМАНДЫ ---
@bot.message_handler(commands=['start'])
def start_msg(message):
    users_list.add(message.chat.id)
    welcome_text = (
        "👋 **Вітаю в Ultimate OSINT Bot (Max Edition)!**\n\n"
        "Доступні потужні інструменти розвідки та утиліти:\n"
        "• 📱 **Телефон / 📧 Email / 🌐 IP / Домен**\n"
        "• 👤 **Пошук ніка по 20+ соцмережах (Sherlock)**\n"
        "• 🔗 **Аналіз URL, редиректів та заголовків безпеки**\n"
        "• 📷 **Зчитування EXIF, QR та OCR (розпізнавання тексту з фото)**\n"
        "• 👁️ **Пошук джерела фото (Google Lens / TinEye)**\n"
        "• 🔤 **Генератор паролів (`/password`) та транслітерація**\n"
        "• 📄 **Автоматичне збереження звітів у файли**"
    )
    bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown", reply_markup=get_main_keyboard())

@bot.message_handler(commands=['stats'])
def stats_msg(message):
    stats_text = (
        f"📊 **Статистика бота:**\n"
        f"• Унікальних користувачів: {len(users_list)}\n"
        f"• Оброблено запитів: {total_requests}"
    )
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
    import random
    import string
    parts = message.text.split()
    length = 16
    if len(parts) > 1 and parts[1].isdigit():
        length = max(min(int(parts[1]), 64), 6)
    
    chars = string.ascii_letters + string.digits + "!@#$%^&*()"
    pwd = "".join(random.choice(chars) for _ in range(length))
    bot.reply_to(message, f"🔑 **Згенерований надійний пароль:**\n`{pwd}`", parse_mode="Markdown")

# --- ОБРАБОТКА ФАЙЛОВ (EXIF, OCR, QR, ЛІНЗИ) ---
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
                make = exif.get('Make', 'N/A')
                model = exif.get('Model', 'N/A')
                date = exif.get('DateTimeOriginal', 'N/A')
                exif_res += f"• Пристрій: `{make} {model}`\n• Дата зйомки: `{date}`\n"
                
                if 'GPSInfo' in exif:
                    gps_info = exif['GPSInfo']
                    try:
                        lat = get_decimal_from_dms(gps_info['GPSLatitude'], gps_info['GPSLatitudeRef'])
                        lon = get_decimal_from_dms(gps_info['GPSLongitude'], gps_info['GPSLongitudeRef'])
                        maps_url = f"https://www.google.com/maps/place/{lat},{lon}"
                        exif_res += f"📍 **GPS Координати:** `{lat}, {lon}`\n🔗 [Відкрити на Google Maps]({maps_url})\n"
                    except Exception:
                        exif_res += "📍 GPS дані пошкоджені або відсутні.\n"
            else:
                exif_res += "Метадані відсутні або очищені.\n"
            
            bot.send_message(message.chat.id, exif_res, parse_mode="Markdown", disable_web_page_preview=True)

        elif message.content_type == 'photo':
            file_info = bot.get_file(message.photo[-1].file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            
            nparr = np.frombuffer(downloaded_file, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            # 1. Перевірка QR
            detector = cv2.QRCodeDetector()
            qr_data, _, _ = detector.detectAndDecode(img)
            
            # 2. Розпізнавання тексту (OCR)
            ocr_text = pytesseract.image_to_string(img, lang='ukr+eng').strip()
            
            res_msg = "📷 **Аналіз зображення:**\n\n"
            if qr_data:
                res_msg += f"🔳 **QR-код:** `{qr_data}`\n\n"
            if ocr_text:
                res_msg += f"📝 **Розпізнаний текст (OCR):**\n`{ocr_text[:800]}`\n\n"
            
            res_msg += "👁️ **Пошук джерела фото в мережі:**\n"
            res_msg += "• [Шукати через Google Lens](https://lens.google.com/)\n"
            res_msg += "• [Шукати через TinEye](https://tineye.com/)"
            
            # Експорт результату у файл
            bio = io.BytesIO(res_msg.encode('utf-8'))
            bio.name = "image_analysis_report.txt"
            bio.seek(0)
            bot.send_document(message.chat.id, document=bio, caption=res_msg, parse_mode="Markdown")
            
    except Exception as e:
        bot.send_message(message.chat.id, "❌ Не вдалося обробити файл.")

# --- ОСНОВНАЯ ЛОГИКА ---
@bot.message_handler(func=lambda message: True)
def process_osint(message):
    global total_requests
    total_requests += 1
    users_list.add(message.chat.id)
    data = message.text.strip()
    add_to_history(message.chat.id, data)

    menu_buttons = [
        "📱 Про номер", "📧 Про Email", "🌐 IP / Домен / WHOIS",
        "👤 Нік / Соцмережі / Dorks", "🪙 Криптогаманець",
        "🔗 URL / Безпека / Заголовки", "🔤 Хеш / Base64 / Пароль", "📷 Фото / OCR / EXIF / QR"
    ]
    if data in menu_buttons:
        bot.reply_to(message, f"Введіть дані для категорії «{data}». Або скористайтесь командою `/password [довжина]` для генерації пароля.")
        return

    if data.lower().startswith("qr "):
        text_to_qr = data[3:].strip()
        img = qrcode.make(text_to_qr)
        bio = io.BytesIO()
        img.save(bio, 'PNG')
        bio.seek(0)
        bot.send_photo(message.chat.id, photo=bio, caption=f"🔳 QR-код для: `{text_to_qr}`", parse_mode="Markdown")
        return

    bot.reply_to(message, f"⚙️ Починаю поглиблений аналіз для: `{data}`...", parse_mode="Markdown")

    # 1. BASE64 / ХЕШИ
    if len(data) % 4 == 0 and re.match(r'^[A-Za-z0-9+/]+={0,2}$', data) and len(data) > 8:
        try:
            import base64
            decoded = base64.b64decode(data).decode('utf-8')
            if decoded.isprintable():
                bot.send_message(message.chat.id, f"🔤 **Розшифровано з Base64:**\n`{decoded}`", parse_mode="Markdown")
                return
        except Exception:
            pass

    if re.match(r'^[a-fA-F0-9]{32}$', data):
        bot.send_message(message.chat.id, f"🔤 **Тип хешу:** `MD5`\n💡 Перевірте на CrackStation.", parse_mode="Markdown")
        return
    elif re.match(r'^[a-fA-F0-9]{40}$', data) and not data.startswith("0x"):
        bot.send_message(message.chat.id, f"🔤 **Тип хешу:** `SHA-1`", parse_mode="Markdown")
        return
    elif re.match(r'^[a-fA-F0-9]{64}$', data):
        bot.send_message(message.chat.id, f"🔤 **Тип хешу:** `SHA-256`", parse_mode="Markdown")
        return

    # 2. URL & SECURITY HEADERS ANALYZER
    if data.startswith("http://") or data.startswith("https://"):
        try:
            res = requests.get(data, allow_redirects=True, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
            history = [resp.url for resp in res.history]
            final_url = res.url
            server = res.headers.get('Server', 'Приховано')
            
            # Заголовки безпеки
            hsts = res.headers.get('Strict-Transport-Security', '❌ Відсутній')
            csp = res.headers.get('Content-Security-Policy', '❌ Відсутній')
            xfo = res.headers.get('X-Frame-Options', '❌ Відсутній')

            text = f"🔗 **Аналіз URL та Безпеки:**\n• Початкове: `{data}`\n"
            if history:
                text += f"• Редиректи ({len(history)}):\n" + "\n".join([f"  ↳ `{u}`" for u in history]) + "\n"
            text += f"• Фінальне: `{final_url}`\n"
            text += f"• Статус: `{res.status_code}` | Сервер: `{server}`\n\n"
            text += f"🛡️ **Заголовки безпеки:**\n• HSTS: `{hsts}`\n• X-Frame-Options: `{xfo}`\n• CSP: `{csp[:30]}...`\n\n"
            text += f"🔍 [Перевірити на VirusTotal](https://www.virustotal.com/gui/search/{urllib.parse.quote_plus(final_url)})"
            
            # Експорт у звіт
            bio = io.BytesIO(text.encode('utf-8'))
            bio.name = "url_security_report.txt"
            bio.seek(0)
            bot.send_document(message.chat.id, document=bio, caption=text, parse_mode="Markdown", disable_web_page_preview=True)
            return
        except Exception:
            bot.send_message(message.chat.id, "❌ Не вдалося отримати доступ за посиланням.")
            return

    # 3. CRYPTO
    if re.match(r'^(1|3|bc1)[a-zA-HJ-NP-Z0-9]{25,39}$', data):
        try:
            r = requests.get(f"https://blockchain.info/rawaddr/{data}", timeout=5).json()
            balance = r.get('final_balance', 0) / 100000000
            tx_count = r.get('n_tx', 0)
            text = f"🪙 **Bitcoin Wallet:** `{data}`\n• Баланс: `{balance:.8f} BTC`\n• Транзакцій: `{tx_count}`"
            bot.send_message(message.chat.id, text, parse_mode="Markdown")
            return
        except Exception:
            pass

    if re.match(r'^0x[a-fA-F0-9]{40}$', data):
        text = f"🪙 **Ethereum Wallet:** `{data}`\n🔗 [Etherscan](https://etherscan.io/address/{data})"
        bot.send_message(message.chat.id, text, parse_mode="Markdown", disable_web_page_preview=True)
        return

    if re.match(r'^T[a-zA-Z0-9]{33}$', data):
        text = f"🪙 **Tron Wallet:** `{data}`\n🔗 [TronScan](https://tronscan.org/#/address/{data})"
        bot.send_message(message.chat.id, text, parse_mode="Markdown", disable_web_page_preview=True)
        return

    # 4. IP
    if re.match(r'^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$', data):
        try:
            res = requests.get(f"http://ip-api.com/json/{data}", timeout=5).json()
            if res.get("status") == "success":
                text = f"🌐 **IP {data}:**\n• Країна: {res.get('country')}\n• Місто: {res.get('city')}\n• Провайдер: {res.get('isp')}\n• Координати: `{res.get('lat')}, {res.get('lon')}`"
            else:
                text = "❌ Помилка IP."
            bot.send_message(message.chat.id, text, parse_mode="Markdown")
            return
        except Exception:
            pass

    # 5. DOMAIN
    if re.match(r'^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', data):
        try:
            res = requests.get(f"https://rdap.org/domain/{data}", timeout=5).json()
            name = res.get('ldhName', data)
            text = f"🌐 **Домен:** `{name}`\n🔗 [WHOIS Деталі](https://whois.domaintools.com/{data})"
            bot.send_message(message.chat.id, text, parse_mode="Markdown", disable_web_page_preview=True)
            return
        except Exception:
            pass

    # 6. CAR NUMBER
    clean_car = data.replace(" ", "").upper()
    if re.match(r'^[A-ZА-ЯІЇЄ]{2}\d{4}[A-ZА-ЯІЇЄ]{2}$', clean_car):
        try:
            res = requests.get(f"https://baza-gai.com.ua/make-check/{clean_car}", headers={"Accept": "application/json"}, timeout=5)
            if res.status_code == 200:
                c = res.json()
                text = f"🚗 **Автономер {clean_car}:**\n• Модель: {c.get('vendor')} {c.get('model')}\n• Рік: {c.get('year')}"
            else:
                text = f"🚗 Номер `{clean_car}` валідний."
            bot.send_message(message.chat.id, text, parse_mode="Markdown")
            return
        except Exception:
            pass

    # 7. PHONE
    if data.startswith('+') or (data.isdigit() and len(data) >= 9):
        try:
            parsed_num = phonenumbers.parse(data, "UA")
            country = geocoder.description_for_number(parsed_num, "uk")
            operator = carrier.name_for_number(parsed_num, "uk")
            res = f"📱 **Номер {data}:**\n• Регіон: {country}\n• Оператор: {operator}"
            bot.send_message(message.chat.id, res, parse_mode="Markdown")
            return
        except Exception:
            pass

    # 8. EMAIL
    if "@" in data:
        try:
            email_info = validate_email(data, check_deliverability=True)
            bot.send_message(message.chat.id, f"📧 **Email {data}:**\n• Домен: `{email_info.domain}`\n• Статус: Валідний", parse_mode="Markdown")
            return
        except EmailNotValidError:
            bot.send_message(message.chat.id, f"❌ Email недійсний.", parse_mode="Markdown")
            return
        except Exception:
            pass

    # 9. USER GENERATOR & TRANSLITERATION
    if " " in data and not data.startswith("@"):
        parts = data.split()
        if len(parts) >= 2:
            fn, ln = parts[0], parts[1]
            trans_res = f"🔤 **Транслітерація для паспорта:**\n• `{transliterate(fn)} {transliterate(ln)}`\n\n"
            emails = [f"{fn.lower()}.{ln.lower()}@gmail.com", f"{fn.lower()}{ln.lower()}@gmail.com"]
            usernames = [f"{fn.lower()}_{ln.lower()}", f"{fn.lower()}.{ln.lower()}"]
            
            trans_res += "🎯 **Варіанти Email та Нікнеймів:**\n" + "\n".join([f"• `{e}`" for e in emails + usernames])
            bot.send_message(message.chat.id, trans_res, parse_mode="Markdown")
            return

    # 10. MULTI-PLATFORM SOCIAL SEARCH (SHERLOCK-STYLE)
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
    found = []
    for name, url in platforms.items():
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            if requests.get(url, timeout=2, headers=headers).status_code == 200:
                found.append(f"• [{name}]({url})")
        except Exception:
            pass

    dork_all = f"https://www.google.com/search?q=%22{username}%22"
    dork_docs = f"https://www.google.com/search?q=%22{username}%22+filetype:pdf+OR+filetype:doc"

    res_text = f"👤 **Широкий пошук акаунтів:** `{username}`\n\n"
    if found:
        res_text += "✅ **Знайдено на платформах:**\n" + "\n".join(found) + "\n\n"
    else:
        res_text += "ℹ️ Прямих відкритих профіль-сторінок не знайдено.\n\n"
        
    res_text += f"🔗 [Google Пошук]({dork_all})\n📄 [Пошук у документах PDF/DOC]({dork_docs})"
    
    # Експорт повного звіту
    bio = io.BytesIO(res_text.encode('utf-8'))
    bio.name = f"osint_{username}_report.txt"
    bio.seek(0)
    bot.send_document(message.chat.id, document=bio, caption=res_text, parse_mode="Markdown", disable_web_page_preview=True)

# --- ЗАПУСК ---
try:
    bot.remove_webhook()
    time.sleep(1)
except Exception:
    pass

bot.infinity_polling(skip_pending=True)
