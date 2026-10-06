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
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username
