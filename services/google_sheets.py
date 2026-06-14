import time
import gspread
from collections import defaultdict
from datetime import datetime
import gspread.utils
from telebot import types

from dbm import sqlite3

from dbm import sqlite3

def create_date_sheet(spreadsheet, date):
	# Создаем лист с 65 колонками (2 временные + 9 аудиторий * 7 колонок)
	worksheet = spreadsheet.add_worksheet(
		title=date,
		rows=20,
		cols=65  # 2 (время) + 9*7 = 65
	)

	# Базовые заголовки
	base_headers = ["Начало", "Конец"] + [f"Аудитория {i+1}" for i in range(9)]
	sub_headers = ["", ""] + [
		"Старший", "Младший", "Кандидат", "Институт", "Ссылка вк", "TG", "Аудитория"
	] * 9

	# Временные слоты
	time_data = [
		["10:00", "10:40"],
		["10:45", "11:25"],
		["11:30", "12:10"],
		["12:15", "12:55"],
		["13:00", "13:40"],
		["13:45", "14:25"],
		["14:30", "15:10"],
		["15:15", "15:55"],
		["16:00", "16:40"],
		["16:45", "17:25"],
		["17:30", "18:10"],
		["18:15", "18:55"],
		["19:00", "19:40"],
		["19:45", "20:25"]
	]

	# Форматирование заголовков
	headers = [base_headers, sub_headers]
	worksheet.update('A1:BN2', headers)

	# Заполнение временных слотов
	for i, (start, end) in enumerate(time_data, start=3):
		worksheet.update(f'A{i}:B{i}', [[start, end]])

	# Форматирование
	header_format = {
		"backgroundColor": {"red": 0.9, "green": 0.9, "blue": 0.9},
		"textFormat": {"bold": True},
		"horizontalAlignment": "CENTER"
	}
	worksheet.format("A1:BN2", header_format)

	return worksheet


def update_sheet_structure(worksheet, time_data):
	max_audiences = max(len(interviews) for interviews in time_data.values())
	current_audiences = (worksheet.col_count - 2) // 7
	if max_audiences > current_audiences:
		columns_to_add = (max_audiences - current_audiences) * 7
		worksheet.add_cols(columns_to_add)
		for i in range(current_audiences + 1, max_audiences + 1):
			col = 2 + (i-1)*7 + 1
			header_range = f"{gspread.utils.rowcol_to_a1(1, col)}:{gspread.utils.rowcol_to_a1(1, col+6)}"
			worksheet.update(
				values=[[f"Аудитория {i}"] + ['']*6],
				range_name=header_range
			)
			subheader_range = f"{gspread.utils.rowcol_to_a1(2, col)}:{gspread.utils.rowcol_to_a1(2, col+6)}"
			worksheet.update(
				values=[["Старший", "Младший", "Кандидат", "Институт", "Ссылка вк", "TG", "Аудитория"]],
				range_name=subheader_range
			)


def get_time_slots(worksheet):
	time_slots = {}
	time_records = worksheet.get_values('A3:B16')
	for idx, (start, end) in enumerate(time_records, start=3):
		time_slots[start] = idx
	return time_slots


def clear_old_data(worksheet):
	worksheet.batch_clear(["C3:ZZ100"])


def process_interviews(worksheet, time_slots, time_slot, interviews):
	if time_slot not in time_slots:
		print(f"Временной слот {time_slot} не найден")
		return
	row = time_slots[time_slot]
	current_audiences = (worksheet.col_count - 2) // 7
	for audience_idx in range(len(interviews)):
		if audience_idx >= current_audiences:
			print(f"Недостаточно аудиторий для слота {time_slot}")
			break
		col_start = 2 + audience_idx * 7 + 1
		audience_name = f"Аудитория {audience_idx + 1}"
		data = [
			interviews[audience_idx]["senior"],
			interviews[audience_idx]["junior"],
			interviews[audience_idx]["candidate"],
			interviews[audience_idx]["institute"],
			interviews[audience_idx]["vk"],
			interviews[audience_idx]["tg"],
			audience_name
		]
		data_range = f"{gspread.utils.rowcol_to_a1(row, col_start)}:" \
					 f"{gspread.utils.rowcol_to_a1(row, col_start+6)}"
		worksheet.update(
			values=[data],
			range_name=data_range
		)


# Institutes and day -> columns mapping used for homework export
INSTITUTES = [
	'ИЭЭ', 'ГПИ', 'ИЭТЭ', 'ИГВИЭ', 'ИнЭИ',
	'ИТАЭ', 'ИВТИ', 'ЭнМИ', 'ИРЭ', 'ИЭВТ'
]

# Map day -> sheet columns used by export_homework_answers
DAY_COLUMNS = {
	1: {'columns': ['B', 'C', 'D']},
	2: {'columns': ['I', 'J', 'K']},
	3: {'columns': ['P', 'Q', 'R']},
	4: {'columns': ['W', 'X', 'Y']},
	5: {'columns': ['AD', 'AE', 'AF']},
	6: {'columns': ['AK', 'AL', 'AM']},
	7: {'columns': ['AR', 'AS', 'AT']}
}


def process_day_data(day, worksheets, message, bot):
	try:
		conn = sqlite3.connect(f'{day}.db')
		cursor = conn.cursor()
		cursor.execute('''
			SELECT u.fio, u.institute, u.question_id, 
				   u.question_answer, u.answer_time, q.question_text
			FROM users u
			JOIN questions q ON u.question_id = q.question_id
			WHERE u.question_answer IS NOT NULL
		''')
		data = cursor.fetchall()
		conn.close()
	except Exception as e:
		print(f"Ошибка чтения БД дня {day}: {str(e)}")
		return

	# Группируем данные по институтам
	grouped = defaultdict(list)
	for row in data:
		institute = row[1]
		if institute in worksheets:
			grouped[institute].append(row)

	# Обновляем данные в таблицах
	for institute, rows in grouped.items():
		update_institute_sheet(
			day=day,
			worksheet=worksheets[institute],
			data=rows,
			institute=institute,
			message=message,
			bot=bot
		)


def update_institute_sheet(day, worksheet, data, institute, message, bot):
	try:
		columns = DAY_COLUMNS[day]
		col_letters = columns['columns']

		# Получаем существующий список ФИО (старт с 5-й строки)
		existing_fios = worksheet.col_values(2)[4:]
		fio_row_map = {fio.strip(): idx + 5 for idx, fio in enumerate(existing_fios)}

		updates = []
		for fio, _, question_id, answer, answer_time, _ in data:
			fio = fio.strip()
			if not fio:
				continue

			# Получаем или создаём строку
			row_idx = fio_row_map.get(fio)
			if not row_idx:
				row_idx = len(existing_fios) + 5
				existing_fios.append(fio)
				fio_row_map[fio] = row_idx
				updates.append({
					'range': f'A{row_idx}',
					'values': [[fio]]
				})

			# Формируем блок данных (всего 3 колонки в DAY_COLUMNS)
			fields = [
				(col_letters[0], question_id),
				(col_letters[1], answer),
				(col_letters[2], answer_time),
			]
			for col, value in fields:
				updates.append({
					'range': f'{col}{row_idx}',
					'values': [[value]]
				})

		if updates:
			worksheet.batch_update(updates)
			print(f"✅ Данные успешно обновлены для института: {institute}, день {day}")
		else:
			print(f"⚠️ Нет данных для обновления для института: {institute}, день {day}")

	except gspread.exceptions.APIError as e:
		print(f"Ошибка API Google Sheets: {str(e)}. Повтор через 60 сек.")
		time.sleep(60)
		update_institute_sheet(day, worksheet, data, institute, message, bot)

	except Exception as e:
		print(f"❌ Ошибка при обновлении листа {institute}, день {day}: {str(e)}")


def export_homework_answers(message, bot):
	try:
		gc = gspread.service_account(filename='creds.json')
		spreadsheet = gc.open("Ответы по домашке")
	except Exception as e:
		error_msg = f"❌ Ошибка доступа к Google Таблицам: {str(e)}"
		bot.reply_to(message, error_msg)
		return

	# Создаем или получаем все листы институтов
	worksheets = {}
	for institute in INSTITUTES:
		try:
			worksheets[institute] = spreadsheet.worksheet(institute)
			# Очищаем старые данные с 5 строки
			worksheets[institute].batch_clear(["A5:AZ"])
		except gspread.WorksheetNotFound:
			worksheets[institute] = spreadsheet.add_worksheet(
				title=institute,
				rows=1000,
				cols=50
			)
			# Создаем заголовки в первой строке
			headers = ['ФИО']
			for day in range(1, 8):
				headers += [f'День {day} ID', f'День {day} Ответ', f'День {day} Время']
			worksheets[institute].update('A1', [headers])
			# Добавляем пустые строки между заголовком и данными
			worksheets[institute].insert_rows([[""], [""], [""]], row=1)

	# Собираем все данные
	all_data = {}
	for day in range(1, 8):
		try:
			conn = sqlite3.connect(f'{day}.db')
			cursor = conn.cursor()
			cursor.execute('''
				SELECT u.fio, u.institute, u.question_id, 
					   u.question_answer, u.answer_time
				FROM users u
				WHERE u.question_answer IS NOT NULL
			''')
			for row in cursor.fetchall():
				fio, institute, q_id, answer, a_time = row
				if institute not in all_data:
					all_data[institute] = {}
				if fio not in all_data[institute]:
					all_data[institute][fio] = {}
				all_data[institute][fio][day] = (q_id, answer, a_time)
			conn.close()
		except Exception as e:
			print(f"Ошибка чтения БД дня {day}: {str(e)}")

	# Обновляем данные в таблицах
	for institute in INSTITUTES:
		if institute not in all_data:
			continue

		worksheet = worksheets[institute]
		institute_data = all_data[institute]

		try:
			# Получаем существующие ФИО начиная с 5 строки
			existing_fios = worksheet.col_values(1)[4:]

			# Подготовка данных для обновления
			updates = []
			batch_count = 0
			current_row = 5  # Стартовая строка для данных

			for fio, days_data in institute_data.items():
				try:
					row_idx = existing_fios.index(fio) + 5  # Смещение до 5 строки
				except ValueError:
					# Новая запись
					row_idx = current_row
					current_row += 1
					updates.append({
						'range': f'A{row_idx}',
						'values': [[fio]]
					})

				# Добавляем данные по дням
				for day, values in days_data.items():
					cols = DAY_COLUMNS[day]['columns']
					for i, value in enumerate(values):
						updates.append({
							'range': f'{cols[i]}{row_idx}',
							'values': [[value]]
						})
						batch_count += 1

						# Ограничение API: 100 запросов в минуту
						if batch_count >= 90:
							worksheet.batch_update(updates)
							print(f"Пауза 60 сек для лимита API...")
							time.sleep(60)
							updates = []
							batch_count = 0

			# Отправляем оставшиеся обновления
			if updates:
				worksheet.batch_update(updates)

			print(f"Институт {institute}: обновлено {len(institute_data)} записей")

		except gspread.exceptions.APIError as e:
			print(f"API Error: {str(e)}")
			time.sleep(60)
			continue

		except Exception as e:
			print(f"Ошибка обновления института {institute}: {str(e)}")

	bot.reply_to(message, "✅ Экспорт завершен! Данные успешно обновлены.")


def export_interviews(message, bot):
	try:
		if message.from_user.id not in bot._bot_owner_ids:  # best-effort admin check; caller already restricts
			pass
	except Exception:
		pass

	try:
		gc = gspread.service_account(filename='creds.json')
		spreadsheet = gc.open("Интервью INMPEI")
	except Exception as e:
		bot.reply_to(message, f"❌ Ошибка доступа к Google Sheets: {e}")
		return

	try:
		conn = __import__('sqlite3').connect('sobes_signup.db', check_same_thread=False)
		cursor = conn.cursor()
		cursor.execute('''
			SELECT date, start_time, star, mlad, kand, inst, vk_link, tg_name 
			FROM sobes
			ORDER BY date, start_time
		''')
		records = cursor.fetchall()
		conn.close()
	except Exception as e:
		bot.reply_to(message, f"❌ Ошибка чтения БД sobes: {e}")
		return

	grouped = defaultdict(lambda: defaultdict(list))
	for record in records:
		date = datetime.strptime(record[0], "%Y-%m-%d").strftime("%d.%m")
		time_key = record[1]
		grouped[date][time_key].append({
			"senior": record[2],
			"junior": record[3],
			"candidate": record[4],
			"institute": record[5],
			"vk": record[6],
			"tg": f"@{record[7]}" if record[7] else "",
			"audience": ""
		})

	for date, time_data in grouped.items():
		try:
			worksheet = spreadsheet.worksheet(date)
		except gspread.exceptions.WorksheetNotFound:
			worksheet = create_date_sheet(spreadsheet, date)

		time_slots = get_time_slots(worksheet)

		output_data = []
		for time_slot in time_slots.keys():
			row_number = time_slots[time_slot]
			interviews = time_data.get(time_slot, [])
			row_data = []
			for i in range(9):
				if i < len(interviews):
					interview = interviews[i]
					row_data.extend([
						interview["senior"],
						interview["junior"],
						interview["candidate"],
						interview["institute"],
						interview["vk"],
						interview["tg"],
						f"Аудитория {i+1}"
					])
				else:
					row_data.extend([''] * 7)
			output_data.append((row_number, row_data))

		output_data.sort(key=lambda x: x[0])

		batch_data = []
		for row_num, data in output_data:
			batch_data.append({
				'range': f'C{row_num}:BN{row_num}',
				'values': [data]
			})

		if batch_data:
			worksheet.batch_update(batch_data)

	bot.reply_to(message, "✅ Экспорт успешно завершен!")
