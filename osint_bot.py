import sqlite3
import logging
import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import aiohttp
import asyncio
import io
import random
import string
from PIL import Image
from PIL.ExifTags import TAGS
import cv2
import numpy as np
from aiohttp import web
import phonenumbers
from phonenumbers import carrier, geocoder, timezone
import ssl
import socket
from datetime import datetime

# Ваш токен
TOKEN = "8856195541:AAE-ta26zPsqk5wESGjhmHMJGby9ljjVjKY"

logging.basicConfig(level=logging.INFO)

bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# --- БАЗА ДАНИХ SQLITE ---
def init_db():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            joined_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

init_db()

# Машини станів (FSM)
class SearchStates(StatesGroup):
    waiting_for_username = State()
    waiting_for_ip_domain = State()
    waiting_for_email = State()
    waiting_for_web_archive = State()
    waiting_for_crypto = State()
    waiting_for_phone = State()
    waiting_for_car = State()
    waiting_for_geoip = State()
    waiting_for_dorks = State()
    waiting_for_ssl_check = State()

# --- ГОЛОВНЕ МЕНЮ ---
def get_main_keyboard():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🕵 Пошук нікнейма", callback_data="search_nick"),
         InlineKeyboardButton(text="📱 Перевірка телефону", callback_data="search_phone")],
        [InlineKeyboardButton(text="🚗 Перевірка авто за номером", callback_data="search_car"),
         InlineKeyboardButton(text="🌍 GeoIP локація", callback_data="search_geoip")],
        [InlineKeyboardButton(text="🌐 Домени, IP & Whois", callback_data="search_ip"),
         InlineKeyboardButton(text="🔒 Аудит SSL сайту", callback_data="search_ssl")],
        [InlineKeyboardButton(text="📦 Зливи даних (IntelX)", callback_data="search_intelx"),
         InlineKeyboardButton(text="🔍 Google Dorks генератор", callback_data="search_dorks")],
        [InlineKeyboardButton(text="⏪ Архів сайту (Wayback)", callback_data="wayback_check"),
         InlineKeyboardButton(text="🪙 Крипто-розвідка", callback_data="crypto_check")],
        [InlineKeyboardButton(text="🛠️ Утиліти (Паролі / QR)", callback_data="utilities_menu"),
         InlineKeyboardButton(text="ℹ️ Про можливості", callback_data="help_info")]
    ])
    return keyboard

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", 
                   (message.from_user.id, message.from_user.username))
    conn.commit()
    conn.close()

    await message.answer(
        f"Вітаю, {message.from_user.first_name}!\n\n"
        "Я ваш оновлений OSINT-комбайн. Оберіть потрібний інструмент з меню нижче або надішліть фото/QR-код для аналізу:",
        reply_markup=get_main_keyboard()
    )

@dp.callback_query(F.data == "help_info")
async def help_callback(callback: types.CallbackQuery):
    help_text = (
        "🤖 **Розширений OSINT-бот (All-in-One v2):**\n\n"
        "• **Нікнейми:** перевірка на платформах.\n"
        "• **Телефони:** оператор, регіон, месенджери.\n"
        "• **Автомобілі:** перевірка держ. номерів України.\n"
        "• **GeoIP:** визначення країни та провайдера за IP.\n"
        "• **Безпека:** аудит SSL-сертифікатів, Shodan, IntelX, HIBP.\n"
        "• **Медіа:** EXIF-метадані та зчитування QR-кодів."
    )
    await callback.message.edit_text(help_text, reply_markup=get_main_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "utilities_menu")
async def utils_menu(callback: types.CallbackQuery):
    chars = string.ascii_letters + string.digits + "!@#$%^&*"
    secure_pass = "".join(random.choice(chars) for _ in range(16))
    
    text = (
        "🛠️ **Корисні утиліти:**\n\n"
        f"🔑 **Безпечний пароль (16 знаків):** `{secure_pass}`\n\n"
        "📷 *Хочете розшифрувати QR-код або перевірити EXIF?* Просто надішліть картинку у чат!"
    )
    await callback.message.edit_text(text, reply_markup=get_main_keyboard())
    await callback.answer()

# --- КНОПКИ ВИЗУВУ СТАНІВ ---
@dp.callback_query(F.data == "search_nick")
async def ask_username(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введіть нікнейм для пошуку (наприклад, `durov`):")
    await state.set_state(SearchStates.waiting_for_username)
    await callback.answer()

@dp.callback_query(F.data == "search_phone")
async def ask_phone(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введіть номер телефону у міжнародному форматі (наприклад, `+380501234567`):")
    await state.set_state(SearchStates.waiting_for_phone)
    await callback.answer()

@dp.callback_query(F.data == "search_car")
async def ask_car(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введіть державний номер автомобіля (наприклад, `KA1234AB` або `АІ4567ВХ`):")
    await state.set_state(SearchStates.waiting_for_car)
    await callback.answer()

@dp.callback_query(F.data == "search_geoip")
async def ask_geoip(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введіть IP-адресу для перевірки GeoIP (наприклад, `8.8.8.8`):")
    await state.set_state(SearchStates.waiting_for_geoip)
    await callback.answer()

@dp.callback_query(F.data == "search_ip")
async def ask_ip(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введіть IP-адресу або домен для Shodan/Censys:")
    await state.set_state(SearchStates.waiting_for_ip_domain)
    await callback.answer()

@dp.callback_query(F.data == "search_ssl")
async def ask_ssl(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введіть домен сайту для аудиту безпеки та SSL (наприклад, `google.com`):")
    await state.set_state(SearchStates.waiting_for_ssl_check)
    await callback.answer()

@dp.callback_query(F.data == "search_dorks")
async def ask_dorks(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введіть ПІБ або ключове слово для генератора Google Dorks:")
    await state.set_state(SearchStates.waiting_for_dorks)
    await callback.answer()

@dp.callback_query(F.data == "search_intelx")
async def ask_intelx(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введіть email або ключове слово для перевірки зливів:")
    await state.set_state(SearchStates.waiting_for_email)
    await callback.answer()

@dp.callback_query(F.data == "wayback_check")
async def ask_wayback(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введіть URL сайту для перегляду його історії в архівах:")
    await state.set_state(SearchStates.waiting_for_web_archive)
    await callback.answer()

@dp.callback_query(F.data == "crypto_check")
async def ask_crypto(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введіть криптогаманець (Bitcoin, Ethereum або TRON/USDT):")
    await state.set_state(SearchStates.waiting_for_crypto)
    await callback.answer()

# --- ОБРОБНИКИ НОВИХ ФУНКЦІЙ ---

@dp.message(SearchStates.waiting_for_phone)
async def process_phone(message: types.Message, state: FSMContext):
    raw_phone = message.text.strip()
    try:
        parsed_number = phonenumbers.parse(raw_phone)
        if not phonenumbers.is_valid_number(parsed_number):
            await message.answer("⚠️ Введений номер виглядає недійсним або некоректним.", reply_markup=get_main_keyboard())
            await state.clear()
            return
        
        country = geocoder.description_for_number(parsed_number, "uk")
        isp = carrier.name_for_number(parsed_number, "en")
        tz = timezone.time_zones_for_number(parsed_number)
        clean_num = phonenumbers.format_number(parsed_number, phonenumbers.PhoneNumberFormat.E164)
        num_digits = clean_num.replace("+", "")

        text = (
            f"📱 **Результати аналізу телефону:** `{clean_num}`\n\n"
            f"🌍 **Країна / Регіон:** {country or 'Невідомо'}\n"
            f"📡 **Оператор (Мобільна мережа):** {isp or 'Визначити не вдалося'}\n"
            f"⏰ **Часовий пояс:** {', '.join(tz) if tz else 'Невідомо'}\n\n"
            f"🔗 **Швидкі посилання на месенджери:**\n"
            f"• [Telegram](https://t.me/{num_digits})\n"
            f"• [WhatsApp](https://wa.me/{num_digits})\n"
            f"• [Viber](viber://chat?number=%2B{num_digits})"
        )
        await message.answer(text, reply_markup=get_main_keyboard(), disable_web_page_preview=True)
    except Exception as e:
        await message.answer(f"❌ Помилка обробки номера: {e}", reply_markup=get_main_keyboard())
    await state.clear()

@dp.message(SearchStates.waiting_for_car)
async def process_car(message: types.Message, state: FSMContext):
    car_number = message.text.strip().upper()
    text = (
        f"🚗 **Пошук транспортного засобу:** `{car_number}`\n\n"
        f"🔍 Перевірка за відкритими реєстрами України:\n"
        f"🔗 [OpenDataBot (Авто)](https://opendatabot.ua/c/{car_number})\n"
        f"🔗 [Baza Demurrer / Номери UA](https://baza.com.ua/search?q={car_number})\n\n"
        f"*(Посилання дозволять швидко перевірити марку, модель, рік випуску та наявність можливих обтяжень)*"
    )
    await message.answer(text, reply_markup=get_main_keyboard(), disable_web_page_preview=True)
    await state.clear()

@dp.message(SearchStates.waiting_for_geoip)
async def process_geoip(message: types.Message, state: FSMContext):
    ip_query = message.text.strip()
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(f"http://ip-api.com/json/{ip_query}", timeout=5) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data["status"] == "success":
                        text = (
                            f"🌍 **GeoIP дані для:** `{ip_query}`\n\n"
                            f"🏳️ **Країна:** {data.get('country')} ({data.get('countryCode')})\n"
                            f"🏙️ **Місто:** {data.get('city')}, {data.get('regionName')}\n"
                            f"🏢 **Провайдер (ISP):** {data.get('isp')}\n"
                            f"🌐 **Організація:** {data.get('org')}\n"
                            f"📌 **Координати:** `{data.get('lat')}, {data.get('lon')}`\n"
                            f"🔗 [Відкрити на мапі](https://maps.google.com/?q={data.get('lat')},{data.get('lon')})"
                        )
                        await message.answer(text, reply_markup=get_main_keyboard(), disable_web_page_preview=True)
                    else:
                        await message.answer("❌ Не вдалося знайти геолокацію за цією IP-адресою.", reply_markup=get_main_keyboard())
                else:
                    await message.answer("⚠️ Сервіс GeoIP тимчасово недоступний.", reply_markup=get_main_keyboard())
        except Exception as e:
            await message.answer(f"❌ Помилка запиту: {e}", reply_markup=get_main_keyboard())
    await state.clear()

@dp.message(SearchStates.waiting_for_ssl_check)
async def process_ssl(message: types.Message, state: FSMContext):
    domain = message.text.strip().replace("https://", "").replace("http://", "").split("/")[0]
    try:
        context = ssl.create_default_context()
        with socket.create_connection((domain, 443), timeout=5) as sock:
            with context.wrap_socket(sock, server_hostname=domain) as ssock:
                cert = ssock.getpeercert()
                
                subject = dict(x[0] for x in cert.get('subject', []))
                issuer = dict(x[0] for x in cert.get('issuer', []))
                not_after = cert.get('notAfter')
                
                text = (
                    f"🔒 **Аудит SSL-сертифіката:** `{domain}`\n\n"
                    f"🏢 **Видавець (Issuer):** {issuer.get('organizationName', 'Невідомо')}\n"
                    f"👤 **Власник (Subject):** {subject.get('commonName', 'Невідомо')}\n"
                    f"⏳ **Дійсний до:** {not_after}\n\n"
                    f"✅ З'єднання захищене шифруванням SSL/TLS."
                )
                await message.answer(text, reply_markup=get_main_keyboard())
    except Exception as e:
        await message.answer(f"❌ Не вдалося отримати SSL-сертифікат для `{domain}`.\nПомилка: {e}", reply_markup=get_main_keyboard())
    await state.clear()

@dp.message(SearchStates.waiting_for_dorks)
async def process_dorks(message: types.Message, state: FSMContext):
    query = message.text.strip()
    q_enc = query.replace(" ", "+")
    text = (
        f"🔍 **Google Dorks для запиту:** `{query}`\n\n"
        f"Натисніть на посилання для глибокого пошуку в Google:\n\n"
        f"📄 **Документи (PDF/DOC):**\n🔗 [Шукати файли](https://www.google.com/search?q=site%3Alinkedin.com+%22{q_enc}%22+OR+site%3Afacebook.com+%22{q_enc}%22)\n\n"
        f"📂 **Згадки в соцмережах:**\n🔗 [Соцмережі](https://www.google.com/search?q=%22{q_enc}%22+site%3Atwitter.com+OR+site%3Ainstagram.com)\n\n"
        f"⚙️ **Конфіденційні файли/звіти:**\n🔗 [Звіти та дані](https://www.google.com/search?q=filetype%3Apdf+OR+filetype%3XLS+%22{q_enc}%22)"
    )
    await message.answer(text, reply_markup=get_main_keyboard(), disable_web_page_preview=True)
    await state.clear()

# --- СТАРІ ОБРОБНИКИ (Нікнейми, IP, IntelX, Wayback, Крипта) ---

@dp.message(SearchStates.waiting_for_username)
async def process_username(message: types.Message, state: FSMContext):
    username = message.text.strip()
    await message.answer(f"⏳ Перевіряю нікнейм `{username}` на платформах...")
    
    platforms = {
        "GitHub": f"https://github.com/{username}",
        "Instagram": f"https://instagram.com/{username}",
        "TikTok": f"https://tiktok.com/@{username}",
        "Twitter (X)": f"https://twitter.com/{username}",
        "Telegram": f"https://t.me/{username}",
        "Reddit": f"https://www.reddit.com/user/{username}"
    }
    
    results = []
    async with aiohttp.ClientSession() as session:
        for name, url in platforms.items():
            try:
                async with session.get(url, timeout=4, headers={"User-Agent": "Mozilla/5.0"}) as resp:
                    if resp.status == 200:
                        results.append(f"✅ **{name}**: {url}")
                    else:
                        results.append(f"❌ **{name}**: не знайдено")
            except:
                results.append(f"⚠️ **{name}**: таймаут/помилка")
                
    await message.answer(f"Результати для `{username}`:\n\n" + "\n".join(results), reply_markup=get_main_keyboard())
    await state.clear()

@dp.message(SearchStates.waiting_for_ip_domain)
async def process_ip(message: types.Message, state: FSMContext):
    query = message.text.strip()
    text = (
        f"🌐 **Інфраструктурний аналіз:** `{query}`\n\n"
        f"🔗 [Shodan](https://www.shodan.io/search?query={query})\n"
        f"🔗 [Censys](https://search.censys.io/search?resource=hosts&q={query})"
    )
    await message.answer(text, reply_markup=get_main_keyboard(), disable_web_page_preview=True)
    await state.clear()

@dp.message(SearchStates.waiting_for_email)
async def process_email(message: types.Message, state: FSMContext):
    query = message.text.strip()
    text = (
        f"📦 **Перевірка даних / витоків:** `{query}`\n\n"
        f"🔗 [Intelligence X](https://intelx.io/?s={query})\n"
        f"🔗 [HaveIBeenPwned](https://haveibeenpwned.com/unifiedsearch/{query})"
    )
    await message.answer(text, reply_markup=get_main_keyboard(), disable_web_page_preview=True)
    await state.clear()

@dp.message(SearchStates.waiting_for_web_archive)
async def process_wayback(message: types.Message, state: FSMContext):
    url = message.text.strip()
    text = f"⏪ **Архівні копії сайту:** `{url}`\n\n🔗 [Wayback Machine](https://web.archive.org/web/*/{url})"
    await message.answer(text, reply_markup=get_main_keyboard(), disable_web_page_preview=True)
    await state.clear()

@dp.message(SearchStates.waiting_for_crypto)
async def process_crypto(message: types.Message, state: FSMContext):
    wallet = message.text.strip()
    text = (
        f"🪙 **Перевірка криптогаманця:** `{wallet}`\n\n"
        f"🔗 [Blockchain.com (BTC)](https://www.blockchain.com/explorer/addresses/btc/{wallet})\n"
        f"🔗 [Etherscan (ETH)](https://etherscan.io/address/{wallet})"
    )
    await message.answer(text, reply_markup=get_main_keyboard(), disable_web_page_preview=True)
    await state.clear()

# --- ОБРОБКА ФОТО ТА QR-КОДІВ ---
@dp.message(F.photo | F.document)
async def handle_media(message: types.Message):
    if message.photo:
        file_id = message.photo[-1].file_id
    else:
        if message.document.mime_type and ('image' in message.document.mime_type):
            file_id = message.document.file_id
        else:
            await message.answer("Будь ласка, надішліть зображення для аналізу.")
            return

    await message.answer("🔍 Завантажую та аналізую файл...")
    file_info = await bot.get_file(file_id)
    
    photo_bytes = io.BytesIO()
    await bot.download_file(file_info.file_path, destination=photo_bytes)
    photo_bytes.seek(0)

    try:
        file_bytes_np = np.frombuffer(photo_bytes.getvalue(), np.uint8)
        img_cv = cv2.imdecode(file_bytes_np, cv2.IMREAD_COLOR)
        detector = cv2.QRCodeDetector()
        val, _, _ = detector.detectAndDecode(img_cv)
        if val:
            await message.answer(f"📱 **Знайдено QR-код!**\n\nВміст:\n`{val}`", reply_markup=get_main_keyboard())
            return
    except:
        pass

    photo_bytes.seek(0)
    try:
        image = Image.open(photo_bytes)
        exif_data = image._getexif()
        if not exif_data:
            await message.answer("⚠️ EXIF-метадані відсутні або вирізані месенджером.", reply_markup=get_main_keyboard())
            return

        exif_info = []
        for tag_id, value in exif_data.items():
            tag = TAGS.get(tag_id, tag_id)
            if not isinstance(value, bytes):
                exif_info.append(f"• **{tag}**: {value}")

        response_text = "📸 **Метадані фото (EXIF):**\n\n" + "\n".join(exif_info[:15])
        await message.answer(response_text, reply_markup=get_main_keyboard(), disable_web_page_preview=True)
    except Exception as e:
        await message.answer(f"❌ Помилка читання метаданих: {e}", reply_markup=get_main_keyboard())

# --- ВЕБСЕРВЕР ДЛЯ RENDER ---
async def handle_web(request):
    return web.Response(text="Bot v2 is running!")

async def web_server():
    app = web.Application()
    app.router.add_get("/", handle_web)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

async def main():
    await web_server()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
