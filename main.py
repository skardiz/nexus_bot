# main.py (The Absolute Final & Unified Architecture)
import asyncio
from dotenv import load_dotenv
from collections import defaultdict

# Эта команда должна быть вызвана самой первой
load_dotenv()

# Теперь импортируем наши модули
import database
import discord_bot
import telegram_bot

async def main():
    """Инициализирует и запускает ботов в едином асинхронном потоке."""
    print("--- [v.Final.Unified] Инициализация систем ---")
    database.init_db()

    # Запускаем все вместе в едином потоке
    await asyncio.gather(
        discord_bot.run(),
        telegram_bot.run()
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n--- Завершение работы... ---")
