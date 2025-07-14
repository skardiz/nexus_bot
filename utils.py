# utils.py (The Absolute Final, "Disk Cache" Version)
import os
import requests
from datetime import datetime, timezone, timedelta
import re
import config
import urllib.parse
import time
import database

MOSCOW_TZ = timezone(timedelta(hours=3))
STEAM_API_KEY = os.getenv('STEAM_API_KEY')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')

async def fetch_steam_app_list_to_db():
    """Скачивает и кэширует список игр в БД, если он устарел."""
    last_updated = database.get_cache_last_updated('steam_apps')
    # Обновляем, если данных нет или они старше 7 дней
    if not last_updated or (datetime.now() - last_updated) > timedelta(days=7):
        print("INFO: Кэш игр Steam устарел или отсутствует. Обновляю...")
        try:
            url = "https://api.steampowered.com/ISteamApps/GetAppList/v2/"
            response = requests.get(url, timeout=15).json()
            apps = response.get('applist', {}).get('apps', [])
            if apps:
                # Готовим данные для массовой вставки
                app_data = [(app['appid'], app['name']) for app in apps]
                database.update_steam_apps(app_data)
                database.set_cache_last_updated('steam_apps')
        except requests.RequestException as e:
            print(f"!!! КРИТИЧЕСКАЯ ОШИБКА: Не удалось загрузить список игр Steam: {e}")
    else:
        print("INFO: Кэш игр Steam актуален. Пропускаю обновление.")


def get_steam_app_url(game_name):
    """Возвращает прямую ссылку на игру, используя кэш в БД."""
    if not game_name or game_name == "Неизвестно":
        return None
    
    appid = database.get_steam_app_id(game_name)
    if appid:
        return f"https://store.steampowered.com/app/{appid}/"
    return None

async def measure_telegram_ping():
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getMe"
    start_time = time.monotonic()
    try:
        requests.get(url, timeout=5)
        end_time = time.monotonic()
        return (end_time - start_time) * 1000
    except requests.RequestException:
        return -1

async def measure_steam_ping():
    url = "https://api.steampowered.com/ISteamWebAPIUtil/GetServerInfo/v1/"
    start_time = time.monotonic()
    try:
        requests.get(url, timeout=5)
        end_time = time.monotonic()
        return (end_time - start_time) * 1000
    except requests.RequestException:
        return -1

def get_day_start_time():
    return datetime.now(MOSCOW_TZ).replace(hour=0, minute=0, second=0, microsecond=0)

def format_duration(seconds):
    seconds = int(seconds)
    if seconds < 60:
        return "меньше минуты"
    
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _ = divmod(remainder, 60)
    
    parts = []
    if days > 0: parts.append(f"{days} д")
    if hours > 0: parts.append(f"{hours} ч")
    if minutes > 0: parts.append(f"{minutes} мин")
        
    return " ".join(parts) if parts else "меньше минуты"

def is_quiet_hours():
    if not hasattr(config, 'QUIET_HOURS_ENABLED') or not config.QUIET_HOURS_ENABLED:
        return False
    now_hour = datetime.now(MOSCOW_TZ).hour
    start, end = config.QUIET_HOURS["start"], config.QUIET_HOURS["end"]
    if start < end:
        return start <= now_hour < end
    else: 
        return now_hour >= start or now_hour < end

def get_game_from_steam(steam_id):
    if not steam_id or not STEAM_API_KEY: return None
    try:
        url = f"http://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/?key={STEAM_API_KEY}&steamids={steam_id}"
        response = requests.get(url, timeout=5).json()
        player = response.get("response", {}).get("players", [{}])[0]
        return player.get("gameextrainfo")
    except requests.RequestException:
        return None

def escape_markdown(text: str) -> str:
    escape_chars = r'\_*[]()~`>#+-.=|{}!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)
