# config.py
import os

ADMIN_USER_IDS = [int(admin_id) for admin_id in os.getenv('ADMIN_USER_IDS', '').split(',') if admin_id]
MENTION_THRESHOLD = 3
MENTIONS = "@here" # или "@username1 @username2"
QUIET_HOURS_ENABLED = True
QUIET_HOURS = {"start": 2, "end": 10}

ACHIEVEMENTS = {
    3600: "Новичок",
    36000: "Завсегдатай",
    360000: "Ветеран",
    3600000: "Легенда",
}
NEW_SESSION_COOLDOWN_SECONDS = 60
