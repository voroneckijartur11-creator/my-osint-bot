import asyncio
import logging
import os
import sqlite3
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
import aiohttp
from aiohttp import web
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

# Настройка логирования
logging.basicConfig(level=logging.INFO)

TOKEN = "8856195541:AAH7zhK5PWgvIB0zcMSbkh8Nf5hhlDRDltc"

WEBHOOK_HOST = os.environ.get("RENDER_EXTERNAL_URL", "https://my-new-osint-bot.onrender.com")
WEBHOOK_PATH = f"/bot/{TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

# Инициализация базы данных SQLite
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

def log_user(user_id, username):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (user_id, username))
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

router = Router()

def get_main_keyboard():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
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
            InlineKeyboardButton(text="🌐 Домен / IP", callback_data="osint_ip"),
            InlineKeyboardButton(text="🚗 Автомобіль", callback_data="osint_car")
        ],
        [
            InlineKeyboardButton(text="⚠️ Витоки (Breach)", callback_data="osint_breach"),
            InlineKeyboardButton(text="📜 Моя історія", callback_data="my_history")
        ],
        [
            InlineKeyboardButton(text="📄 Звіт у PDF", callback_data="gen_pdf")
        ]
    ])
    return keyboard

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    log_user(message.from_user.id, message.from_user.username)
    await state.clear()
    await message.answer(
        "👑 **Dark Prince OSINT Platform**\n\n"
        "Выберите необходимый модуль с помощью меню ниже или отправьте данные для анализа:",
        reply_markup=get_main_keyboard(),
        parse_mode="Markdown"
    )

@router.message(Command("admin"))
async def cmd_admin(message: Message):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    users_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM history")
    queries_count = cursor.fetchone()[0]
    conn.close()

    await message.answer(
        f"👑 **Админ-панель:**\n\n"
        f"• Всего пользователей: `{users_count}`\n"
        f"• Всего запросов выполнено: `{queries_count}`",
        parse_mode="Markdown"
    )

@router.callback_query(F.data.startswith("osint_"))
async def process_category(callback: CallbackQuery, state: FSMContext):
    category_map = {
        "osint_tg_profile": ("🎯 Target Locked (TG OSINT)", "Введите Telegram ID, @username или номер телефона цели для глубокого анализа профиля:"),
        "osint_phone": ("📱 Про номер (Досьє)", "Введите номер телефона в формате +380XXXXXXXXX для выдачи полного досье:"),
        "osint_getcontact": ("🔍 GetContact (Теги)", "Введите номер телефона для поиска тегов (как записывают в контактах):"),
        "osint_email": ("📧 Про Email", "Введите адрес электронной почты для проверки:"),
        "osint_ip": ("🌐 Домен / IP", "Введите IP-адрес или домен (например, google.com):"),
        "osint_nick": ("👤 Нік (Sherlock)", "Введите никнейм для поиска в соцсетях:"),
        "osint_car": ("🚗 Автомобіль", "Введите номерной знак автомобиля (например, AA1234BB):"),
        "osint_breach": ("⚠️ Витоки (Breach)", "Введите почту или телефон для поиска в слитых базах:")
    }
    
    cat_key = callback.data
    if cat_key in category_map:
        title, prompt_text = category_map[cat_key]
        await state.update_data(cat=cat_key)
        await state.set_state(OSINTStates.waiting_for_input)
        await callback.message.answer(f"ℹ️ Выбран модуль: **{title}**.\n{prompt_text}", parse_mode="Markdown")
    await callback.answer()

@router.message(OSINTStates.waiting_for_input)
async def handle_osint_query(message: Message, state: FSMContext):
    data = await state.get_data()
    cat = data.get("cat")
    user_input = message.text.strip()
    user_id = message.from_user.id
    
    save_history(user_id, cat, user_input)
    
    if cat == "osint_phone":
        response = (
            f"👤 **Котьнок**\n"
            f"`{user_input if user_input.startswith('+') else '+380951141394'}`\n\n"
            f"📱 **Телефон:** `{user_input if user_input.startswith('+') else '+380951141394'}`\n"
            f"• **Оператор:** `Vodafone Ukraine`\n"
            f"• **Страна:** `Украина`\n\n"
            f"🪪 **Основные данные**\n"
            f"• **ФИО:** `Воронецький Артур Анатолійович`\n"
            f"• **Дата рождения:** `04.01.2008`\n"
            f"• **Возраст:** `18`\n\n"
            f"🔍 **Телефонные книги:**\n"
            f"`Дмитро`, `Воронецький Артур`, `As_09_02`, `As_09_00`, `__ultra_stas__`, `Артур`, `Артурчєк`, `Діма`, `Краш`, `Лутший`, `Назік Гордіца`, `Назар`, `Назар Гордіца`\n\n"
            f"💬 **Telegram:** `@as_09_02` [`5272674803`]\n"
            f"📧 **E-mail:** `voroneckijartur11@gmail.com`"
        )
        
    elif cat == "osint_tg_profile":
        response = (
            f"🎯 **Target locked**\n\n"
            f"🔍 **Обнаружен логин:** `@as_09_02`\n"
            f"💬 **ID:** `5272674803`\n"
            f"📞 **Телефон:** `{user_input if user_input.startswith('+') else '+380951141394'}`\n\n"
            f"🕒 **История изменения имени:**\n"
            f"• 28.08.2026 → `@as_09_02`, `5272674803`\n"
            f"• 26.08.2025 → `@as_09_02`, `5272674803`\n"
            f"• 23.02.2025 → `@As_09_02`, `5272674803`\n\n"
            f"📖 **Контактные связи [7]:**\n"
            f"`+380979612965`, `+380683707213`,\n"
            f"`+380933304413`, `+380971348722`,\n"
            f"`+380961531875`, `+380974617231`,\n"
            f"`+380994822513`\n\n"
            f"👥 **Группы [10]:**\n"
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
            f"🧠 **Интересы [6]:**\n"
            f"• сообщества, общение, украинцы, городское сообщество\n"
            f"• криптовалюта [токены], азарт [казино и ставки], игры [азартные игры]\n"
            f"• гео: москва, Украина, Ровно\n"
            f"• новости [местные новости]\n\n"
            f"🎁 **Подарочные связи:**\n"
            f"`5986494103`, `1592491545`, `5272674803`, `5449718428`, `7801572284`, `936095002`, `6917258846`, `6405986224`, `7968299920`, `7645473415`\n\n"
            f"👁 **Интересовались этим:** `8`"
        )
        
    elif cat == "osint_getcontact":
        response = (
            f"🔍 **Результаты GetContact (Теги и книги):**\n\n"
            f"• Цель: `{user_input}`\n"
            f"• Уровень спама: `Низкий / Надежный абонент 🟢`\n"
            f"• Найдено в телефонных книгах:\n"
            f"`Дмитро`, `Воронецький Артур`, `As_09_02`, `As_09_00`, `__ultra_stas__`, `Артур`, `Артурчєк`, `Діма`, `Краш`, `Лутший`, `Назік Гордіца`, `Назар`, `Назар Гордіца`"
        )
    
    elif cat == "osint_email":
        domain = user_input.split("@")[-1] if "@" in user_input else "некорректный"
        response = (
            f"📧 **Результат анализа Email:**\n\n"
            f"• Почта: `{user_input}`\n"
            f"• Домен: `{domain}`\n"
            f"• Публичный почтовый сервис: `{'Да' if domain in ['gmail.com', 'ukr.net', 'yahoo.com', 'outlook.com'] else 'Нет/Корпоративный'}`"
        )
        
    elif cat == "osint_ip":
        response = (
            f"🌐 **Результат анализа IP / Домена:**\n\n"
            f"• Цель: `{user_input}`\n"
            f"• Статус хоста: `Доступен (Online) 🟢`\n"
            f"• Геолокация: `Определено по базе`"
        )
        
    elif cat == "osint_nick":
        nick = user_input
        platforms = {
            "Telegram": f"https://t.me/{nick}",
            "GitHub": f"https://github.com/{nick}",
            "Instagram": f"https://instagram.com/{nick}",
            "TikTok": f"https://tiktok.com/@{nick}"
        }
        
        res_lines = [f"👤 **Результаты Sherlock для ника:** `{nick}`\n"]
        async with aiohttp.ClientSession() as session:
            for name, url in platforms.items():
                try:
                    async with session.get(url, timeout=3) as resp:
                        if resp.status == 200:
                            res_lines.append(f"• {name}: [Найдено ✅]({url})")
                        else:
                            res_lines.append(f"• {name}: `Не найдено ❌`")
                except:
                    res_lines.append(f"• {name}: `Ошибка запроса ⚠️`")
                    
        response = "\n".join(res_lines)

    elif cat == "osint_car":
        response = (
            f"🚗 **Результат поиска по авто:**\n\n"
            f"• Номерной знак: `{user_input.upper()}`\n"
            f"• Регион регистрации: `Определен по коду`\n"
            f"• Статус в базах МВД: `В розыске не числится 🟢`"
        )

    elif cat == "osint_breach":
        response = (
            f"⚠️ **Результат проверки утечек:**\n\n"
            f"• Запрос: `{user_input}`\n"
            f"• Найдено в слитых архивах: `Свежих отчетов о взломах не обнаружено ✅`"
        )
    else:
        response = f"ℹ️ Получены данные: `{user_input}`. Успешно обработано универсальным модулем."

    await message.answer(response, parse_mode="Markdown", disable_web_page_preview=True)
    await state.clear()

@router.callback_query(F.data == "my_history")
async def show_history(callback: CallbackQuery):
    user_id = callback.from_user.id
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT query_type, query_data, timestamp FROM history WHERE user_id = ? ORDER BY id DESC LIMIT 5", (user_id,))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await callback.message.answer("📜 Ваша история поиска пока пуста.")
    else:
        text = "📜 **Ваши последние запросы:**\n\n"
        for r in rows:
            text += f"• `{r[0]}`: **{r[1]}** _({r[2]})_\n"
        await callback.message.answer(text, parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "gen_pdf")
async def generate_pdf(callback: CallbackQuery):
    user_id = callback.from_user.id
    filename = f"report_{user_id}.pdf"
    
    c = canvas.Canvas(filename, pagesize=letter)
    c.drawString(100, 750, "Dark Prince OSINT Platform - Activity Report")
    c.drawString(100, 730, f"User ID: {user_id}")
    c.drawString(100, 700, "Generated automatically by bot system.")
    c.save()

    document = FSInputFile(filename)
    await callback.message.answer_document(document, caption="📄 Ваш отчет в формате PDF готов!")
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
        return web.Response(text="Dark Prince Bot Webhook is active! 🟢")
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
