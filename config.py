# config.py
import os

# ID администраторов в Telegram (через запятую, без пробелов)
ADMIN_USER_IDS = [int(admin_id) for admin_id in os.getenv('ADMIN_USER_IDS', '').split(',') if admin_id]

# Порог пользователей в войсе для отправки упоминания
MENTION_THRESHOLD = 33
# Текст упоминания. Может быть "@here", "@all" или перечисление вида "@username1 @username2"
MENTIONS = "@here"

# Настройки "тихих часов" (по МСК)
QUIET_HOURS_ENABLED = True
QUIET_HOURS = {
    "start": 2,  # 02:00
    "end": 10    # 10:00
}

# Достижения (в секундах)
ACHIEVEMENTS = {
    3600: "Новичок",
    36000: "Завсегдатай",
    360000: "Житель",
    3600000: "Старожил",
}

# Кулдаун для новой сессии при быстром перезаходе (в секундах)
NEW_SESSION_COOLDOWN_SECONDS = 60
