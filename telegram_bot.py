# telegram_bot.py (The Absolute Final, "Network Stats" Version)
import os
import psutil
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.constants import ParseMode
from telegram.error import BadRequest
import asyncio

import database
import utils
import config

# --- Настройка ---
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
ADMIN_USER_IDS = [int(admin_id) for admin_id in os.getenv('ADMIN_USER_IDS', '').split(',') if admin_id]
app_instance = None 

# --- Вспомогательные функции для сообщений ---
async def delete_message_job(context: ContextTypes.DEFAULT_TYPE):
    job_data = context.job.data
    try:
        await context.bot.delete_message(chat_id=job_data['chat_id'], message_id=job_data['message_id'])
    except Exception:
        pass

async def edit_countdown_job(context: ContextTypes.DEFAULT_TYPE):
    job_data = context.job.data
    base_text = job_data['base_text']
    remaining_time = job_data['remaining_time']
    footer = f"\n\n*🗑️ Сообщение исчезнет через {remaining_time} секунд...*"
    try:
        await context.bot.edit_message_text(
            text=base_text + footer,
            chat_id=job_data['chat_id'],
            message_id=job_data['message_id'],
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )
    except BadRequest:
        pass

async def send_and_animate_delete(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, parse_mode=None):
    footer = "\n\n*🗑️ Сообщение исчезнет через 60 секунд...*"
    chat_id = update.message.chat_id
    sent_message = await context.bot.send_message(
        chat_id=chat_id,
        text=text + footer,
        parse_mode=parse_mode,
        disable_web_page_preview=True
    )
    
    try:
        await update.message.delete()
    except Exception:
        pass

    if context.job_queue:
        base_data = {'chat_id': sent_message.chat_id, 'message_id': sent_message.message_id, 'base_text': text}
        context.job_queue.run_once(edit_countdown_job, 30, data={**base_data, 'remaining_time': 30})
        context.job_queue.run_once(edit_countdown_job, 50, data={**base_data, 'remaining_time': 10})
        context.job_queue.run_once(delete_message_job, 60, data={'chat_id': sent_message.chat_id, 'message_id': sent_message.message_id})

# --- Обработчики кнопок ---
async def refresh_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from discord_bot import rescan_all_voice_users
    query = update.callback_query
    await query.answer("Запущена принудительная проверка...")
    asyncio.create_task(rescan_all_voice_users())

async def daily_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from discord_bot import send_or_edit_message
    query = update.callback_query
    await query.answer("Загружаю статистику...")
    asyncio.create_task(send_or_edit_message(mode="daily_stats"))

async def back_to_main_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from discord_bot import send_or_edit_message
    query = update.callback_query
    await query.answer("Возвращаюсь к мониторингу...")
    asyncio.create_task(send_or_edit_message(mode="main"))

# --- Команды ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_and_animate_delete(update, context, "👋 Привет! Я бот для уведомлений о голосовой активности. Используйте /help.")

async def up_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from discord_bot import repost_message
    await update.message.delete()
    asyncio.create_task(repost_message())

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = ("📜 *Список доступных команд:*\n\n"
                 "`/time` - Зал славы\n"
                 "`/games` - Топ-5 игр\n"
                 "`/mystats` - Моя статистика\n"
                 "`/king` - 'Король войса'\n"
                 "`/status` - (только для админов)\n"
                 "`/up` - Пересоздать сообщение о статусе")
    await send_and_animate_delete(update, context, help_text, parse_mode=ParseMode.MARKDOWN)

async def time_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    top_users = database.get_top_users()
    text = "🏆 Пока никто не сидел в войсе."
    if top_users:
        lines = ["*🏆 Зал славы (Топ-15):*\n"]
        for i, (name, secs, telegram_id) in enumerate(top_users, 1):
            user_link = f"[{name}](tg://user?id={telegram_id})" if telegram_id else name
            lines.append(f"*{i}.* {user_link} - {utils.format_duration(secs)}")
        text = "\n".join(lines)
    await send_and_animate_delete(update, context, text, parse_mode=ParseMode.MARKDOWN)

async def games_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    top_games = database.get_top_games()
    text = "🎮 Пока никто не играл в игры."
    if top_games:
        lines = ["*🎮 Топ-5 игр сервера:*\n"]
        for i, (name, secs) in enumerate(top_games, 1):
            url = utils.get_steam_app_url(name)
            game_link = f"[{name}]({url})" if url else name
            lines.append(f"*{i}.* {game_link} - {utils.format_duration(secs)}")
        text = "\n".join(lines)
    await send_and_animate_delete(update, context, text, parse_mode=ParseMode.MARKDOWN)

async def king_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    king = database.get_weekly_king()
    text = f"👑 Нынешний король войса: *{king[0]}*!" if king else "👑 Трон короля пока свободен!"
    await send_and_animate_delete(update, context, text, parse_mode=ParseMode.MARKDOWN)

async def mystats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    discord_id = database.get_discord_id_by_telegram_id(update.effective_user.id)
    text = "❌ Ваш Telegram не привязан."
    if discord_id:
        stats = database.get_user_stats(discord_id)
        if not stats:
            text = "📊 У вас пока нет статистики."
        else:
            secs, name = stats
            achievements = database.get_user_achievements(discord_id)
            lines = [f"📊 *Статистика для {name}:*\n", f"*Общее время:* {utils.format_duration(secs)}"]
            if achievements:
                lines.append("\n*Достижения:*")
                lines.extend([f"🏅 {ach}" for ach in achievements])
            top_user_games = database.get_top_games_for_user(discord_id, limit=3)
            if top_user_games:
                lines.append("\n*Любимые игры:*")
                for game_name, game_secs in top_user_games:
                    url = utils.get_steam_app_url(game_name)
                    game_link = f"[{game_name}]({url})" if url else game_name
                    lines.append(f"• {game_link} - {utils.format_duration(game_secs)}")
            text = "\n".join(lines)
    await send_and_animate_delete(update, context, text, parse_mode=ParseMode.MARKDOWN)

async def confirm_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "⚠️ Укажите код. `/confirm ABC-123`"
    if context.args:
        discord_id = database.find_discord_id_by_code(context.args[0].upper())
        if not discord_id:
            text = "❌ Неверный или истекший код."
        else:
            database.link_telegram_account(discord_id, update.effective_user.id)
            database.delete_linking_code(context.args[0].upper())
            text = "✅ Успех! Аккаунты связаны."
    await send_and_animate_delete(update, context, text)

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from discord_bot import client as discord_client
    if update.effective_user.id not in ADMIN_USER_IDS:
        await update.message.delete()
        return

    # Сбор данных
    start_time_iso = database.get_key_value('start_time')
    start_time = datetime.fromisoformat(start_time_iso) if start_time_iso else datetime.now(utils.MOSCOW_TZ)
    uptime = utils.format_duration((datetime.now(utils.MOSCOW_TZ) - start_time).total_seconds())
    
    process = psutil.Process(os.getpid())
    cpu_usage = process.cpu_percent(interval=0.1)
    ram_usage = process.memory_info().rss / (1024 * 1024)
    
    # КЛЮЧЕВОЕ ИЗМЕНЕНИЕ: Получаем статистику сети
    net_io = psutil.net_io_counters()
    net_sent = net_io.bytes_sent / (1024 * 1024)
    net_recv = net_io.bytes_recv / (1024 * 1024)
    
    db_size = os.path.getsize(database.DB_FILE) / (1024 * 1024)
    total_voice_time = utils.format_duration(database.get_total_voice_time())

    discord_ping = round(discord_client.latency * 1000)
    telegram_ping = await utils.measure_telegram_ping()
    steam_ping = await utils.measure_steam_ping()
    
    now = datetime.now(utils.MOSCOW_TZ)
    def format_last_seen(key):
        last_seen_iso = database.get_key_value(key)
        if not last_seen_iso: return "никогда"
        last_seen_time = datetime.fromisoformat(last_seen_iso)
        delta = (now - last_seen_time).total_seconds()
        return f"{int(delta)} сек. назад" if delta < 60 else utils.format_duration(delta) + " назад"

    last_discord = format_last_seen('last_discord_success')
    last_telegram = format_last_seen('last_telegram_success')
    last_steam = format_last_seen('last_steam_success')

    # Форматирование вывода
    lines = [
        "🤖 *Статус бота (Финальная версия)*",
        "",
        "**Технические данные:**",
        f"- Аптайм: {uptime}",
        f"- Нагрузка CPU: {cpu_usage:.1f}%",
        f"- Память RAM: {ram_usage:.2f} МБ",
        f"- Сеть (отправлено): {net_sent:.2f} МБ",
        f"- Сеть (получено): {net_recv:.2f} МБ",
        "",
        "**API:**",
        f"- Discord: {discord_ping} мс, {last_discord}",
        f"- Telegram: {int(telegram_ping)} мс, {last_telegram}" if telegram_ping !=-1 else "- Telegram: Ошибка",
        f"- Steam: {int(steam_ping)} мс, {last_steam}" if steam_ping != -1 else "- Steam: Ошибка",
        "",
        "**Статистика базы данных:**",
        f"- Размер БД: {db_size:.2f} МБ",
        f"- Общее время в войсе: {total_voice_time}"
    ]
    await send_and_animate_delete(update, context, "\n".join(lines), parse_mode=ParseMode.MARKDOWN)

async def run():
    global app_instance
    app_instance = Application.builder().token(TELEGRAM_TOKEN).build()
    
    handlers = [CommandHandler(cmd, func) for cmd, func in [
        ("start", start), ("help", help_command), ("time", time_command),
        ("games", games_command), ("king", king_command), ("mystats", mystats_command),
        ("confirm", confirm_command), ("status", status_command), ("up", up_command)
    ]] + [
        CallbackQueryHandler(refresh_callback, pattern='^refresh$'),
        CallbackQueryHandler(daily_stats_callback, pattern='^daily_stats$'),
        CallbackQueryHandler(back_to_main_callback, pattern='^back_to_main$')
    ]
    
    app_instance.add_handlers(handlers)
    
    print("✅ Бот Telegram ОНЛАЙН.")
    await app_instance.initialize()
    await app_instance.start()
    await app_instance.updater.start_polling()
