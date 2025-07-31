# main.py
import asyncio
import logging
import os
from logging.handlers import RotatingFileHandler

import database
import discord_bot
import telegram_bot
import utils

def setup_logging():
    """Настраивает логирование в консоль и в файл."""
    if not os.path.exists('logs'):
        os.makedirs('logs')
        
    log_formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
    
    log_handler = RotatingFileHandler('logs/bot.log', maxBytes=5*1024*1024, backupCount=2, encoding='utf-8')
    log_handler.setFormatter(log_formatter)
    
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(log_handler)
    
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_formatter)
    root_logger.addHandler(console_handler)

    def log_print(*args, **kwargs):
        logging.info(' '.join(map(str, args)))
    
    __builtins__.print = log_print

async def main():
    """Главная асинхронная функция для запуска всех систем."""
    print("--- [Nexus Bot v1.0] Инициализация систем ---")
    
    database.init_db()
    
    await asyncio.gather(
        discord_bot.run(),
        telegram_bot.run()
    )

if __name__ == "__main__":
    setup_logging()
    asyncio.run(main())
