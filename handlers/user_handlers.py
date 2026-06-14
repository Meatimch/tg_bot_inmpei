from datetime import datetime
import sqlite3
import re

from database.users import get_users_database_values

bot = None
User = None
user_isStart = None
user_states = None


def init(bot_obj, User_class, user_isStart_dict, user_states_dict, tg_id_admin_list):
    global bot, User, user_isStart, user_states
    bot = bot_obj
    User = User_class
    user_isStart = user_isStart_dict
    user_states = user_states_dict
    global tg_id_admin
    tg_id_admin = tg_id_admin_list

    # Register handlers at runtime
    bot.message_handler(commands=['start'])(start)
    bot.message_handler(commands=['report'])(report)
    bot.message_handler(commands=['help'])(help_cmd)
    bot.message_handler(commands=['register'])(register)
    bot.message_handler(commands=['1register_1'])(register_1)
    bot.message_handler(commands=['edit'])(edit)
    bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == waiting_name)(handle_fio)
    bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == waiting_group)(handle_group)
    # Catch-all fallback routed to user state processor
    bot.message_handler(func=lambda message: True)(fallback_handler)


waiting_name = 'waiting_name'
waiting_group = 'waiting_group'


def is_cyrrillic_and_spaces(string) -> bool:
    pattern = r'^[\u0400-\u04FF\s]+$'
    return bool(re.match(pattern, string))


def is_vk_link(url) -> bool:
    pattern = r'^(https?://)?(www\.)?(vk\.com|vkontakte\.ru)/([a-zA-Z0-9._-]+|id\d+)$'
    return bool(re.match(pattern, url))


def start(message):
    user_isStart[message.from_user.id] = True
    user_states[message.from_user.id] = ' '
    if type(message.from_user.username) is str:
        print(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), ' :Выполнение команды /start пользователем @'
              + message.from_user.username)
        bot.send_message(message.chat.id, text='Привет! Это бот Института наставничества МЭИ, узнать список доступных команд можно с помощью /help')
        User(tg_user_id=message.from_user.id, tg_name=message.from_user.username)
    else:
        print(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), ' :Выполнение команды /start пользователем '
              + str(message.from_user.id))
        bot.send_message(message.chat.id, text='Привет! Это бот Института наставничества МЭИ. Пожалуйста установи имя пользователя в настройках телеграма для доступа к боту.')


def report(message):
    if not(message.from_user.id in user_isStart):
        User(tg_user_id=message.from_user.id, tg_name=message.from_user.username)
        user_isStart[message.from_user.id] = True
    if message.from_user.id in user_isStart:
        if user_isStart[message.from_user.id]:
            if type(message.from_user.username) is not None:
                print(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), ' :Выполнение команды /report пользователем @'
                      + message.from_user.username)
            else:
                print(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), ' :Выполнение команды /report пользователем '
                      + str(message.from_user.id))
            bot.send_message(message.chat.id, text = 'Здесь ты можешь предложить идеи по улучшению или сообщить об '
                                                     'ошибке и мы обязательно их учтём!')
            user_iswriting_report = {}
            user_iswriting_report[message.from_user.id] = True
            if not(message.from_user.id in user_states):
                user_states[message.from_user.id] = ' '


def help_cmd(message):
    if not(message.from_user.id in user_isStart):
        User(tg_user_id=message.from_user.id, tg_name=message.from_user.username)
        user_isStart[message.from_user.id] = True
    if message.from_user.id in user_isStart:
        if user_isStart[message.from_user.id]:
            if type(message.from_user.username) is not None:
                print(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), ' :Выполнение команды /help пользователем @'
                      + message.from_user.username)
            else:
                print(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), ' :Выполнение команды /help пользователем '
                      + str(message.from_user.id))
            bot.send_message(message.chat.id, text='Список доступных команд:'
                                                   '\n /help - список доступных команд'
                                                   '\n /register - регистрация в боте'
                                                   '\n /edit - изменение данных'
                                                   '\n /report - Предложить улучшение или сообщить об ошибке'
                                                   '\n /faq - Частые вопросы')


def register(message):
    if not (message.from_user.id in user_isStart):
        User(tg_user_id=message.from_user.id, tg_name=message.from_user.username)
        user_isStart[message.from_user.id] = True

    if message.from_user.id in user_isStart and user_isStart[message.from_user.id]:
        user_id = message.from_user.id

        # Проверяем, зарегистрирован ли пользователь
        conn = sqlite3.connect('pervaki.db')
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM pervaki WHERE tg_id = ?", (user_id,))
        already_registered = cursor.fetchone() is not None
        conn.close()

        if already_registered:
            bot.send_message(message.chat.id, "✅ Вы уже зарегистрированы!")
            return

        if type(message.from_user.username) is not None:
            print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} : /register @{message.from_user.username}")
        else:
            print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} : /register user_id={user_id}")

    # Начинаем процесс регистрации
    user_states[user_id] = waiting_name
    bot.send_message(
        message.chat.id,
        "Регистрация \n\n"
        "Пожалуйста, напишите своё ФИО в формате: Фамилия Имя Отчество"
    )


def register_1(message):
    if not(message.from_user.id in user_isStart):
        User(tg_user_id=message.from_user.id, tg_name=message.from_user.username)
        user_isStart[message.from_user.id] = True
    if message.from_user.id in user_isStart:
        pass


def edit(message):
    if not (message.from_user.id in user_isStart):
        User(tg_user_id=message.from_user.id, tg_name=message.from_user.username)
        user_isStart[message.from_user.id] = True
    if message.from_user.id in user_isStart:
        if user_isStart[message.from_user.id]:
            user_id = message.from_user.id
            if type(message.from_user.username) is not None:
                print(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), ' :Выполнение команды /edit пользователем @'
                      + message.from_user.username)
            else:
                print(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), ' :Выполнение команды /edit пользователем '
                      + str(message.from_user.id))
            is_already_recorded = False
            list_of_users = get_users_database_values()
            for i in range(0, len(list_of_users)):
                if list_of_users[i][0] == user_id:
                    is_already_recorded = True
                    break
            if is_already_recorded:
                user_states[user_id] = waiting_name
                bot.send_message(message.chat.id, text='Напиши своё ФИО в формате: Фамилия Имя Отчество')
            else:
                bot.send_message(message.chat.id, text='Вы ещё не зарегестрированны!')


def handle_fio(message):
    user_id = message.from_user.id
    if is_cyrrillic_and_spaces(message.text):
        user = User.find_user(user_id)
        if user:
            user.set_fio(message.text)
            user_states[user_id] = waiting_group
            bot.send_message(user_id, "✅ ФИО принято! Теперь укажите вашу группу в формате АБВ-11-11")
        else:
            bot.send_message(user_id, "❌ Ошибка: пользователь не найден. Начните регистрацию заново /register")
    else:
        bot.send_message(user_id, "❌ Пожалуйста, используйте только кириллицу и пробелы")


def handle_group(message):
    user_id = message.from_user.id
    group = message.text.upper()
    user = User.find_user(user_id)

    if user:
        user.set_group(group)

        # Сохраняем в БД
        conn = sqlite3.connect('pervaki.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO pervaki (tg_id, fio, "group")
            VALUES (?, ?, ?)
        ''', (user_id, user.get_fio, group))
        conn.commit()
        conn.close()

        # Завершаем регистрацию
        del user_states[user_id]
        bot.send_message(
            user_id,
            f"✅ Регистрация завершена!\n\n"
            f"ФИО: {user.get_fio}\n"
            f"Группа: {group}"
        )
    else:
        bot.send_message(user_id, "❌ Ошибка: пользователь не найден. Начните регистрацию заново /register")


# Runtime state for reports
user_iswriting_report = {}


def process_report(message):
    user_id = message.from_user.id
    report_text = message.text

    for admin_id in tg_id_admin:
        try:
            bot.send_message(admin_id, f"📨 Репорт от @{message.from_user.username or user_id}:\n{report_text}")
        except Exception as e:
            print(f"Ошибка отправки админу {admin_id}: {str(e)}")

    bot.reply_to(message, "✅ Спасибо! Мы получили твое сообщение 🙌")
    user_iswriting_report[user_id] = False


def handle_user_states(message):
    """Обработка состояний пользователя (регистрация)"""
    user_id = message.from_user.id

    # Обработка состояний регистрации
    if user_id in user_states:
        state = user_states[user_id]

        # Состояние ожидания ФИО
        if state == waiting_name:
            if is_cyrrillic_and_spaces(message.text):
                user = User.find_user(user_id)
                if user:
                    user.set_fio(message.text)
                    user_states[user_id] = waiting_group
                    bot.send_message(user_id, "Отлично! Теперь укажи свою группу в формате АБВ-11-11")
                else:
                    bot.send_message(user_id, "Ошибка: пользователь не найден. Начните регистрацию заново /register")
            else:
                bot.send_message(user_id, "Пожалуйста, используйте только кириллицу и пробелы")
            return

        # Состояние ожидания группы
        elif state == waiting_group:
            user = User.find_user(user_id)
            if user:
                user.set_group(message.text.upper())

                # Сохраняем в БД первокурсников
                conn = __import__('sqlite3').connect('pervaki.db')
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO pervaki (tg_id, fio, "group")
                    VALUES (?, ?, ?)
                ''', (user_id, user.get_fio, user.get_group))
                conn.commit()
                conn.close()

                # Завершаем регистрацию
                del user_states[user_id]
                bot.send_message(user_id, "✅ Регистрация завершена!")
            else:
                bot.send_message(user_id, "Ошибка: пользователь не найден. Начните регистрацию заново /register")
            return

    # Обработка отчетов (если нужно)
    if user_id in user_iswriting_report and user_iswriting_report[user_id]:
        process_report(message)
        return


def fallback_handler(message):
    handle_user_states(message)