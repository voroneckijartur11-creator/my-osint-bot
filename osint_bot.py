import os
import asyncio
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton

TOKEN = "8747134357:AAFjsPvLaskM5TymQZoXzmpYWrfqVSkMzWE"

bot = Bot(token=TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)

@router.message(Command("start"))
async def cmd_start(message: Message):
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⚙️ Тест")]], resize_keyboard=True)
    await message.answer("🚀 Повна перевірка! Жодних каналів.", reply_markup=kb)

@router.message(F.text)
async def all_text(message: Message):
    await message.answer(f"Отримано: {message.text}")

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
