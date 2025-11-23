"""Главный файл Telegram бота модератора."""
import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message

from config import settings
from src.logger.logger import setup_logger
from src.database.connection import db
from src.moderation.moderator import Moderator

# Настройка логирования
logger = setup_logger()

# Инициализация бота и диспетчера
bot = Bot(token=settings.BOT_TOKEN)
dp = Dispatcher()

# Инициализация модератора
moderator = Moderator(bot)


@dp.message(Command("start", "help"))
async def cmd_start(message: Message):
    """Обработчик команды /start и /help."""
    help_text = (
        "🤖 Бот-модератор активирован!\n\n"
        "Бот автоматически:\n"
        "• Удаляет сообщения с нецензурными выражениями\n"
        "• Выдает предупреждения нарушителям\n"
        "• Блокирует пользователей при превышении лимита\n"
        "• Логирует все действия в базу данных\n\n"
        "Команды:\n"
        "/stats - статистика модерации\n"
        "/ban <user_id> - заблокировать пользователя\n"
        "/unban <user_id> - разблокировать пользователя"
    )
    await message.answer(help_text)


@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    """Показывает статистику модерации."""
    if not message.chat.type in ['group', 'supergroup']:
        await message.answer("Эта команда доступна только в группах.")
        return
    
    # Проверяем, является ли пользователь администратором
    is_admin = await moderator._is_admin(message.from_user.id, message.chat.id)
    if not is_admin:
        await message.answer("Эта команда доступна только администраторам.")
        return
    
    try:
        # Получаем статистику из БД
        stats_query = """
            SELECT 
                COUNT(DISTINCT user_id) as total_users,
                COUNT(*) as total_actions,
                SUM(CASE WHEN action_type = 'message_deleted' THEN 1 ELSE 0 END) as deleted_messages,
                SUM(CASE WHEN action_type = 'ban' THEN 1 ELSE 0 END) as bans
            FROM moderation_actions
            WHERE chat_id = $1
        """
        
        async with db.pool.acquire() as conn:
            row = await conn.fetchrow(stats_query, message.chat.id)
        
        if row:
            stats_text = (
                "📊 Статистика модерации:\n\n"
                f"Всего пользователей в базе: {row['total_users']}\n"
                f"Всего действий модерации: {row['total_actions']}\n"
                f"Удалено сообщений: {row['deleted_messages']}\n"
                f"Заблокировано пользователей: {row['bans']}"
            )
        else:
            stats_text = "Статистика пока отсутствует."
        
        await message.answer(stats_text)
    except Exception as e:
        logger.error(f"Ошибка получения статистики: {e}")
        await message.answer("Ошибка получения статистики.")


@dp.message(Command("ban"))
async def cmd_ban(message: Message):
    """Команда для блокировки пользователя."""
    if not message.chat.type in ['group', 'supergroup']:
        await message.answer("Эта команда доступна только в группах.")
        return
    
    # Проверяем права администратора
    is_admin = await moderator._is_admin(message.from_user.id, message.chat.id)
    if not is_admin:
        await message.answer("Эта команда доступна только администраторам.")
        return
    
    # Получаем user_id из команды
    try:
        args = message.text.split()
        if len(args) < 2:
            await message.answer("Использование: /ban <user_id>")
            return
        
        user_id = int(args[1])
        reason = ' '.join(args[2:]) if len(args) > 2 else "Блокировка администратором"
        
        await moderator.ban_user(user_id, message.chat.id, reason)
        await message.answer(f"Пользователь {user_id} заблокирован.")
    except ValueError:
        await message.answer("Неверный формат user_id. Используйте числовой ID.")
    except Exception as e:
        logger.error(f"Ошибка выполнения команды /ban: {e}")
        await message.answer("Ошибка при блокировке пользователя.")


@dp.message(Command("unban"))
async def cmd_unban(message: Message):
    """Команда для разблокировки пользователя."""
    if not message.chat.type in ['group', 'supergroup']:
        await message.answer("Эта команда доступна только в группах.")
        return
    
    # Проверяем права администратора
    is_admin = await moderator._is_admin(message.from_user.id, message.chat.id)
    if not is_admin:
        await message.answer("Эта команда доступна только администраторам.")
        return
    
    # Получаем user_id из команды
    try:
        args = message.text.split()
        if len(args) < 2:
            await message.answer("Использование: /unban <user_id>")
            return
        
        user_id = int(args[1])
        await moderator.unban_user(user_id, message.chat.id)
        await message.answer(f"Пользователь {user_id} разблокирован.")
    except ValueError:
        await message.answer("Неверный формат user_id. Используйте числовой ID.")
    except Exception as e:
        logger.error(f"Ошибка выполнения команды /unban: {e}")
        await message.answer("Ошибка при разблокировке пользователя.")


@dp.message()
async def handle_message(message: Message):
    """Обработчик всех сообщений."""
    # Игнорируем команды и служебные сообщения
    if message.text and message.text.startswith('/'):
        return
    
    # Игнорируем сообщения от ботов
    if message.from_user and message.from_user.is_bot:
        return
    
    # Проверяем сообщение на нарушение правил
    if await moderator.check_message(message):
        await moderator.handle_violation(message)


async def main():
    """Главная функция запуска бота."""
    logger.info("Запуск бота-модератора...")
    
    try:
        # Подключаемся к базе данных
        await db.connect()
        logger.info("База данных подключена")
        
        # Запускаем polling
        logger.info("Бот запущен и готов к работе")
        await dp.start_polling(bot)
        
    except KeyboardInterrupt:
        logger.info("Остановка бота...")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
    finally:
        # Отключаемся от базы данных
        await db.disconnect()
        await bot.session.close()
        logger.info("Бот остановлен")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Прерывание пользователем")
        sys.exit(0)

