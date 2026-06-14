import gspread
from telebot import types
from datetime import datetime
from database.interviews import counting_per_date, get_available_times
from database.users import get_user_info


def get_markup_dates():
    pairs = counting_per_date()
    buttons = []
    start_date = datetime.strptime("23.03.2025", "%d.%m.%Y").date()
    end_date = datetime.strptime("31.03.2025", "%d.%m.%Y").date()
    current_date = datetime.now().date()
    for pair in pairs:
        date_str, count = pair
        try:
            date_obj = datetime.strptime(f"{date_str}.2025", "%d.%m.%Y").date()
            if (current_date <= date_obj) and (date_obj < end_date) and (date_obj >= start_date) and (count > 1):
                if not((date_obj - current_date).total_seconds() <= 24 * 3600):
                    buttons.append(
                        types.InlineKeyboardButton(
                            text=date_str,
                            callback_data=f"date_{date_str}"
                        )
                    )
        except ValueError:
            continue
    return buttons


def signup(message, bot):
    user_info = get_user_info(message.from_user.id)
    if type(message.from_user.username) is not None:
        print(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), ' :Выполнение команды /signup пользователем @'
              + message.from_user.username)
    else:
        print(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), ' :Выполнение команды /signup пользователем '
              + str(message.from_user.id))
    if not user_info or not user_info[0] or not user_info[2]:  # [fio, group, vk_link, tg_name]
        bot.send_message(message.chat.id, "❌ Вы не прошли регистрацию в боте! Используйте /register")
        return
    fio, _, vk_link, _ = user_info
    try:
        gc = gspread.service_account(filename='creds.json')
        spreadsheet = gc.open("ГФ")
        worksheet = spreadsheet.worksheet('Все ответы')
        records = worksheet.get_all_values()
        user_vk = vk_link.split("vk.com/")[-1].strip().lower()
        found = False
        for row in records[1:]:
            row_fio = row[2].strip()
            row_vk = row[5].split("vk.com/")[-1].strip().lower() if row[5] else ''
            if row_fio == fio.strip() and row_vk == user_vk:
                found = True
                break
        if not found:
            bot.send_message(
                message.chat.id,
                "❌ Вы не заполняли Яндекс Форму регистрации!"
            )
            return
    except Exception as e:
        print(f"Ошибка доступа к Google Sheets: {str(e)}")
        bot.send_message(message.chat.id, "⚠️ Ошибка проверки данных, попробуйте позже")
        return

    conn = __import__('sqlite3').connect('sobes_signup.db', check_same_thread=False)
    conn.isolation_level = None
    cursor = conn.cursor()
    try:
        cursor.execute('''
        SELECT EXISTS(
            SELECT 1 
            FROM sobes 
            WHERE tg_id = ?
            LIMIT 1
        )
        ''', (message.from_user.id,))
        if cursor.fetchone()[0]:
            cursor.execute("SELECT * FROM sobes WHERE tg_id = ?", (message.from_user.id,))
            row = cursor.fetchone()
            date = datetime.strptime(row[0], "%Y-%m-%d").strftime("%d.%m")
            callback_id = None
            # The caller is expected to use CallbackDataManager for callback handling
            markup = types.InlineKeyboardMarkup()
            cancel_button = types.InlineKeyboardButton(
                text="❌ Отменить запись",
                callback_data=f"cancel_{callback_id}"
            )
            markup.add(cancel_button)
            bot.send_message(
                chat_id=message.chat.id,
                text=f"❌ Вы уже записаны на собеседование!\n {date} на {row[1]}",
                reply_markup=markup
            )
            return
    finally:
        conn.close()

    markup = types.InlineKeyboardMarkup(row_width=2)
    buttons = get_markup_dates()
    for i in range(0, len(buttons), 3):
        chunk = buttons[i:i+3]
        if chunk:
            markup.row(*chunk)
    if buttons:
        bot.send_message(
            chat_id=message.chat.id,
            text='Вот доступные даты для записи:',
            reply_markup=markup
        )
    else:
        bot.send_message(
            chat_id=message.chat.id,
            text='На это время нельзя записаться, так как нет свободных экспертов. Попробуйте выбрать другое'
        )
