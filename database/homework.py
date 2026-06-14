import sqlite3
from datetime import datetime

def init_homework_status_db():
	"""Инициализация БД статуса рассылки"""
	conn = sqlite3.connect('homework_status.db')
	cursor = conn.cursor()
	cursor.execute('''
		CREATE TABLE IF NOT EXISTS status (
			day INTEGER PRIMARY KEY,
			current_user_index INTEGER DEFAULT 0,
			last_sent_time DATETIME
		)
	''')
	conn.commit()
	conn.close()


def get_current_day():
	"""Получает текущий день рассылки из статуса"""
	conn = sqlite3.connect('homework_status.db')
	cursor = conn.cursor()
	cursor.execute('SELECT day, current_user_index FROM status ORDER BY day DESC LIMIT 1')
	result = cursor.fetchone()
	conn.close()
	return result or (1, 0)


def update_status(day, index):
	"""Обновляет статус рассылки"""
	conn = sqlite3.connect('homework_status.db')
	cursor = conn.cursor()
	cursor.execute('''
		INSERT OR REPLACE INTO status (day, current_user_index, last_sent_time)
		VALUES (?, ?, ?)
	''', (day, index, datetime.now().isoformat()))
	conn.commit()
	conn.close()


