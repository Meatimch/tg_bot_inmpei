import sqlite3
from datetime import datetime

def is_user_registered(tg_id):
	"""Проверяет, зарегистрирован ли пользователь в основной базе"""
	conn = sqlite3.connect('users_database.db', check_same_thread=False)
	cursor = conn.cursor()
	try:
		cursor.execute('SELECT 1 FROM users WHERE tg_id = ? LIMIT 1', (tg_id,))
		return cursor.fetchone() is not None
	finally:
		conn.close()


def get_user_info_for_homework(tg_id):
	"""Получает информацию о пользователе для домашней работы"""
	conn = sqlite3.connect('users_database.db')
	cursor = conn.cursor()
	cursor.execute('SELECT fio, "group" FROM users WHERE tg_id = ?', (tg_id,))
	result = cursor.fetchone()
	conn.close()
	return result or ('Неизвестный', 'Без группы')


def get_users_database_values():
	conn = sqlite3.connect('users_database.db', check_same_thread=False)
	conn.isolation_level = None
	cursor = conn.cursor()
	cursor.execute('SELECT * FROM users')
	rows = cursor.fetchall()
	users_data = []
	for row in rows:
		users_data.append(row)
	conn.close()
	return list(map(list, users_data))


def get_user_info(tg_id):
	conn = sqlite3.connect('users_database.db', check_same_thread=False)
	conn.isolation_level = None
	cursor = conn.cursor()
	try:
		cursor.execute('''
			SELECT fio, "group", vk_link, tg_name 
			FROM users 
			WHERE tg_id = ?
		''', (tg_id,))
		return cursor.fetchone()
	except Exception as e:
		print(f"Ошибка получения данных пользователя: {str(e)}")
		return None
	finally:
		conn.close()


def get_institute(group):
	normalized = group.replace('-', '').upper()[:4]
	if normalized.startswith('ЭР'):
		return 'ИРЭ'
	elif normalized.startswith('ГП'):
		return 'ГПИ'
	elif normalized.startswith('ТФ'):
		return 'ИТАЭ'
	elif normalized.startswith('ФП'):
		return 'ИЭВТ'
	elif normalized.startswith('С'):
		return 'ЭнМИ'
	elif normalized.startswith('ИГ'):
		return 'ИГВИЭ'
	elif normalized.startswith('А'):
		return 'ИВТИ'
	elif normalized.startswith('ИЭ'):
		return 'ИнЭИ'
	elif normalized.startswith('ЭЛ'):
		return 'ИЭТЭ'
	elif normalized.startswith('Э'):
		return 'ИЭЭ'
	else:
		return 'Неизвестный институт'


def write_registration(user):
	"""Записать или обновить данные пользователя в базе users_database.db.
	Принимает объект user с интерфейсом `get_tg_id`, `get_tg_name`, `get_fio`, `get_group`, `get_vk_link`.
	"""
	try:
		uid = user.get_tg_id
	except Exception:
		return

	is_already_recorded = False
	list_of_users = get_users_database_values()
	for i in range(0, len(list_of_users)):
		if list_of_users[i][0] == uid:
			is_already_recorded = True
			break

	conn = sqlite3.connect('users_database.db', check_same_thread=False)
	conn.isolation_level = None
	cursor = conn.cursor()
	cursor.execute('''
		CREATE TABLE IF NOT EXISTS users (
			tg_id INTEGER PRIMARY KEY AUTOINCREMENT,
			tg_name TEXT,
			time TEXT NOT NULL,
			fio TEXT NOT NULL,
			"group" TEXT NOT NULL,
			vk_link TEXT NOT NULL,
			is_proshel_sobes BOOLEAN,
			is_proshel_shin BOOLEAN
		)
	''')

	if not is_already_recorded:
		cursor.execute('''
			INSERT INTO users (tg_id, tg_name, time, fio, "group", vk_link)
			VALUES (?, ?, ?, ?, ?, ?)
		''', (
			user.get_tg_id,
			user.get_tg_name,
			datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
			user.get_fio,
			user.get_group,
			user.get_vk_link
		))
		conn.commit()
	else:
		cursor.execute("SELECT * FROM users WHERE tg_id = ?", (uid,))
		row = cursor.fetchone()
		if row:
			cursor.execute('UPDATE users SET fio = ? WHERE tg_id = ?', (user.get_fio, uid))
			cursor.execute('UPDATE users SET "group" = ? WHERE tg_id = ?', (user.get_group, uid))
			cursor.execute('UPDATE users SET vk_link = ? WHERE tg_id = ?', (user.get_vk_link, uid))
			conn.commit()

	conn.close()
