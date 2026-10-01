import os
import re
import io
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

# --- ВЕБ-СЕРВЕР ДЛЯ РЕНДЕРУ (HEALTH CHECK) ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def run_health_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    server.serve_forever()

threading.Thread(target=run_health_server, daemon=True).start()

# --- ІНІЦІАЛІЗАЦІЯ БОТА ---
TOKEN = "8747134357:AAHqkHA7H7fU_WT5yf0cra5XUzih_l58Owk"
ADMIN_ID = 0  # Вкажіть свій Telegram ID, щоб мати доступ до /stats та /broadcast

bot = telebot.TeleBot(TOKEN)

# База користувачів у пам'яті
users_list = set()
total_requests = 0

# --- МЕНЮ БОТА ---
def get_main_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn1 = types.KeyboardButton("📱 Про номер")
    btn2 = types.KeyboardButton("📧 Про Email")
    btn3 = types.KeyboardButton("🌐 IP / Домен / WHOIS")
    btn4 = types.KeyboardButton("👤 Нік / Dorks / Варіанти")
    btn5 = types.KeyboardButton("🪙 Криптогаманець")
    btn6 = types.KeyboardButton("🔗 Розпаковка URL / Безпека")
    btn7 = types.KeyboardButton("🔤 Декодер Хешів / Base64")
    btn8 = types.KeyboardButton("📷 Інфо / QR / EXIF")
    
    keyboard.add(btn1, btn2)
    keyboard.add(btn3, btn4)
    keyboard.add(btn5, btn6)
    keyboard.add(btn7, btn8)
    return keyboard

# --- ДОПОМІЖНІ ФУНКЦІЇ EXIF ---
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

# --- ОБРОБКА КОМАНДИ /start ---
@bot.message_handler(commands=['start'])
def start_msg(message):
    users_list.add(message.chat.id)
    welcome_text = (
        "👋 **Вітаю в Ultimate OSINT Bot!**\n\n"
        "Можливості аналізу даних:\n"
        "• 📱 **Номер телефону** (`+380...`)\n"
        "• 📧 **Email** (`example@gmail.com`)\n"
        "• 🌐 **IP / Домен** (`8.8.8.8` або `github.com`)\n"
        "• 🔗 **Скорочені / Підозрілі посилання** (`bit.ly/...`)\n"
        "• 🚗 **Автономер України** (`AA1234BB`)\n"
        "• 👤 **Нікнейм / Ім'я** (`@username` або `Іван Іванов`)\n"
        "• 🔤 **Декодер Хешів/Base64** (`SGVsbG8=` або `MD5`)\n"
        "• 🪙 **Crypto Wallet** (Bitcoin, Ethereum, Tron/USDT)\n"
        "• 📷 **Фото без стиснення (як файл)** — для EXIF/GPS\n"
        "• 🔳 **Фото з QR-кодом** або `qr ВашТекст` — для генерації/сканування"
    )
    bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown", reply_markup=get_main_keyboard())

# --- АДМІН-СТАТИСТИКА /stats ---
@bot.message_handler(commands=['stats'])
def stats_msg(message):
    stats_text = (
        f"📊 **Статистика бота:**\n"
        f"• Унікальних користувачів: {len(users_list)}\n"
        f"• Оброблено запитів: {total_requests}"
    )
    bot.send_message(message.chat.id, stats_text, parse_mode="Markdown")

# --- АДМІН-РОЗСИЛКА /broadcast ---
@bot.message_handler(commands=['broadcast'])
def broadcast_msg(message):
    if ADMIN_ID != 0 and message.chat.id != ADMIN_ID:
        bot.reply_to(message, "❌ У вас немає прав для виконання цієї команди.")
        return
    
    msg_text = message.text.replace("/broadcast", "").strip()
    if not msg_text:
        bot.reply_to(message, "⚠️ Вкажіть текст для розсилки. Приклад:\n`/broadcast Всім привіт! Бот оновлено.`", parse_mode="Markdown")
        return

    count = 0
    for user_id in users_list:
        try:
            bot.send_message(user_id, f"📢 **Повідомлення від адміністратора:**\n\n{msg_text}", parse_mode="Markdown")
            count += 1
        except Exception:
            pass
    bot.send_message(message.chat.id, f"✅ Розсилку завершено! Доставлено: {count} користувачам.")

# --- ОБРОБКА ФОТО ТА ДОКУМЕНТІВ (EXIF & QR) ---
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
            detector = cv2.QRCodeDetector()
            data, bbox, _ = detector.detectAndDecode(img)
            
            if data:
                bot.send_message(message.chat.id, f"🔳 **Розшифровка QR-коду:**\n`{data}`", parse_mode="Markdown")
            else:
                bot.send_message(message.chat.id, "ℹ️ QR-код на зображенні не виявлено. Для зчитування EXIF-метаданих надсилайте фото як документ (файл).")
    except Exception:
        bot.send_message(message.chat.id, "❌ Не вдалося обробити файл.")

# --- ОСНОВНА ЛОГІКА ТЕКСТОВИХ ЗАПИТІВ ---
@bot.message_handler(func=lambda message: True)
def process_osint(message):
    global total_requests
    total_requests += 1
    users_list.add(message.chat.id)
    data = message.text.strip()

    # Підказки для кнопок меню
    menu_buttons = [
        "📱 Про номер", "📧 Про Email", "🌐 IP / Домен / WHOIS",
        "👤 Нік / Dorks / Варіанти", "🪙 Криптогаманець",
        "🔗 Розпаковка URL / Безпека", "🔤 Декодер Хешів / Base64", "📷 Інфо / QR / EXIF"
    ]
    if data in menu_buttons:
        bot.reply_to(message, f"Введіть відповідні дані для категорії «{data}».")
        return

    # Генерація QR-коду
    if data.lower().startswith("qr "):
        text_to_qr = data[3:].strip()
        img = qrcode.make(text_to_qr)
        bio = io.BytesIO()
        img.save(bio, 'PNG')
        bio.seek(0)
        bot.send_photo(message.chat.id, photo=bio, caption=f"🔳 QR-код для: `{text_to_qr}`", parse_mode="Markdown")
        return

    bot.reply_to(message, f"⚙️ Починаю аналіз для: `{data}`...", parse_mode="Markdown")

    # 1. ДЕКОДЕР BASE64 ТА ХЕШІВ
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
        bot.send_message(message.chat.id, f"🔤 **Тип хешу:** `MD5`\n💡 Скористайтесь сервісом CrackStation для підбору значення.", parse_mode="Markdown")
        return
    elif re.match(r'^[a-fA-F0-9]{40}$', data) and not data.startswith("0x"):
        bot.send_message(message.chat.id, f"🔤 **Тип хешу:** `SHA-1`", parse_mode="Markdown")
        return
    elif re.match(r'^[a-fA-F0-9]{64}$', data):
        bot.send_message(message.chat.id, f"🔤 **Тип хешу:** `SHA-256`", parse_mode="Markdown")
        return

    # 2. РОЗПАКУВАННЯ ПОСИЛАНЬ ТА АНАЛІЗ HTTP/SSL
    if data.startswith("http://") or data.startswith("https://"):
        try:
            res = requests.get(data, allow_redirects=True, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
            history = [resp.url for resp in res.history]
            final_url = res.url
            
            headers = res.headers
            server = headers.get('Server', 'Приховано')
            
            text = f"🔗 **Аналіз URL:**\n• Початкове посилання: `{data}`\n"
            if history:
                text += f"• Редиректи ({len(history)}):\n" + "\n".join([f"  ↳ `{u}`" for u in history]) + "\n"
            text += f"• Фінальне посилання: `{final_url}`\n"
            text += f"• Код відповіді: `{res.status_code}`\n"
            text += f"• Веб-сервер: `{server}`\n\n"
            text += f"🛡️ [Перевірити на VirusTotal](https://www.virustotal.com/gui/search/{urllib.parse.quote_plus(final_url)})"
            
            bot.send_message(message.chat.id, text, parse_mode="Markdown", disable_web_page_preview=True)
            return
        except Exception:
            bot.send_message(message.chat.id, "❌ Не вдалося отримати доступ за цим посиланням.")
            return

    # 3. КРИПТОГАМАНЦІ
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
        text = f"🪙 **Ethereum/ERC20 Wallet:** `{data}`\n🔗 [Переглянути на Etherscan](https://etherscan.io/address/{data})"
        bot.send_message(message.chat.id, text, parse_mode="Markdown", disable_web_page_preview=True)
        return

    if re.match(r'^T[a-zA-Z0-9]{33}$', data):
        text = f"🪙 **Tron/TRC20 Wallet:** `{data}`\n🔗 [Переглянути на TronScan](https://tronscan.org/#/address/{data})"
        bot.send_message(message.chat.id, text, parse_mode="Markdown", disable_web_page_preview=True)
        return

    # 4. IP-АДРЕСА
    ip_pattern = r'^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$'
    if re.match(ip_pattern, data):
        try:
            res = requests.get(f"http://ip-api.com/json/{data}", timeout=5).json()
            if res.get("status") == "success":
                text = f"🌐 **IP {data}:**\n• Країна: {res.get('country')}\n• Місто: {res.get('city')}\n• Провайдер: {res.get('isp')}\n• Координати: `{res.get('lat')}, {res.get('lon')}`"
            else:
                text = "❌ Помилка отримання даних IP."
            bot.send_message(message.chat.id, text, parse_mode="Markdown")
            return
        except Exception:
            pass

    # 5. ДОМЕН ТА WHOIS
    if re.match(r'^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', data):
        try:
            res = requests.get(f"https://rdap.org/domain/{data}", timeout=5).json()
            name = res.get('ldhName', data)
            events = res.get('events', [])
            reg_date = "N/A"
            for ev in events:
                if ev.get('eventAction') == 'registration':
                    reg_date = ev.get('eventDate', 'N/A')[:10]
            
            text = f"🌐 **Домен:** `{name}`\n• Дата реєстрації: `{reg_date}`\n"
            text += f"🔗 [Переглянути детальний WHOIS](https://whois.domaintools.com/{data})"
            bot.send_message(message.chat.id, text, parse_mode="Markdown", disable_web_page_preview=True)
            return
        except Exception:
            pass

    # 6. АВТОНОМЕР УКРАЇНИ
    clean_car = data.replace(" ", "").upper()
    if re.match(r'^[A-ZА-ЯІЇЄ]{2}\d{4}[A-ZА-ЯІЇЄ]{2}$', clean_car):
        try:
            res = requests.get(f"https://baza-gai.com.ua/make-check/{clean_car}", headers={"Accept": "application/json"}, timeout=5)
            if res.status_code == 200:
                c = res.json()
                text = f"🚗 **Автономер {clean_car}:**\n• Модель: {c.get('vendor')} {c.get('model')}\n• Рік: {c.get('year')}\n• Колір: {c.get('color')}"
            else:
                text = f"🚗 Номер `{clean_car}` валідний (формат України)."
            bot.send_message(message.chat.id, text, parse_mode="Markdown")
            return
        except Exception:
            pass

    # 7. НОМЕР ТЕЛЕФОНУ
    if data.startswith('+') or (data.isdigit() and len(data) >= 9):
        try:
            parsed_num = phonenumbers.parse(data, "UA")
            country = geocoder.description_for_number(parsed_num, "uk")
            operator = carrier.name_for_number(parsed_num, "uk")
            valid = phonenumbers.is_valid_number(parsed_num)
            res = f"📱 **Номер {data}:**\n• Регіон: {country}\n• Оператор: {operator}\n• Дійсний: {'Так' if valid else 'Ні'}"
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
            bot.send_message(message.chat.id, f"❌ Email `{data}` недійсний.", parse_mode="Markdown")
            return
        except Exception:
            pass

    # 9. ГЕНЕРАТОР ВАРІАНТІВ ПОШТ ТА НІКНЕЙМІВ
    if " " in data and not data.startswith("@"):
        parts = data.split()
        if len(parts) >= 2:
            fn, ln = parts[0].lower(), parts[1].lower()
            emails = [
                f"{fn}.{ln}@gmail.com",
                f"{fn}{ln}@gmail.com",
                f"{fn[0]}{ln}@gmail.com",
                f"{ln}.{fn}@gmail.com"
            ]
            usernames = [f"{fn}_{ln}", f"{fn}.{ln}", f"{ln}_{fn}", f"{fn}{ln}"]
            
            res_gen = f"🎯 **Згенеровані варіанти за ім'ям {data}:**\n\n"
            res_gen += "📧 **Ймовірні Email:**\n" + "\n".join([f"• `{e}`" for e in emails]) + "\n\n"
            res_gen += "👤 **Ймовірні нікнейми:**\n" + "\n".join([f"• `{u}`" for u in usernames])
            bot.send_message(message.chat.id, res_gen, parse_mode="Markdown")
            return

    # 10. НІКНЕЙМ ТА GOOGLE DORKS
    username = data.lstrip('@')
    platforms = {
        "Telegram": f"https://t.me/{username}",
        "GitHub": f"https://github.com/{username}",
        "TikTok": f"https://www.tiktok.com/@{username}",
        "Reddit": f"https://www.reddit.com/user/{username}"
    }
    found = []
    for name, url in platforms.items():
        try:
            if requests.get(url, timeout=2, headers={"User-Agent": "Mozilla/5.0"}).status_code == 200:
                found.append(f"• [{name}]({url})")
        except Exception:
            pass

    dork_all = f"https://www.google.com/search?q=%22{username}%22"
    dork_docs = f"https://www.google.com/search?q=%22{username}%22+filetype:pdf+OR+filetype:doc"

    res_text = f"👤 **Пошук:** `{username}`\n\n"
    if found:
        res_text += "✅ **Знайдено акаунти:**\n" + "\n".join(found) + "\n\n"
    res_text += f"🔗 [Google Пошук]({dork_all})\n📄 [Пошук у документах (PDF/DOC)]({dork_docs})"
    
    bot.send_message(message.chat.id, res_text, parse_mode="Markdown", disable_web_page_preview=True)

# --- БЛОК ЗАПУСКУ З ЗАХИСТОМ ВІД КОНФЛІКТІВ ---
try:
    bot.remove_webhook()
except Exception:
    pass

bot.infinity_polling(skip_pending=True)
