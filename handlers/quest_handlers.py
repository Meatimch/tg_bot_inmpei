
import sqlite3
import random
from telebot import types
from telebot.apihelper import ApiTelegramException
from services import quests as svc_quests

bot = None


def init(bot_obj):
	global bot
	bot = bot_obj

	bot.message_handler(commands=['start_quest'])(start_quest)
	bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == "waiting_quest_group")(set_quest_group)
	bot.callback_query_handler(func=lambda call: call.data == "quest_next")(next_quest_step)
	bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == "waiting_quest_answer")(handle_quest_answer)


# Note: `user_states` and `User` are expected to be global vars in main.py; we'll import them at runtime
from main import PHOTO_DIR, user_states, User


def start_quest(message):
	user_id = message.from_user.id

	# Проверка что пользователь наставник
	conn_nast = sqlite3.connect('nastavniki.db')
	cursor_nast = conn_nast.cursor()
	cursor_nast.execute("SELECT na_gruppe FROM matched_users WHERE tg_id= ?", (user_id,))
	row = cursor_nast.fetchone()
	conn_nast.close()

	if not row:
		bot.send_message(message.chat.id, "❌ Вы не являетесь наставником!")
		return

	group = row[0]
	state = svc_quests.get_quest_state(user_id)

	# Если группа не указана
	if not group:
		bot.send_message(message.chat.id, "Введите номер вашей группы:")
		user_states[user_id] = "waiting_quest_group"
		return

	# Сброс квеста если он завершен
	if state and state["stage"] > 8:
		svc_quests.delete_quest_state(user_id)
		state = None

	# Если квест уже начат - продолжаем
	if state:
		# Отправляем кнопку для продолжения
		markup = types.InlineKeyboardMarkup()
		next_btn = types.InlineKeyboardButton("next", callback_data="quest_next")
		markup.add(next_btn)
		bot.send_message(
			user_id,
			f"Квест продолжается! Текущий этап: {state['stage']}",
			reply_markup=markup
		)
	else:
		# Начинаем новый квест
		svc_quests.update_quest_state(user_id, 0, group)
		send_intro_message(user_id)


def set_quest_group(message):
	user_id = message.from_user.id
	group = message.text.upper()

	# Обновляем группу в nastavniki.db
	conn_nast = sqlite3.connect('nastavniki.db')
	cursor_nast = conn_nast.cursor()
	cursor_nast.execute('UPDATE matched_users SET na_gruppe=? WHERE tg_id=?', (group, user_id))
	conn_nast.commit()
	conn_nast.close()

	# Инициализируем состояние квеста
	svc_quests.update_quest_state(user_id, 0, group)
	user_states[user_id] = None

	# Отправляем вступительное сообщение
	send_intro_message(user_id)


def send_intro_message(user_id):
	conn_quest = sqlite3.connect('quest.db')
	cursor_quest = conn_quest.cursor()
	cursor_quest.execute("SELECT text FROM quest WHERE name='vstup'")
	row = cursor_quest.fetchone()
	intro_text = row[0] if row else "Нажмите next, чтобы продолжить"
	conn_quest.close()

	markup = types.InlineKeyboardMarkup()
	next_btn = types.InlineKeyboardButton("next", callback_data="quest_next")
	markup.add(next_btn)

	# Отправляем наставнику
	bot.send_message(user_id, intro_text, reply_markup=markup)

	# Отправляем 5 случайным студентам из группы наставника
	state = svc_quests.get_quest_state(user_id)
	if state and state.get('group'):
		group = state['group']
		conn_pervaki = sqlite3.connect('pervaki.db')
		cursor_pervaki = conn_pervaki.cursor()
		cursor_pervaki.execute('SELECT tg_id FROM pervaki WHERE "group" = ?', (group,))
		students = [row[0] for row in cursor_pervaki.fetchall()]
		conn_pervaki.close()

		if students:
			selected = random.sample(students, min(5, len(students)))
			for student_id in selected:
				try:
					bot.send_message(student_id, intro_text)
				except ApiTelegramException:
					pass


def next_quest_step(call):
	user_id = call.from_user.id
	state = svc_quests.get_quest_state(user_id)

	if not state:
		bot.answer_callback_query(call.id, "Квест не начат! Введите /start_quest")
		return

	new_stage = state["stage"] + 1

	# Завершение квеста
	if new_stage > 8:
		# Сбрасываем состояние
		svc_quests.delete_quest_state(user_id)
		bot.send_message(user_id, "Квест завершен")
		return

	# Всегда отправляем задание
	send_quest_step(user_id, new_stage, state["group"])

	# Всегда обновляем состояние
	svc_quests.update_quest_state(user_id, new_stage)

	# Всегда отправляем кнопку для следующего этапа
	markup = types.InlineKeyboardMarkup()
	next_btn = types.InlineKeyboardButton("next", callback_data="quest_next")
	markup.add(next_btn)
	bot.send_message(
		user_id,
		f"Задание №{new_stage} отправлено! Нажмите next, когда будете готовы к следующему этапу",
		reply_markup=markup
	)


def send_quest_step(user_id, stage, group):
	QUEST_MAP = {
		1: {"name": "ege", "count": 5},
		2: {"name": "posvyat", "count": 5},
		3: {"name": "1_sent", "count": 0},
		4: {"name": "1_kontrol", "count": 5},
		5: {"name": "1_merop", "count": 6},
		6: {"name": "1_konsult", "count": 0},
		7: {"name": "zavershenie_bars", "count": 0},
		8: {"name": "1_sessiya", "count": 3}
	}

	quest_data = QUEST_MAP[stage]
	quest_name = quest_data["name"]

	conn_quest = sqlite3.connect('quest.db')
	cursor_quest = conn_quest.cursor()
	cursor_quest.execute("SELECT text FROM quest WHERE name=?", (quest_name,))
	row = cursor_quest.fetchone()
	quest_text = row[0] if row else f"Задание для этапа {stage}"
	conn_quest.close()

	if stage == 5:
		handle_special_quest(user_id, group, quest_text)
	elif stage == 7:
		send_quest_task(user_id, group, quest_text, 0)
		user_states[user_id] = "waiting_quest_answer"
		bot.send_message(user_id, "Пожалуйста, напишите ответ на задание:")
	elif stage == 8:
		send_photos_for_quest(user_id, group)
		send_quest_task(user_id, group, quest_text, quest_data["count"])
	else:
		send_quest_task(user_id, group, quest_text, quest_data["count"])


def send_quest_task(nastavnik_id, group, text, count):
	try:
		if count == 0:
			bot.send_message(nastavnik_id, text)
			return

		conn_pervaki = sqlite3.connect('pervaki.db')
		cursor_pervaki = conn_pervaki.cursor()
		cursor_pervaki.execute('SELECT tg_id, fio FROM pervaki WHERE "group" = ?', (group,))
		students = cursor_pervaki.fetchall()
		conn_pervaki.close()

		if not students:
			bot.send_message(nastavnik_id, f"❌ В вашей группе ({group}) нет студентов!")
			return

		selected = random.sample(students, min(count, len(students)))
		report = ["Задания получили:"]

		for i, (student_id, fio) in enumerate(selected):
			try:
				bot.send_message(student_id, text)
				report.append(f"{i+1}. {fio}")
			except ApiTelegramException:
				report.append(f"{i+1}. ❌ {fio} (не удалось отправить)")

		bot.send_message(nastavnik_id, "\n".join(report))
		bot.send_message(nastavnik_id, text)

	except Exception as e:
		bot.send_message(nastavnik_id, f"⚠️ Ошибка при отправке задания: {str(e)}")


def handle_special_quest(nastavnik_id, group, text):
	conn_pervaki = sqlite3.connect('pervaki.db')
	cursor_pervaki = conn_pervaki.cursor()
	cursor_pervaki.execute('SELECT tg_id, fio FROM pervaki WHERE "group" = ?', (group,))
	students = cursor_pervaki.fetchall()
	conn_pervaki.close()

	if len(students) < 3:
		bot.send_message(nastavnik_id, "❌ Недостаточно студентов для задания! Нужно минимум 3.")
		return

	selected = random.sample(students, 3)

	conn_quest = sqlite3.connect('quest.db')
	cursor_quest = conn_quest.cursor()
	cursor_quest.execute("SELECT word FROM quest_words")
	words = [row[0] for row in cursor_quest.fetchall()]
	conn_quest.close()

	if len(words) < 3:
		additional = [f"Слово{i+1}" for i in range(3 - len(words))]
		words.extend(additional)

	report = ["Задания получили:"]

	for i, (student_id, fio) in enumerate(selected):
		if i < len(words):
			word = words[i]
			try:
				bot.send_message(student_id, f"{text}\n\nВаше слово: {word}")
				report.append(f"{i+1}. {fio} - {word}")
			except ApiTelegramException:
				report.append(f"{i+1}. ❌ {fio} - {word} (не удалось отправить)")
		else:
			report.append(f"{i+1}. ❌ {fio} - нет слова для отправки")

	bot.send_message(nastavnik_id, "\n".join(report))


def handle_quest_answer(message):
	user_id = message.from_user.id
	answer_text = message.text

	state = svc_quests.get_quest_state(user_id)
	if not state:
		bot.send_message(user_id, "❌ Ошибка: состояние квеста не найдено.")
		return

	group = state['group']

	conn_nast = sqlite3.connect('nastavniki.db')
	cursor_nast = conn_nast.cursor()
	cursor_nast.execute("SELECT fio, na_gruppe FROM matched_users WHERE tg_id= ?", (user_id,))
	row = cursor_nast.fetchone()
	conn_nast.close()

	if row:
		fio, na_gruppe = row
		conn_otv = sqlite3.connect('otveti.db')
		cursor_otv = conn_otv.cursor()
		cursor_otv.execute('''
			INSERT INTO answers 
			(nastavnik_id, nastavnik_fio, nastavnik_group, na_gruppe, answer_text)
			VALUES (?, ?, ?, ?, ?)
		''', (user_id, fio, group, na_gruppe, answer_text))
		conn_otv.commit()
		conn_otv.close()

		bot.send_message(user_id, "✅ Ответ сохранен!")
	else:
		bot.send_message(user_id, "❌ Не удалось сохранить ответ. Вы не найдены в базе наставников.")

	user_states[user_id] = None

	markup = types.InlineKeyboardMarkup()
	next_btn = types.InlineKeyboardButton("next", callback_data="quest_next")
	markup.add(next_btn)
	bot.send_message(user_id, "Теперь вы можете продолжить квест.", reply_markup=markup)


def send_photos_for_quest(nastavnik_id, group):
	photos = [
		'motivacia.png',
		'son.png',
		'znania.png',
		'lekcii (1).png'
	]

	conn_pervaki = sqlite3.connect('pervaki.db')
	cursor_pervaki = conn_pervaki.cursor()
	cursor_pervaki.execute('SELECT tg_id, fio FROM pervaki WHERE "group" = ?', (group,))
	students = cursor_pervaki.fetchall()
	conn_pervaki.close()

	try:
		media = []
		for photo_name in photos:
			photo_path = f"{PHOTO_DIR}/{photo_name}"
			media.append(types.InputMediaPhoto(open(photo_path, 'rb')))

		bot.send_media_group(nastavnik_id, media)
	except Exception:
		pass

	report = ["Фотографии отправлены:"]
	if len(students) >= 4:
		selected_students = random.sample(students, 4)
		for i, (student_id, fio) in enumerate(selected_students):
			try:
				photo_path = f"{PHOTO_DIR}/{photos[i]}"
				with open(photo_path, 'rb') as photo:
					bot.send_photo(student_id, photo)
				report.append(f"{i+1}. {fio} - {photos[i]}")
			except Exception:
				report.append(f"{i+1}. ❌ {fio} - {photos[i]}")
	else:
		report.append("❌ Недостаточно студентов для отправки фотографий")

	bot.send_message(nastavnik_id, "\n".join(report))