bot.send_message(message.chat.id, text, parse_mode="Markdown")
            return
        except Exception:
            bot.send_message(message.chat.id, f"🚗 Автономер {clean_car_num} має правильний формат.")
            return

    # 3. ПЕРЕВІРКА НОМЕРА ТЕЛЕФОНУ
    if data.startswith('+') or (data.isdigit() and len(data) >= 9):
        try:
            parsed_num = phonenumbers.parse(data, "UA")
            country = geocoder.description_for_number(parsed_num, "uk")
            operator = carrier.name_for_number(parsed_num, "uk")
            valid = phonenumbers.is_valid_number(parsed_num)
            
            res = f"📱 Результат по номеру {data}:\n• Країна/Регіон: {country if country else 'Невідомо'}\n• Оператор: {operator if operator else 'Невідомо'}\n• Статус: {'Дійсний' if valid else 'Недійсний'}"
            bot.send_message(message.chat.id, res, parse_mode="Markdown")
            return
        except Exception:
            bot.send_message(message.chat.id, "❌ Помилка аналізу номера. Перевірте формат (+380...).")
            return

    # 4. ПЕРЕВІРКА EMAIL
    elif "@" in data:
        try:
            email_info = validate_email(data, check_deliverability=True)
            domain = email_info.domain
            bot.send_message(
                message.chat.id, 
                f"📧 Результат по email {data}:\n• Домен: {domain}\n• Статус: Формат і поштовий сервер дійсні!",
                parse_mode="Markdown"
            )
            return
        except EmailNotValidError:
            bot.send_message(message.chat.id, f"❌ Пошта {data} недійсна або не існує.", parse_mode="Markdown")
            return
        except Exception:
            bot.send_message(message.chat.id, f"📧 Результат по email {data}:\n• Формат правильний.", parse_mode="Markdown")
            return

    # 5. ПОШУК НІКНЕЙМУ В СОЦМЕРЕЖАХ ТА ГУГЛ-ДОРКИ
    else:
        username = data.lstrip('@')
        bot.send_message(message.chat.id, f"🔍 Шукаю профіль {username} у соцмережах...", parse_mode="Markdown")
        
        platforms = {
            "Telegram": f"https://t.me/{username}",
            "GitHub": f"https://github.com/{username}",
            "TikTok": f"https://www.tiktok.com/@{username}",
            "Reddit": f"https://www.reddit.com/user/{username}",
            "Pinterest": f"https://www.pinterest.com/{username}/"
        }
        
        found = []
        for name, url in platforms.items():
            try:
                r = requests.get(url, timeout=3, headers={"User-Agent": "Mozilla/5.0"})
                if r.status_code == 200:
                    found.append(f"• [{name}]({url})")
            except Exception:
                pass

        google_dork = f"https://www.google.com/search?q=%22{username}%22"
        
        res_text = f"👤 Пошук для нікнейму: {username}\n\n"
        if found:
            res_text += "✅ Знайдено можливі профілі:\n" + "\n".join(found) + "\n\n"
        else:
            res_text += "ℹ️ Прямих співпадінь на базових платформах не знайдено.\n\n"
            
        res_text += f"🔗 [Запустити пошук у Google Dorks]({google_dork})"
        
        bot.send_message(message.chat.id, res_text, parse_mode="Markdown", disable_web_page_preview=True)

bot.infinity_polling()
