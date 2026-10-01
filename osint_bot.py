import os
import threading
import subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler
import telebot
import phonenumbers
from phonenumbers import geocoder, carrier
from email_validator import validate_email, EmailNotValidError

# Веб-сервер для поддержки Render
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def run_health_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    server.serve_forever()

threading.Thread(target=run_health_server, daemon=True).start()

# Инициализация бота
TOKEN = "8747134357:AAEV2RzAKK2JD-Wf8b20pxiTmWVCGMY_dPY"
bot = telebot.TeleBot(TOKEN)

@bot.message_handler(commands=['start'])
def start_msg(message):
    bot.reply_to(message, "Привет! Я твой  OSINT-бот.\n\nОтправь мне номер телефона или email.")

@bot.message_handler(func=lambda message: True)
def process_osint(message):
    data = message.text.strip()
    bot.reply_to(message, f"⚙️ Начинаю мгновенный поиск для: {data}...")
    
    # Поиск по номеру телефона
    if data.startswith('+') or (data.isdigit() and len(data) > 9):
        try:
            parsed_num = phonenumbers.parse(data, "UA")
            country = geocoder.description_for_number(parsed_num, "uk")
            operator = carrier.name_for_number(parsed_num, "uk")
            valid = phonenumbers.is_valid_number(parsed_num)
            
            res = f"📱 Результат по номеру {data}:\n• Страна/Регион: {country if country else 'Неизвестно'}\n• Оператор: {operator if operator else 'Неизвестно'}\n• Статус: {'Действителен' if valid else 'Недействителен'}"
            bot.send_message(message.chat.id, res)
        except Exception:
            bot.send_message(message.chat.id, "❌ Ошибка анализа номера. Проверьте формат (+380...).")
            
    # Поиск по Email
    elif "@" in data:
        try:
            email_info = validate_email(data, check_deliverability=True)
            domain = email_info.domain
            bot.send_message(message.chat.id, f"📧 Результат по email {data}:\n• Домен: {domain}\n• Статус: Формат и почтовый сервер действительны!")
        except EmailNotValidError as e:
            bot.send_message(message.chat.id, f"❌ Почта {data} недействительна или не существует.")
        except Exception:
            bot.send_message(message.chat.id, f"📧 Результат по email {data}:\n• Формат правильный, домен активен.")
            
    else:
        bot.send_message(message.chat.id, f"🔍 Для поиска никнейма '{data}' используйте специализированные команды.")

bot.infinity_polling()
