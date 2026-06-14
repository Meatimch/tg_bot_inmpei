import sqlite3
from datetime import datetime

QUEST_STATES_DB = "quest_states.db"
QUEST_DB = "quest.db"


def init_quest_states_db():
	try:
		conn = sqlite3.connect(QUEST_STATES_DB)
		cursor = conn.cursor()

		# Проверяем существование столбца group_name
		cursor.execute("PRAGMA table_info(quest_progress)")
		columns = [info[1] for info in cursor.fetchall()]

		if 'group_name' not in columns:
			# Если столбца нет - пересоздаем таблицу
			cursor.execute("DROP TABLE IF EXISTS quest_progress")
			cursor.execute('''
			CREATE TABLE IF NOT EXISTS quest_progress (
				user_id INTEGER PRIMARY KEY,
				stage INTEGER DEFAULT 0,
				group_name TEXT,
				last_action TIMESTAMP DEFAULT CURRENT_TIMESTAMP
			)
			''')
			print("✅ Таблица quest_progress пересоздана с правильной структурой")
		else:
			# Просто создаем таблицу если не существует
			cursor.execute('''
			CREATE TABLE IF NOT EXISTS quest_progress (
				user_id INTEGER PRIMARY KEY,
				stage INTEGER DEFAULT 0,
				group_name TEXT,
				last_action TIMESTAMP DEFAULT CURRENT_TIMESTAMP
			)
			''')

		conn.commit()
		print(f"✅ Таблица quest_progress создана/проверена в {QUEST_STATES_DB}")
	except Exception as e:
		print(f"❌ Ошибка при создании таблицы: {e}")
	finally:
		conn.close()


def get_quest_state(user_id):
	try:
		conn = sqlite3.connect(QUEST_STATES_DB)
		cursor = conn.cursor()
		cursor.execute("SELECT stage, [group_name] FROM quest_progress WHERE user_id= ?", (user_id,))
		row = cursor.fetchone()
		return {"stage": row[0], "group": row[1]} if row else None
	except sqlite3.OperationalError as e:
		if "no such table" in str(e):
			print("⚠️ Таблица не найдена, создаем заново...")
			init_quest_states_db()
			return get_quest_state(user_id)
		raise
	finally:
		conn.close()


def update_quest_state(user_id, stage, group=None):
	conn = sqlite3.connect(QUEST_STATES_DB)
	cursor = conn.cursor()

	if group:
		cursor.execute('''
		INSERT OR REPLACE INTO quest_progress (user_id, stage, [group_name])
		VALUES (?, ?, ?)
		''', (user_id, stage, group))
	else:
		cursor.execute('''
		UPDATE quest_progress SET stage = ? WHERE user_id = ?
		''', (stage, user_id))

	conn.commit()
	conn.close()


def delete_quest_state(user_id):
	conn = sqlite3.connect(QUEST_STATES_DB)
	cursor = conn.cursor()
	cursor.execute("DELETE FROM quest_progress WHERE user_id=?", (user_id,))
	conn.commit()
	conn.close()


def init_quest_db():
	"""Инициализирует базу данных для квеста"""
	conn = sqlite3.connect(QUEST_DB)
	cursor = conn.cursor()

	# Создаем таблицу для текстов заданий
	cursor.execute('''
	CREATE TABLE IF NOT EXISTS quest (
		name TEXT PRIMARY KEY,
		text TEXT NOT NULL
	)
	''')

	# Создаем таблицу для слов (для специального задания)
	cursor.execute('''
	CREATE TABLE IF NOT EXISTS quest_words (
		word TEXT NOT NULL
	)
	''')

	# Проверяем наличие базовых данных
	cursor.execute("SELECT COUNT(*) FROM quest")
	if cursor.fetchone()[0] == 0:
		# Добавляем заглушки для заданий
		default_quests = [
			('vstup', ''),
			('ege', ''),
			('posvyat', ''),
			('1_sent', ''),
			('1_kontrol', ''),
			('1_merop', ''),
			('1_konsult', ''),
			('zavershenie_bars', ''),
			('1_sessiya', '')
		]
		cursor.executemany("INSERT INTO quest (name, text) VALUES (?, ?)", default_quests)

		# Добавляем слова для специального задания
		default_words = ['19 20 21 5 14 1 18 1 22 16 15 ', '19 3 16 33 10 15 18 1 16 20 10 26 14 31 10',
						 '14 10 19 19 14 31 10']
		cursor.executemany("INSERT INTO quest_words (word) VALUES (?)", [(w,) for w in default_words])

	conn.commit()
	conn.close()


def init_pervaki_db():
	"""Инициализация БД для первокурсников"""
	conn = sqlite3.connect('pervaki.db')
	cursor = conn.cursor()
	cursor.execute('''
		CREATE TABLE IF NOT EXISTS pervaki (
			tg_id INTEGER PRIMARY KEY,
			fio TEXT NOT NULL,
			"group" TEXT NOT NULL
		)
	''')
	conn.commit()
	conn.close()


def init_otveti_db():
	conn = sqlite3.connect('otveti.db')
	cursor = conn.cursor()
	cursor.execute('''
		CREATE TABLE IF NOT EXISTS answers (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			nastavnik_id INTEGER NOT NULL,
			nastavnik_fio TEXT,
			nastavnik_group TEXT,
			na_gruppe TEXT,
			answer_text TEXT,
			timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
		)
	''')
	conn.commit()
	conn.close()


