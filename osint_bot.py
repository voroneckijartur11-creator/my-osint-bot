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

# Машини станів (FSM)
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
        [InlineKeyboardButton(text="🕵️️ Пошук нікнейма (30+ платформ)", callback_data="search_nick")],
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
        "• **Безпека:** IntelX, HIBP (перевірка зливів паштів).\n"
        "• **Крипта:** перевірка балансів адрес BTC, ETH, TRON.\n"
        "• **Фото та медіа:** повний аналіз EXIF (з автоконвертацією GPS у Google Maps) та читання QR-кодів з картинок."
    )
    await callback.message.edit_text(help_text, reply_markup=get_main_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "utilities_menu")
async def utils_menu(callback: types.CallbackQuery):
    # Генерація випадкового пароля на льоту
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
    await callback.message.answer("Введіть кри
