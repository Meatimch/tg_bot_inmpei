from datetime import datetime
import threading
from telebot.apihelper import ApiTelegramException

bot = None
tg_id_admin = None
admin_states = {}

import sqlite3
import time
from collections import defaultdict
from telebot import types
from database.interviews import get_freetime_table
from database.homework import get_current_day, update_status
from services import google_sheets

# Globals for notifications
notification_storage = {}
db_notification_storage = {}


def init(bot_obj, tg_admin_list):
    global bot, tg_id_admin
    bot = bot_obj
    tg_id_admin = tg_admin_list

    bot.message_handler(commands=['admin'])(admin_cmd)
    bot.message_handler(commands=['send_message'])(handle_send_message)
    bot.message_handler(commands=['get_timetable'])(get_timetable)
    bot.message_handler(commands=['next_day'])(force_next_day)
    bot.message_handler(commands=['export_homework_answers'])(handle_export_homework_answers)
    bot.message_handler(commands=['export_interviews'])(handle_export_interviews)
    bot.message_handler(func=lambda m: m.from_user.id in admin_states and admin_states[m.from_user.id]['step'] == waiting_user_id)(handle_user_id_input)
    bot.message_handler(func=lambda m: m.from_user.id in admin_states and admin_states[m.from_user.id]['step'] == waiting_message_text)(handle_message_text_input)
    # register notification handlers (mass_notify, notify_nastavniki, callbacks)
    _register_notification_handlers()


waiting_user_id = 'waiting_user_id'
waiting_message_text = 'waiting_message_text'


def admin_cmd(message):
    if int(message.from_user.id) in tg_id_admin:
        sp = ('Список команд:'
              '\n/admin'
              '\n /kill - не функционирует на данный момент'
              '\n /get_timetable - Выгружает данные о свободном времени в бд бота'
              '\n /export_interviews - выгружает данные о записи на интервью из бд бота в гугл таблицы'
              '\n /fast - команда для точечной отладки разработчиком'
              '\n /mass_notify - рассылка всем пользователям'
              '\n /send_homework - выслать домашку'
              '\n /export_homework_answers - экспорт в гугл таблицу')
        bot.send_message(message.chat.id, text=sp)


def handle_send_message(message):
    if message.from_user.id not in tg_id_admin:
        bot.reply_to(message, "❌ Команда доступна только администраторам")
        return

    admin_states[message.from_user.id] = {'step': waiting_user_id}
    bot.send_message(message.chat.id, "Пришлите ID пользователя, которому хотите отправить сообщение:")


def handle_user_id_input(message):
    try:
        user_id = int(message.text.strip())
        admin_states[message.from_user.id] = {
            'step': waiting_message_text,
            'target_user_id': user_id
        }
        bot.send_message(message.chat.id, "Теперь введите текст сообщения:")
    except ValueError:
        bot.send_message(message.chat.id, "❌ Неверный формат ID. Пришлите числовой ID пользователя:")


def handle_message_text_input(message):
    admin_data = admin_states[message.from_user.id]
    target_user_id = admin_data['target_user_id']
    text = message.text

    try:
        bot.send_message(target_user_id, f"📨 Сообщение от администратора:\n\n{text}")
        bot.send_message(message.chat.id, f"✅ Сообщение успешно отправлено пользователю с ID {target_user_id}")
    except ApiTelegramException as e:
        if hasattr(e, 'result') and getattr(e.result, 'status_code', None) == 403:
            bot.send_message(message.chat.id, "❌ Пользователь заблокировал бота или не начинал с ним диалог")
        else:
            bot.send_message(message.chat.id, f"❌ Ошибка при отправке сообщения: {str(e)}")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Произошла ошибка: {str(e)}")

    # Сбрасываем состояние
    admin_states.pop(message.from_user.id, None)


def mass_notify(message):
    if message.from_user.id not in tg_id_admin:
        bot.reply_to(message, "❌ Команда доступна только администраторам")
        return

    msg = bot.send_message(message.chat.id, "Введите текст для рассылки:")
    bot.register_next_step_handler(msg, process_notify_text)


def process_notify_text(message):
    text_to_send = message.text
    confirm_msg = f"Вы уверены, что хотите разослать это сообщение?\n\n{text_to_send}"

    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("✅ Да", callback_data="confirm_notify"),
        types.InlineKeyboardButton("❌ Отмена", callback_data="cancel_notify")
    )

    sent_msg = bot.send_message(message.chat.id, confirm_msg, reply_markup=markup)
    notification_storage[sent_msg.message_id] = text_to_send


def confirm_notification(call):
    try:
        text_to_send = notification_storage.get(call.message.message_id)
        if not text_to_send:
            bot.answer_callback_query(call.id, "❌ Текст рассылки не найден")
            return

        conn = sqlite3.connect('users_database.db')
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT tg_id FROM users WHERE tg_id IS NOT NULL")
        user_ids = [row[0] for row in cursor.fetchall()]
        conn.close()

        total = len(user_ids)
        success = failed = blocked = 0

        bot.answer_callback_query(call.id, "⏳ Начинаю рассылку...")
        bot.delete_message(call.message.chat.id, call.message.message_id)

        DELAY = 2
        BATCH_SIZE = 20
        progress_msg = bot.send_message(call.message.chat.id, "🔄 Рассылка начата...")

        for idx, user_id in enumerate(user_ids, 1):
            try:
                bot.send_message(user_id, text_to_send)
                success += 1
                if idx % BATCH_SIZE == 0:
                    progress = (
                        f"Прогресс: {idx}/{total}\n"
                        f"✅ Успешно: {success}\n"
                        f"❌ Ошибок: {failed}\n"
                        f"🚫 Заблокировали: {blocked}"
                    )
                    bot.edit_message_text(progress, progress_msg.chat.id, progress_msg.message_id)
                time.sleep(DELAY)
            except ApiTelegramException as e:
                if hasattr(e, 'result') and getattr(e.result, 'status_code', None) == 403:
                    blocked += 1
                failed += 1
            except Exception:
                failed += 1

        report = (
            f"📊 Итоги рассылки:\n"
            f"Всего получателей: {total}\n"
            f"✅ Успешно: {success}\n"
            f"❌ Ошибок: {failed}\n"
            f"🚫 Заблокировали бота: {blocked}"
        )

        if call.message.message_id in notification_storage:
            del notification_storage[call.message.message_id]

        bot.edit_message_text(report, progress_msg.chat.id, progress_msg.message_id)

    except Exception as e:
        bot.edit_message_text(f"❌ Критическая ошибка: {str(e)}", progress_msg.chat.id, progress_msg.message_id)


def cancel_notification(call):
    bot.edit_message_text("❌ Рассылка отменена", call.message.chat.id, call.message.message_id)
    bot.answer_callback_query(call.id)


# ---- Notify nastavniki block ----
def notify_nastavniki(message):
    if message.from_user.id not in tg_id_admin:
        bot.reply_to(message, "❌ Только админы могут запускать рассылку")
        return
    sent = bot.send_message(message.chat.id, "Введите текст для рассылки наставникам:")
    bot.register_next_step_handler(sent, process_nastavniki_notify_text)


def process_nastavniki_notify_text(message):
    text = message.text.strip()
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("✅ Да — рассылать", callback_data="confirm_nast_notify"),
        types.InlineKeyboardButton("❌ Отмена", callback_data="cancel_nast_notify")
    )
    preview = bot.send_message(message.chat.id, f"Будет разослано всем наставникам:\n\n{text}", reply_markup=markup)
    db_notification_storage[preview.message_id] = text


def confirm_nast_notify(call):
    bot.answer_callback_query(call.id, text="⏳ Начинаю рассылку...")
    text = db_notification_storage.pop(call.message.message_id, None)
    if not text:
        bot.edit_message_text("❌ Текст рассылки не найден или уже отправлен", call.message.chat.id, call.message.message_id)
        return

    conn = sqlite3.connect('nastavniki.db', check_same_thread=False)
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT tg_id
        FROM matched_users
        WHERE typeof(tg_id) = 'integer'
    """)
    user_ids = [row[0] for row in cur.fetchall()]
    conn.close()

    total = len(user_ids)
    success = failed = blocked = 0
    progress = bot.send_message(call.message.chat.id, f"🔄 Рассылка: 0/{total}")

    DELAY = 2
    BATCH = 20

    for idx, uid in enumerate(user_ids, start=1):
        try:
            bot.send_message(uid, text)
            success += 1
        except ApiTelegramException as e:
            if hasattr(e, 'result') and getattr(e.result, 'status_code', None) == 403:
                blocked += 1
            failed += 1
        except Exception:
            failed += 1

        if idx % BATCH == 0 or idx == total:
            bot.edit_message_text(
                f"🔄 Рассылка: {idx}/{total}\n" f"✅ Успешно: {success}\n" f"❌ Ошибок: {failed}\n" f"🚫 Заблокировали: {blocked}",
                progress.chat.id, progress.message_id
            )
        time.sleep(DELAY)

    bot.edit_message_text(
        f"📊 Итоги рассылки:\n" f"Всего получателей: {total}\n" f"✅ Успехов: {success}\n" f"❌ Ошибок: {failed}\n" f"🚫 Заблокировали: {blocked}",
        progress.chat.id, progress.message_id
    )


def cancel_nast_notify(call):
    bot.answer_callback_query(call.id)
    db_notification_storage.pop(call.message.message_id, None)
    bot.edit_message_text("❌ Рассылка отменена", call.message.chat.id, call.message.message_id)


def get_timetable(message):
    if int(message.from_user.id) in tg_id_admin:
        try:
            print(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), ' :Начало выполнения команды /get_timetable пользователем @'
                  + message.from_user.username)
            get_freetime_table('Опытные эксперты', True)
            get_freetime_table('Младшие эксперты', False)
            print(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), ' :Успешное окончание выполнения команды /get_timetable пользователем @'
                  + message.from_user.username)
        except Exception as e:
            bot.send_message(message.chat.id, f"Ошибка выполнения /get_timetable: {str(e)}")


def force_next_day(message):
    if message.from_user.id not in tg_id_admin:
        return

    current_day, _ = get_current_day()
    if current_day >= 8:
        bot.reply_to(message, "❌ Все дни рассылки уже завершены (23.04-30.04.2025).")
        return

    new_day = current_day + 1
    update_status(new_day, 0)  # Сбрасываем индекс пользователя
    try:
        from handlers import homework_handlers
        date_str = homework_handlers.get_date_from_day(new_day)
    except Exception:
        date_str = str(new_day)
    bot.reply_to(message, f"✅ Принудительно начат день {new_day} ({date_str}). Индекс сброшен.")


def handle_export_homework_answers(message):
    if message.from_user.id not in tg_id_admin:
        bot.reply_to(message, "❌ Команда доступна только администраторам")
        return
    threading.Thread(target=google_sheets.export_homework_answers, args=(message, bot)).start()


def handle_export_interviews(message):
    if message.from_user.id not in tg_id_admin:
        bot.reply_to(message, "❌ Команда доступна только администраторам")
        return
    threading.Thread(target=google_sheets.export_interviews, args=(message, bot)).start()


# Register admin notification handlers
def _register_notification_handlers():
    bot.message_handler(commands=['mass_notify'])(mass_notify)
    bot.callback_query_handler(func=lambda call: call.data == "confirm_notify")(confirm_notification)
    bot.callback_query_handler(func=lambda call: call.data == "cancel_notify")(cancel_notification)
    bot.message_handler(commands=['notify_nastavniki'])(notify_nastavniki)
    bot.callback_query_handler(func=lambda call: call.data == "confirm_nast_notify")(confirm_nast_notify)
    bot.callback_query_handler(func=lambda call: call.data == "cancel_nast_notify")(cancel_nast_notify)
