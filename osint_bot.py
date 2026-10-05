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
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS

# Вставлено ваш новий токен Telegram бота
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

# --- ГОЛОВНЕ МЕНЮ ---
def get_main_keyboard():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🕵️ Пошук нікнейма", callback_data="search_nick")],
        [InlineKeyboardButton(text="🌐 Перевірка IP / Домену (Shodan)", callback_data="search_ip")],
        [InlineKeyboardButton(text="📦 Пошук у зливах (IntelX)", callback_data="search_intelx")],
        [InlineKeyboardButton(text="🗺️ Перевірка Gmail (EPIOS)", callback_data="search_epios")],
        [InlineKeyboardButton(text="⏪ Архів сайту (Wayback Machine)", callback_data="wayback_check")],
        [InlineKeyboardButton(text="ℹ️ Допомога та опис інструментів", callback_data="help_info")]
    ])
    return keyboard

# --- СТАРТ ТА ГОЛОВНЕ МЕНЮ ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    # Зберігаємо користувача в базі даних
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", 
                   (message.from_user.id, message.from_user.username))
    conn.commit()
    conn.close()

    await message.answer(
        f"Вітаю, {message.from_user.first_name}!\n\n"
        "Я ваш розширений OSINT-бот. Оберіть потрібний інструмент з меню нижче або надішліть фото для аналізу метаданих:",
        reply_markup=get_main_keyboard()
    )

# --- ОБРОБКА КНОПОК ГОЛОВНОГО МЕНЮ ---
@dp.callback_query(F.data == "help_info")
async def help_callback(callback: types.CallbackQuery):
    help_text = (
        "🤖 **Доступні інструменти та функції:**\n\n"
        "1. **Пошук нікнейма** — перевіряє наявність акаунта за ніком у соцмережах.\n"
        "2. **Shodan** — пошук інформації про відкриті порти, сервери та пристрої за IP чи доменом.\n"
        "3. **IntelX** — пошук зливів даних, даркнету та архівів за поштою чи ключовим словом.\n"
        "4. **EPIOS** — зв'язування Gmail із сервісами Google (відгуки, карти).\n"
        "5. **Wayback Machine** — перегляд старих/видалених версій сайту.\n"
        "6. **Аналіз фото (EXIF)** — надішліть будь-яке фото як файл, щоб спробувати витягнути з нього координати та характеристики камери."
    )
    await callback.message.edit_text(help_text, reply_markup=get_main_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "search_nick")
async def ask_username(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введіть нікнейм для пошуку (наприклад, `durov`):")
    await state.set_state(SearchStates.waiting_for_username)
    await callback.answer()

@dp.callback_query(F.data == "search_ip")
async def ask_ip(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введіть IP-адресу або домен для перевірки через Shodan:")
    await state.set_state(SearchStates.waiting_for_ip_domain)
    await callback.answer()

@dp.callback_query(F.data == "search_intelx")
async def ask_intelx(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введіть email, домен або ключове слово для пошуку в IntelX:")
    await state.set_state(SearchStates.waiting_for_email)
    await callback.answer()

@dp.callback_query(F.data == "search_epios")
async def ask_epios(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введіть Gmail-адресу для перевірки через EPIOS:")
    await state.set_state(SearchStates.waiting_for_email)
    await callback.answer()

@dp.callback_query(F.data == "way
