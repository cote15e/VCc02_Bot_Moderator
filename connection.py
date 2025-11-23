"""Подключение к базе данных PostgreSQL."""
import asyncpg
import logging
from typing import Optional
from config import settings

logger = logging.getLogger(__name__)


class Database:
    """Класс для работы с базой данных."""
    
    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None
    
    async def connect(self):
        """Подключение к базе данных."""
        try:
            self.pool = await asyncpg.create_pool(
                host=settings.DB_HOST,
                port=settings.DB_PORT,
                user=settings.DB_USER,
                password=settings.DB_PASSWORD,
                database=settings.DB_NAME,
                min_size=1,
                max_size=10
            )
            logger.info("Подключение к базе данных установлено")
            
            # Создание необходимых таблиц
            await self.create_tables()
        except Exception as e:
            logger.error(f"Ошибка подключения к базе данных: {e}")
            raise
    
    async def disconnect(self):
        """Отключение от базы данных."""
        if self.pool:
            await self.pool.close()
            logger.info("Отключение от базы данных")
    
    async def create_tables(self):
        """Создание необходимых таблиц."""
        async with self.pool.acquire() as conn:
            # Таблица для логирования действий модерации
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS moderation_actions (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    username VARCHAR(255),
                    chat_id BIGINT NOT NULL,
                    action_type VARCHAR(50) NOT NULL,
                    reason TEXT,
                    message_text TEXT,
                    moderator_id BIGINT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Таблица для статистики пользователей
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS user_stats (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    username VARCHAR(255),
                    chat_id BIGINT NOT NULL,
                    warnings_count INTEGER DEFAULT 0,
                    deleted_messages_count INTEGER DEFAULT 0,
                    banned BOOLEAN DEFAULT FALSE,
                    last_action_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, chat_id)
                )
            """)
            
            # Таблица для логов сообщений
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS message_logs (
                    id SERIAL PRIMARY KEY,
                    message_id INTEGER NOT NULL,
                    user_id BIGINT NOT NULL,
                    username VARCHAR(255),
                    chat_id BIGINT NOT NULL,
                    message_text TEXT,
                    is_deleted BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            logger.info("Таблицы базы данных проверены/созданы")
    
    async def log_action(
        self,
        user_id: int,
        chat_id: int,
        action_type: str,
        reason: str = None,
        message_text: str = None,
        username: str = None,
        moderator_id: int = None
    ):
        """Логирование действия модерации."""
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO moderation_actions 
                    (user_id, username, chat_id, action_type, reason, message_text, moderator_id)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                """, user_id, username, chat_id, action_type, reason, message_text, moderator_id)
        except Exception as e:
            logger.error(f"Ошибка логирования действия: {e}")
    
    async def log_message(
        self,
        message_id: int,
        user_id: int,
        chat_id: int,
        message_text: str = None,
        username: str = None
    ):
        """Логирование сообщения."""
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO message_logs 
                    (message_id, user_id, username, chat_id, message_text)
                    VALUES ($1, $2, $3, $4, $5)
                """, message_id, user_id, username, chat_id, message_text)
        except Exception as e:
            logger.error(f"Ошибка логирования сообщения: {e}")
    
    async def mark_message_deleted(self, message_id: int, chat_id: int):
        """Отметка сообщения как удаленного."""
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    UPDATE message_logs 
                    SET is_deleted = TRUE 
                    WHERE message_id = $1 AND chat_id = $2
                """, message_id, chat_id)
        except Exception as e:
            logger.error(f"Ошибка обновления статуса сообщения: {e}")
    
    async def get_user_stats(self, user_id: int, chat_id: int) -> dict:
        """Получение статистики пользователя."""
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow("""
                    SELECT * FROM user_stats 
                    WHERE user_id = $1 AND chat_id = $2
                """, user_id, chat_id)
                
                if row:
                    return dict(row)
                else:
                    # Создаем новую запись
                    await conn.execute("""
                        INSERT INTO user_stats (user_id, chat_id)
                        VALUES ($1, $2)
                    """, user_id, chat_id)
                    return {
                        'user_id': user_id,
                        'chat_id': chat_id,
                        'warnings_count': 0,
                        'deleted_messages_count': 0,
                        'banned': False
                    }
        except Exception as e:
            logger.error(f"Ошибка получения статистики пользователя: {e}")
            return {}
    
    async def update_user_stats(
        self,
        user_id: int,
        chat_id: int,
        username: str = None,
        increment_warnings: int = 0,
        increment_deleted: int = 0,
        set_banned: bool = None
    ):
        """Обновление статистики пользователя."""
        try:
            async with self.pool.acquire() as conn:
                # Проверяем существование записи
                exists = await conn.fetchval("""
                    SELECT EXISTS(SELECT 1 FROM user_stats 
                    WHERE user_id = $1 AND chat_id = $2)
                """, user_id, chat_id)
                
                if not exists:
                    await conn.execute("""
                        INSERT INTO user_stats (user_id, username, chat_id)
                        VALUES ($1, $2, $3)
                    """, user_id, username, chat_id)
                
                # Обновляем статистику
                update_parts = []
                params = []
                param_num = 1
                
                if increment_warnings:
                    update_parts.append(f"warnings_count = warnings_count + ${param_num}")
                    params.append(increment_warnings)
                    param_num += 1
                
                if increment_deleted:
                    update_parts.append(f"deleted_messages_count = deleted_messages_count + ${param_num}")
                    params.append(increment_deleted)
                    param_num += 1
                
                if set_banned is not None:
                    update_parts.append(f"banned = ${param_num}")
                    params.append(set_banned)
                    param_num += 1
                
                if username:
                    update_parts.append(f"username = ${param_num}")
                    params.append(username)
                    param_num += 1
                
                update_parts.append(f"last_action_at = CURRENT_TIMESTAMP")
                
                if update_parts:
                    params.extend([user_id, chat_id])
                    query = f"""
                        UPDATE user_stats 
                        SET {', '.join(update_parts)}
                        WHERE user_id = ${param_num} AND chat_id = ${param_num + 1}
                    """
                    await conn.execute(query, *params)
        except Exception as e:
            logger.error(f"Ошибка обновления статистики пользователя: {e}")


# Глобальный экземпляр базы данных
db = Database()

