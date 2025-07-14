# database.py (The Absolute Final, "Persistent Memory" Version)
import sqlite3
from datetime import datetime, timedelta

DB_FILE = "voice_stats.db"

def query(sql, params=(), fetchone=False, commit=False):
    """Универсальная функция для выполнения SQL-запросов."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.cursor().execute("PRAGMA foreign_keys = ON;")
        cursor = conn.cursor()
        cursor.execute(sql, params)
        rowcount = cursor.rowcount
        if commit:
            conn.commit()
        if fetchone:
            return cursor.fetchone(), rowcount
        is_select = sql.strip().upper().startswith('SELECT')
        if is_select:
            return cursor.fetchall(), rowcount
        return None, rowcount

def init_db():
    """Инициализирует все таблицы в базе данных."""
    _execute_query('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, name TEXT, total_seconds INTEGER DEFAULT 0, steam_id TEXT, telegram_id INTEGER)')
    _execute_query('CREATE TABLE IF NOT EXISTS games (name TEXT PRIMARY KEY, total_seconds INTEGER DEFAULT 0)')
    _execute_query('CREATE TABLE IF NOT EXISTS achievements (user_id INTEGER, achievement TEXT, UNIQUE(user_id, achievement))')
    _execute_query('CREATE TABLE IF NOT EXISTS linking_codes (code TEXT PRIMARY KEY, discord_id INTEGER, expires_at DATETIME)')
    _execute_query('CREATE TABLE IF NOT EXISTS voice_sessions (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, start_time TIMESTAMP, duration_seconds INTEGER, game_name TEXT)')
    _execute_query('CREATE TABLE IF NOT EXISTS key_value_store (key TEXT PRIMARY KEY, value TEXT)')
    _execute_query('CREATE TABLE IF NOT EXISTS steam_apps (appid INTEGER PRIMARY KEY, name TEXT COLLATE NOCASE)')
    _execute_query('CREATE INDEX IF NOT EXISTS idx_steam_apps_name ON steam_apps(name)')
    _execute_query('CREATE TABLE IF NOT EXISTS cache_info (key TEXT PRIMARY KEY, last_updated TIMESTAMP)')
    # Таблица для хранения активных сессий для защиты от перезапусков
    _execute_query("""
        CREATE TABLE IF NOT EXISTS active_sessions (
            user_id INTEGER PRIMARY KEY,
            join_time TIMESTAMP NOT NULL
        )
    """)
    try:
        _execute_query('SELECT game_name FROM voice_sessions LIMIT 1')
    except sqlite3.OperationalError:
        _execute_query('ALTER TABLE voice_sessions ADD COLUMN game_name TEXT')
    print("    -> База данных (v.PersistentMemory) инициализирована.")

def _execute_query(sql, params=()):
    """Простая внутренняя функция для выполнения запросов с коммитом."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute(sql, params)
        conn.commit()

def start_active_session(user_id, join_time):
    """Начинает новую активную сессию в БД."""
    query("INSERT OR REPLACE INTO active_sessions (user_id, join_time) VALUES (?, ?)", (user_id, join_time.isoformat()), commit=True)

def end_active_session(user_id):
    """Удаляет активную сессию из БД и возвращает время начала."""
    result, _ = query("SELECT join_time FROM active_sessions WHERE user_id = ?", (user_id,), fetchone=True)
    if result:
        query("DELETE FROM active_sessions WHERE user_id = ?", (user_id,), commit=True)
        return datetime.fromisoformat(result[0])
    return None

def get_all_active_sessions():
    """Возвращает все активные сессии из БД для восстановления состояния."""
    results, _ = query("SELECT user_id, join_time FROM active_sessions")
    return [(uid, datetime.fromisoformat(jt)) for uid, jt in results]

def get_cache_last_updated(key: str):
    result, _ = query("SELECT last_updated FROM cache_info WHERE key = ?", (key,), fetchone=True)
    return datetime.fromisoformat(result[0]) if result else None

def set_cache_last_updated(key: str):
    query("INSERT OR REPLACE INTO cache_info (key, last_updated) VALUES (?, ?)", (key, datetime.now().isoformat()), commit=True)

def update_steam_apps(apps: list):
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM steam_apps")
        cursor.executemany("INSERT OR IGNORE INTO steam_apps (appid, name) VALUES (?, ?)", apps)
        conn.commit()
    print(f"INFO: Успешно кэшировано {len(apps)} приложений Steam в БД.")

def get_steam_app_id(game_name: str):
    sql = "SELECT appid FROM steam_apps WHERE name = ? LIMIT 1"
    result, _ = query(sql, (game_name,), fetchone=True)
    return result[0] if result else None

def grant_achievement(user_id, achievement) -> bool:
    _, rowcount = query('INSERT OR IGNORE INTO achievements (user_id, achievement) VALUES (?, ?)', (user_id, achievement), commit=True)
    return rowcount > 0

def get_top_games_for_user(user_id, limit=3):
    sql = "SELECT game_name, SUM(duration_seconds) as total_time FROM voice_sessions WHERE user_id = ? AND game_name IS NOT NULL AND game_name != 'Неизвестно' GROUP BY game_name ORDER BY total_time DESC LIMIT ?"
    results, _ = query(sql, (user_id, limit))
    return results

def get_top_users(limit=15):
    sql = f"SELECT name, total_seconds, telegram_id FROM users WHERE total_seconds > 0 ORDER BY total_seconds DESC LIMIT {limit}"
    results, _ = query(sql)
    return results

def get_total_voice_time():
    result, _ = query("SELECT SUM(total_seconds) FROM users", fetchone=True)
    return result[0] if result and result[0] is not None else 0

def get_detailed_daily_sessions(day_start_time):
    sql = "SELECT u.id, u.name, u.telegram_id, vs.start_time, vs.duration_seconds, vs.game_name FROM voice_sessions vs JOIN users u ON u.id = vs.user_id WHERE vs.start_time >= ? ORDER BY u.name, vs.start_time"
    results, _ = query(sql, (day_start_time.isoformat(),))
    return results

def get_user_achievements(user_id):
    results, _ = query("SELECT DISTINCT achievement FROM achievements WHERE user_id = ?", (user_id,))
    return [item[0] for item in results]

def set_key_value(key, value):
    query("INSERT OR REPLACE INTO key_value_store (key, value) VALUES (?, ?)", (key, str(value)), commit=True)

def get_key_value(key):
    result, _ = query("SELECT value FROM key_value_store WHERE key = ?", (key,), fetchone=True)
    return result[0] if result else None

def add_voice_session(user_id, start_time, duration_seconds, game_name):
    query("INSERT INTO voice_sessions (user_id, start_time, duration_seconds, game_name) VALUES (?, ?, ?, ?)", (user_id, start_time.isoformat(), duration_seconds, game_name), commit=True)

def get_daily_stats(day_start_time):
    results, _ = query("SELECT u.id, u.name, SUM(vs.duration_seconds) FROM voice_sessions vs JOIN users u ON vs.user_id = u.id WHERE vs.start_time >= ? GROUP BY vs.user_id ORDER BY SUM(vs.duration_seconds) DESC", (day_start_time.isoformat(),))
    return results

def get_telegram_id_by_discord_id(discord_id):
    result, _ = query("SELECT telegram_id FROM users WHERE id = ?", (discord_id,), fetchone=True)
    return result[0] if result and result[0] else None

def link_steam_account(discord_id, steam_id):
    query('INSERT OR IGNORE INTO users (id, name) VALUES (?, ?)', (discord_id, f'user_{discord_id}'), commit=True)
    query('UPDATE users SET steam_id = ? WHERE id = ?', (steam_id, discord_id), commit=True)

def get_steam_id(discord_id):
    result, _ = query("SELECT steam_id FROM users WHERE id = ?", (discord_id,), fetchone=True)
    return result[0] if result and result[0] else None

def create_linking_code(code, discord_id):
    expires_at = datetime.utcnow() + timedelta(minutes=5)
    query('INSERT OR REPLACE INTO linking_codes (code, discord_id, expires_at) VALUES (?, ?, ?)', (code, discord_id, expires_at.isoformat()), commit=True)

def find_discord_id_by_code(code):
    result, _ = query("SELECT discord_id, expires_at FROM linking_codes WHERE code = ?", (code,), fetchone=True)
    if result and result[1] and datetime.fromisoformat(result[1]) > datetime.utcnow():
        return result[0]
    return None

def link_telegram_account(discord_id, telegram_id):
    query('UPDATE users SET telegram_id = ? WHERE id = ?', (telegram_id, discord_id), commit=True)

def get_discord_id_by_telegram_id(telegram_id):
    result, _ = query("SELECT id FROM users WHERE telegram_id = ?", (telegram_id,), fetchone=True)
    return result[0] if result else None

def delete_linking_code(code):
    query("DELETE FROM linking_codes WHERE code = ?", (code,), commit=True)

def update_stats(user_id, user_name, session_seconds, game_name):
    query('INSERT OR IGNORE INTO users (id, name) VALUES (?, ?)', (user_id, user_name), commit=True)
    query('UPDATE users SET total_seconds = total_seconds + ?, name = ? WHERE id = ?', (session_seconds, user_name, user_id), commit=True)
    if game_name and game_name != "Неизвестно":
        query('INSERT OR IGNORE INTO games (name) VALUES (?)', (game_name,), commit=True)
        query('UPDATE games SET total_seconds = total_seconds + ? WHERE name = ?', (session_seconds, game_name), commit=True)

def get_user_stats(user_id):
    result, _ = query("SELECT total_seconds, name FROM users WHERE id = ?", (user_id,), fetchone=True)
    return result

def get_top_games(limit=5):
    results, _ = query(f"SELECT name, total_seconds FROM games WHERE total_seconds > 0 ORDER BY total_seconds DESC LIMIT {limit}")
    return results

def get_weekly_king():
    result, _ = query("SELECT name FROM users ORDER BY total_seconds DESC LIMIT 1", fetchone=True)
    return result
