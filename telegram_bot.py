# telegram_bot.py
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

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
app_instance = None 

async def delete_message_job(context: ContextTypes.DEFAULT_TYPE):
    try: await context.bot.delete_message(chat_id=context.job.data['chat_id'], message_id=context.job.data['message_id'])
    except Exception: pass

async def edit_countdown_job(context: ContextTypes.DEFAULT_TYPE):
    job_data = context.job.data
    footer = f"\n\n*🗑️ Сообщение исчезнет через {job_data['remaining_time']} секунд...*"
    try:
        await context.bot.edit_message_text(
            text=job_data['base_text'] + footer,
            chat_id=job_data['chat_id'], message_id=job_data['message_id'],
            parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True
        )
    except BadRequest: pass

async def send_and_animate_delete(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, parse_mode=None):
    try: await update.message.delete()
    except Exception: pass
    
    footer = "\n\n*🗑️ Сообщение исчезнет через 60 секунд...*"
    sent_message = await context.bot.send_message(
        chat_id=update.effective_chat.id, text=text + footer,
        parse_mode=parse_mode, disable_web_page_preview=True
    )
    
    if context.job_queue:
        base_data = {'chat_id': sent_message.chat_id, 'message_id': sent_message.message_id, 'base_text': text}
        context.job_queue.run_once(edit_countdown_job, 30, data={**base_data, 'remaining_time': 30})
        context.job_queue.run_once(edit_countdown_job, 50, data={**base_data, 'remaining_time': 10})
        context.job_queue.run_once(delete_message_job, 60, data={'chat_id': sent_message.chat_id, 'message_id': sent_message.message_id})

async def coming_soon_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from discord_bot import add_coming_soon_user, send_or_edit_message
    query = update.callback_query
    user = query.from_user
    discord_id = database.get_discord_id_by_telegram_id(user.id)
    if not discord_id:
        await query.answer("❌ Ваш Telegram не привязан к Discord.", show_alert=True)
        return
        
    user_stats = database.get_user_stats(discord_id)
    user_name = user_stats[1] if user_stats else user.first_name

    await query.answer("✅ Вы добавлены в список ожидания на 30 минут!", show_alert=False)
    add_coming_soon_user(discord_id, user_name)
    asyncio.create_task(send_or_edit_message())

async def refresh_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from discord_bot import send_or_edit_message
    query = update.callback_query
    await query.answer("Запущена принудительная проверка...")
    asyncio.create_task(send_or_edit_message(force_creation=True))

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
    if not top_users: return await update.message.delete()
    lines = ["*🏆 Зал славы (Топ-15):*\n"]
    for i, (name, secs, telegram_id) in enumerate(top_users, 1):
        user_link = f"[{utils.escape_markdown(name)}](tg://user?id={telegram_id})" if telegram_id else utils.escape_markdown(name)
        lines.append(f"*{i}.* {user_link} - {utils.format_duration(secs)}")
    await send_and_animate_delete(update, context, "\n".join(lines), parse_mode=ParseMode.MARKDOWN)

async def games_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    top_games = database.get_top_games()
    if not top_games: return await update.message.delete()
    lines = ["*🎮 Топ-5 игр сервера:*\n"]
    for i, (name, secs) in enumerate(top_games, 1):
        url = utils.get_steam_app_url(name)
        game_link = f"[{utils.escape_markdown(name)}]({url})" if url else utils.escape_markdown(name)
        lines.append(f"*{i}.* {game_link} - {utils.format_duration(secs)}")
    await send_and_animate_delete(update, context, "\n".join(lines), parse_mode=ParseMode.MARKDOWN)

async def king_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    king = database.get_weekly_king()
    if not king: return await update.message.delete()
    await send_and_animate_delete(update, context, f"👑 Нынешний король войса: *{utils.escape_markdown(king[0])}*!", parse_mode=ParseMode.MARKDOWN)

async def mystats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    discord_id = database.get_discord_id_by_telegram_id(update.effective_user.id)
    if not discord_id: text = "❌ Ваш Telegram не привязан."
    else:
        stats = database.get_user_stats(discord_id)
        if not stats: text = "📊 У вас пока нет статистики."
        else:
            secs, name = stats
            achievements = database.get_user_achievements(discord_id)
            lines = [f"📊 *Статистика для {utils.escape_markdown(name)}:*\n", f"*Общее время:* {utils.format_duration(secs)}"]
            if achievements:
                lines.append("\n*Достижения:*")
                lines.extend([f"🏅 {ach}" for ach in achievements])
            top_user_games = database.get_top_games_for_user(discord_id, limit=3)
            if top_user_games:
                lines.append("\n*Любимые игры:*")
                for game_name, game_secs in top_user_games:
                    url = utils.get_steam_app_url(game_name)
                    game_link = f"[{utils.escape_markdown(game_name)}]({url})" if url else utils.escape_markdown(game_name)
                    lines.append(f"• {game_link} - {utils.format_duration(game_secs)}")
            text = "\n".join(lines)
    await send_and_animate_delete(update, context, text, parse_mode=ParseMode.MARKDOWN)

async def confirm_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: text = "⚠️ Укажите код. `/confirm ABC-123`"
    else:
        discord_id = database.find_discord_id_by_code(context.args[0].upper())
        if not discord_id: text = "❌ Неверный или истекший код."
        else:
            database.link_telegram_account(discord_id, update.effective_user.id)
            database.delete_linking_code(context.args[0].upper())
            text = "✅ Успех! Аккаунты связаны."
    await send_and_animate_delete(update, context, text)

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from discord_bot import client as discord_client
    if update.effective_user.id not in config.ADMIN_USER_IDS: return await update.message.delete()
    start_time_iso = database.get_key_value('start_time')
    start_time = datetime.fromisoformat(start_time_iso) if start_time_iso else datetime.now(utils.MOSCOW_TZ)
    uptime = utils.format_duration((datetime.now(utils.MOSCOW_TZ) - start_time).total_seconds())
    process = psutil.Process(os.getpid()); cpu_usage = process.cpu_percent(interval=0.1); ram_usage = process.memory_info().rss / (1024 * 1024)
    net_io = psutil.net_io_counters(); net_sent = net_io.bytes_sent / (1024 * 1024); net_recv = net_io.bytes_recv / (1024 * 1024)
    db_size = os.path.getsize(database.DB_FILE) if os.path.exists(database.DB_FILE) else 0
    total_voice_time = utils.format_duration(database.get_total_voice_time())
    discord_ping = round(discord_client.latency * 1000) if discord_client.is_ready() else -1
    telegram_ping = await utils.measure_telegram_ping(); steam_ping = await utils.measure_steam_ping()
    now = datetime.now(utils.MOSCOW_TZ)
    def format_last_seen(key):
        last_seen_iso = database.get_key_value(key)
        if not last_seen_iso: return "никогда"
        last_seen_time = datetime.fromisoformat(last_seen_iso)
        delta = (now - last_seen_time).total_seconds()
        return f"{int(delta)} сек. назад" if delta < 60 else utils.format_duration(delta) + " назад"
    lines = [
        "🤖 *Статус бота (v1.0)*", "", "**Технические данные:**",
        f"- Аптайм: {uptime}", f"- Нагрузка CPU: {cpu_usage:.1f}%", f"- Память RAM: {ram_usage:.2f} МБ",
        f"- Сеть (отправлено/получено): {net_sent:.2f} / {net_recv:.2f} МБ", "", "**API:**",
        f"- Discord: {discord_ping} мс, {format_last_seen('last_discord_success')}" if discord_ping != -1 else "- Discord: Не подключен",
        f"- Telegram: {int(telegram_ping)} мс, {format_last_seen('last_telegram_success')}" if telegram_ping !=-1 else "- Telegram: Ошибка",
        f"- Steam: {int(steam_ping)} мс, {format_last_seen('last_steam_success')}" if steam_ping != -1 else "- Steam: Ошибка", "", "**Статистика базы данных:**",
        f"- Размер БД: {db_size / (1024*1024):.2f} МБ", f"- Общее время в войсе: {total_voice_time}"
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
        CallbackQueryHandler(back_to_main_callback, pattern='^back_to_main$'),
        CallbackQueryHandler(coming_soon_callback, pattern='^coming_soon$')
    ]
    app_instance.add_handlers(handlers)
    print("✅ Бот Telegram ОНЛАЙН.")
    await app_instance.initialize()
    await app_instance.start()
    await app_instance.updater.start_polling(drop_pending_updates=True)
