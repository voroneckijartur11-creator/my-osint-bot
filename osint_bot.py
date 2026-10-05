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

# Новий токен Telegram бота
TOKEN = "8856195541:AAE-ta26zPsqk5wESGjhmHMJGby9ljjVjKY"

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
        [InlineKeyboardButton(text="🕵 Пошук нікнейма (30+ платформ)", callback_data="search_nick")],
        [InlineKeyboardButton(text="🌐 Домени, IP & Whois (Shodan)", callback_data="search_ip")],
        [InlineKeyboardButton(text="📦 Зливи даних (IntelX / HIBP)", callback_data="search_intelx")],
        [InlineKeyboardButton(text="🗺️ Gmail (EPIOS) & Координати", callback_data="search_epios")],
        [InlineKeyboardButton(text="⏪ Архів сайту (Wayback)", callback_data="wayback_check")],
        [InlineKeyboardButton(text="🪙 Крипто-розвідка (BTC/ETH/TRON)", callback_data="crypto_check")],
        [InlineKeyboardButton(text="🛠️ Утиліти (Паролі / QR-коди)", callback_data="utilities_menu")],
        [InlineKeyboardButton(text="ℹ️ Про можливості бота", callback_data="help_info")]
    ])
    return
