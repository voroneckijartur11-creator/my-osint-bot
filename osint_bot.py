import telebot
import subprocess
import phonenumbers
from phonenumbers import carrier, geocoder

TOKEN = "8747134357:AAEFUq7uTrregLntvID-E_HI_TKDNiwCQ4M"
bot = telebot.TeleBot(TOKEN)

@bot.message_handler(commands=['start'])
def start_msg(message):
    bot.reply_to(message, "🔍 Привіт! Я твій швидкий та безкоштовний OSINT-бот.\n\n👉 Надішли мені:\n• email (перевірка реєстрацій)\n• номер телефону з + (країна та оператор)")

@bot.message_handler(func=lambda message: True)
def process_osint(message):
    data = message.text.strip()
    bot.reply_to(message, f"⚙️ Починаю миттєвий пошук для: {data}...")
    if data.startswith('+') or (data.isdigit() and len(data) > 9):
        try:
            parsed_num = phonenumbers.parse(data, "UA")
            country = geocoder.description_for_number(parsed_num, "uk")
            operator = carrier.name_for_number(parsed_num, "uk")
            valid = phonenumbers.is_valid_number(parsed_num)
            res = f"📱 Результат по номеру {data}:\n• Країна/Регіон: {country if country else 'Невідомо'}\n• Operator: {operator if operator else 'Невідомо'}\n• Status: {'Дійсний' if valid else 'Неіснуючий формат'}"
            bot.send_message(message.chat.id, res)
        except Exception:
            bot.send_message(message.chat.id, "❌ Помилка аналізу номера. Перевірте формат (+380...).")
    elif "@" in data:
        try:
            result = subprocess.check_output(f"holehe {data} --only-used", shell=True, text=True)
            if result.strip():
                bot.send_message(message.chat.id, f"🔒 Знайдено акаунти для пошти {data}:\n\n{result}")
            else:
                bot.send_message(message.chat.id, f"🟩 Пошта {data} чиста (активних реєстрацій не знайдено).")
        except Exception:
            bot.send_message(message.chat.id, "❌ Помилка роботи з поштою. Перевірте підключення до інтернету.")
    else:
        bot.send_message(message.chat.id, f"💡 Для безкоштовного пошуку нікнейму '{data}' без зависань бота, скористайся сайтом whatsmyname.app у браузері. Це значно швидше!")

print("🚀 Оновлений бот успішно запущений! Не закривайте це вікно.")
bot.infinity_polling()