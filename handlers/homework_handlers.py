import threading
import time
import sqlite3
from telebot.apihelper import ApiTelegramException
from database.homework import init_homework_status_db, get_current_day, update_status
from database.users import get_user_info_for_homework, is_user_registered


bot = None
User = None
user_isStart = None
tg_id_admin = None


def init(bot_obj, User_class=None, user_isStart_dict=None, tg_admins=None):
	global bot, User, user_isStart, tg_id_admin
	bot = bot_obj
	User = User_class
	user_isStart = user_isStart_dict
	tg_id_admin = tg_admins

	# Register /homework command handler
	bot.message_handler(commands=['homework'])(homework)


def get_date_from_day(day):
	from datetime import datetime, timedelta
	start_date = datetime(2025, 4, 23)
	current_date = start_date + timedelta(days=day-1)
	return current_date.strftime("%d.%m.%Y")


def homework(message):
	# Delegate signup check and start distribution for admins
	from services import interviews as svc_interviews
	if not(type(message.from_user.username) is str):
		bot.send_message(message.chat.id, text='Пожалуйста установи имя пользователя в настройках телеграма для доступа к дз')
		return
	if not(message.from_user.id in user_isStart):
		User(tg_user_id=message.from_user.id, tg_name=message.from_user.username)
		user_isStart[message.from_user.id] = True

	if message.from_user.id in user_isStart and user_isStart[message.from_user.id]:
		# Проверка регистрации пользователя
		if not __import__('database').homework:  # harmless check to avoid lint complaints
			pass
		if not __import__('database').users.is_user_registered(message.from_user.id):
			return svc_interviews.signup(message, bot)

	if message.from_user.id not in (tg_id_admin or []):
		return
	threading.Thread(target=process_homework_distribution, args=(message,)).start()


def process_homework_distribution(message):
	"""Основной процесс рассылки домашних заданий с улучшенным управлением днями"""
	try:
		init_homework_status_db()
		current_day, current_index = get_current_day()

		# Логирование текущего состояния
		date_str = get_date_from_day(current_day)
		bot.send_message(message.chat.id,
						 f"📅 Текущий день: {current_day} ({date_str})\n"
						 f"👤 Текущий пользователь: {current_index + 1}")

		# Проверка на завершение всех дней
		if current_day > 8:
			bot.send_message(message.chat.id,
							 "✅ Все дни рассылки завершены (23.04-30.04.2025).\n"
							 "Используйте /next_day для сброса.")
			return

		# Получение списка пользователей
		conn = sqlite3.connect('homework_members.db')
		cursor = conn.cursor()
		cursor.execute('SELECT tg_id FROM members')
		users = [row[0] for row in cursor.fetchall()]
		conn.close()
		total_users = len(users)

		# Проверка пустого списка пользователей
		if not users:
			bot.send_message(message.chat.id, "❌ Нет пользователей для рассылки!")
			return

		# Подключение к БД текущего дня
		day_conn = sqlite3.connect(f'{current_day}.db')
		day_cursor = day_conn.cursor()

		# Создаем таблицы если их нет
		day_cursor.execute('''
			CREATE TABLE IF NOT EXISTS questions (
				question_id INTEGER PRIMARY KEY AUTOINCREMENT,
				question_text TEXT NOT NULL
			)
		''')
		day_cursor.execute('''
			CREATE TABLE IF NOT EXISTS users (
				user_id INTEGER PRIMARY KEY,
				fio TEXT,
				institute TEXT,
				question_id INTEGER,
				question_answer TEXT,
				answer_time TEXT,
				FOREIGN KEY (question_id) REFERENCES questions(question_id)
			)
		''')
		day_conn.commit()

		# Проверяем наличие вопросов
		day_cursor.execute('SELECT COUNT(*) FROM questions')
		if day_cursor.fetchone()[0] == 0:
			bot.send_message(message.chat.id,
							 f"⚠️ В БД дня {current_day} нет вопросов!\n"
							 f"Добавьте их перед рассылкой.")
			day_conn.close()
			return

		# Основной цикл рассылки
		for index in range(current_index, total_users):
			user_tg_id = users[index]

			# Пропускаем если уже отправили
			day_cursor.execute('SELECT 1 FROM users WHERE user_id = ?', (user_tg_id,))
			if day_cursor.fetchone():
				continue

			# Получаем информацию о пользователе
			fio, group = get_user_info_for_homework(user_tg_id)
			institute = group if group else 'Неизвестный'

			# Выбираем случайный вопрос
			day_cursor.execute('''
				SELECT question_id, question_text 
				FROM questions 
				ORDER BY RANDOM() 
				LIMIT 1
			''')
			question = day_cursor.fetchone()

			if not question:
				bot.send_message(message.chat.id,
								 f"⚠️ В БД дня {current_day} закончились вопросы!")
				break

			q_id, q_text = question

			try:
				# Отправляем вопрос с указанием даты
				bot.send_message(user_tg_id, f"📅 {date_str}\n\n{q_text}")

				# Записываем факт отправки
				day_cursor.execute('''
					INSERT INTO users (user_id, fio, institute, question_id)
					VALUES (?, ?, ?, ?)
				''', (user_tg_id, fio, institute, q_id))
				day_conn.commit()

				# Обновляем статус каждые 10 пользователей
				if (index + 1) % 10 == 0:
					update_status(current_day, index + 1)
					bot.send_message(message.chat.id,
									 f"⏳ Прогресс: {index + 1}/{total_users}\n"
									 f"Последний отправленный: {fio}")

			except ApiTelegramException as e:
				if hasattr(e, 'result') and getattr(e.result, 'status_code', None) == 403:
					print(f"Пользователь {user_tg_id} заблокировал бота")
				else:
					raise e

			# Обновляем статус и делаем задержку
			update_status(current_day, index + 1)
			time.sleep(1)  # Защита от флуда

		else:
			bot.send_message(message.chat.id,
							 f"⏸ Рассылка дня {current_day} приостановлена\n"
							 f"Осталось пользователей: {total_users - current_index - 1}\n"
							 f"Для продолжения снова используйте /send_homework")

		day_conn.close()

	except Exception as e:
		error_msg = f"⚠️ Критическая ошибка в рассылке:\n{str(e)}"
		print(error_msg)
		bot.send_message(message.chat.id, error_msg)
		if 'day_conn' in locals():
			day_conn.close()

		# Проверяем завершение рассылки для текущего дня
		if current_index >= total_users:
			if current_day < 8:
				# Переходим к следующему дню
				new_day = current_day + 1
				update_status(new_day, 0)
				next_date_str = get_date_from_day(new_day)
				bot.send_message(message.chat.id,
								 f"✅ Рассылка для {date_str} завершена.\nСледующий день: {next_date_str}")
			else:
				bot.send_message(message.chat.id,
								 f"✅ Финальная рассылка для {date_str} завершена!")
		else:
			bot.send_message(message.chat.id,
							 f"✅ Рассылка для {date_str} продолжена с пользователя {current_index+1}")

		day_conn.close()

	except Exception as e:
		bot.send_message(message.chat.id, f"⚠️ Ошибка рассылки: {str(e)}")
		print(f"Ошибка рассылки: {str(e)}")
