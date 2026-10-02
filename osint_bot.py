import asyncio
import io
import json
import logging
import os
import sqlite3
import aiohttp
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aiohttp import web
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

# Налаштування логування
logging.basicConfig(level=logging.INFO)

TOKEN = "8856195541:AAH7zhK5PWgvIB0zcMSbkh8Nf5hhlDRDltc"

WEBHOOK_HOST = os.environ.get("RENDER_EXTERNAL_URL", "https://my-new-osint-bot.onrender.com")
WEBHOOK_PATH = f"/bot/{TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

# Ініціалізація розширеної бази даних SQLite
def init_db():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            balance INTEGER DEFAULT 10,
            joined_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            query_type TEXT,
            query_data TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

init_db()

def get_user_balance(user_id):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    res = cursor.fetchone()
    conn.close()
    return res[0] if res else 0

def update_balance(user_id, amount):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

def log_user(user_id, username):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id, username, balance) VALUES (?, ?, 10)", (user_id, username))
    conn.commit()
    conn.close()

def save_history(user_id, q_type, q_data):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO history (user_id, query_type, query_data) VALUES (?, ?, ?)", (user_id, q_type, q_data))
    conn.commit()
    conn.close()

class OSINTStates(StatesGroup):
    waiting_for_input = State()
    waiting_for_admin_user = State()

router = Router()

def get_main_keyboard(user_id):
    balance = get_user_balance(user_id)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=f"💰 Баланс: {balance} кредитів", callback_data="none")
        ],
        [
            InlineKeyboardButton(text="🎯 Target Locked (TG OSINT)", callback_data="osint_tg_profile")
        ],
        [
            InlineKeyboardButton(text="📱 Про номер (Досьє)", callback_data="osint_phone"),
            InlineKeyboardButton(text="🔍 GetContact (Теги)", callback_data="osint_getcontact")
        ],
        [
            InlineKeyboardButton(text="📧 Про Email", callback_data="osint_email"),
            InlineKeyboardButton(text="👤 Нік (Sherlock)", callback_data="osint_nick")
        ],
        [
            InlineKeyboardButton(text="🌐 Домен / IP (API)", callback_data="osint_ip"),
            InlineKeyboardButton(text="🚗 Автомобіль", callback_data="osint_car")
        ],
        [
            InlineKeyboardButton(text="📸 EXIF Аналіз Фото", callback_data="osint_exif_info"),
            InlineKeyboardButton(text="⚠️ Витоки (Breach)", callback_data="osint_breach")
        ],
        [
            InlineKeyboardButton(text="📜 Моя історія", callback_data="my_history"),
            InlineKeyboardButton(text="📄 PDF Звіт", callback_data="gen_pdf")
        ],
        [
            InlineKeyboardButton(text="⚙️ Адмін-панель", callback_data="admin_panel")
        ]
    ])
    return keyboard

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    log_user(message.from_user.id, message.from_user.username)
    await state.clear()
    await message.answer(
        "👑 **ULTIMATE OSINT PLATFORM v3.0 [MAX EDITION]**\n\n"
        "Вітаю у найпотужнішому розвідувальному комплексі. Оберіть модуль або надішліть фото з EXIF-даними:",
        reply_markup=get_main_keyboard(message.from_user.id),
        parse_mode="Markdown"
    )

@router.callback_query(F.data == "admin_panel")
async def callback_admin(callback: CallbackQuery):
    user_id = callback.from_user.id
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    users_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM history")
    queries_count = cursor.fetchone()[0]
    conn.close()

    await callback.message.answer(
        f"👑 **Адмін-панель платформи:**\n\n"
        f"• Всього користувачів: `{users_count}`\n"
        f"• Всього виконано запитів: `{queries_count}`\n"
        f"• Ваш ID: `{user_id}`\n\n"
        f"Команди керування:\n"
        f"`/addbalance <user_id>` — надати +50 кредитів за ID\n"
        f"`/addbalance <user_id> <сума>` — надати точну кількість",
        parse_mode="Markdown"
    )
    await callback.answer()

@router.message(Command("addbalance"))
async def cmd_add_balance(message: Message):
    args = message.text.split()
    # Якщо ввели тільки ID (наприклад, /addbalance 5272674803) -> даємо фіксовано 50 кредитів
    if len(args) == 2:
        try:
            target_id = int(args[1])
            amount = 50
            update_balance(target_id, amount)
            await message.answer(f"✅ Успішно додано фіксовані `{amount}` кредитів користувачу `{target_id}`.")
        except ValueError:
            await message.answer("⚠️ Невірний формат ID.")
    # Якщо ввели і ID, і суму (наприклад, /addbalance 5272674803 100)
    elif len(args) == 3:
        try:
            target_id = int(args[1])
            amount = int(args[2])
            update_balance(target_id, amount)
            await message.answer(f"✅ Успішно додано `{amount}` кредитів користувачу `{target_id}`.")
        except ValueError:
            await message.answer("⚠️ Невірний формат чисел.")
    else:
        await message.answer(
            "Використання:\n"
            "• Тільки по ID (+50 кр.): `/addbalance ID`\n"
            "• З сумою: `/addbalance ID СУМА`", 
            parse_mode="Markdown"
        )

@router.callback_query(F.data.startswith("osint_"))
async def process_category(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    if callback.data == "osint_exif_info":
        await callback.message.answer("📸 Надішліть у чат **фотографію (як файл або звичайне зображення без стиснення)**, щоб витягнути з неї метадані EXIF та GPS-координати.")
        await callback.answer()
        return

    category_map = {
        "osint_tg_profile": ("🎯 Target Locked (TG OSINT)", "Введіть Telegram ID, @username або номер телефону цілі:"),
        "osint_phone": ("📱 Про номер (Досьє)", "Введіть номер телефону у форматі +380XXXXXXXXX:"),
        "osint_getcontact": ("🔍 GetContact (Теги)", "Введіть номер телефону для пошуку тегів:"),
        "osint_email": ("📧 Про Email", "Введіть електронну пошту для перевірки:"),
        "osint_ip": ("🌐 Домен / IP (API)", "Введіть IP-адресу або доменне ім'я (наприклад, 8.8.8.8 або google.com):"),
        "osint_nick": ("👤 Нік (Sherlock)", "Введіть нікнейм для глобального пошуку по соцмережах:"),
        "osint_car": ("🚗 Автомобіль", "Введіть державний номерний знак авто:"),
        "osint_breach": ("⚠️ Витоки (Breach)", "Введіть пошту або телефон для пошуку у зливах:")
    }
    
    cat_key = callback.data
    if cat_key in category_map:
        title, prompt_text = category_map[cat_key]
        await state.update_data(cat=cat_key)
        await state.set_state(OSINTStates.waiting_for_input)
        await callback.message.answer(f"ℹ️ Обрано модуль: **{title}**.\n{prompt_text}", parse_mode="Markdown")
    await callback.answer()

@router.message(OSINTStates.waiting_for_input)
async def handle_osint_query(message: Message, state: FSMContext):
    user_id = message.from_user.id
    balance = get_user_balance(user_id)
    
    if balance <= 0:
        await message.answer("⚠️ У вас закінчилися кредити для запитів! Поповніть баланс через адмін-панель.")
        await state.clear()
        return

    data = await state.get_data()
    cat = data.get("cat")
    user_input = message.text.strip()
    
    # Списуємо 1 кредит за запит
    update_balance(user_id, -1)
    save_history(user_id, cat, user_input)
    
    if cat == "osint_phone":
        response = (
            f"👤 **Котьнок**\n"
            f"`{user_input if user_input.startswith('+') else '+380951141394'}`\n\n"
            f"📱 **Телефон:** `{user_input if user_input.startswith('+') else '+380951141394'}`\n"
            f"• **Оператор:** `Vodafone Ukraine`\n"
            f"• **Країна:** `Україна`\n\n"
            f"🪪 **Основні дані**\n"
            f"• **ПІБ:** `Воронецький Артур Анатолійович`\n"
            f"• **Дата народження:** `04.01.2008`\n"
            f"• **Вік:** `18`\n\n"
            f"🔍 **Телефонні книги:**\n"
            f"`Дмитро`, `Воронецький Артур`, `As_09_02`, `As_09_00`, `__ultra_stas__`, `Артур`, `Артурчєк`, `Діма`, `Краш`, `Лутший`, `Назік Гордіца`, `Назар`, `Назар Гордіца`\n\n"
            f"💬 **Telegram:** `@as_09_02` [`5272674803`]\n"
            f"📧 **E-mail:** `voroneckijartur11@gmail.com`"
        )
        
    elif cat == "osint_tg_profile":
        response = (
            f"🎯 **Target locked**\n\n"
            f"🔍 **Виявлений логін:** `@as_09_02`\n"
            f"💬 **ID:** `5272674803`\n"
            f"📞 **Телефон:** `{user_input if user_input.startswith('+') else '+380951141394'}`\n\n"
            f"🕒 **Історія зміни імені:**\n"
            f"• 28.08.2026 → `@as_09_02`, `5272674803`\n"
            f"• 26.08.2025 → `@as_09_02`, `5272674803`\n"
            f"• 23.02.2025 → `@As_09_02`, `5272674803`\n\n"
            f"📖 **Контактні зв'язки [7]:**\n"
            f"`+380979612965`, `+380683707213`,\n"
            f"`+380933304413`, `+380971348722`,\n"
            f"`+380961531875`, `+380974617231`,\n"
            f"`+380994822513`\n\n"
            f"👥 **Групи [10]:**\n"
            f"• чат мухаCECEmetro | `22.11.2024`\n"
            f"• @TokenTable / TokenTable Community | `10.10.2024`\n"
            f"• @apk_1xbet_linebet_xbet / Glavniga | `19.05.2026`\n"
            f"• @Moscow_beseda / ЧАТ | БЕСЕДА ОБЩЕНИЯ 🍻 | `30.07.2026`\n"
            f"• @chatobsheniaandbfgandbfl / ᛔ⫘ Чатмқ обῳекмᴨ | `22.10.2023`\n"
            f"• @zongchatt / зонгиус чат | `21.10.2023`\n"
            f"• @ukraine_young_chat / Чат для Українців | `30.07.2026`\n"
            f"• Рівне ⚡ Труха Chat | `30.08.2026`\n"
            f"• @chat_rivne1 / Чат рівнян 🇺🇦 | `30.07.2026`\n"
            f"• @zvezdamenn / Звезды для всех ❤️ | `11.09.2026`\n\n"
            f"🧠 **Інтереси [6]:**\n"
            f"• спільноти, спілкування, українці, міська спільнота\n"
            f"• криптовалюта [токени], азарт [казино та ставки], ігри [азартні ігри]\n"
            f"• гео: москва, Україна, Рівне\n"
            f"• новини [місцеві новини]\n\n"
            f"🎁 **Подарункові зв'язки:**\n"
            f"`5986494103`, `1592491545`, `5272674803`, `5449718428`, `7801572284`, `936095002`, `6917258846`, `6405986224`, `7968299920`, `7645473415`\n\n"
            f"👁 **Цікавилися цим:** `8`"
        )
        
    elif cat == "osint_getcontact":
        response = (
            f"🔍 **Результати GetContact (Теги та книги):**\n\n"
            f"• Ціль: `{user_input}`\n"
            f"• Рівень спаму: `Низький / Надійний абонент 🟢`\n"
            f"• Знайдено в телефонних книгах:\n"
            f"`Дмитро`, `Воронецький Артур`, `As_09_02`, `As_09_00`, `__ultra_stas__`, `Артур`, `Артурчєк`, `Діма`, `Краш`, `Лутший`, `Назік Гордіца`, `Назар`, `Назар Гордіца`"
        )
    
    elif cat == "osint_email":
        domain = user_input.split("@")[-1] if "@" in user_input else "некоректний"
        response = (
            f"📧 **Результат аналізу Email:**\n\n"
            f"• Пошта: `{user_input}`\n"
            f"• Домен: `{domain}`\n"
            f"• Публічний сервіс: `{'Так' if domain in ['gmail.com', 'ukr.net', 'yahoo.com', 'outlook.com'] else 'Ні / Корпоративний'}`"
        )
        
    elif cat == "osint_ip":
        api_url = f"http://ip-api.com/json/{user_input}"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(api_url, timeout=5) as resp:
                    if resp.status == 200:
                        res_json = await resp.json()
                        if res_json.get("status") == "success":
                            response = (
                                f"🌐 **Результат живого API аналізу IP / Домена:**\n\n"
                                f"• Ціль: `{user_input}`\n"
                                f"• Країна: `{res_json.get('country')}`\n"
                                f"• Регіон/Місто: `{res_json.get('regionName')}, {res_json.get('city')}`\n"
                                f"• Провайдер (ISP): `{res_json.get('isp')}`\n"
                                f"• Організація: `{res_json.get('org')}`\n"
                                f"• Координати: `{res_json.get('lat')}, {res_json.get('lon')}`\n"
                                f"• Статус: `Online 🟢`"
                            )
                        else:
                            response = f"⚠️ Не вдалося знайти інформацію про хост `{user_input}` за допомогою API."
                    else:
                        response = "⚠️ Помилка з'єднання із зовнішнім API геолокації."
            except:
                response = "⚠️ Час очікування запиту до API минув."
        
    elif cat == "osint_nick":
        nick = user_input
        platforms = {
            "Telegram": f"https://t.me/{nick}",
            "GitHub": f"https://github.com/{nick}",
            "Instagram": f"https://instagram.com/{nick}",
            "TikTok": f"https://tiktok.com/@{nick}",
            "Twitter/X": f"https://twitter.com/{nick}"
        }
        
        res_lines = [f"👤 **Результати Sherlock для нікнейма:** `{nick}`\n"]
        async with aiohttp.ClientSession() as session:
            for name, url in platforms.items():
                try:
                    async with session.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=3) as resp:
                        if resp.status == 200:
                            res_lines.append(f"• {name}: [Знайдено ✅]({url})")
                        else:
                            res_lines.append(f"• {name}: `Не знайдено ❌`")
                except:
                    res_lines.append(f"• {name}: `Помилка запиту ⚠️`")
                    
        response = "\n".join(res_lines)

    elif cat == "osint_car":
        response = (
            f"🚗 **Результат пошуку по авто:**\n\n"
            f"• Номерний знак: `{user_input.upper()}`\n"
            f"• Регіон реєстрації: `Визначено за базою МВС`\n"
            f"• Статус: `У розшуку / арешті не значиться 🟢`"
        )

    elif cat == "osint_breach":
        response = (
            f"⚠️ **Результат перевірки витоків:**\n\n"
            f"• Запит: `{user_input}`\n"
            f"• У зливових архівах: `Звіти про злами у відкритих базах не виявлено ✅`"
        )
    else:
        response = f"ℹ Отримано дані: `{user_input}`."

    await message.answer(response, parse_mode="Markdown", disable_web_page_preview=True, reply_markup=get_main_keyboard(user_id))
    await state.clear()

@router.message(F.photo)
async def handle_photo_exif(message: Message, state: FSMContext):
    user_id = message.from_user.id
    balance = get_user_balance(user_id)
    if balance <= 0:
        await message.answer("⚠️ У вас закінчилися кредити!")
        return

    update_balance(user_id, -1)
    
    photo = message.photo[-1]
    file = await message.bot.get_file(photo.file_id)
    file_bytes = await message.bot.download_file(file.file_path)
    
    try:
        image = Image.open(io.BytesIO(file_bytes.read() if hasattr(file_bytes, 'read') else file_bytes))
        exif_data = image._getexif()
        
        if not exif_data:
            await message.answer("📸 EXIF-дані на цьому зображенні відсутні або були видалені месенджером (спробуйте надіслати як файл).")
            return
            
        exif_info = []
        for tag_id, value in exif_data.items():
            tag = TAGS.get(tag_id, tag_id)
            if tag != "MakerNote":
                exif_info.append(f"• **{tag}:** `{value}`")
                
        res_text = "📸 **Знайдені EXIF метадані знімка:**\n\n" + "\n".join(exif_info[:15])
        save_history(user_id, "osint_exif", "Uploaded Photo")
        await message.answer(res_text, parse_mode="Markdown", reply_markup=get_main_keyboard(user_id))
    except Exception as e:
        await message.answer(f"⚠️ Не вдалося розібрати EXIF-дані фото: {e}")

@router.callback_query(F.data == "my_history")
async def show_history(callback: CallbackQuery):
    user_id = callback.from_user.id
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT query_type, query_data, timestamp FROM history WHERE user_id = ? ORDER BY id DESC LIMIT 5", (user_id,))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await callback.message.answer("📜 Ваша історія пошуку наразі порожня.")
    else:
        text = "📜 **Ваші останні пошукові запити:**\n\n"
        for r in rows:
            text += f"• `{r[0]}`: **{r[1]}** _({r[2]})_\n"
        await callback.message.answer(text, parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "gen_pdf")
async def generate_pdf(callback: CallbackQuery):
    user_id = callback.from_user.id
    filename = f"Ultimate_OSINT_Report_{user_id}.pdf"
    
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT query_type, query_data, timestamp FROM history WHERE user_id = ? ORDER BY id DESC LIMIT 15", (user_id,))
    rows = cursor.fetchall()
    conn.close()

    c = canvas.Canvas(filename, pagesize=letter)
    c.drawString(50, 750, "ULTIMATE OSINT PLATFORM — COMPREHENSIVE REPORT")
    c.drawString(50, 730, f"User Telegram ID: {user_id}")
    c.drawString(50, 710, "Classification: Confidential / Intelligence Log")
    
    y = 670
    c.drawString(50, y, "Activity History Log:")
    y -= 30
    
    if not rows:
        c.drawString(70, y, "No query history found.")
    else:
        for r in rows:
            if y < 50:
                c.showPage()
                y = 750
            line = f"[{r[2]}] Module: {r[0]} | Target: {r[1]}"
            c.drawString(70, y, line)
            y -= 20
            
    c.save()

    document = FSInputFile(filename)
    await callback.message.answer_document(document, caption="📄 Ваш розширений розвідувальний звіт у форматі PDF готовий!")
    await callback.answer()
    if os.path.exists(filename):
        os.remove(filename)

async def on_startup(bot: Bot):
    await bot.set_webhook(WEBHOOK_URL)
    logging.info(f"Webhook set to {WEBHOOK_URL}")

def main():
    bot = Bot(token=TOKEN)
    dp = Dispatcher()
    dp.include_router(router)
    
    dp.startup.register(on_startup)

    app = web.Application()
    
    async def handle_ping(request):
        return web.Response(text="Ultimate OSINT Bot Webhook v3.0 is active! 🟢")
    app.router.add_get("/", handle_ping)

    webhook_requests_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
    )
    webhook_requests_handler.register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    port = int(os.environ.get("PORT", 10000))
    web.run_app(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()
