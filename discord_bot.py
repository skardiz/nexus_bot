# discord_bot.py
import os
import discord
from discord import app_commands
import asyncio
from datetime import datetime, timedelta
from collections import defaultdict
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.error import BadRequest
import random
import string

import database
import utils
import config

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

intents = discord.Intents.default()
intents.voice_states = True
intents.presences = True
intents.members = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)
telegram_bot = Bot(token=TELEGRAM_TOKEN)

voice_users, telegram_message_info = {}, {"message_id": None}
active_channel_link, last_voice_session_end_time = None, None
coming_soon_users = {}

@tree.command(name="link", description="Привязать ваш Steam и Telegram аккаунты.")
@app_commands.describe(steam_id="Ваш уникальный SteamID64 (можно найти на steamid.io)")
async def link_command(interaction: discord.Interaction, steam_id: str):
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    code_formatted = f"{code[:3]}-{code[3:]}"
    database.link_steam_account(interaction.user.id, steam_id)
    database.create_linking_code(code_formatted, interaction.user.id)
    try:
        await interaction.user.send(
            f"👋 Привет! Ваш Steam-аккаунт `{steam_id}` успешно привязан.\n\n"
            f"Теперь, чтобы связать Telegram, отправьте боту в Telegram команду `/confirm` с этим кодом:\n\n"
            f"**{code_formatted}**\n\nКод действителен 5 минут."
        )
        await interaction.response.send_message("✅ Я отправил вам в личные сообщения код для привязки Telegram.", ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message("❌ Не могу отправить ЛС. Разрешите прием сообщений в настройках приватности.", ephemeral=True)

def add_coming_soon_user(user_id, user_name):
    if user_id in voice_users: return
    print(f"INFO: Пользователь {user_name} ({user_id}) добавлен в список 'Скоро зайду'.")
    expiration_time = datetime.now(utils.MOSCOW_TZ) + timedelta(minutes=30)
    coming_soon_users[user_id] = {"name": user_name, "expires_at": expiration_time}

async def repost_message():
    global telegram_message_info
    if telegram_message_info.get("message_id"):
        try: await telegram_bot.delete_message(TELEGRAM_CHAT_ID, telegram_message_info["message_id"])
        except BadRequest: pass
    telegram_message_info["message_id"] = None
    await send_or_edit_message(force_creation=True)

async def format_telegram_message():
    global coming_soon_users
    now = datetime.now(utils.MOSCOW_TZ)
    lines = ["🎧 **Сейчас в голосовом чате:**"] if voice_users else ["🎤 **В голосовых каналах сейчас пусто.**"]
    
    for uid, data in sorted(voice_users.items(), key=lambda i: i[1]['join_time']):
        coming_soon_users.pop(uid, None)
        tg_id = database.get_telegram_id_by_discord_id(uid)
        link = f"[{utils.escape_markdown(data['name'])}](tg://user?id={tg_id})" if tg_id else utils.escape_markdown(data['name'])
        dur = utils.format_duration((now - data['join_time']).total_seconds())
        stat = "".join([" 🎥" if data.get('video') else "", " 🔴" if data.get('streaming') else ""])
        game = data.get('game', 'Неизвестно')
        game_url = utils.get_steam_app_url(game)
        game_str = f" (играет в [{utils.escape_markdown(game)}]({game_url}))" if game_url else (f" (играет в *{utils.escape_markdown(game)}*)" if game != "Неизвестно" else "")
        lines.append(f"• {link}{stat} - {dur}{game_str}")
    
    if voice_users: lines.append("")
    
    expired_users = [uid for uid, data in coming_soon_users.items() if now > data['expires_at']]
    for uid in expired_users:
        print(f"INFO: Пользователь {coming_soon_users[uid]['name']} удален из 'Скоро зайду' по тайм-ауту.")
        del coming_soon_users[uid]
        
    if coming_soon_users:
        lines.append("🚶‍♂️ **Скоро зайдет:**")
        for uid, data in coming_soon_users.items():
            tg_id = database.get_telegram_id_by_discord_id(uid)
            link = f"[{utils.escape_markdown(data['name'])}](tg://user?id={tg_id})" if tg_id else utils.escape_markdown(data['name'])
            lines.append(f"• {link}")
        lines.append("")

    today_stats = database.get_daily_stats(utils.get_day_start_time())
    users_in_voice_ids = set(voice_users.keys())
    filtered_today_stats = [s for s in today_stats if s[0] not in users_in_voice_ids]

    if filtered_today_stats:
        lines.append("🗓 **Были сегодня:**")
        for uid, name, secs in filtered_today_stats:
            tg_id = database.get_telegram_id_by_discord_id(uid)
            link = f"[{utils.escape_markdown(name)}](tg://user?id={tg_id})" if tg_id else utils.escape_markdown(name)
            lines.append(f"• {link} - {utils.format_duration(secs)}")
            
    return "\n".join(lines).strip()

async def send_or_edit_message(text_override=None, mode="main", force_creation=False):
    global telegram_message_info
    database.set_key_value('voice_users_count', len(voice_users))
    
    is_new_message_needed = not telegram_message_info.get("message_id")
    if is_new_message_needed and utils.is_quiet_hours() and not force_creation and not text_override and mode == "main":
        print("INFO: Тихие часы. Создание нового сообщения подавлено.")
        return

    keyboard = []
    # КЛЮЧЕВОЕ ИЗМЕНЕНИЕ: Строгая логика ОДНОЙ кнопки
    if mode == "main":
        if voice_users: # Кнопка есть ТОЛЬКО если кто-то в войсе
            keyboard.append([InlineKeyboardButton("🚶‍♂️ Скоро зайду", callback_data='coming_soon')])

    elif mode == "daily_stats":
        keyboard.append([InlineKeyboardButton("⬅️ Назад к мониторингу", callback_data='back_to_main')])
        day_start = utils.get_day_start_time()
        sessions = database.get_detailed_daily_sessions(day_start)
        if not sessions:
            text_override = "📊 **За сегодня еще не было активности.**"
        else:
            # Логика детальной статистики
            user_stats = defaultdict(lambda: {'total_seconds': 0, 'sessions': [], 'games': defaultdict(int), 'telegram_id': None})
            for user_id, name, telegram_id, start_str, duration, game in sessions:
                user_stats[name].update({'user_id': user_id, 'telegram_id': telegram_id})
                user_stats[name]['total_seconds'] += duration
                if duration >= 900:
                    start_time = datetime.fromisoformat(start_str)
                    user_stats[name]['sessions'].append(f"{start_time.strftime('%H:%M')}-{(start_time + timedelta(seconds=duration)).strftime('%H:%M')}")
                if game and game != "Неизвестно":
                    user_stats[name]['games'][game] += duration
            
            lines = ["📊 **Статистика за сегодня:**\n"]
            for name, data in user_stats.items():
                name_link = f"[{utils.escape_markdown(name)}](tg://user?id={data['telegram_id']})" if data['telegram_id'] else utils.escape_markdown(name)
                lines.append(f"👤 {name_link}")
                lines.append(f"   - *Всего в войсе:* {utils.format_duration(data['total_seconds'])}")
                if data['sessions']: lines.append(f"   - *Интервалы (МСК):* {', '.join(data['sessions'])}")
                top_games = sorted(data['games'].items(), key=lambda item: item[1], reverse=True)
                if top_games:
                    games_str = ', '.join([f"[{utils.escape_markdown(g)}]({utils.get_steam_app_url(g)})" if utils.get_steam_app_url(g) else utils.escape_markdown(g) + f" ({utils.format_duration(t)})" for g, t in top_games])
                    lines.append(f"   - *Играл в:* {games_str}")
                lines.append("")
            text_override = "\n".join(lines).strip()
            
    is_fully_inactive = not voice_users and not database.get_daily_stats(utils.get_day_start_time()) and not coming_soon_users
    if is_fully_inactive and mode == "main":
        if telegram_message_info.get("message_id"):
            print("INFO: Сервер неактивен, удаляю старое сообщение.")
            try: await telegram_bot.delete_message(TELEGRAM_CHAT_ID, telegram_message_info["message_id"])
            except BadRequest: pass
            telegram_message_info["message_id"] = None
        return

    text = text_override or await format_telegram_message()
    markup = InlineKeyboardMarkup(keyboard) if keyboard else None
    
    try:
        if not telegram_message_info.get("message_id"):
            msg = await telegram_bot.send_message(TELEGRAM_CHAT_ID, text, ParseMode.MARKDOWN, reply_markup=markup, disable_notification=True, disable_web_page_preview=True)
            telegram_message_info["message_id"] = msg.message_id
        else:
            await telegram_bot.edit_message_text(text, TELEGRAM_CHAT_ID, telegram_message_info["message_id"], parse_mode=ParseMode.MARKDOWN, reply_markup=markup, disable_web_page_preview=True)
        database.set_key_value('last_telegram_success', datetime.now(utils.MOSCOW_TZ).isoformat())
    except BadRequest as e:
        if "message is not modified" not in str(e).lower():
            print(f"ERROR: Ошибка BadRequest при отправке сообщения: {e}")
            telegram_message_info["message_id"] = None
            await asyncio.sleep(1)
            await send_or_edit_message(text, mode=mode, force_creation=True)
    except Exception as e:
        print(f"КРИТИЧЕСКАЯ ОШИБКА отправки: {e}")
        telegram_message_info["message_id"] = None

async def check_achievements(uid, name):
    stats = database.get_user_stats(uid)
    if not stats: return
    for required_seconds, achievement_name in config.ACHIEVEMENTS.items():
        if stats[0] >= required_seconds and database.grant_achievement(uid, achievement_name):
            print(f"INFO: Выдана новая ачивка '{achievement_name}' пользователю {name}")
            await telegram_bot.send_message(
                TELEGRAM_CHAT_ID,
                f"🎉 **Новое достижение!**\nПользователь **{utils.escape_markdown(name)}** открыл ачивку: **{achievement_name}**",
                parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True
            )
            database.set_key_value('last_telegram_success', datetime.now(utils.MOSCOW_TZ).isoformat())

async def update_user_status(member) -> bool:
    if member.id not in voice_users: return False
    old_status = {k: voice_users[member.id].get(k) for k in ('game', 'streaming', 'video')}
    steam_id = database.get_steam_id(member.id)
    game = next((a.name for a in member.activities if a.type == discord.ActivityType.playing), "Неизвестно")
    steam_game = utils.get_game_from_steam(steam_id)
    if steam_game:
        database.set_key_value('last_steam_success', datetime.now(utils.MOSCOW_TZ).isoformat())
    new_status = {
        'name': member.display_name, 'game': steam_game or game,
        'streaming': member.voice.self_stream if member.voice else False,
        'video': member.voice.self_video if member.voice else False
    }
    voice_users[member.id].update(new_status)
    return any(old_status[key] != new_status.get(key) for key in old_status)

@client.event
async def on_ready():
    global active_channel_link, last_voice_session_end_time, voice_users
    await tree.sync()
    client.loop.create_task(utils.fetch_steam_app_list_to_db())
    print("--- [RE]CONNECT: Восстановление состояния из БД... ---")
    database.set_key_value('last_discord_success', datetime.now(utils.MOSCOW_TZ).isoformat())
    
    voice_users.clear()
    stored_sessions = database.get_all_active_sessions()
    all_voice_members = {m.id: m for g in client.guilds for m in g.members if m.voice}

    for user_id, join_time in stored_sessions:
        if user_id in all_voice_members:
            member = all_voice_members[user_id]
            voice_users[user_id] = {"name": member.display_name, "join_time": join_time}
            await update_user_status(member)
        else:
            print(f"INFO: Пользователь {user_id} вышел, пока бот был оффлайн.")
            ended_session_join_time = database.end_active_session(user_id)
            if ended_session_join_time:
                duration = (datetime.now(utils.MOSCOW_TZ) - ended_session_join_time).total_seconds()
                database.add_voice_session(user_id, ended_session_join_time, duration, 'Неизвестно')

    for member_id, member in all_voice_members.items():
        if member_id not in voice_users:
            print(f"INFO: Пользователь {member.display_name} зашел, пока бот был оффлайн.")
            now = datetime.now(utils.MOSCOW_TZ)
            voice_users[member_id] = {"name": member.display_name, "join_time": now}
            database.start_active_session(member_id, now)
            await update_user_status(member)

    active_channel_link = None
    if voice_users:
        first_user_id = next(iter(voice_users))
        if all_voice_members.get(first_user_id) and all_voice_members[first_user_id].voice:
             active_channel_link = f"https://discord.com/channels/{all_voice_members[first_user_id].guild.id}/{all_voice_members[first_user_id].voice.channel.id}"

    print(f"✅ Состояние восстановлено. В войсе: {len(voice_users)} пользователей.")
    await send_or_edit_message(force_creation=True)
    client.loop.create_task(periodic_updater())

@client.event
async def on_voice_state_update(member, before, after):
    global active_channel_link, last_voice_session_end_time
    database.set_key_value('last_discord_success', datetime.now(utils.MOSCOW_TZ).isoformat())
    if member.bot: return
    now = datetime.now(utils.MOSCOW_TZ)
    
    if not before.channel and after.channel:
        print(f"EVENT: {member.display_name} зашел в канал.")
        database.start_active_session(member.id, now)
        voice_users[member.id] = {"name": member.display_name, "join_time": now}
        await update_user_status(member)
        if len(voice_users) == 1:
            active_channel_link = f"https://discord.com/channels/{member.guild.id}/{after.channel.id}"
            
        current_voice_count = len(voice_users)
        if config.MENTION_THRESHOLD > 0 and current_voice_count == config.MENTION_THRESHOLD:
            print(f"INFO: Порог в {config.MENTION_THRESHOLD} участников достигнут. Отправляю упоминание.")
            mention_text = f"🗣️ В голосом чате компания! {config.MENTIONS}"
            try:
                await telegram_bot.send_message(
                    TELEGRAM_CHAT_ID, text=mention_text, disable_notification=False
                )
            except Exception as e:
                print(f"ERROR: Не удалось отправить упоминание: {e}")
                
        await send_or_edit_message()

    elif before.channel and not after.channel:
        print(f"EVENT: {member.display_name} вышел из канала.")
        join_time = database.end_active_session(member.id)
        if join_time:
            duration = (now - join_time).total_seconds()
            game_name = voice_users.get(member.id, {}).get('game', "Неизвестно")
            database.add_voice_session(member.id, join_time, duration, game_name)
            database.update_stats(member.id, member.display_name, duration, game_name)
            await check_achievements(member.id, member.display_name)
        
        voice_users.pop(member.id, None)
        
        if not voice_users:
            last_voice_session_end_time = now
            active_channel_link = None
        await send_or_edit_message()
    
    elif before.channel and after.channel and before.channel != after.channel:
        if len(voice_users) == 1:
            active_channel_link = f"https://discord.com/channels/{member.guild.id}/{after.channel.id}"
            await send_or_edit_message()

@client.event
async def on_presence_update(before, after):
    if after.id in voice_users and await update_user_status(after):
        await send_or_edit_message()

async def periodic_updater():
    while True:
        await asyncio.sleep(60)
        await send_or_edit_message()

async def run():
    print("--- Запуск Discord бота... ---")
    database.set_key_value('start_time', datetime.now(utils.MOSCOW_TZ).isoformat())
    try:
        await client.start(DISCORD_TOKEN)
    finally:
        await client.close()
