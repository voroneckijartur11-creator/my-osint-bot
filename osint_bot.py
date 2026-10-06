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

TOKEN = "8856195541:AAE-ta26zPsqk5wESGjhmHMJGby9ljjVjKY"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

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

def get_main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
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

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", 
                   (message.from_user.id, message.from_user.username))
    conn.commit()
    conn.close()
    await message.answer("Вітаю! Оберіть потрібний інструмент з меню нижче:", reply_markup=get_main_keyboard())

@dp.callback_query(F.data == "help_info")
async def help_callback(callback: types.CallbackQuery):
    await callback.message.edit_text("🤖 Розширений OSINT-бот (All-in-One). Використовуйте кнопки для пошуку.", reply_markup=get_main_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "utilities_menu")
async def utils_menu(callback: types.CallbackQuery):
    secure_pass = "".join(random.choice(string.ascii_letters + string.digits + "!@#$%^&*") for _ in range(16))
    await callback.message.edit_text(f"🛠 **Утиліти:**\n\n🔑 Пароль: `{secure_pass}`\n\n📷 Надішліть картинку з QR-кодом або EXIF у чат!", reply_markup=get_main_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "search_nick")
async def ask_username(c: types.CallbackQuery, state: FSMContext):
    await c.message.answer("Введіть нікнейм для пошуку:")
    await state.set_state(SearchStates.waiting_for_username)
    await c.answer()

@dp.callback_query(F.data == "search_phone")
async def ask_phone(c: types.CallbackQuery, state: FSMContext):
    await c.message.answer("Введіть номер телефону (наприклад, 0951141394):")
    await state.set_state(SearchStates.waiting_for_phone)
    await c.answer()

@dp.callback_query(F.data == "search_car")
async def ask_car(c: types.CallbackQuery, state: FSMContext):
    await c.message.answer("Введіть держ. номер автомобіля:")
    await state.set_state(SearchStates.waiting_for_car)
    await c.answer()

@dp.callback_query(F.data == "search_geoip")
async def ask_geoip(c: types.CallbackQuery, state: FSMContext):
    await c.message.answer("Введіть IP-адресу для перевірки GeoIP:")
    await state.set_state(SearchStates.waiting_for_geoip)
    await c.answer()

@dp.callback_query(F.data == "search_ip")
async def ask_ip(c: types.CallbackQuery, state: FSMContext):
    await c.message.answer("Введіть IP або домен:")
    await state.set_state(SearchStates.waiting_for_ip_domain)
    await c.answer()

@dp.callback_query(F.data == "search_ssl")
async def ask_ssl(c: types.CallbackQuery, state: FSMContext):
    await c.message.answer("Введіть домен для SSL аудиту:")
    await state.set_state(SearchStates.waiting_for_ssl_check)
    await c.answer()

@dp.callback_query(F.data == "search_dorks")
async def ask_dorks(c: types.CallbackQuery, state: FSMContext):
    await c.message.answer("Введіть ПІБ або ключове слово для Dorks:")
    await state.set_state(SearchStates.waiting_for_dorks)
    await c.answer()

@dp.callback_query(F.data == "search_intelx")
async def ask_intelx(c: types.CallbackQuery, state: FSMContext):
    await c.message.answer("Введіть email або слово для пошуку зливів:")
    await state.set_state(SearchStates.waiting_for_email)
    await c.answer()

@dp.callback_query(F.data == "wayback_check")
async def ask_wayback(c: types.CallbackQuery, state: FSMContext):
    await c.message.answer("Введіть URL сайту для Wayback Machine:")
    await state.set_state(SearchStates.waiting_for_web_archive)
    await c.answer()

@dp.callback_query(F.data == "crypto_check")
async def ask_crypto(c: types.CallbackQuery, state: FSMContext):
    await c.message.answer("Введіть криптогаманець:")
    await state.set_state(SearchStates.waiting_for_crypto)
    await c.answer()

@dp.message(SearchStates.waiting_for_phone)
async def process_phone(message: types.Message, state: FSMContext):
    raw_phone = message.text.strip()
    if raw_phone.startswith("0") and len(raw_phone) == 10:
        raw_phone = "+38" + raw_phone
    elif raw_phone.startswith("380") and len(raw_phone) == 12:
        raw_phone = "+" + raw_phone
    try:
        parsed_number = phonenumbers.parse(raw_phone)
        if not phonenumbers.is_valid_number(parsed_number):
            await message.answer("⚠️ Недійсний номер.", reply_markup=get_main_keyboard())
            await state.clear()
            return
        country = geocoder.description_for_number(parsed_number, "uk")
        isp = carrier.name_for_number(parsed_number, "en")
        tz = timezone.time_zones_for_number(parsed_number)
        clean_num = phonenumbers.format_number(parsed_number, phonenumbers.PhoneNumberFormat.E164)
        num_digits = clean_num.replace("+", "")
        text = (
            f"📱 **Телефон:** `{clean_num}`\n\n"
            f"🌍 **Регіон:** {country or 'Невідомо'}\n"
            f"📡 **Оператор:** {isp or 'Невідомо'}\n"
            f"⏰ **Часовий пояс:** {', '.join(tz) if tz else 'Невідомо'}\n\n"
            f"🔗 [Telegram](https://t.me/{num_digits}) | [WhatsApp](https://wa.me/{num_digits})"
        )
        await message.answer(text, reply_markup=get_main_keyboard(), disable_web_page_preview=True)
    except Exception as e:
        await message.answer(f"❌ Помилка: {e}", reply_markup=get_main_keyboard())
    await state.clear()

@dp.message(SearchStates.waiting_for_car)
async def process_car(message: types.Message, state: FSMContext):
    car = message.text.strip().upper()
    text = f"🚗 **Авто:** `{car}`\n\n🔗 [OpenDataBot](https://opendatabot.ua/c/{car})\n🔗 [Baza Demurrer](https://baza.com.ua/search?q={car})"
    await message.answer(text, reply_markup=get_main_keyboard(), disable_web_page_preview=True)
    await state.clear()

@dp.message(SearchStates.waiting_for_geoip)
async def process_geoip(message: types.Message, state: FSMContext):
    ip = message.text.strip()
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(f"http://ip-api.com/json/{ip}", timeout=5) as resp:
                data = await resp.json()
                if data["status"] == "success":
                    text = f"🌍 **IP:** {ip}\n🏳️ **Країна:** {data.get('country')}\n🏙️ **Місто:** {data.get('city')}\n🏢 **ISP:** {data.get('isp')}"
                    await message.answer(text, reply_markup=get_main_keyboard(), disable_web_page_preview=True)
                else:
                    await message.answer("❌ Не знайдено.", reply_markup=get_main_keyboard())
        except:
            await message.answer("❌ Помилка запиту.", reply_markup=get_main_keyboard())
    await state.clear()

@dp.message(SearchStates.waiting_for_ssl_check)
async def process_ssl(message: types.Message, state: FSMContext):
    domain = message.text.strip().replace("https://", "").replace("http://", "").split("/")[0]
    try:
        context = ssl.create_default_context()
        with socket.create_connection((domain, 443), timeout=5) as sock:
            with context.wrap_socket(sock, server_hostname=domain) as ssock:
                cert = ssock.getpeercert()
                issuer = dict(x[0] for x in cert.get('issuer', []))
                await message.answer(f"🔒 **SSL:** `{domain}`\n🏢 **Видавець:** {issuer.get('organizationName', 'Невідомо')}\n⏳ **Дійсний до:** {cert.get('notAfter')}", reply_markup=get_main_keyboard())
    except Exception as e:
        await message.answer(f"❌ Помилка SSL: {e}", reply_markup=get_main_keyboard())
    await state.clear()

@dp.message(SearchStates.waiting_for_dorks)
async def process_dorks(message: types.Message, state: FSMContext):
    q = message.text.strip().replace(" ", "+")
    text = f"🔍 **Dorks:**\n🔗 [Точний збіг](https://www.google.com/search?q=%22{q}%22)\n🔗 [Соцмережі](https://www.google.com/search?q=site%3Alinkedin.com+{q}+OR+site%3Afacebook.com+{q})\n🔗 [PDF](https://www.google.com/search?q=filetype%3Apdf+%22{q}%22)"
    await message.answer(text, reply_markup=get_main_keyboard(), disable_web_page_preview=True)
    await state.clear()

@dp.message(SearchStates.waiting_for_username)
async def process_username(message: types.Message, state: FSMContext):
    username = message.text.strip()
    platforms = {
        "GitHub": f"https://github.com/{username}",
        "Instagram": f"https://instagram.com/{username}",
        "TikTok": f"https://tiktok.com/@{username}",
        "Telegram": f"https://t.me/{username}",
        "Reddit": f"https://www.reddit.com/user/{username}"
    }
    results = []
    async with aiohttp.ClientSession() as session:
        for name, url in platforms.items():
            try:
                async with session.get(url, timeout=3, headers={"User-Agent": "Mozilla/5.0"}) as resp:
                    if resp.status == 200:
                        results.append(f"✅ {name}: {url}")
                    else:
                        results.append(f"❌ {name}: не знайдено")
            except:
                results.append(f"⚠️ {name}: помилка")
    await message.answer(f"Результати для `{username}`:\n\n" + "\n".join(results), reply_markup=get_main_keyboard())
    await state.clear()

@dp.message(SearchStates.waiting_for_ip_domain)
async def process_ip(message: types.Message, state: FSMContext):
    q = message.text.strip()
    await message.answer(f"🌐 **Аналіз:** `{q}`\n\n🔗 [Shodan](https://www.shodan.io/search?query={q})\n🔗 [Censys](https://search.censys.io/search?resource=hosts&q={q})", reply_markup=get_main_keyboard(), disable_web_page_preview=True)
    await state.clear()

@dp.message(SearchStates.waiting_for_email)
async def process_email(message: types.Message, state: FSMContext):
    q = message.text.strip()
    await message.answer(f"📦 **Витоки:** `{q}`\n\n🔗 [IntelX](https://intelx.io/?s={q})\n🔗 [HIBP](https://haveibeenpwned.com/unifiedsearch/{q})", reply_markup=get_main_keyboard(), disable_web_page_preview=True)
    await state.clear()

@dp.message(SearchStates.waiting_for_web_archive)
async def process_wayback(message: types.Message, state: FSMContext):
    url = message.text.strip()
    await message.answer(f"⏪ **Архів:** `{url}`\n\n🔗 [Wayback Machine](https://web.archive.org/web/*/{url})", reply_markup=get_main_keyboard(), disable_web_page_preview=True)
    await state.clear()

@dp.message(SearchStates.waiting_for_crypto)
async def process_crypto(message: types.Message, state: FSMContext):
    w = message.text.strip()
    await message.answer(f"🪙 **Гаманець:** `{w}`\n\n🔗 [Blockchain (BTC)](https://www.blockchain.com/explorer/addresses/btc/{w})\n🔗 [Etherscan (ETH)](https://etherscan.io/address/{w})", reply_markup=get_main_keyboard(), disable_web_page_preview=True)
    await state.clear()

@dp.message(F.photo | F.document)
async def handle_media(message: types.Message):
    file_id = message.photo[-1].file_id if message.photo else message.document.file_id
    file_info = await bot.get_file(file_id)
    photo_bytes = io.BytesIO()
    await bot.download_file(file_info.file_path, destination=photo_bytes)
    photo_bytes.seek(0)
    try:
        img_cv = cv2.imdecode(np.frombuffer(photo_bytes.getvalue(), np.uint8), cv2.IMREAD_COLOR)
        val, _, _ = cv2.QRCodeDetector().detectAndDecode(img_cv)
        if val:
            await message.answer(f"📱 **QR-код:**\n`{val}`", reply_markup=get_main_keyboard())
            return
    except:
        pass
    photo_bytes.seek(0)
    try:
        exif = Image.open(photo_bytes)._getexif()
        if not exif:
            await message.answer("⚠️ EXIF метадані відсутні.", reply_markup=get_main_keyboard())
            return
        info = [f"• {TAGS.get(k, k)}: {v}" for k, v in exif.items() if not isinstance(v, bytes)][:10]
        await message.answer("📸 **EXIF:**\n\n" + "\n".join(info), reply_markup=get_main_keyboard(), disable_web_page_preview=True)
    except Exception as e:
        await message.answer(f"❌ Помилка EXIF: {e}", reply_markup=get_main_keyboard())

async def handle_web(request):
    return web.Response(text="Bot is running!")

async def web_server():
    app = web.Application()
    app.router.add_get("/", handle_web)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", int(os.environ.get("PORT", 10000))).start()

async def main():
    await web_server()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
