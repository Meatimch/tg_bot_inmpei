import sqlite3
from datetime import datetime
import gspread

def get_freetime_table(sheet_name, is_starsh):
	gc = gspread.service_account(filename='creds.json')
	spreadsheet = gc.open(sheet_name)
	for worksheet in spreadsheet.worksheets():
		try:
			date_str = worksheet.title
			if datetime.strptime(date_str, "%d.%m").date().replace(year=2025) < datetime(2025, 3, 10).date():
				continue
			parse_sheet(worksheet, is_starsh)
		except ValueError:
			continue


def parse_sheet(sheet, is_starsh):
	conn = sqlite3.connect('schedule.db', check_same_thread=False)
	conn.isolation_level = None
	cursor = conn.cursor()
	cursor.execute('''
	CREATE TABLE IF NOT EXISTS schedule (
		date TEXT,
		start_time TEXT,
		end_time TEXT,
		person_name TEXT,
		available BOOLEAN,
		is_starshiy_nast BOOLEAN,
		is_interviewing BOOLEAN,
		PRIMARY KEY (date, start_time, person_name)
	)
	''')
	conn.commit()
	try:
		date_str = sheet.title
		date_obj = datetime.strptime(date_str, "%d.%m").date().replace(year=2025)
		date = date_obj.isoformat()  # Формат "YYYY-MM-DD"
	except ValueError:
		return
	all_data = sheet.get_all_values()
	headers = all_data[2][2:]
	for row in all_data[3:]:
		if len(row) < 2 or not row[0] or not row[1]:
			continue

		try:
			start_time = datetime.strptime(row[0], "%H:%M").strftime("%H:%M")
			end_time = datetime.strptime(row[1], "%H:%M").strftime("%H:%M")
		except ValueError:
			continue

		for i, status in enumerate(row[2:2+len(headers)]):
			if i >= len(headers):
				break

			person = headers[i].strip()
			if not person:
				continue

			available = status.strip().lower() == 'да'

			cursor.execute('''
				INSERT INTO schedule 
				(date, start_time, end_time, person_name, available, is_starshiy_nast, is_interviewing) 
				VALUES (?, ?, ?, ?, ?, ?, ?)
				ON CONFLICT(date, start_time, person_name) 
				DO UPDATE SET
					end_time = excluded.end_time,
					available = excluded.available,
					is_starshiy_nast = excluded.is_starshiy_nast,
					is_interviewing = COALESCE(schedule.is_interviewing, excluded.is_interviewing)
			''', (date, start_time, end_time, person, available, is_starsh, False))

	conn.commit()


def counting_per_date():
	conn = sqlite3.connect('schedule.db', check_same_thread=False)
	conn.isolation_level = None
	cursor = conn.cursor()
	cursor.execute('''
		SELECT 
			date,
			COUNT(DISTINCT start_time) as pair_count
		FROM (
			SELECT 
				s1.date,
				s1.start_time
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
			GROUP BY s1.date, s1.start_time
			HAVING COUNT(DISTINCT s1.person_name) >= 1 
				AND COUNT(DISTINCT s2.person_name) >= 1
		)
		GROUP BY date
	''')
	result = []
	for date_str, count in cursor.fetchall():
		original_date = datetime.strptime(date_str, "%Y-%m-%d").strftime("%d.%m")
		result.append([original_date, count])

	conn.close()
	return result


def get_available_times(date_str):
	conn = sqlite3.connect('schedule.db', check_same_thread=False)
	conn.isolation_level = None
	cursor = conn.cursor()
	try:
		date_obj = datetime.strptime(f"{date_str}.2025", "%d.%m.%Y").date()
		date_yyyy_mm_dd = date_obj.isoformat()
		query = '''
		SELECT DISTINCT 
			s.start_time,
			s.end_time
		FROM schedule s
		WHERE EXISTS (
			SELECT 1
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
			WHERE 
				s1.date = ?
				AND s1.start_time = s.start_time
		)
		'''
		cursor.execute(query, (date_yyyy_mm_dd,))
		return [{
			'start_time': row[0],
			'end_time': row[1]
		} for row in cursor.fetchall()]

	except Exception as e:
		print(f"Ошибка: {e}")
		return []
	finally:
		conn.close()
