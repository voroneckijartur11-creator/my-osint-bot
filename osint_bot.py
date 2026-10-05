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

# Вставте свій токен Telegram бота
TOKEN = "ТУТ_ВАШ_ТОКЕН_БОТА"

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
async def help_callback(callback: types.CallbackInfo):
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
async def ask_username(callback: types.CallbackInfo, state: FSMContext):
    await callback.message.answer("Введіть нікнейм для пошуку (наприклад, `durov`):")
    await state.set_state(SearchStates.waiting_for_username)
    await callback.answer()

@dp.callback_query(F.data == "search_ip")
async def ask_ip(callback: types.CallbackInfo, state: FSMContext):
    await callback.message.answer("Введіть IP-адресу або домен для перевірки через Shodan:")
    await state.set_state(SearchStates.waiting_for_ip_domain)
    await callback.answer()

@dp.callback_query(F.data == "search_intelx")
async def ask_intelx(callback: types.CallbackInfo, state: FSMContext):
    await callback.message.answer("Введіть email, домен або ключове слово для пошуку в IntelX:")
    await state.set_state(SearchStates.waiting_for_email)
    await callback.answer()

@dp.callback_query(F.data == "search_epios")
async def ask_epios(callback: types.CallbackInfo, state: FSMContext):
    await callback.message.answer("Введіть Gmail-адресу для перевірки через EPIOS:")
    await state.set_state(SearchStates.waiting_for_email) # Можна використати той самий стан або створити окремий
    await callback.answer()

@dp.callback_query(F.data == "wayback_check")
async def ask_wayback(callback: types.CallbackInfo, state: FSMContext):
    await callback.message.answer("Введіть URL сайту (наприклад, `example.com`), щоб перевірити його архівні копії:")
    await state.set_state(SearchStates.waiting_for_web_archive)
    await callback.answer()


# --- ВИКОНАННЯ ПОШУКУ ЗА НІКНЕЙМОМ ---
@dp.message(SearchStates.waiting_for_username)
async def process_username(message: types.Message, state: FSMContext):
    username = message.text.strip()
    await message.answer(f"⏳ Шукаю нікнейм `{username}` на популярних платформах...")
    
    # Приклад перевірки кількох базових платформ через асинхронні запити
    platforms = {
        "GitHub": f"https://github.com/{username}",
        "Instagram": f"https://instagram.com/{username}",
        "TikTok": f"https://tiktok.com/@{username}",
        "Twitter (X)": f"https://twitter.com/{username}",
        "Telegram": f"https://t.me/{username}"
    }
    
    results = []
    async with aiohttp.ClientSession() as session:
        for name, url in platforms.items():
            try:
                async with session.get(url, timeout=5) as response:
                    if response.status == 200:
                        results.append(f"✅ **{name}**: {url}")
                    else:
                        results.append(f"❌ **{name}**: не знайдено")
            except:
                results.append(f"⚠️ **{name}**: помилка перевірки")
                
    response_text = f"Результати пошуку для `{username}`:\n\n" + "\n".join(results)
    await message.answer(response_text, reply_markup=get_main_keyboard())
    await state.clear()


# --- ОБРОБКА IP / ДОМЕНУ (SHODAN) ---
@dp.message(SearchStates.waiting_for_ip_domain)
async def process_ip(message: types.Message, state: FSMContext):
    query = message.text.strip()
    shodan_url = f"https://www.shodan.io/search?query={query}"
    censys_url = f"https://search.censys.io/search?resource=hosts&q={query}"
    
    text = (
        f"🌐 **Результати для запиту:** `{query}`\n\n"
        f"🔗 [Перевірити в Shodan]({shodan_url})\n"
        f"🔗 [Перевірити в Censys]({censys_url})"
    )
    await message.answer(text, reply_markup=get_main_keyboard(), disable_web_page_preview=True)
    await state.clear()


# --- ОБРОБКА INTELX / EPIOS ---
@dp.message(SearchStates.waiting_for_email)
async def process_email_intelx(message: types.Message, state: FSMContext):
    query = message.text.strip()
    intelx_url = f"https://intelx.io/?s={query}"
    epios_url = f"https://epios.fr/"
    
    text = (
        f"📦 **Інформація для запиту:** `{query}`\n\n"
        f"🔗 [Шукати в Intelligence X (IntelX)]({intelx_url})\n"
        f"🔗 [Перевірити через EPIOS (Google ID)]({epios_url})"
    )
    await message.answer(text, reply_markup=get_main_keyboard(), disable_web_page_preview=True)
    await state.clear()


# --- ОБРОБКА WAYBACK MACHINE ---
@dp.message(SearchStates.waiting_for_web_archive)
async def process_wayback(message: types.Message, state: FSMContext):
    url = message.text.strip()
    wayback_url = f"https://web.archive.org/web/*/{url}"
    
    text = (
        f"⏪ **Архівні копії для сайту:** `{url}`\n\n"
        f"🔗 [Відкрити в Wayback Machine]({wayback_url})"
    )
    await message.answer(text, reply_markup=get_main_keyboard(), disable_web_page_preview=True)
    await state.clear()


# --- АНАЛІЗ МЕТАДАНІВ ФОТО (EXIF / EXIFTOOL АНАЛОГ) ---
@dp.message(F.photo | F.document)
async def handle_photo(message: types.Message):
    # Визначаємо файл (фото або документ з картинкою)
    if message.photo:
        file_id = message.photo[-1].file_id
    else:
        if message.document.mime_type and 'image' in message.document.mime_type:
            file_id = message.document.file_id
        else:
            await message.answer("Будь ласка, надішліть зображення для аналізу метаданих.")
            return

    await message.answer("🔍 Завантажую та аналізую метадані фото...")

    file_info = await bot.get_file(file_id)
    file_path = file_info.file_path
    
    # Завантажуємо файл у пам'ять
    photo_bytes = io.BytesIO()
    await bot.download_file(file_path, destination=photo_bytes)
    photo_bytes.seek(0)

    try:
        image = Image.open(photo_bytes)
        exif_data = image._getexif()
        
        if not exif_data:
            await message.answer("⚠️ На жаль, у цьому фото відсутні EXIF-метадані (можливо, вони були видалені соцмережами під час пересилання).")
            return

        exif_info = []
        gps_info = {}

        for tag_id, value in exif_data.items():
            tag = TAGS.get(tag_id, tag_id)
            if tag == "GPSInfo":
                for gps_tag_id in value:
                    gps_tag = GPSTAGS.get(gps_tag_id, gps_tag_id)
                    gps_info[gps_tag] = value[gps_tag_id]
            else:
                # Обрізаємо занадто довгі значення бінарних даних
                if isinstance(value, bytes):
                    value = "<бінарні дані>"
                exif_info.append(f"• **{tag}**: {value}")

        response_text = "📸 **Знайдені метадані фото (EXIF):**\n\n" + "\n".join(exif_info[:15]) # Обмежуємо першими 15 полями
        
        if gps_info:
            response_text += "\n\n📍 **Виявлено GPS-дані у файлі!**"

        if len(response_text) > 4096:
            response_text = response_text[:4090] + "..."

        await message.answer(response_text, reply_markup=get_main_keyboard())

    except Exception as e:
        await message.answer(f"❌ Поשilка при читанні метаданих: {e}")

# Запуск бота
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
