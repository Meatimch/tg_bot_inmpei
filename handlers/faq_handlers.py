import sqlite3
from telebot import types

faq_user_state = {}  # { user_id: {'stage': ..., 'category': ...} }
faq_cat_map = {}  # { user_id: { idx_str: category_name } }
faq_question_map = {}  # { user_id: { idx_str: real_faq_id } }

bot = None
TG_ADMINS = []
PHOTO_DIR = 'photos'
DB_PATH = 'faq.db'


def start_faq(message):
    uid = message.from_user.id
    if uid in faq_user_state:
        return bot.reply_to(message, "Вы уже в режиме FAQ. Нажмите «❌ Выход».")

    # Получаем категории
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    with conn:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT category FROM faq ORDER BY category")
        cats = [r[0] for r in cursor.fetchall()]
    conn.close()

    if not cats:
        return bot.reply_to(message, "❌ FAQ пока пуст.")

    # Строим клавиатуру: по одному ряду на категорию
    markup = types.InlineKeyboardMarkup(row_width=1)
    faq_cat_map[uid] = {}
    faq_question_map[uid] = {}
    for idx, cat in enumerate(cats, start=1):
        key = str(idx)
        faq_cat_map[uid][key] = cat
        markup.add(types.InlineKeyboardButton(cat, callback_data=f"faq_cat:{key}"))

    # Кнопки «Задать свой вопрос» и «Выход»
    markup.add(
        types.InlineKeyboardButton("Задать свой вопрос", callback_data="faq_ask"),
        types.InlineKeyboardButton("❌ Выход", callback_data="faq_exit")
    )
    bot.send_message(
        message.chat.id,
        "📖 Выберите категорию или действие:",
        reply_markup=markup
    )
    faq_user_state[uid] = {'stage': 'categories'}


def faq_callbacks(call):
    uid = call.from_user.id
    data = call.data
    if uid not in faq_user_state:
        return bot.answer_callback_query(call.id, text="Сначала введите /faq")
    bot.answer_callback_query(call.id)

    # — Выход
    if data == 'faq_exit':
        faq_user_state.pop(uid, None)
        faq_cat_map.pop(uid, None)
        faq_question_map.pop(uid, None)
        return bot.edit_message_text(
            "Вы вышли из режима FAQ.",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id
        )

    # — Задать свой вопрос
    if data == 'faq_ask':
        bot.edit_message_text(
            "Напишите, пожалуйста, ваш вопрос, и мы скоро его внесём.",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id
        )
        faq_user_state[uid] = {'stage': 'ask'}
        sent = bot.send_message(call.message.chat.id, "Ваш вопрос:")
        bot.register_next_step_handler(sent, handle_user_faq)
        return

    # — Выбор категории
    if data.startswith('faq_cat:'):
        key = data.split(':', 1)[1]
        category = faq_cat_map[uid].get(key)
        if not category:
            return bot.answer_callback_query(call.id, text="Категория не найдена.")

        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        with conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, question FROM faq WHERE category = ? ORDER BY id",
                (category,)
            )
            rows = cursor.fetchall()
        conn.close()

        text = f"📂 Категория: {category}\n\n"
        faq_question_map[uid] = {}
        for idx, (real_id, ques) in enumerate(rows, start=1):
            key_q = str(idx)
            faq_question_map[uid][key_q] = real_id
            text += f"{idx}. {ques}\n"
        text += "\nОтправьте номер вопроса для ответа или «❌ Выход»."
        markup = types.InlineKeyboardMarkup().add(
            types.InlineKeyboardButton("❌ Выход", callback_data="faq_exit")
        )
        bot.edit_message_text(
            text,
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=markup
        )
        faq_user_state[uid] = {'stage': 'questions', 'category': category}


def handle_question_selection(message):
    uid = message.from_user.id
    key = message.text.strip()
    real_id = faq_question_map.get(uid, {}).get(key)
    if not real_id:
        return bot.reply_to(message,
                            "Введите корректный номер вопроса или нажмите «❌ Выход»."
                            )

    # читаем из БД сразу question, answer и photo
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    with conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT question, answer, photo FROM faq WHERE id = ?",
            (real_id,)
        )
        row = cursor.fetchone()
    conn.close()

    if not row:
        return bot.reply_to(message, "Вопрос не найден.")

    question, answer, photo = row

    # отправляем текстовый ответ
    bot.send_message(message.chat.id, f"❔ {question}\n\n💡 {answer}")

    # и, если в колонке photo есть имена файлов через ';', шлём их
    if photo:
        for fname in photo.split(';'):
            path = f"{PHOTO_DIR}/{fname.strip()}"
            try:
                with open(path, 'rb') as f:
                    bot.send_photo(message.chat.id, f)
            except FileNotFoundError:
                bot.send_message(
                    message.chat.id,
                    f"📷 Не найден файл: {fname}"
                )


def handle_user_faq(message):
    uid = message.from_user.id
    text = message.text.strip()

    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    with conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO user_questions(user_id, question) VALUES(?, ?)",
            (uid, text)
        )
        conn.commit()
    conn.close()

    for admin in TG_ADMINS:
        try:
            bot.send_message(admin, f"📨 Новый вопрос от {uid}:\n{text}")
        except Exception:
            pass

    bot.send_message(message.chat.id, "✅ Спасибо! Скоро внесём его.")
    faq_user_state.pop(uid, None)
    faq_cat_map.pop(uid, None)
    faq_question_map.pop(uid, None)


def init(bot_instance, tg_admins=None, photo_dir='photos'):
    global bot, TG_ADMINS, PHOTO_DIR
    bot = bot_instance
    TG_ADMINS = tg_admins or []
    PHOTO_DIR = photo_dir

    bot.message_handler(commands=['faq'])(start_faq)
    bot.callback_query_handler(func=lambda call: call.data.startswith('faq_'))(faq_callbacks)
    bot.message_handler(func=lambda m: m.from_user.id in faq_user_state and faq_user_state[m.from_user.id]['stage'] == 'questions')(handle_question_selection)