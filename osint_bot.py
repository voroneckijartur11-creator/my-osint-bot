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
import io

TOKEN = "8856195541:AAGe5Hi9-9BHlwPkATUw_qYta50i6qBujSc"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

def init_db():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, joined_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
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
    secure_pass = "".join(random.choice(string.ascii_letters +
