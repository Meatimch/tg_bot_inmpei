import time
import gspread
import telebot
from telebot import types
import re
import sqlite3
from collections import defaultdict
import threading
from telebot.apihelper import ApiTelegramException
from datetime import datetime, timedelta
import random

# Split helpers moved into their modules; main.py only orchestrates
from database.users import (
    is_user_registered,
    get_user_info_for_homework,
    get_users_database_values,
    get_user_info,
    get_institute,
)
from database.homework import (
    init_homework_status_db,
    get_current_day,
    update_status,
)
from database.interviews import (
    parse_sheet,
    get_freetime_table,
    counting_per_date,
    get_available_times,
)
from services.google_sheets import (
    create_date_sheet,
    update_sheet_structure,
    get_time_slots,
    clear_old_data,
    process_interviews,
)

# Threading lock for DB operations
db_lock = threading.Lock()

BotToken = ''  # Сюда вставить токен бота
bot = telebot.TeleBot(BotToken)

# Globals
tg_id_admin = []  # тг id админов для доступа к расширенным командам
DB_PATH = "faq.db"
PHOTO_DIR = 'photos'

# Initialize local DB for FAQ and questions
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
with conn:
    conn.execute('''
    CREATE TABLE IF NOT EXISTS faq (
        id       INTEGER PRIMARY KEY AUTOINCREMENT,
        category TEXT,
        question TEXT NOT NULL,
        answer   TEXT NOT NULL
    )
    ''')

    conn.execute('''
    CREATE TABLE IF NOT EXISTS user_questions (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id    INTEGER,
        question   TEXT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')


class User:
    users = {}

    def __init__(self, tg_user_id, tg_name, fio=None, group=None, vk_link=None):
        self.tg_user_id = tg_user_id
        self.tg_name = tg_name
        self.fio = fio
        self.group = group
        self.vk_link = vk_link
        User.users[tg_user_id] = self

    def __str__(self):
        return (
            f"User(tg_user_id={self.tg_user_id}, tg_name={self.tg_name}, fio={self.fio}, group={self.group}, "
            f"vk_link={self.vk_link})"
        )

    def set_fio(self, fio):
        self.fio = fio
        User.users[self.tg_user_id] = self

    def set_group(self, group):
        self.group = group
        User.users[self.tg_user_id] = self

    def set_vk_link(self, vk_link):
        self.vk_link = vk_link
        User.users[self.tg_user_id] = self

    @property
    def get_tg_id(self) -> int:
        return self.tg_user_id

    @property
    def get_tg_name(self) -> str:
        return self.tg_name

    @property
    def get_fio(self) -> str:
        return self.fio

    @property
    def get_group(self) -> str:
        return self.group

    @property
    def get_vk_link(self) -> str:
        return self.vk_link

    def update(self, fio=None, group=None, vk_link=None):
        if fio is not None:
            self.fio = fio
        if group is not None:
            self.group = group
        if vk_link is not None:
            self.vk_link = vk_link

    @classmethod
    def find_user(cls, tg_user_id):
        return cls.users.get(tg_user_id)


class CallbackDataManager:
    _instance = None
    _lock = threading.Lock()
    _data = {}
    _current_id = 0

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
            return cls._instance

    @classmethod
    def add_data(cls, data: dict) -> int:
        MAX_ENTRIES = 10000
        with cls._lock:
            if len(cls._data) >= MAX_ENTRIES:
                cls.cleanup_old_data()
            cls._current_id += 1
            cls._data[cls._current_id] = {
                'data': data,
                'timestamp': time.time(),
            }
            return cls._current_id

    @classmethod
    def get_data(cls, callback_id: int) -> dict:
        with cls._lock:
            return cls._data.get(callback_id, {}).get('data')

    @classmethod
    def cleanup_old_data(cls, max_age_seconds=86400):
        with cls._lock:
            now = time.time()
            to_delete = [k for k, v in cls._data.items() if (now - v['timestamp']) > max_age_seconds]
            for k in to_delete:
                del cls._data[k]


# Shared state
user_isStart = {}
waiting_name = 'waiting_name'
waiting_group = 'waiting_group'
waiting_user_id = 'waiting_user_id'
waiting_message_text = 'waiting_message_text'
admin_states = {}
user_states = {}
quest_states = {}


# Import and initialize handler/service modules (they register their own handlers at runtime)
from handlers import (
    user_handlers,
    admin_handlers,
    homework_handlers,
    quest_handlers,
    faq_handlers,
    interviews as interviews_handlers,
)
from database import users as db_users, interviews as db_interviews, homework as db_homework
from services import google_sheets, notifications, quests as svc_quests

try:
    homework_handlers.init(bot, User, user_isStart, tg_id_admin)
    user_handlers.init(bot, User, user_isStart, user_states, tg_id_admin)
    admin_handlers.init(bot, tg_id_admin)
    interviews_handlers.init(bot, CallbackDataManager)
    try:
        faq_handlers.init(bot, tg_id_admin, PHOTO_DIR)
    except Exception as e:
        print(f"main: error initializing faq_handlers: {e}")
except Exception as e:
    print(f"main: error initializing handler modules: {e}")


if __name__ == "__main__":
    print("Инициализация баз данных...")
    # Initialize quest-related DBs via services/quests
    try:
        svc_quests.init_quest_states_db()
    except Exception as e:
        print(f"main: svc_quests.init_quest_states_db failed: {e}")
    try:
        svc_quests.init_quest_db()
    except Exception as e:
        print(f"main: svc_quests.init_quest_db failed: {e}")
    try:
        svc_quests.init_pervaki_db()
    except Exception as e:
        print(f"main: svc_quests.init_pervaki_db failed: {e}")
    try:
        svc_quests.init_otveti_db()
    except Exception as e:
        print(f"main: svc_quests.init_otveti_db failed: {e}")
    print("✅ Базы данных инициализированы")
    print("Скрипт запущен")
    try:
        bot.polling(none_stop=True)
    except Exception as e:
        print(f"Ошибка при работе бота: {str(e)}")
    finally:
        del user_isStart
        del user_states
        print("Бот остановлен")
