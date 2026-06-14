import sqlite3
from telebot import types
from datetime import datetime
from telebot.apihelper import ApiTelegramException

from database.interviews import get_available_times
from database.users import get_user_info

bot = None
CallbackDataManager = None


def init(bot_instance, callback_manager):
    global bot, CallbackDataManager
    bot = bot_instance
    CallbackDataManager = callback_manager

    bot.callback_query_handler(func=lambda call: call.data.startswith('date_'))(handle_date_selection)
    bot.callback_query_handler(func=lambda call: call.data == "back_to_dates")(handle_back)
    bot.callback_query_handler(func=lambda call: call.data.startswith('time_'))(handle_time_selection)
    bot.callback_query_handler(func=lambda call: call.data.startswith('cancel_'))(handle_cancel_selection)


def handle_date_selection(call):
    try:
        selected_date = call.data.split('_', 1)[1]
        user_id = call.from_user.id
        times = get_available_times(selected_date)
        markup = types.InlineKeyboardMarkup(row_width=2)
        buttons = []
        for time_slot in times:
            start_time = time_slot['start_time']
            end_time = time_slot['end_time']
            time_str = f"{start_time}-{end_time}"
            buttons.append(
                types.InlineKeyboardButton(
                    text=time_str,
                    callback_data=f"time_{selected_date}_{start_time}"
                )
            )
        for i in range(0, len(buttons), 3):
            markup.row(*buttons[i:i+3])
        markup.add(types.InlineKeyboardButton("← Назад", callback_data="back_to_dates"))
        bot.edit_message_text(
            chat_id=user_id,
            message_id=call.message.message_id,
            text=f"Выбрана дата: {selected_date}\nВыберите время:",
            reply_markup=markup
        )
    except Exception as e:
        print(f"Ошибка обработки даты: {str(e)}")
        bot.answer_callback_query(call.id, "Ошибка при загрузке времени", show_alert=True)


def handle_back(call):
    try:
        markup = types.InlineKeyboardMarkup(row_width=2)
        # Reuse interview date buttons from service if available
        from services import interviews as svc_interviews
        buttons = svc_interviews.get_markup_dates()
        user_id = call.from_user.id
        for i in range(0, len(buttons), 3):
            chunk = buttons[i:i+3]
            if chunk:
                markup.row(*chunk)
        if buttons:
            bot.edit_message_text(
                chat_id=user_id,
                message_id=call.message.message_id,
                text="Вот доступные даты для записи:",
                reply_markup=markup
            )
        else:
            bot.edit_message_text(
                chat_id=user_id,
                message_id=call.message.message_id,
                text="Нет доступных дат для записи",
            )
    except Exception as e:
        print(f"Ошибка при возврате к датам: {e}")
        bot.answer_callback_query(call.id, "Ошибка", show_alert=True)


def write_signup_sobes(date, start_time, senior, junior, user_id):
    try:
        user_info = get_user_info(user_id) or ('', '', '', '')
        fio = user_info[0] if len(user_info) > 0 else ''
        inst = user_info[1] if len(user_info) > 1 else ''
        vk_link = user_info[2] if len(user_info) > 2 else ''
        tg_name = user_info[3] if len(user_info) > 3 else ''

        conn = sqlite3.connect('sobes_signup.db', check_same_thread=False)
        conn.isolation_level = None
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sobes (
                date TEXT,
                start_time TEXT,
                star TEXT,
                mlad TEXT,
                kand TEXT,
                inst TEXT,
                vk_link TEXT,
                tg_name TEXT,
                tg_id INTEGER
            )
        ''')
        cursor.execute('''
            INSERT INTO sobes (date, start_time, star, mlad, kand, inst, vk_link, tg_name, tg_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (date, start_time, senior, junior, fio, inst, vk_link, tg_name, user_id))
        conn.commit()
    except Exception as e:
        print(f"Ошибка записи sobes: {e}")
    finally:
        if 'conn' in locals():
            conn.close()


def handle_time_selection(call):
    try:
        _, date_str_dd_mm, start_time = call.data.split('_')
        user_id = call.from_user.id
        # validate user registration
        user_info = get_user_info(user_id)
        if not user_info:
            bot.edit_message_text(
                chat_id=user_id,
                message_id=call.message.message_id,
                text="❌ Сначала пройдите регистрацию!\nДля регистрации введите /register",
            )
            return
        date_obj = datetime.strptime(f"{date_str_dd_mm}.2025", "%d.%m.%Y").date()
        date_yyyy_mm_dd = date_obj.isoformat()

        conn = sqlite3.connect('schedule.db', check_same_thread=False)
        conn.isolation_level = None
        cursor = conn.cursor()
        query = '''
        SELECT 
            s1.person_name as senior,
            s2.person_name as junior
        FROM schedule s1
        JOIN schedule s2 
            ON s1.date = s2.date 
            AND s1.start_time = s2.start_time 
            AND s1.is_starshiy_nast = 1 
            AND s2.is_starshiy_nast = 0 
            AND s1.available = 1 
            AND s2.available = 1 
            AND s1.is_interviewing = 0
            AND s2.is_interviewing = 0
            AND s1.person_name < s2.person_name
        WHERE 
            s1.date = ? 
            AND s1.start_time = ?
        ORDER BY RANDOM()
        LIMIT 1
        '''
        cursor.execute(query, (date_yyyy_mm_dd, start_time))
        pair = cursor.fetchone()
        if not pair:
            bot.answer_callback_query(call.id, "Нет доступных пар. Попробуйте записаться ещё раз", show_alert=True)
            return
        senior, junior = pair
        cursor.execute('''
            UPDATE schedule
            SET is_interviewing = 1
            WHERE 
                date = ? 
                AND start_time = ? 
                AND person_name IN (?, ?)
        ''', (date_yyyy_mm_dd, start_time, senior, junior))
        conn.commit()

        callback_id = CallbackDataManager.add_data({
            'date': date_yyyy_mm_dd,
            'start_time': start_time,
            'senior': senior,
            'junior': junior
        })

        # write signup into sobes DB
        write_signup_sobes(date_yyyy_mm_dd, start_time, senior, junior, user_id)

        markup = types.InlineKeyboardMarkup()
        cancel_button = types.InlineKeyboardButton(
            text="❌ Отменить запись",
            callback_data=f"cancel_{callback_id}"
        )
        markup.add(cancel_button)

        bot.edit_message_text(
            chat_id=user_id,
            message_id=call.message.message_id,
            text=f"Вы записались на интервью {date_str_dd_mm} на {start_time}\nОтменить запись можно не позднее, чем за сутки до интервью",
            reply_markup=markup
        )
    except Exception as e:
        print(f"Ошибка записи: {str(e)}")
        bot.answer_callback_query(call.id, "Ошибка записи", show_alert=True)
    finally:
        if 'conn' in locals():
            conn.close()


def handle_cancel_selection(call):
    try:
        callback_id = int(call.data.split('_')[1])
        data = CallbackDataManager.get_data(callback_id)
        if not data:
            raise ValueError("Данные не найдены")

        user_id = call.from_user.id
        date_str = data['date']
        start_time = data['start_time']
        senior = data['senior']
        junior = data['junior']

        datetime_str = f"{date_str} {start_time}"
        appointment_datetime = datetime.strptime(datetime_str, "%Y-%m-%d %H:%M")
        current_datetime = datetime.now()
        time_difference = (appointment_datetime - current_datetime).total_seconds()

        if time_difference <= 24 * 3600:
            bot.answer_callback_query(
                call.id,
                "❌ Отмена невозможна: до записи осталось менее cуток",
                show_alert=True
            )
            return

        conn = sqlite3.connect('sobes_signup.db', check_same_thread=False)
        conn.isolation_level = None
        cursor = conn.cursor()
        cursor.execute('''
            DELETE FROM sobes 
            WHERE 
                date = ? 
                AND start_time = ? 
                AND tg_id = ?
        ''', (date_str, start_time, user_id))

        schedule_conn = sqlite3.connect('schedule.db', check_same_thread=False)
        schedule_conn.isolation_level = None
        schedule_cursor = schedule_conn.cursor()
        schedule_cursor.execute('''
            UPDATE schedule
            SET available = 1
            WHERE 
                date = ? 
                AND start_time = ? 
                AND person_name IN (?, ?)
                AND is_interviewing = ?
        ''', (date_str, start_time, senior, junior, False))
        conn.commit()
        schedule_conn.commit()
        print(f"Отмена записи пользователем {user_id}: {date_str} {start_time} {senior} {junior}")
        bot.edit_message_text(
            chat_id=user_id,
            message_id=call.message.message_id,
            text="❌ Запись успешно отменена"
        )

    except Exception as e:
        print(f" Ошибка отмены: {str(e)}")
        bot.answer_callback_query(call.id, "❌ Ошибка при отмене записи", show_alert=True)
    finally:
        if 'conn' in locals():
            conn.close()
        if 'schedule_conn' in locals():
            schedule_conn.close()
