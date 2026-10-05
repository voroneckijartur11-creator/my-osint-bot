import sqlite3
import logging
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
from PIL.ExifTags import TAGS, GPSTAGS
import cv2
import numpy as np

# Ваш токен Telegram бота
TOKEN = "8856195541:AAH4WMkaJeVo_4Q3Tq4TSM98y9TrNx9EFzg"

# Налаштування логування
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

# Машини станів (FSM) - всі стани оголошені чітко
class SearchStates(StatesGroup):
    waiting_for_username = State()
    waiting_for_ip_domain = State()
    waiting_for_email = State()
    waiting_for_web_archive = State()
    waiting_for_crypto = State()
    waiting_for_coords = State()

# --- ГОЛОВНЕ МЕНЮ ---
def get_main_keyboard():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🕵 Пошук нікнейма (30+ платформ)", callback_data="search_nick")],
        [InlineKeyboardButton(text="🌐 Домени, IP & Whois (Shodan)", callback_data="search_ip")],
        [InlineKeyboardButton(text="📦 Зливи даних (IntelX / HIBP)", callback_data="search_intelx")],
        [InlineKeyboardButton(text="🗺️ Gmail (EPIOS) & Координати", callback_data="search_epios")],
        [InlineKeyboardButton(text="⏪ Архів сайту (Wayback)", callback_data="wayback_check")],
        [InlineKeyboardButton(text="🪙 Крипто-розвідка (BTC/ETH/TRON)", callback_data="crypto_check")],
        [InlineKeyboardButton(text="🛠️ Утиліти (Паролі / QR-коди)", callback_data="utilities_menu")],
        [InlineKeyboardButton(text="ℹ️ Про можливості бота", callback_data="help_info")]
    ])
    return keyboard

# --- СТАРТ ТА ГОЛОВНЕ МЕНЮ ---
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
        "Я ваш максимальний OSINT-комбайн. Оберіть потрібний інструмент з меню нижче або надішліть фото/QR-код для аналізу:",
        reply_markup=get_main_keyboard()
    )

# --- ДОПОМОГА ТА УТИЛІТИ ---
@dp.callback_query(F.data == "help_info")
async def help_callback(callback: types.CallbackQuery):
    help_text = (
        "🤖 **Розширений OSINT-бот (All-in-One):**\n\n"
        "• **Нікнейми:** перевірка наявності акаунтів.\n"
        "• **Інфраструктура:** Shodan, Censys, Whois/DNS.\n"
        "• **Безпека:** IntelX, HIBP (перевірка зливів пошт).\n"
        "• **Крипта:** перевірка балансів адрес BTC, ETH, TRON.\n"
        "• **Фото та медіа:** повний аналіз EXIF (з автоконвертацією GPS у Google Maps) та читання QR-кодів з картинок."
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
        "📷 *Хочете розшифрувати QR-код?* Просто надішліть картинку з QR-кодом у чат!"
    )
    await callback.message.edit_text(text, reply_markup=get_main_keyboard())
    await callback.answer()

# --- CALLBACKS ДЛЯ ЗАПИТІВ СТАНІВ ---
@dp.callback_query(F.data == "search_nick")
async def ask_username(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введіть нікнейм для пошуку (наприклад, `durov`):")
    await state.set_state(SearchStates.waiting_for_username)
    await callback.answer()

@dp.callback_query(F.data == "search_ip")
async def ask_ip(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введіть IP-адресу або домен (наприклад, `google.com` або `8.8.8.8`):")
    await state.set_state(SearchStates.waiting_for_ip_domain)
    await callback.answer()

@dp.callback_query(F.data == "search_intelx")
async def ask_intelx(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введіть email або ключове слово для перевірки зливів:")
    await state.set_state(SearchStates.waiting_for_email)
    await callback.answer()

@dp.callback_query(F.data == "search_epios")
async def ask_epios(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введіть Gmail-адресу для перевірки через EPIOS:")
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

# --- ОБРОБНИКИ ПОШУКУ (FSM) ---

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
        "Reddit": f"https://www.reddit.com/user/{username}",
        "Pinterest": f"https://www.pinterest.com/{username}",
        "SoundCloud": f"https://soundcloud.com/{username}",
        "Steam": f"https://steamcommunity.com/id/{username}"
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
    shodan_url = f"https://www.shodan.io/search?query={query}"
    censys_url = f"https://search.censys.io/search?resource=hosts&q={query}"
    securitytrails = f"https://securitytrails.com/domain/{query}/dns"
    
    text = (
        f"🌐 **Інфраструктурний аналіз:** `{query}`\n\n"
        f"🔗 [Shodan (Пристрої та порти)]({shodan_url})\n"
        f"🔗 [Censys (Хости та сертифікати)]({censys_url})\n"
        f"🔗 [SecurityTrails (Історія DNS)]({securitytrails})"
    )
    await message.answer(text, reply_markup=get_main_keyboard(), disable_web_page_preview=True)
    await state.clear()


@dp.message(SearchStates.waiting_for_email)
async def process_email(message: types.Message, state: FSMContext):
    query = message.text.strip()
    intelx_url = f"https://intelx.io/?s={query}"
    hibp_url = f"https://haveibeenpwned.com/unifiedsearch/{query}"
    epios_url = f"https://epios.fr/"
    
    text = (
        f"📦 **Перевірка даних / витоків:** `{query}`\n\n"
        f"🔗 [Intelligence X (Зливи/Архіви)]({intelx_url})\n"
        f"🔗 [HaveIBeenPwned (Перевірка паролів/пошт)]({hibp_url})\n"
        f"🔗 [EPIOS (Зв'язки Google ID)]({epios_url})"
    )
    await message.answer(text, reply_markup=get_main_keyboard(), disable_web_page_preview=True)
    await state.clear()


@dp.message(SearchStates.waiting_for_web_archive)
async def process_wayback(message: types.Message, state: FSMContext):
    url = message.text.strip()
    wayback_url = f"https://web.archive.org/web/*/{url}"
    
    text = (
        f"⏪ **Архівні копії сайту:** `{url}`\n\n"
        f"🔗 [Відкрити в Wayback Machine]({wayback_url})"
    )
    await message.answer(text, reply_markup=get_main_keyboard(), disable_web_page_preview=True)
    await state.clear()


@dp.message(SearchStates.waiting_for_crypto)
async def process_crypto(message: types.Message, state: FSMContext):
    wallet = message.text.strip()
    btc_url = f"https://www.blockchain.com/explorer/addresses/btc/{wallet}"
    eth_url = f"https://etherscan.io/address/{wallet}"
    tron_url = f"https://tronscan.org/#/address/{wallet}"
    
    text = (
        f"🪙 **Перевірка криптогаманця:** `{wallet}`\n\n"
        f"🔗 [Blockchain.com (Bitcoin)]({btc_url})\n"
        f"🔗 [Etherscan (Ethereum/ERC20)]({eth_url})\n"
        f"🔗 [Tronscan (TRON/USDT TRC20)]({tron_url})"
    )
    await message.answer(text, reply_markup=get_main_keyboard(), disable_web_page_preview=True)
    await state.clear()


# --- ДОПОМІЖНА ФУНКЦІЯ ДЛЯ КОНВЕРТАЦІЇ GPS ---
def convert_to_degress(value):
    d = float(value[0])
    m = float(value[1])
    s = float(value[2])
    return d + (m / 60.0) + (s / 3600.0)

# --- АНАЛІЗ ФОТО, EXIF ТА ДЕКОДЕР QR-КОДІВ ---
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
    file_path = file_info.file_path
    
    photo_bytes = io.BytesIO()
    await bot.download_file(file_path, destination=photo_bytes)
    photo_bytes.seek(0)

    try:
        file_bytes_np = np.frombuffer(photo_bytes.getvalue(), np.uint8)
        img_cv = cv2.imdecode(file_bytes_np, cv2.IMREAD_COLOR)
        detector = cv2.QRCodeDetector()
        val, _, _ = detector.detectAndDecode(img_cv)
        
        if val:
            await message.answer(f"📱 **Знайдено QR-код у файлі!**\n\nВміст:\n`{val}`", reply_markup=get_main_keyboard())
            return
    except:
        pass

    photo_bytes.seek(0)
    try:
        image = Image.open(photo_bytes)
        exif_data = image._getexif()
        
        if not exif_data:
            await message.answer("⚠️ EXIF-метадані у файлі відсутні (або вирізані месенджером).", reply_markup=get_main_keyboard())
            return

        exif_info = []
        lat, lon = None, None
        lat_ref, lon_ref = None, None

        for tag_id, value in exif_data.items():
            tag = TAGS.get(tag_id, tag_id)
            if tag == "GPSInfo":
                for gps_tag_id in value:
                    gps_tag = GPSTAGS.get(gps_tag_id, gps_tag_id)
                    if gps_tag == "GPSLatitude":
                        lat = convert_to_degress(value[gps_tag_id])
                    elif gps_tag == "GPSLatitudeRef":
                        lat_ref = value[gps_tag_id]
                    elif gps_tag == "GPSLongitude":
                        lon = convert_to_degress(value[gps_tag_id])
                    elif gps_tag == "GPSLongitudeRef":
                        lon_ref = value[gps_tag_id]
            else:
                if isinstance(value, bytes):
                    value = "<бінарні дані>"
                exif_info.append(f"• **{tag}**: {value}")

        response_text = "📸 **Метадані фото (EXIF):**\n\n" + "\n".join(exif_info[:15])
        
        if lat and lon:
            if lat_ref == 'S': lat = -lat
            if lon_ref == 'W': lon = -lon
            maps_url = f"https://maps.google.com/?q={lat},{lon}"
            response_text += f"\n\n📍 **Геолокація виявлена!**\n🔗 [Відкрити місце на Google Maps]({maps_url})"

        await message.answer(response_text, reply_markup=get_main_keyboard(), disable_web_page_preview=True)

    except Exception as e:
        await message.answer(f"❌ Помилка обробки файлу: {e}", reply_markup=get_main_keyboard())

# Запуск бота
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
