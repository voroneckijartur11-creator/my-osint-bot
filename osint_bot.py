@dp.message(SearchStates.waiting_for_dorks)
async def process_dorks(message: types.Message, state: FSMContext):
    query = message.text.strip()
    q_enc = query.replace(" ", "+")
    text = (
        f"🔍 **Google Dorks для запиту:** `{query}`\n\n"
        f"Натисніть на посилання для пошуку в Google:\n\n"
        f"👤 **Точний збіг у лапках:**\n🔗 [Шукати ПІБ у Google](https://www.google.com/search?q=%22{q_enc}%22)\n\n"
        f"🌐 **Пошук у соцмережах (LinkedIn / Facebook):**\n🔗 [Соцмережі](https://www.google.com/search?q=site%3Alinkedin.com+{q_enc}+OR+site%3Afacebook.com+{q_enc})\n\n"
        f"📄 **Документи та звіти (PDF/DOC):**\n🔗 [Файли](https://www.google.com/search?q=filetype%3Apdf+%22{q_enc}%22)"
    )
    await message.answer(text, reply_markup=get_main_keyboard(), disable_web_page_preview=True)
    await state.clear()
